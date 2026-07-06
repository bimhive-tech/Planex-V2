"""Import monthly cash flow from an Excel workbook.

Two layouts are supported:

* WIDE (the common site-office / Primavera cash-flow sheet): months run across a
  header row as real dates, with labelled "planned" and "actual" cash rows below.
* TALL (a simple template): Month | Planned | Actual columns down the rows.

Cumulative and percentage rows are ignored — we only want the per-month amounts,
since the app stores those and charts the cumulative S-curve itself.
"""
import datetime
from decimal import Decimal, InvalidOperation

import openpyxl
from django.db import transaction

from .models import CashFlowEntry

SCAN_ROWS = 100          # how deep to look for the header / label rows
SCAN_COLS = 200          # cap width so 16k-column export sheets don't stall us
MIN_MONTHS = 3           # a valid cash-flow needs at least a few months
_EXCLUDE = ("cumulative", "cumm", "%", "percent")  # skip running-total / % rows


_MONTH_STR_FORMATS = ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y", "%b %Y", "%B %Y")


def _as_month(value, strings=False):
    """Coerce a cell to the first day of its month, or None if it isn't a date.

    `strings=True` also parses common textual dates ("2026-06-01", "Jun 2026") —
    used only by the tall-template reader, so stray text like a manpower "OCT"
    header can't masquerade as a month in the wide reader's detection."""
    if isinstance(value, datetime.datetime):
        return value.date().replace(day=1)
    if isinstance(value, datetime.date):
        return value.replace(day=1)
    if strings and isinstance(value, str):
        text = value.strip()
        for fmt in _MONTH_STR_FORMATS:
            try:
                return datetime.datetime.strptime(text, fmt).date().replace(day=1)
            except ValueError:
                continue
    return None


def _as_amount(value):
    """Coerce a cell to a 2dp Decimal, or None if it isn't a plain number."""
    if value is None or isinstance(value, (datetime.datetime, datetime.date, str)):
        # strings are rejected: a label column must not be read as an amount
        if isinstance(value, str):
            value = value.strip().replace(",", "")
            if not value:
                return None
        else:
            return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _row_label(ws, row):
    """The first text cell in the first few columns — the row's label."""
    for col in range(1, 5):
        v = ws.cell(row=row, column=col).value
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _is_data_label(label, keyword):
    return keyword in label and not any(x in label for x in _EXCLUDE)


def _read_wide(ws):
    """Find a date-header row and the planned/actual rows beneath it."""
    header_row = header = None
    for row in range(1, min(ws.max_row, SCAN_ROWS) + 1):
        months = {}
        for col in range(1, min(ws.max_column, SCAN_COLS) + 1):
            m = _as_month(ws.cell(row=row, column=col).value)
            if m:
                months[col] = m
        if len(months) >= MIN_MONTHS:
            header_row, header = row, months
            break
    if not header:
        return {}

    planned_row = actual_row = None
    for row in range(header_row, min(ws.max_row, SCAN_ROWS) + 1):
        label = _row_label(ws, row)
        if planned_row is None and _is_data_label(label, "planned"):
            planned_row = row
        elif actual_row is None and _is_data_label(label, "actual"):
            actual_row = row
    if planned_row is None and actual_row is None:
        return {}

    out = {}
    for col, month in header.items():
        planned = _as_amount(ws.cell(row=planned_row, column=col).value) if planned_row else None
        actual = _as_amount(ws.cell(row=actual_row, column=col).value) if actual_row else None
        if planned is None and actual is None:
            continue  # a header date with no cash under it isn't a real month
        out[month] = (planned or Decimal("0"), actual or Decimal("0"))
    return out


def _read_tall(ws):
    """Find a Month / Planned / Actual column header, then read rows beneath."""
    cols = {}
    header_row = None
    for row in range(1, min(ws.max_row, SCAN_ROWS) + 1):
        found = {}
        for col in range(1, min(ws.max_column, SCAN_COLS) + 1):
            v = ws.cell(row=row, column=col).value
            if not isinstance(v, str):
                continue
            t = v.strip().lower()
            if t in ("month", "date") and "month" not in found:
                found["month"] = col
            elif _is_data_label(t, "planned") and "planned" not in found:
                found["planned"] = col
            elif _is_data_label(t, "actual") and "actual" not in found:
                found["actual"] = col
        if "month" in found and ("planned" in found or "actual" in found):
            cols, header_row = found, row
            break
    if not header_row:
        return {}

    out = {}
    for row in range(header_row + 1, ws.max_row + 1):
        month = _as_month(ws.cell(row=row, column=cols["month"]).value, strings=True)
        if not month:
            continue
        planned = _as_amount(ws.cell(row=row, column=cols["planned"]).value) if "planned" in cols else None
        actual = _as_amount(ws.cell(row=row, column=cols["actual"]).value) if "actual" in cols else None
        out[month] = (planned or Decimal("0"), actual or Decimal("0"))
    return out


def parse_cashflow(upload):
    """Return {month(date): (planned, actual)} from the first sheet that yields a
    recognisable cash-flow layout, or raise ValueError if none do."""
    wb = openpyxl.load_workbook(upload, read_only=False, data_only=True)
    try:
        # A reader only returns data once it has locked onto a real layout (the
        # wide reader needs MIN_MONTHS date cells to accept a header row), so any
        # non-empty result here is a genuine cash-flow — even a couple of months.
        for reader in (_read_wide, _read_tall):
            for ws in wb.worksheets:
                data = reader(ws)
                if data:
                    return data
    finally:
        wb.close()
    raise ValueError(
        "No cash-flow layout found. Expected either month dates across a row with "
        "'planned'/'actual' rows below, or Month/Planned/Actual columns."
    )


def import_cashflow(project, upload):
    """Replace the project's monthly cash flow from an uploaded workbook.

    Returns a small summary for the UI. Replace (not merge) keeps it predictable:
    what's in the sheet is what you get, matching how the manual grid saves."""
    data = parse_cashflow(upload)
    months = sorted(data)
    rows = [
        CashFlowEntry(company=project.company, project=project, month=m,
                      planned=data[m][0], actual=data[m][1])
        for m in months
    ]
    with transaction.atomic():
        project.cashflow_entries.all().delete()
        CashFlowEntry.objects.bulk_create(rows)
    return {
        "months": len(rows),
        "first_month": months[0].isoformat(),
        "last_month": months[-1].isoformat(),
    }
