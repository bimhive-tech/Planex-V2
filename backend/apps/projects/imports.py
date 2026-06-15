"""Excel import: parse a zone-based progress-tracker workbook into the project
hierarchy (one Zone scope per sheet, one Activity per task — progress averaged
across that task's subzones).

The layout varies between sheets (some have a leading weight column, some don't),
so the structure is *detected* per sheet rather than assumed. The Primavera
'FOR (P6)' round-trip sheet and the 'Summary' sheet are skipped in this version.
"""
import re

import openpyxl
from django.db import transaction

from .models import Activity, ProjectScope
from .services import project_overall_progress

CODE_RE = re.compile(r"^\(.+\)$")  # subzone codes look like "(A6)", "(B12)"
SKIP_SHEETS = {"for (p6)", "summary"}
MAX_TASKS_PER_ZONE = 3000


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def parse_sheet(rows):
    """Detect the grid and return a list of {name, weight, progress(0-100)}."""
    # 1) Find the row that holds subzone codes (most parenthesised string cells).
    code_row, code_cols = None, []
    for i, row in enumerate(rows[:8]):
        cols = [j for j, v in enumerate(row) if isinstance(v, str) and CODE_RE.match(v.strip())]
        if len(cols) > len(code_cols):
            code_row, code_cols = i, cols
    if not code_cols:
        return []

    first_sub = min(code_cols)
    name_col = first_sub - 1
    weight_col = name_col - 1 if name_col - 1 >= 0 else None
    if name_col < 0:
        return []

    # Task rows start after the code row + the per-subzone summary row beneath it.
    tasks = []
    for row in rows[code_row + 2:]:
        if len(tasks) >= MAX_TASKS_PER_ZONE:
            break
        name = row[name_col] if name_col < len(row) else None
        if not isinstance(name, str) or not name.strip():
            continue

        weight = 1.0
        if weight_col is not None and weight_col < len(row):
            wv = _num(row[weight_col])
            if wv is not None and wv > 0:
                weight = float(wv)

        vals = [_num(row[c]) for c in code_cols if c < len(row)]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        pct = avg * 100 if avg <= 1.0001 else avg  # values are fractions (0–1)
        pct = max(0.0, min(100.0, round(pct, 2)))
        tasks.append({"name": name.strip()[:200], "weight": weight, "progress": pct})
    return tasks


def parse_workbook(file_obj) -> dict:
    """Return {zone_sheet_name: [task dicts]} for every zone sheet."""
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    result = {}
    try:
        for name in wb.sheetnames:
            if name.strip().lower() in SKIP_SHEETS:
                continue
            ws = wb[name]
            rows = list(ws.iter_rows(values_only=True))
            tasks = parse_sheet(rows)
            if tasks:
                result[name.strip()] = tasks
    finally:
        wb.close()
    return result


@transaction.atomic
def import_workbook(project, file_obj, *, replace=True) -> dict:
    """Parse the workbook and (re)build the project's hierarchy from it."""
    parsed = parse_workbook(file_obj)
    if not parsed:
        return {"zones": 0, "activities": 0, "overall_progress": 0.0, "error": "No zone sheets recognised."}

    if replace:
        project.scopes.all().delete()  # cascades activities

    activities = []
    for z, (zone_name, tasks) in enumerate(parsed.items()):
        zone = ProjectScope.objects.create(
            company=project.company, project=project,
            scope_type=ProjectScope.ScopeType.ZONE, name=zone_name, sort_order=z,
        )
        for i, t in enumerate(tasks):
            activities.append(Activity(
                company=project.company, project=project, scope=zone,
                name=t["name"], weight=t["weight"], progress_percent=t["progress"],
                progress_type=Activity.ProgressType.PERCENTAGE, sort_order=i,
            ))
    Activity.objects.bulk_create(activities, batch_size=1000)

    return {
        "zones": len(parsed),
        "activities": len(activities),
        "overall_progress": project_overall_progress(project),
    }
