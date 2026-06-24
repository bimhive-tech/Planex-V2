"""Primavera 'FOR (P6)'-style Excel export of a project's hierarchy + ACCEPTED
progress.

Matches the reference sheet's core layout: three columns — Activity ID,
Activity Name, Activity Complete % (a 0–1 fraction) — with the WBS hierarchy
rendered as indented group rows above their activities. The reference's wide
matrix of per-month baseline/update columns is Primavera snapshot history we
don't store, so it's omitted. Built only from accepted data
(activity.progress_percent reflects accepted submissions). Returns .xlsx bytes.
"""
from collections import defaultdict
from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = ["Activity ID", "Activity Name", "Activity Complete %"]
_WIDTHS = [22, 60, 18]


def _children_map(project):
    """parent_id -> [scopes] ordered by sort_order, plus the top-level list."""
    by_parent = defaultdict(list)
    for s in project.scopes.all().order_by("sort_order", "name"):
        by_parent[s.parent_id].append(s)
    return by_parent


def _activities_by_scope(project):
    acts = defaultdict(list)
    for a in project.activities.all().order_by("sort_order", "name"):
        acts[a.scope_id].append(a)
    return acts


def build_p6_workbook(project) -> bytes:
    """Render the project to an in-memory .xlsx (P6 layout) and return its bytes."""
    by_parent = _children_map(project)
    acts = _activities_by_scope(project)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FOR (P6)"

    # Title + header rows (mirrors the reference's banner over the columns).
    ws.cell(row=1, column=1, value=project.name).font = Font(bold=True, size=12)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="5B4FE9")
    for col, title in enumerate(HEADERS, start=1):
        cell = ws.cell(row=2, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = _WIDTHS[col - 1]
    ws.freeze_panes = "A3"

    group_fill = PatternFill("solid", fgColor="EFEDFE")
    state = {"row": 3}

    def emit_scope(scope, depth):
        # WBS group row: name in column A, bold + indented by depth.
        r = state["row"]
        cell = ws.cell(row=r, column=1, value=scope.name)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(indent=depth)
        for c in (1, 2, 3):
            ws.cell(row=r, column=c).fill = group_fill
        state["row"] += 1

        for child in by_parent.get(scope.id, []):
            emit_scope(child, depth + 1)

        for a in acts.get(scope.id, []):
            rr = state["row"]
            ws.cell(row=rr, column=1, value=a.code or str(a.id)[:8])
            name_cell = ws.cell(row=rr, column=2, value=a.name)
            name_cell.alignment = Alignment(indent=depth + 1)
            # Activity Complete % as a 0–1 fraction, shown as a percentage.
            pct = ws.cell(row=rr, column=3, value=round(float(a.progress_percent) / 100, 4))
            pct.number_format = "0%"
            state["row"] += 1

    for top in by_parent.get(None, []):
        emit_scope(top, 0)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
