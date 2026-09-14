"""Read the summary panels off a dashboard workbook's "Dashboard" sheet.

Three panels the report charts directly (planner review, register F3-F5):

  duration     the project duration block and its delay
  submittals   the shop-drawing and material-submittal grids
  boq          "Financial Progress according to BOQ"

Every panel is found by its own LABELS, never by a fixed cell. Two real
dashboards built from the same template already disagree on where things sit
and on the wording around them, so a cell address that is right for one is
wrong for the other.

Shapes, as stored on DashboardPanels.data:

  duration   {"project_days", "completed_days", "remaining_days",
              "elapsed_pct", "remaining_pct", "delay_days"}   any may be absent
  submittals {"shop_drawing": [{"discipline", "submitted", "approved",
                                "rejected", "pending"}, ...],
              "material": [...]}
  boq        {"total": float|None,
              "rows": [{"category", "budget_share", "financial_percent"}]}

Percentages are kept as the sheet stores them — fractions of 1 — and scaled to
0-100 only where the report draws them, so nothing here rounds.
"""
import openpyxl

SHEET = "dashboard"

# A label's value is the first number to its right on the same row, within
# this many columns. Wide enough for the one-column gap the delay row leaves
# ("PROJECT DELAY IN CALENDAR DAYS" -> blank -> -47), narrow enough not to
# wander into the next panel along.
_VALUE_REACH = 3


def _norm(value) -> str:
    return " ".join(str(value).split()).lower() if isinstance(value, str) else ""


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _grid(ws):
    """The sheet as a list of rows of cell values, read once."""
    return [list(row) for row in ws.iter_rows(values_only=True)]


def _labelled_values(rows) -> dict:
    """{normalised label: [values found to its right, in sheet order]}.

    A list per label because the template repeats some — "PROJECT DURATION"
    appears in two panels, and "Remaining Duration" is both a day count and a
    fraction depending on which panel it sits in."""
    found = {}
    for row in rows:
        for c, cell in enumerate(row):
            label = _norm(cell)
            if not label:
                continue
            for dc in range(1, _VALUE_REACH + 1):
                if c + dc >= len(row):
                    break
                value = _number(row[c + dc])
                if value is not None:
                    found.setdefault(label, []).append(value)
                    break
    return found


def _first(found, *needles, where=lambda v: True):
    """The first value under a label starting with any of `needles` that
    satisfies `where`."""
    for label, values in found.items():
        if any(label.startswith(n) for n in needles):
            for value in values:
                if where(value):
                    return value
    return None


def parse_duration(rows) -> dict:
    """The project duration block.

    "Remaining duration" names two different things in the template — days
    left in the duration panel, and the fraction of time left in the time
    performance panel beside it — so which one is meant is read off the value
    itself: a day count is larger than 1, a fraction never is."""
    found = _labelled_values(rows)
    days = lambda v: abs(v) > 1           # noqa: E731
    fraction = lambda v: 0 <= v <= 1      # noqa: E731
    out = {
        "project_days": _first(found, "project duration", where=days),
        "completed_days": _first(found, "completed duration", where=days),
        "remaining_days": _first(found, "remaining duration", where=days),
        "elapsed_pct": _first(found, "ellapsed duration", "elapsed duration", where=fraction),
        "remaining_pct": _first(found, "remaining duration", where=fraction),
        # The template writes the project's delay twice — once in its own block
        # and once as a label beside the duration bar. Either will do; they
        # agree.
        "delay_days": _first(found, "project delay in calendar days", "delay"),
    }
    return {k: v for k, v in out.items() if v is not None}


_STATUS_KEYS = ("submitted", "approved", "rejected", "pending")


def _parse_submittal_grid(rows, heading) -> list:
    """One status-by-discipline grid, starting at its `heading` cell.

    The template carries each grid twice — the current position and the
    previous one — so the first grid holding any counts is the current one."""
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if not _norm(cell).startswith(heading):
                continue
            # Status columns to the right of the heading, stopping at the next
            # grid's own heading. The shop-drawing and material grids sit side
            # by side with their status headers only a few columns apart, so
            # scanning a fixed width took the material grid's SUBMITTED column
            # for the shop drawings and reported 165 civil drawings as
            # submitted when the sheet says 426.
            columns = {}
            for cc in range(c + 1, len(row)):
                key = _norm(row[cc])
                if key in _STATUS_KEYS:
                    columns.setdefault(key, cc)
                elif key:
                    break
            if not columns:
                continue
            lines = []
            for below in rows[r + 1:]:
                discipline = below[c] if c < len(below) else None
                if not isinstance(discipline, str) or not discipline.strip():
                    break
                counts = {k: _number(below[cc]) if cc < len(below) else None
                          for k, cc in columns.items()}
                lines.append({"discipline": discipline.strip(),
                              **{k: int(v) if v is not None else 0 for k, v in counts.items()}})
            if any(sum(line[k] for k in columns) for line in lines):
                return lines
    return []


def parse_submittals(rows) -> dict:
    out = {
        "shop_drawing": _parse_submittal_grid(rows, "shop drawing"),
        "material": _parse_submittal_grid(rows, "material submittal"),
    }
    return {k: v for k, v in out.items() if v}


def parse_boq(rows) -> dict:
    """ "Financial Progress according to BOQ": one category per column, with a
    "Budget" row and an "Actual" row beneath, both fractions of the contract
    total.

    Those are exactly the two series the report's BOQ chart already draws —
    each category's share of the whole budget, and how much of the WHOLE
    budget it has earned — so they are carried over as they are."""
    for r, row in enumerate(rows):
        if not any(_norm(cell).startswith("financial progress according to boq") for cell in row):
            continue
        # Categories: the next row holding several text cells.
        for cat_r in range(r + 1, min(r + 4, len(rows))):
            names = {c: v.strip() for c, v in enumerate(rows[cat_r])
                     if isinstance(v, str) and v.strip()}
            if len(names) >= 2:
                break
        else:
            return {}

        def series(label):
            for below in rows[cat_r + 1: cat_r + 8]:
                for c, cell in enumerate(below):
                    if _norm(cell) == label:
                        return {col: _number(below[col]) for col in names if col < len(below)}
            return {}

        budget, actual = series("budget"), series("actual")
        if not budget and not actual:
            return {}
        # The contract total the fractions are taken against sits at the start
        # of the category row.
        total = next((_number(v) for v in rows[cat_r] if _number(v) is not None), None)
        return {
            "total": total,
            "rows": [{"category": name,
                      "budget_share": budget.get(col),
                      "financial_percent": actual.get(col)}
                     for col, name in names.items()],
        }
    return {}


def parse_dashboard_panels(wb) -> dict:
    """Every panel the workbook's Dashboard sheet carries, or {} without one."""
    sheet = next((ws for ws in wb.worksheets if ws.title.strip().lower() == SHEET), None)
    if sheet is None:
        return {}
    rows = _grid(sheet)
    out = {
        "duration": parse_duration(rows),
        "submittals": parse_submittals(rows),
        "boq": parse_boq(rows),
    }
    return {k: v for k, v in out.items() if v}


def import_dashboard_panels(project, upload) -> dict:
    """Replace the project's stored panels with this workbook's.

    Raises ValueError when the workbook has no Dashboard sheet, or one with
    none of the panels on it — the dashboard import reports that as a part it
    skipped rather than as a failure, and leaves any panels already stored
    alone."""
    from .models import DashboardPanels

    wb = openpyxl.load_workbook(upload, data_only=True)
    try:
        panels = parse_dashboard_panels(wb)
    finally:
        wb.close()
    if not panels:
        raise ValueError("No Dashboard sheet with duration, submittal or BOQ panels found.")
    DashboardPanels.objects.update_or_create(
        project=project, defaults={"company": project.company, "data": panels})
    return {name: _describe(name, panel) for name, panel in panels.items()}


def _describe(name, panel) -> int:
    """How much of a panel came in, for the import summary."""
    if name == "submittals":
        return sum(len(lines) for lines in panel.values())
    if name == "boq":
        return len(panel.get("rows") or [])
    return len(panel)
