"""Import monthly cash flow, and invoices/extracts, from an Excel workbook.

Cash flow supports two layouts:

* WIDE (the common site-office / Primavera cash-flow sheet): months run across a
  header row as real dates, with labelled "planned" and "actual" cash rows below.
* TALL (a simple template): Month | Planned | Actual columns down the rows.

Cumulative and percentage rows are ignored — we only want the per-month amounts,
since the app stores those and charts the cumulative S-curve itself.

Invoices come from a different shape entirely — see parse_invoice_extracts below.
"""
import datetime
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

import openpyxl
from django.db import transaction

from .models import CashFlowEntry, Invoice, ProgressCurvePoint

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
        # Site cash-flow sheets often call the actual cash-in "invoices" rather
        # than "actual" — treat either as the real-money row.
        elif actual_row is None and (_is_data_label(label, "actual") or _is_data_label(label, "invoice")):
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
    """Return {month(date): (planned, actual)} from the best sheet that yields a
    recognisable cash-flow layout, or raise ValueError if none do.

    A workbook with several per-contract cash-flow sheets (e.g. cashflow1/2/3)
    plus one aggregating them (e.g. "cashflow total") should import the total,
    not whichever partial sheet happens to come first — so sheets with "total"
    in their name are tried before the rest."""
    wb = openpyxl.load_workbook(upload, read_only=False, data_only=True)
    try:
        sheets = sorted(wb.worksheets, key=lambda ws: "total" not in ws.title.strip().lower())
        # A reader only returns data once it has locked onto a real layout (the
        # wide reader needs MIN_MONTHS date cells to accept a header row), so any
        # non-empty result here is a genuine cash-flow — even a couple of months.
        for reader in (_read_wide, _read_tall):
            for ws in sheets:
                data = reader(ws)
                if data:
                    return data
    finally:
        wb.close()
    raise ValueError(
        "No cash-flow layout found. Expected either month dates across a row with "
        "'planned'/'actual' rows below, or Month/Planned/Actual columns."
    )


# The dashboard's "progress curve" sheet is transposed: month dates run across
# one header row and each series is a row beneath it.
#
# Matched on the least each label can be trusted to carry, because the wording
# is the project team's own and varies per workbook. Two real files of the same
# template disagree on every row but one:
#
#   Cummulative Early Budget Expense  %   vs   Cummulative Early Planned %
#   Cummulative Late Budget  %            vs   Cummulative Late Panned %
#   Cummulative Actual Cost  %            vs   Cummulative Actual  %
#   Cumm Remaining  Cost%                 vs   Cummulative Remaining %
#
# Needling on "cummulative early budget" matched the first and not the second,
# so the airport project imported its actual line alone and its S-curve came
# out blank (2026-09-08). "cum" rather than "cummulative" also survives the
# spelling being corrected, and the "%" is what separates each cumulative
# PERCENTAGE row from the cost row of the same name directly above it.
_CURVE_SERIES = {
    "early_planned": ("cum", "early", "%"),
    "late_planned": ("cum", "late", "%"),
    "actual": ("cum", "actual", "%"),
    "remaining": ("cum", "remaining", "%"),
}


def _curve_label_matches(label, needles) -> bool:
    flat = " ".join(str(label or "").lower().split())
    return all(n in flat for n in needles)


def parse_progress_curve(wb):
    """{month(date): {early_planned, late_planned, actual, remaining}} from a
    workbook's "progress curve" sheet, or {} when it has no such sheet.

    Values are the sheet's own fractions scaled to percentages. Only the
    columns whose header is a real date are read: the rows run on past the
    plotted series into working cells, and those tails would otherwise arrive
    as spurious 13,647% points."""
    sheet = next((ws for ws in wb.worksheets if "progress curve" in ws.title.strip().lower()), None)
    if sheet is None:
        return {}
    rows = [r for r in sheet.iter_rows(min_row=1, max_row=30, values_only=True)]

    # The header row is whichever of the first few carries the most dates.
    best, best_cols = None, []
    for row in rows:
        cols = [i for i, c in enumerate(row) if isinstance(c, datetime.datetime)]
        if len(cols) > len(best_cols):
            best, best_cols = row, cols
    if not best_cols or len(best_cols) < 2:
        return {}

    out = {}
    for key, needles in _CURVE_SERIES.items():
        row = next((r for r in rows if _curve_label_matches(r[0] if r else None, needles)), None)
        if row is None:
            continue
        for i in best_cols:
            value = row[i] if i < len(row) else None
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            month = best[i].date().replace(day=1)
            out.setdefault(month, {})[key] = round(float(value) * 100, 2)
    return out


def import_progress_curve(project, wb) -> int:
    """Replace the project's Progress Curve from an already-open workbook.

    Replace, not merge — same rule as the cash flow beside it: the sheet is
    the whole curve, so a re-import restating fewer months must not leave the
    old ones dangling past the end of the new one."""
    data = parse_progress_curve(wb)
    if not data:
        return 0
    rows = [
        ProgressCurvePoint(
            company=project.company, project=project, date=month,
            early_planned=values.get("early_planned"), late_planned=values.get("late_planned"),
            actual=values.get("actual"), remaining=values.get("remaining"),
        )
        for month, values in sorted(data.items())
    ]
    with transaction.atomic():
        project.curve_points.all().delete()
        ProgressCurvePoint.objects.bulk_create(rows)
    return len(rows)


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

    # The same workbook carries the Progress Curve the report's S-curve draws,
    # so one upload brings both rather than asking for the same file twice.
    # Re-read from the start: parse_cashflow has already consumed the stream.
    curve_months = 0
    try:
        upload.seek(0)
        wb = openpyxl.load_workbook(upload, read_only=False, data_only=True)
        try:
            curve_months = import_progress_curve(project, wb)
        finally:
            wb.close()
    except Exception:
        # A workbook with no such sheet (or an unreadable one) still imported
        # its cash flow — that must not be undone over a curve it never had.
        curve_months = 0

    return {
        "months": len(rows),
        "first_month": months[0].isoformat(),
        "last_month": months[-1].isoformat(),
        "curve_months": curve_months,
    }


# --- Invoices / extracts (مستخلصات) ----------------------------------------
#
# The reference layout is NOT a flat invoice list — it's a per-BOQ-item matrix:
# one row per work item/zone, and one column-GROUP per submitted extract
# ("حتى <date>" = "up to <date>"), each group holding a "رقم المستخلص" (extract
# number) column and an "اجمالي الأعمال" (total work value) column. The value in
# that column is the item's CUMULATIVE work done as of that extract, not the
# extract's own amount — it climbs toward the item's contract value.
#
# An invoice's own value is therefore derived, not read directly: sum the
# "اجمالي الأعمال" column down every row to get the project's cumulative total at
# that extract, then subtract the previous extract's cumulative total. That
# matches how a progress "مستخلص" actually works — it bills the work done since
# the last one.

_ARABIC_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4, "مايو": 5,
    "يونيو": 6, "يوليو": 7, "اغسطس": 8, "أغسطس": 8, "سبتمبر": 9,
    "اكتوبر": 10, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}
_EXTRACT_DATE_RX = re.compile(r"(\d{1,2})\s+([^\s\-]+)\s*-\s*(\d{4})")
# The per-extract money column. Most blocks head it "اجمالي الأعمال"; the
# airport tracker heads its own latest one "اجمالي  المستخلص" (the extract's
# total) instead — same column, same block shape, a different word. Matching
# only the first name found that project's 19 named-but-empty columns and
# missed the one filled block, so its invoices imported as nothing at all
# (2026-09-08). Compared with whitespace collapsed: the real cells double
# their internal spaces.
_TOTAL_WORKS_LABELS = {"اجمالي الأعمال", "اجمالي المستخلص", "إجمالي الأعمال", "إجمالي المستخلص"}
_EXTRACT_HEADER_SCAN_ROWS = 10


def _is_total_works(value) -> bool:
    return isinstance(value, str) and " ".join(value.split()) in _TOTAL_WORKS_LABELS


def _parse_extract_date(label):
    """Best-effort parse of a "حتى 15 ديسمبر - 2023" style label. Real trackers
    have typos (a wrong year on a late column is common) — return None rather
    than raise, so one bad label doesn't block the whole import.

    A block can head itself with a real date cell instead of that text, which
    arrives here as a date and needs no parsing."""
    if isinstance(label, datetime.datetime):
        return label.date()
    if isinstance(label, datetime.date):
        return label
    m = _EXTRACT_DATE_RX.search(label or "")
    if not m:
        return None
    day, month_name, year = m.groups()
    month = _ARABIC_MONTHS.get(month_name.strip())
    if not month:
        return None
    try:
        return datetime.date(int(year), month, int(day))
    except ValueError:
        return None


def _locate_extract_header(ws):
    """Find (group_row, sub_row): sub_row is the row carrying "اجمالي الأعمال"
    sub-headers; group_row is the nearest row above it carrying the per-extract
    label (the label only occupies the first cell of its merged span — read_only
    cells outside that first cell come back None, same as every other merged
    header in these trackers)."""
    for sub_row in range(1, min(ws.max_row, _EXTRACT_HEADER_SCAN_ROWS) + 1):
        cells = [c.value for c in next(ws.iter_rows(min_row=sub_row, max_row=sub_row))]
        if any(_is_total_works(v) for v in cells):
            for group_row in range(sub_row - 1, 0, -1):
                grp = [c.value for c in next(ws.iter_rows(min_row=group_row, max_row=group_row))]
                if any(isinstance(v, str) and v.strip() for v in grp):
                    return group_row, sub_row
    return None


def _extract_label_text(label) -> str:
    """The group heading as a name, for a block whose rows carry no
    "رقم المستخلص" to name it by."""
    if isinstance(label, (datetime.date, datetime.datetime)):
        return label.strftime("%d %b %Y")
    return str(label or "")


_EXTRACT_NUMBER_LABEL = "رقم المستخلص"
_PLACEHOLDER_VALUES = {"-", "—", ""}

# The sheet ends with its own totals row ("الاجمالي"), which already adds up
# every item row above it. Summing the column blind therefore counted each
# extract TWICE — every invoice, and the project's invoiced total, came out at
# exactly 2x (confirmed on the client's own workbook: the totals row reads
# 772,765,610.74 where the naive sum read 1,545,531,221.48, 2026-09-07).
# Spelling varies across trackers (hamza and alef-maqsura both appear), so
# match a normalised form rather than one literal.
_TOTAL_ROW_LABELS = {"الاجمالي", "الإجمالي", "الاجمالى", "الإجمالى", "اجمالي", "إجمالي"}


# Only the row-title columns are checked for it. The word also appears as a
# label deep inside the data columns (col 69 on the client's own sheet), and
# matching there stopped the scan 20 rows early on a row that is not a total.
_TOTAL_LABEL_MAX_COL = 3


def _extract_order(dated):
    """`dated` — [(column, name, date, cumulative)] — in the order the extracts
    were actually submitted.

    Neither the column order nor the dates can be trusted on their own. One
    tracker appends a column out of date order, so diffing cumulative totals in
    sheet order there compares two unrelated points in time; another carries a
    typo'd year on its latest column ("حتى 15 يناير - 2025" for 2026), which
    sorts the largest figure in the sheet to the middle and makes every real
    extract after it look like it went backwards — five of them were dropped
    (2026-09-08).

    A cumulative series only ever grows, so that is the test: take whichever
    order never goes backwards, preferring the dates when both hold. Neither
    working leaves the dates, and the caller's own guard drops what still
    contradicts itself."""
    def key_date(t):
        return (t[2] is None, t[2] or datetime.date.max, t[0])

    def never_backwards(seq):
        return all(a[3] <= b[3] for a, b in zip(seq, seq[1:]))

    by_date = sorted(dated, key=key_date)
    if never_backwards(by_date):
        return by_date
    by_column = sorted(dated, key=lambda t: t[0])
    return by_column if never_backwards(by_column) else by_date


def _numeric(value):
    """`value` as a float, or None when the cell isn't a number. Booleans are
    not numbers here — a "yes/no" column would otherwise total as 1s."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _totals_the_items(stated, running) -> bool:
    """Does a totals cell actually add up the item rows above it?

    Three things in real trackers look like a grand total and are not, and
    this one test rejects all three (2026-09-08):

    - an intermediate subtotal ("إجمالي الكميات المنفذة") sitting part way
      down with dozens of item rows still below it — it states a fraction of
      the column, so it doesn't match;
    - a hardcoded leftover on the totals line of a column whose item cells are
      all empty (one tracker carries 3,742,205,096 there, 5.7x that project's
      whole contract, and being the sheet's largest figure it suppressed every
      genuine extract dated after it as "going backwards");
    - the tax-inclusive line a sheet puts under its works total
      ("الاجمالي شامل الضريبة" below "الاجمالي غير شامل الضريبة") — it is
      bigger than the items by exactly the tax, so the works figure above it
      is the one taken, which is also what a single-total tracker means.

    Relative tolerance, because these columns are long sums of decimals."""
    return abs(stated - running) <= max(1.0, abs(stated) * 1e-6)


def _is_total_row(row) -> bool:
    """True when a data row is the sheet's own totals line.

    Matched on how the label STARTS, and only in the leading label columns.
    Real sheets qualify the word — "الاجمالي غير شامل الضريبة" (total
    excluding tax) sits above "الاجمالي شامل الضريبة" — and requiring the
    whole cell to equal "الاجمالي" matched neither, so the totals line was
    summed along with the item rows above it: one extract column came out at
    3.74 BILLION against a 656M contract and, being the largest figure in the
    sheet, then suppressed every extract dated after it as "going backwards"
    (2026-09-08).

    Never a bare substring, and never past those first columns: the value
    sub-header one row above is "اجمالي الأعمال", which carries the same
    word, and the word also appears as a data heading deep in a real row."""
    for cell in row[:_TOTAL_LABEL_MAX_COL]:
        if not isinstance(cell, str):
            continue
        text = " ".join(cell.split())
        if any(text == word or text.startswith(word + " ") for word in _TOTAL_ROW_LABELS):
            return True
    return False


def parse_invoice_extracts(upload):
    """Return ([{name, date, value}], skipped) — one dict per submitted extract
    in chronological order, value already converted from cumulative to the
    extract's own amount; `skipped` counts extracts dropped as unreliable (see
    below). None (not a tuple) if no sheet matches this layout at all."""
    wb = openpyxl.load_workbook(upload, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            located = _locate_extract_header(ws)
            if not located:
                continue
            group_row, sub_row = located
            group_cells = [c.value for c in next(ws.iter_rows(min_row=group_row, max_row=group_row))]
            sub_cells = [c.value for c in next(ws.iter_rows(min_row=sub_row, max_row=sub_row))]

            # Forward-fill the group label across its merged span, keeping the
            # "اجمالي الأعمال" sub-column of each group — one per extract — and,
            # when present, the "رقم المستخلص" column immediately to its left.
            # That extract-number cell (e.g. "مستخلص جاري (8)") is the real,
            # human-recognizable name of the invoice; the date label above it is
            # just the column heading and reads badly as a name.
            periods, label = [], ""
            for i, v in enumerate(group_cells):
                # A group heading is normally the "حتى 15 مارس - 2025" text, but
                # a block can carry a real date cell instead — keep either, or
                # the forward-fill hands that block the PREVIOUS block's date.
                if isinstance(v, (datetime.date, datetime.datetime)):
                    label = v
                elif isinstance(v, str) and v.strip():
                    label = v.strip()
                if i < len(sub_cells) and _is_total_works(sub_cells[i]) and label:
                    number_col = i - 1 if i >= 1 and isinstance(sub_cells[i - 1], str) \
                        and sub_cells[i - 1].strip() == _EXTRACT_NUMBER_LABEL else None
                    # Prefer the heading over the block's OWN first column.
                    # Forward-filling reaches this block's value column too, and
                    # one tracker puts a different string there ("خلال الفترة من
                    # بداية الاعمال حتى…") which overwrote the date the block
                    # actually carries (2026-09-08).
                    own = (group_cells[number_col]
                           if number_col is not None and number_col < len(group_cells) else None)
                    if isinstance(own, (datetime.date, datetime.datetime)):
                        periods.append((i, number_col, own))
                    elif isinstance(own, str) and own.strip():
                        periods.append((i, number_col, own.strip()))
                    else:
                        periods.append((i, number_col, label))
            if not periods:
                continue

            sums = defaultdict(float)
            numbers = {}  # value_col -> first real "رقم المستخلص" text seen
            # value_col -> the sheet's own stated total, accepted only where it
            # actually totals the items above it (see _totals_the_items).
            totals = {}
            for row in ws.iter_rows(min_row=sub_row + 1, values_only=True):
                if _is_total_row(row):
                    # Authoritative where it applies: adding it to the running
                    # sum would double every extract (see _TOTAL_ROW_LABELS).
                    # A row that only LOOKS like a total is an ordinary line
                    # and falls through to be counted as one — this tracker has
                    # a real work item headed "إجمالي الكميات المنفذة", and
                    # skipping it lost its 4,463,299 from the column.
                    if any(_totals_the_items(v, sums.get(idx, 0.0))
                           for idx, _, _ in periods
                           if idx not in totals
                           and (v := _numeric(row[idx] if idx < len(row) else None)) is not None):
                        for idx, _, _ in periods:
                            v = _numeric(row[idx] if idx < len(row) else None)
                            if v is not None and idx not in totals                                     and _totals_the_items(v, sums.get(idx, 0.0)):
                                totals[idx] = v
                        continue
                for idx, number_col, _ in periods:
                    # A column closed by its own stated total ignores whatever
                    # follows — a sheet can carry stray rows below its total.
                    v = None if idx in totals else _numeric(row[idx] if idx < len(row) else None)
                    if v is not None:
                        sums[idx] += v
                    if number_col is not None and idx not in numbers and number_col < len(row):
                        n = row[number_col]
                        if isinstance(n, str) and n.strip() and n.strip() not in _PLACEHOLDER_VALUES:
                            numbers[idx] = n.strip()

            # The sheet's own total wins where it has one; the item rows are
            # only added up for a tracker that carries no totals line.
            dated = [(idx, numbers.get(idx) or _extract_label_text(label),
                      _parse_extract_date(label), totals.get(idx, sums.get(idx, 0.0)))
                    for idx, _, label in periods]
            dated = _extract_order(dated)

            # A cumulative-to-date total must not go backwards. It does, hard, in
            # trackers whose source formulas have quietly broken (this workbook
            # has confirmed #REF! errors elsewhere) — a later column's cached sum
            # can be a stale fraction of an earlier one. Once a column's total
            # comes in below the highest total seen so far, it and everything
            # computed from it is unreliable: drop it rather than book a
            # fabricated invoice, and keep comparing later columns against the
            # last column that *did* make sense.
            seen = defaultdict(int)  # de-dupes a repeated extract name into "(2)", "(3)"...
            out, last_good = [], 0.0
            skipped = 0
            for idx, name, date, cumulative in dated:
                if cumulative < last_good:
                    skipped += 1
                    continue
                seen[name] += 1
                display = name if seen[name] == 1 else f"{name} ({seen[name]})"
                out.append({
                    "name": display[:200], "date": date,
                    "value": round(cumulative - last_good, 2),
                })
                last_good = cumulative
            return out, skipped
    finally:
        wb.close()
    return None


def import_invoices(project, upload):
    """Create/update the project's invoices from an uploaded extract-comparison
    workbook. Upserts by (name, date) rather than replacing wholesale, so a
    re-import (the tracker gets a new extract column each period) never touches
    invoices entered by hand or their attached scan images."""
    result = parse_invoice_extracts(upload)
    if not result:
        raise ValueError(
            "No invoice/extract layout found. Expected a per-item table with "
            "'رقم المستخلص' and 'اجمالي الأعمال' columns, one pair per submitted extract."
        )
    periods, skipped = result
    created = updated = 0
    with transaction.atomic():
        existing = {(inv.name, inv.date): inv for inv in project.invoices.all()}
        for i, p in enumerate(periods):
            value = Decimal(str(p["value"])).quantize(Decimal("0.01"))
            match = existing.get((p["name"], p["date"]))
            if match:
                if match.value != value:
                    match.value = value
                    match.save(update_fields=["value"])
                updated += 1
            else:
                Invoice.objects.create(
                    company=project.company, project=project, name=p["name"],
                    value=value, date=p["date"], sort_order=i,
                )
                created += 1
    return {"periods": len(periods), "created": created, "updated": updated, "skipped": skipped}
