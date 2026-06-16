"""Excel import for zone-based progress trackers.

Each ZONE sheet is a matrix: subzones across the columns, tasks down the rows,
and a progress cell at every (task, subzone). We import it as:
    Zone (scope)  ->  Subzone (area scope, one per column)  ->  Activity (one per
    (task, subzone) cell, grouped by row_index into task rows).

Layout is detected per sheet (the subzone-label row, the name column, and an
optional leading weight column). Phase/summary rows (col-A "W") are skipped.
The Primavera 'FOR (P6)' and 'Summary' sheets are skipped in this version.
"""
import openpyxl
from django.db import transaction

from .models import Activity, ProjectScope
from .services import project_overall_progress

SKIP_SHEETS = {"for (p6)", "summary"}
MAX_TASKS_PER_ZONE = 2000
MAX_SUBZONES_PER_ZONE = 300


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
            skip_first_summary = False
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


@transaction.atomic
def import_workbook(project, file_obj, *, replace=True) -> dict:
    parsed = parse_workbook(file_obj)
    if not parsed:
        return {"zones": 0, "subzones": 0, "activities": 0, "overall_progress": 0.0,
                "error": "No zone sheets recognised."}

    if replace:
        project.scopes.all().delete()  # cascades subzones + activities

    company = project.company
    subzone_total, activities = 0, []
    for z, (zone_name, sheet) in enumerate(parsed.items()):
        zone = ProjectScope.objects.create(
            company=company, project=project,
            scope_type=ProjectScope.ScopeType.ZONE, name=zone_name, sort_order=z,
        )
        subzone_scopes = [
            ProjectScope.objects.create(
                company=company, project=project, parent=zone,
                scope_type=ProjectScope.ScopeType.AREA, name=label or f"SZ{c + 1}", sort_order=c,
            )
            for c, label in enumerate(sheet["subzones"])
        ]
        subzone_total += len(subzone_scopes)

        for task in sheet["tasks"]:
            for c, val in enumerate(task["cells"]):
                if val is None:
                    continue
                activities.append(Activity(
                    company=company, project=project, scope=subzone_scopes[c],
                    name=task["name"], weight=task["weight"], progress_percent=val,
                    phase_name=task["phase"], row_index=task["row_index"], sort_order=task["row_index"],
                    progress_type=Activity.ProgressType.PERCENTAGE,
                ))
    Activity.objects.bulk_create(activities, batch_size=2000)

    return {
        "zones": len(parsed),
        "subzones": subzone_total,
        "activities": len(activities),
        "overall_progress": project_overall_progress(project),
    }
