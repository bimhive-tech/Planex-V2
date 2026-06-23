"""Excel import for zone-based progress trackers.

Each ZONE sheet is a matrix: subzones across the columns, tasks down the rows,
and a progress cell at every (task, subzone). We import it as:
    Zone (scope)  ->  Subzone (area scope, one per column)  ->  Activity (one per
    (task, subzone) cell, grouped by row_index into task rows).

Layout is detected per sheet (the subzone-label row, the name column, and an
optional leading weight column). Phase/summary rows (col-A "W") are skipped.
The Primavera 'FOR (P6)' and 'Summary' sheets are skipped in this version.
"""
import datetime
import re

import openpyxl
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import Activity, ProgressSnapshot, ProjectScope
from .services import project_overall_progress, scope_progress_map

# Dates embedded in tracker file names, e.g. "... - 3-Mar-2026.xlsm" or "2026-03-03".
# The month group captures the first 3 letters (Mar/March both -> "Mar" -> %b).
_DATE_PATTERNS = [
    (re.compile(r"(\d{1,2})[-_ ]([A-Za-z]{3})[a-z]*[-_ ](\d{4})"), "%d %b %Y"),
    (re.compile(r"(\d{4})[-_](\d{1,2})[-_](\d{1,2})"), "%Y %m %d"),
]


def parse_date_from_name(name: str):
    for rx, fmt in _DATE_PATTERNS:
        m = rx.search(name or "")
        if m:
            try:
                return datetime.datetime.strptime(" ".join(m.groups()), fmt).date()
            except ValueError:
                continue
    return None

SKIP_SHEETS = {"for (p6)", "summary"}
MAX_TASKS_PER_ZONE = 2000
MAX_SUBZONES_PER_ZONE = 300


# Phase names in these trackers are usually already one trade's work package
# (e.g. "الاعمال الكهربائية") — a quick keyword guess saves having to tag
# hundreds of imported phases by hand. Blank ("") means unclassified; the
# user can still correct it via the phase's edit form.
_DISCIPLINE_KEYWORDS = {
    ProjectScope.Discipline.CONCRETE: ["خرسان", "حفر", "اساسات", "هيكل", "concrete", "structure"],
    ProjectScope.Discipline.ARCHITECTURE: [
        "تشطيب", "بياض", "دهان", "سيراميك", "رخام", "نجارة", "حدادة", "بلاط", "ارضيات",
        "architecture", "finish",
    ],
    ProjectScope.Discipline.ELECTRICAL: ["كهرب", "تيار خفيف", "اضاءة", "انارة", "electrical"],
    ProjectScope.Discipline.MECHANICAL: [
        "صحي", "صرف", "تكييف", "ميكانيك", "حريق", "مكافحة الحريق", "تهوية", "مياه", "ري",
        "mechanical", "plumbing", "hvac",
    ],
}


def _guess_discipline(phase_name: str) -> str:
    name = (phase_name or "").lower()
    for discipline, keywords in _DISCIPLINE_KEYWORDS.items():
        if any(k in name for k in keywords):
            return discipline
    return ""


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _to_pct(v):
    f = float(v)
    pct = f * 100 if f <= 1.0001 else f  # values are fractions (0–1)
    return max(0.0, min(100.0, round(pct, 2)))


def _contiguous_runs(row):
    runs, start = [], None
    for i, v in enumerate(row):
        empty = v is None or v == ""
        if not empty and start is None:
            start = i
        elif empty and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(row) - 1))
    return runs


def _detect_label_row(rows):
    """Find the subzone-label row: the row whose longest non-empty run has the
    most *string* cells (the index row above it is numeric, so it loses)."""
    best = None  # (string_count, start, end, row_index)
    for i, row in enumerate(rows[:8]):
        for a, b in _contiguous_runs(row):
            strings = sum(1 for c in range(a, b + 1) if isinstance(row[c], str) and row[c].strip())
            if strings >= 2 and (best is None or strings > best[0]):
                best = (strings, a, b, i)
    return best


def parse_sheet(rows):
    """Return {subzones: [labels], tasks: [{name, weight, phase, row_index, cells}]}
    where cells is a list aligned to subzones (None for blanks)."""
    det = _detect_label_row(rows)
    if not det:
        return None
    _, sub_start, sub_end, label_row = det
    subzone_cols = list(range(sub_start, min(sub_end + 1, sub_start + MAX_SUBZONES_PER_ZONE)))
    name_col = sub_start - 1
    if name_col < 0:
        return None
    weight_col = name_col - 1 if name_col - 1 >= 0 else None

    subzones = [str(rows[label_row][c]).strip() for c in subzone_cols]

    tasks, phase, ri = [], "", 0
    skip_first_summary = weight_col is None  # no "W" marker -> first row is the summary
    for row in rows[label_row + 1:]:
        if len(tasks) >= MAX_TASKS_PER_ZONE:
            break
        wcell = row[weight_col] if (weight_col is not None and weight_col < len(row)) else None
        name = row[name_col] if name_col < len(row) else None

        # Phase / summary header row (col-A "W").
        if isinstance(wcell, str) and wcell.strip().upper() == "W":
            if isinstance(name, str) and name.strip():
                phase = name.strip()[:180]
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        if skip_first_summary:
            # No "W" column on this sheet — the first named row is the phase/summary.
            skip_first_summary = False
            phase = name.strip()[:180]
            continue

        cells, any_num = [], False
        for c in subzone_cols:
            v = row[c] if c < len(row) else None
            if _is_num(v):
                cells.append(_to_pct(v))
                any_num = True
            else:
                cells.append(None)
        if not any_num:
            continue

        weight = float(wcell) if (_is_num(wcell) and wcell > 0) else 1.0
        ri += 1
        tasks.append({"name": name.strip()[:200], "weight": weight, "phase": phase,
                      "row_index": ri, "cells": cells})
    return {"subzones": subzones, "tasks": tasks}


def parse_workbook(file_obj) -> dict:
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    result = {}
    try:
        for name in wb.sheetnames:
            if name.strip().lower() in SKIP_SHEETS:
                continue
            rows = list(wb[name].iter_rows(values_only=True))
            sheet = parse_sheet(rows)
            if sheet and sheet["tasks"] and sheet["subzones"]:
                result[name.strip()] = sheet
    finally:
        wb.close()
    return result


def _save_snapshot(project, *, date, source):
    """Capture the project's aggregate progress as a dated snapshot (upsert by date)."""
    agg = project.activities.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(progress_percent__gte=100)),
        not_started=Count("id", filter=Q(progress_percent__lte=0)),
    )
    total = agg["total"]
    breakdown = {
        "total": total, "completed": agg["completed"], "not_started": agg["not_started"],
        "in_progress": total - agg["completed"] - agg["not_started"],
    }
    progress = scope_progress_map(project)
    zones = [
        {"name": z.name, "progress": progress.get(str(z.id), 0.0)}
        for z in project.scopes.filter(scope_type=ProjectScope.ScopeType.ZONE).order_by("sort_order")
    ]
    ProgressSnapshot.objects.update_or_create(
        project=project, date=date,
        defaults={"company": project.company, "overall_progress": project_overall_progress(project),
                  "breakdown": breakdown, "zones": zones, "scopes": progress, "source": source[:200]},
    )


@transaction.atomic
def import_workbook(project, file_obj, *, replace=True, snapshot_date=None, source="") -> dict:
    parsed = parse_workbook(file_obj)
    if not parsed:
        return {"zones": 0, "subzones": 0, "activities": 0, "overall_progress": 0.0,
                "error": "No zone sheets recognised."}

    if replace:
        project.scopes.all().delete()  # cascades subzones + activities

    company = project.company
    Scope = ProjectScope
    zones, subz, phases, activities = [], [], [], []
    subzone_total = 0
    for z, (zone_name, sheet) in enumerate(parsed.items()):
        zone = Scope(company=company, project=project,
                     scope_type=Scope.ScopeType.ZONE, name=zone_name, sort_order=z)
        zones.append(zone)

        # Group tasks by phase (preserving order). Tree is
        # Zone -> Subzone -> Phase -> Task: each subzone holds the phases, each phase
        # holds that subzone's task cells (an Activity per cell).
        order, by_phase = [], {}
        for task in sheet["tasks"]:
            ph = task["phase"] or "Tasks"
            if ph not in by_phase:
                by_phase[ph] = []
                order.append(ph)
            by_phase[ph].append(task)

        for c, label in enumerate(sheet["subzones"]):
            subzone = Scope(company=company, project=project, parent=zone,
                            scope_type=Scope.ScopeType.AREA, name=label or f"SZ{c + 1}", sort_order=c)
            subz.append(subzone)
            subzone_total += 1
            for pi, ph in enumerate(order):
                phase = Scope(company=company, project=project, parent=subzone,
                              scope_type=Scope.ScopeType.PHASE, name=ph, sort_order=pi,
                              discipline=_guess_discipline(ph))
                phases.append(phase)
                for task in by_phase[ph]:
                    val = task["cells"][c]
                    if val is None:
                        continue
                    activities.append(Activity(
                        company=company, project=project, scope=phase,
                        name=task["name"], weight=task["weight"], progress_percent=val,
                        phase_name=ph, row_index=task["row_index"],
                        subzone_code=label or f"SZ{c + 1}", subzone_index=c,
                        progress_type=Activity.ProgressType.PERCENTAGE,
                    ))

    # Insert parents before children (UUID PKs are generated client-side).
    Scope.objects.bulk_create(zones, batch_size=1000)
    Scope.objects.bulk_create(subz, batch_size=1000)
    Scope.objects.bulk_create(phases, batch_size=1000)
    Activity.objects.bulk_create(activities, batch_size=2000)

    snap_date = snapshot_date or parse_date_from_name(source) or timezone.now().date()
    _save_snapshot(project, date=snap_date, source=source)

    return {
        "zones": len(zones),
        "subzones": subzone_total,
        "phases": len(phases),
        "activities": len(activities),
        "overall_progress": project_overall_progress(project),
        "snapshot_date": snap_date.isoformat(),
    }
