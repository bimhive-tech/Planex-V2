"""The dashboard workbook's own Progress Curve — parsed from its "progress
curve" sheet and drawn as the report's S-curve (client ask, 2026-09-07).

Before this the S-curve had no source at all: its points came from seeded demo
rows, and its planned line was a straight interpolation between two project
dates. This reads the four cumulative series the client's dashboard already
plots, so the report's curve IS the curve they publish.
"""
import datetime
import io

import openpyxl
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import Company

from .finance_imports import import_progress_curve, parse_progress_curve
from .models import Project, ProgressCurvePoint

# The sheet is transposed: month dates across a header row, one series per row
# below it. Row labels are matched loosely because the real file's own wording
# is inconsistent about spacing ("Cummulative Actual Cost  %").
ROWS = [
    ["Spreadsheet Field", datetime.datetime(2022, 1, 1), datetime.datetime(2022, 2, 1),
     datetime.datetime(2022, 3, 1)],
    ["Early Budget  Expense Cost", 100, 200, 300],
    ["Cummulative Early Budget  Expense Cost", 100, 300, 600],
    ["Cummulative Early Budget Expense  %", 0.10, 0.30, 0.60],
    ["Cummulative Late Budget  %", 0.05, 0.25, 0.55],
    ["Cummulative Actual Cost  %", 0.09, 0.28, None],
    ["Cumm Remaining  Cost%", None, None, 1.0],
]


def _workbook(rows=None, title="progress curve"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for r in (rows if rows is not None else ROWS):
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return openpyxl.load_workbook(buf, data_only=True)


class ParseProgressCurveTests(SimpleTestCase):
    def test_reads_the_four_series_as_percentages(self):
        data = parse_progress_curve(_workbook())
        self.assertEqual(sorted(data), [datetime.date(2022, 1, 1), datetime.date(2022, 2, 1),
                                        datetime.date(2022, 3, 1)])
        self.assertEqual(data[datetime.date(2022, 1, 1)],
                         {"early_planned": 10.0, "late_planned": 5.0, "actual": 9.0})

    def test_a_series_may_stop_short_or_start_late(self):
        """Each covers a different span — the planned pair stops at the
        baseline finish, actual at the data date, remaining runs on from
        there — so a month carries only the series that reach it."""
        data = parse_progress_curve(_workbook())
        last = data[datetime.date(2022, 3, 1)]
        self.assertNotIn("actual", last)          # actual had no value that month
        self.assertEqual(last["remaining"], 100.0)
        self.assertNotIn("remaining", data[datetime.date(2022, 1, 1)])

    def test_a_workbook_without_the_sheet_yields_nothing(self):
        self.assertEqual(parse_progress_curve(_workbook(title="cashflow total")), {})

    def test_values_past_the_dated_columns_are_ignored(self):
        """The real rows run on past the plotted months into working cells;
        read positionally those tails arrive as 13,647% points."""
        rows = [list(r) for r in ROWS]
        rows[0].append("not a date")
        for r in rows[1:]:
            r.append(1364.7)
        data = parse_progress_curve(_workbook(rows))
        self.assertEqual(len(data), 3)
        self.assertTrue(all(v <= 100.0 for m in data.values() for v in m.values()))


class ImportProgressCurveTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type="commercial")

    def test_import_stores_a_row_per_month(self):
        self.assertEqual(import_progress_curve(self.project, _workbook()), 3)
        first = ProgressCurvePoint.objects.get(project=self.project, date=datetime.date(2022, 1, 1))
        self.assertEqual(float(first.early_planned), 10.0)
        self.assertEqual(float(first.late_planned), 5.0)
        self.assertEqual(float(first.actual), 9.0)
        self.assertIsNone(first.remaining)

    def test_reimport_replaces_rather_than_merges(self):
        """The sheet is the whole curve, so a restatement covering fewer
        months must not leave the old ones dangling past its end."""
        import_progress_curve(self.project, _workbook())
        shorter = [r[:3] for r in ROWS]   # 3 months restated as 2
        self.assertEqual(import_progress_curve(self.project, _workbook(shorter)), 2)
        self.assertEqual(
            list(ProgressCurvePoint.objects.filter(project=self.project)
                 .values_list("date", flat=True)),
            [datetime.date(2022, 1, 1), datetime.date(2022, 2, 1)])

    def test_a_workbook_without_the_sheet_leaves_an_existing_curve_alone(self):
        import_progress_curve(self.project, _workbook())
        self.assertEqual(import_progress_curve(self.project, _workbook(title="cashflow")), 0)
        self.assertEqual(ProgressCurvePoint.objects.filter(project=self.project).count(), 3)


class InvoiceTotalsRowTests(SimpleTestCase):
    """An extracts tracker ends with its own "الاجمالي" line, which already
    adds up every item row above it. Summing the column blind counted each
    extract twice — every invoice, and the project's invoiced total, came out
    at exactly 2x (client's own workbook, 2026-09-07)."""

    HEADER = [None, None, "حتى 10 يناير - 2023", None, "حتى 01 مارس - 2023", None]
    SUB = [None, None, "رقم المستخلص", "اجمالي الأعمال", "رقم المستخلص", "اجمالي الأعمال"]

    def _sheet(self, body):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(self.HEADER)
        ws.append(self.SUB)
        for row in body:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_the_sheets_own_total_is_used_not_the_sum_of_both(self):
        from .finance_imports import parse_invoice_extracts

        rows, _ = parse_invoice_extracts(self._sheet([
            ["Zone", "Item A", "م-1", 40.0, "م-2", 100.0],
            ["Zone", "Item B", None, 60.0, None, 150.0],
            [None, "الاجمالي", None, 100.0, None, 250.0],
        ]))
        # 100 then 250 cumulative -> 100 and 150, NOT 200 and 500.
        self.assertEqual([r["value"] for r in rows], [100.0, 150.0])

    def test_a_tracker_with_no_total_row_still_sums_its_items(self):
        from .finance_imports import parse_invoice_extracts

        rows, _ = parse_invoice_extracts(self._sheet([
            ["Zone", "Item A", "م-1", 40.0, "م-2", 100.0],
            ["Zone", "Item B", None, 60.0, None, 150.0],
        ]))
        self.assertEqual([r["value"] for r in rows], [100.0, 150.0])

    def test_the_word_in_a_data_column_is_not_a_total_row(self):
        """It appears as a column label deep in the real sheet (col 69);
        matching there stopped the scan 20 rows early."""
        from .finance_imports import _is_total_row

        self.assertTrue(_is_total_row([None, "الاجمالي", None, 1.0]))
        self.assertFalse(_is_total_row(["Zone", "Item A", None, 1.0] + [None] * 60 + ["اجمالي"]))


class CurveLabelWordingTests(SimpleTestCase):
    """The row labels are the project team's own wording and vary per
    workbook. Two real files built from the same template disagree on three
    of the four rows, and needling on the first file's exact phrasing left
    the airport project importing its actual line alone — so its S-curve came
    out blank on 53 real months of progress (2026-09-08)."""

    MONTHS = [datetime.datetime(2022, 1, 1), datetime.datetime(2022, 2, 1)]

    # Verbatim from the two files.
    TEMPLATE_WORDING = ["Cummulative Early Budget  Expense  %", "Cummulative Late Budget  %",
                        "Cummulative Actual Cost  %", "Cumm Remaining  Cost%"]
    AIRPORT_WORDING = ["Cummulative Early Planned %", "Cummulative Late Panned %",
                       "Cummulative Actual  %", "Cummulative Remaining %"]

    def _sheet(self, wording):
        # The cost row of the same name sits directly above each percentage
        # row in both files; only the "%" tells them apart.
        rows = [["Spreadsheet Field", *self.MONTHS]]
        for label, value in zip(wording, (0.10, 0.08, 0.09, 0.50)):
            rows.append([label.replace(" %", " Cost").replace("%", " Cost"), 100, 200])
            rows.append([label, value, value * 2])
        return _workbook(rows)

    def test_both_real_wordings_yield_all_four_series(self):
        for name, wording in (("template", self.TEMPLATE_WORDING), ("airport", self.AIRPORT_WORDING)):
            with self.subTest(file=name):
                data = parse_progress_curve(self._sheet(wording))
                self.assertEqual(
                    sorted(data[datetime.date(2022, 1, 1)]),
                    ["actual", "early_planned", "late_planned", "remaining"])

    def test_the_percentage_row_is_taken_not_the_cost_row_above_it(self):
        data = parse_progress_curve(self._sheet(self.AIRPORT_WORDING))
        first = data[datetime.date(2022, 1, 1)]
        self.assertEqual(first["early_planned"], 10.0)     # 0.10 -> 10%, not 100
        self.assertEqual(first["remaining"], 50.0)

    def test_a_corrected_spelling_still_matches(self):
        """"Cummulative" is a typo both files share; matching the whole word
        would break the day someone fixes it."""
        data = parse_progress_curve(self._sheet(
            [w.replace("Cummulative", "Cumulative") for w in self.AIRPORT_WORDING]))
        self.assertEqual(len(data[datetime.date(2022, 1, 1)]), 4)


class ExtractBlockShapeTests(SimpleTestCase):
    """Two real trackers of the same template disagree about almost every part
    of an extract block, and the airport one imported no invoices at all until
    each difference was handled (2026-09-08)."""

    MONTHS = ["حتى 10 يناير - 2023", "حتى 01 مارس - 2023"]

    def _sheet(self, blocks, body, totals=()):
        """`blocks`: [(group heading, value sub-header)]. `body`/`totals`: rows
        of [label, *per-block values]."""
        rows = [[None, None], [None, None]]
        for heading, value_label in blocks:
            rows[0] += [heading, None]
            rows[1] += ["رقم المستخلص", value_label]
        for source in (body, totals):
            for label, *values in source:
                row = [None, label]
                for v in values:
                    row += ["مستخلص جاري (1)", v]
                rows.append(row)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "مقارنة مستخلصات"
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def _parse(self, upload):
        from .finance_imports import parse_invoice_extracts

        return parse_invoice_extracts(upload)

    def test_the_value_column_may_be_headed_total_of_the_extract(self):
        """One tracker heads its filled block "اجمالي المستخلص" where every
        other heads it "اجمالي الأعمال" — same column, different word."""
        rows, _ = self._parse(self._sheet(
            [(self.MONTHS[0], "اجمالي  المستخلص")],
            [["Item A", 40.0], ["Item B", 60.0]]))
        self.assertEqual([r["value"] for r in rows], [100.0])

    def test_a_block_headed_with_a_real_date_keeps_that_date(self):
        """Its heading is a date cell, not "حتى … - ….". Forward-filling from
        the block to its left dated it months early and named it wrongly."""
        rows, _ = self._parse(self._sheet(
            [(self.MONTHS[0], "اجمالي الأعمال"), (datetime.datetime(2026, 7, 8), "اجمالي المستخلص")],
            [["Item A", 40.0, 90.0]]))
        self.assertEqual([r["date"] for r in rows],
                         [datetime.date(2023, 1, 10), datetime.date(2026, 7, 8)])

    def test_a_qualified_total_line_is_still_a_total(self):
        """"الاجمالي غير شامل الضريبة" — requiring the bare word matched
        neither it nor the tax-inclusive line under it, so both were summed
        along with the items."""
        rows, _ = self._parse(self._sheet(
            [(self.MONTHS[0], "اجمالي الأعمال")],
            [["Item A", 40.0], ["Item B", 60.0]],
            [["الاجمالي غير شامل الضريبة", 100.0], ["الاجمالي شامل الضريبة", 114.0]]))
        self.assertEqual([r["value"] for r in rows], [100.0])   # works, not tax-inclusive

    def test_a_line_that_does_not_add_up_the_items_is_an_item(self):
        """A real work item headed "إجمالي الكميات المنفذة" sits among the
        rows. Treating it as a totals line dropped its value from the column."""
        rows, _ = self._parse(self._sheet(
            [(self.MONTHS[0], "اجمالي الأعمال")],
            [["Item A", 40.0], ["إجمالي الكميات المنفذة", 5.0], ["Item B", 60.0]],
            [["الاجمالي", 105.0]]))
        self.assertEqual([r["value"] for r in rows], [105.0])

    def test_a_total_over_an_empty_column_is_ignored(self):
        """One tracker carries a hardcoded 3,742,205,096 on the totals line of
        a column whose item cells are all empty — 5.7x that project's whole
        contract. Being the sheet's largest figure, it suppressed every
        genuine extract dated after it as "going backwards"."""
        rows, skipped = self._parse(self._sheet(
            [(self.MONTHS[0], "اجمالي الأعمال"), (self.MONTHS[1], "اجمالي الأعمال")],
            [["Item A", None, 40.0], ["Item B", None, 60.0]],
            [["الاجمالي", 3742205096.51, 100.0]]))
        self.assertEqual([r["value"] for r in rows], [0.0, 100.0])
        self.assertEqual(skipped, 0)

    def test_a_typo_in_one_heading_does_not_drop_the_extracts_after_it(self):
        """A tracker's latest column is headed "حتى 15 يناير - 2025" where it
        means 2026. Sorting on that date puts the largest figure in the sheet
        in the middle, and every genuine extract after it then looks like it
        went backwards — five real ones were dropped (2026-09-08). A
        cumulative series only ever grows, so the order that never goes
        backwards is the right one."""
        rows, skipped = self._parse(self._sheet(
            [("حتى 10 يناير - 2023", "اجمالي الأعمال"),
             ("حتى 01 مارس - 2023", "اجمالي الأعمال"),
             ("حتى 15 يناير - 2022", "اجمالي الأعمال")],   # the typo, physically last
            [["Item A", 40.0, 120.0, 240.0], ["Item B", 60.0, 180.0, 360.0]],
            [["الاجمالي", 100.0, 300.0, 600.0]]))
        self.assertEqual(skipped, 0)
        self.assertEqual([r["value"] for r in rows], [100.0, 200.0, 300.0])

    def test_dates_still_win_when_they_are_consistent(self):
        """A tracker that appends a column out of date order is the case the
        date sort exists for — diffing in sheet order there would compare two
        unrelated points in time."""
        rows, skipped = self._parse(self._sheet(
            [("حتى 01 مارس - 2023", "اجمالي الأعمال"),
             ("حتى 10 يناير - 2023", "اجمالي الأعمال")],   # appended late, dated early
            [["Item A", 300.0, 100.0]],
            [["الاجمالي", 300.0, 100.0]]))
        self.assertEqual(skipped, 0)
        self.assertEqual([(r["date"].month, r["value"]) for r in rows], [(1, 100.0), (3, 200.0)])
