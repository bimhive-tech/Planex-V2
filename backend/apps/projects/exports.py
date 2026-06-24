"""Primavera-friendly Excel export of a project's hierarchy + ACCEPTED progress.

Note: the importer skips the native P6 sheet and doesn't capture P6's column
formulas, so this isn't a byte-for-byte round-trip — it's a clean activity
export in the column shape P6 expects (Activity ID/Name/WBS/Dates/% Complete),
built only from accepted data (activity.progress_percent reflects accepted
submissions). Returns raw .xlsx bytes.
"""
from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = [
    "Activity ID", "Activity Name", "WBS", "Discipline",
    "Start", "Finish", "Original Duration (d)", "Unit",
    "Planned Qty", "% Complete", "Weight",
]
_WIDTHS = [16, 34, 40, 14, 12, 12, 18, 10, 12, 12, 9]


def _scope_index(project):
    """Map every scope id -> (node, ' / '-joined path) without per-row queries."""
    nodes = {s.id: s for s in project.scopes.all()}
    paths: dict = {}

    def path_for(node):
        if node.id in paths:
            return paths[node.id]
        parent = nodes.get(node.parent_id)
        prefix = f"{path_for(parent)} / " if parent else ""
        paths[node.id] = prefix + node.name
        return paths[node.id]

    for node in nodes.values():
        path_for(node)
    return nodes, paths


def _duration_days(scope):
    if scope and scope.planned_start and scope.planned_finish:
        return (scope.planned_finish - scope.planned_start).days + 1
    return None


def _fmt(d):
    return d.strftime("%d-%b-%y") if d else ""


def build_p6_workbook(project) -> bytes:
    """Render the project's activities to an in-memory .xlsx and return its bytes."""
    nodes, paths = _scope_index(project)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Activities"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="5B4FE9")
    for col, title in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = _WIDTHS[col - 1]
    ws.freeze_panes = "A2"

    activities = (project.activities.select_related("scope")
                  .order_by("scope__sort_order", "sort_order", "name"))
    row = 2
    for a in activities:
        scope = a.scope
        disc = scope.get_discipline_display() if scope and scope.discipline else ""
        ws.cell(row=row, column=1, value=a.code or str(a.id)[:8])
        ws.cell(row=row, column=2, value=a.name)
        ws.cell(row=row, column=3, value=paths.get(a.scope_id, ""))
        ws.cell(row=row, column=4, value=disc)
        ws.cell(row=row, column=5, value=_fmt(scope.planned_start if scope else None))
        ws.cell(row=row, column=6, value=_fmt(scope.planned_finish if scope else None))
        ws.cell(row=row, column=7, value=_duration_days(scope))
        ws.cell(row=row, column=8, value=a.unit or "")
        ws.cell(row=row, column=9, value=float(a.planned_quantity) if a.planned_quantity is not None else None)
        ws.cell(row=row, column=10, value=float(a.progress_percent))
        ws.cell(row=row, column=11, value=float(a.weight))
        row += 1

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
