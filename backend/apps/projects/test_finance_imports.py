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
