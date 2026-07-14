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


def parse_sheet(rows, is_header=None):
    """Return {subzones: [labels], tasks: [{name, weight, phase, row_index, cells}]}
    where cells is a list aligned to subzones (None for blanks).

    `is_header(row_idx, name_col)` (optional) flags a styled section/phase header
    row — the trackers only mark the FIRST discipline with a col-A "W", styling
    the rest (bold + fill) instead, so without this every later discipline's
    tasks would collapse into the first phase."""
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
    for offset, row in enumerate(rows[label_row + 1:]):
        idx = label_row + 1 + offset  # absolute 0-based row index (for style lookups)
        if len(tasks) >= MAX_TASKS_PER_ZONE:
            break
        wcell = row[weight_col] if (weight_col is not None and weight_col < len(row)) else None
        name = row[name_col] if name_col < len(row) else None

        # Phase / section header row — col-A "W", or a styled (bold + filled) name
        # cell for the disciplines that carry no "W".
        is_phase = isinstance(wcell, str) and wcell.strip().upper() == "W"
        if not is_phase and is_header is not None and isinstance(name, str) and name.strip():
            is_phase = is_header(idx, name_col)
        if is_phase:
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


def _styled_header(cell):
    """True when a cell is a styled section header (bold + a solid fill). Works on
    read-only cells too, so we can detect phase headers without leaving streaming
    mode — a full-workbook load of a 20MB+ tracker needs ~1GB and OOMs the worker."""
    try:
        return bool(cell.font and cell.font.bold) and bool(cell.fill and cell.fill.patternType)
    except (AttributeError, ValueError):
        return False


def parse_workbook(file_obj) -> dict:
    # read_only streams the file (keeps memory sane on big workbooks). ReadOnlyCell
    # still exposes font/fill, so styled phase headers are detectable here — and we
    # only iterate the zone sheets, never the huge skipped FOR (P6)/Summary sheets.
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    result = {}
    try:
        for name in wb.sheetnames:
            if name.strip().lower() in SKIP_SHEETS:
                continue
            ws = wb[name]
            values, styled = [], []
            for row in ws.iter_rows():
                values.append(tuple(c.value for c in row))
                styled.append(tuple(_styled_header(c) for c in row))

            def is_header(row_idx0, name_col0, styled=styled):
                return name_col0 < len(styled[row_idx0]) and styled[row_idx0][name_col0]

            sheet = parse_sheet(values, is_header)
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
        # No zone-matrix sheets — fall back to a Primavera 'FOR (P6)' sheet if the
        # workbook has one, so a P6-only export still imports.
        from .p6_import import build_from_p6, parse_p6_tree
        try:
            file_obj.seek(0)
        except (AttributeError, OSError):
            pass
        roots = parse_p6_tree(file_obj)
        if roots:
            return build_from_p6(project, roots, replace=replace,
                                 snapshot_date=snapshot_date, source=source)
        return {"zones": 0, "subzones": 0, "activities": 0, "overall_progress": 0.0,
                "error": "No zone sheets or FOR (P6) sheet recognised."}

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


SCHEDULE_HEADER_SCAN_ROWS = 15  # how deep to look for the header row in a sheet


def _find_col(header, *names):
    for n in names:
        if n in header:
            return header.index(n)
    return None


def _locate_schedule_header(rows):
    """Find the (index, name_col, id_col, start_col, finish_col) of the header row
    within a sheet's first rows, or None. Requires a name column plus a start or
    finish column so a progress matrix (no Start/Finish) can't be mistaken for a
    schedule. id_col is a fallback: Primavera often puts the activity/WBS name in
    the 'Activity ID' column and leaves 'Activity Name' blank."""
    for idx in range(min(len(rows), SCHEDULE_HEADER_SCAN_ROWS)):
        header = [str(h or "").strip().lower() for h in rows[idx]]
        name_col = _find_col(header, "activity name", "name", "zone", "phase")
        id_col = _find_col(header, "activity id", "id")
        start_col = _find_col(header, "start", "planned start", "start date", "early start")
        finish_col = _find_col(header, "finish", "planned finish", "finish date", "end", "early finish")
        if name_col is not None and (start_col is not None or finish_col is not None):
            return idx, name_col, id_col, start_col, finish_col
    return None


def _cell(row, col):
    return row[col] if col is not None and col < len(row) else None


def _parse_schedule_sheet(rows):
    located = _locate_schedule_header(rows)
    if not located:
        return []
    header_idx, name_col, id_col, start_col, finish_col = located

    def as_date(v):
        if isinstance(v, datetime.datetime):
            return v.date()
        return v if isinstance(v, datetime.date) else None

    out = []
    for row in rows[header_idx + 1:]:
        name = _cell(row, name_col)
        if not isinstance(name, str) or not name.strip():
            name = _cell(row, id_col)  # fall back to the Activity ID column
        if not isinstance(name, str) or not name.strip():
            continue
        start = as_date(_cell(row, start_col))
        finish = as_date(_cell(row, finish_col))
        if not start and not finish:
            continue
        out.append({"name": name.strip(), "start": start, "finish": finish})
    return out


def parse_schedule_workbook(file_obj) -> list:
    """Parse a flat schedule export — Activity Name + Start + Finish columns,
    the same shape Primavera P6 exports to Excel — into [{name, start, finish}].

    Scans every sheet (and the first rows of each) for the header, so a schedule
    tab like 'FOR (P6)' is found even when it isn't the first sheet. The first
    sheet that yields any dated rows wins. Extra columns (duration, float,
    % complete...) are ignored; rows missing a name or both dates are skipped."""
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            parsed = _parse_schedule_sheet(rows)
            if parsed:
                return parsed
    finally:
        wb.close()
    return []


@transaction.atomic
def import_schedule(project, file_obj) -> dict:
    """Match each parsed row's name (case-insensitive) to existing scope(s) and
    set their planned dates — never creates or deletes structure, only ever
    sets dates on scopes that already exist. Rows matching no scope, and
    scopes with no matching row, are simply left alone."""
    rows = parse_schedule_workbook(file_obj)
    if not rows:
        return {"matched": 0, "unmatched": 0, "total_rows": 0}

    by_name = {}
    for s in project.scopes.only("id", "name", "planned_start", "planned_finish"):
        by_name.setdefault(s.name.strip().lower(), []).append(s)

    matched, unmatched, to_update = 0, 0, []
    for row in rows:
        scopes = by_name.get(row["name"].lower())
        if not scopes:
            unmatched += 1
            continue
        for s in scopes:
            if row["start"]:
                s.planned_start = row["start"]
            if row["finish"]:
                s.planned_finish = row["finish"]
            to_update.append(s)
        matched += 1

    if to_update:
        ProjectScope.objects.bulk_update(to_update, ["planned_start", "planned_finish"], batch_size=1000)
    return {"matched": matched, "unmatched": unmatched, "total_rows": len(rows)}
