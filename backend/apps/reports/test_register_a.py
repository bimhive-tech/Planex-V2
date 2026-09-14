"""Register section A: every figure in the report is the one its source states.

The rules these pin down (planner decisions, 2026-09-14):

  A1  where P6 states a figure, P6's figure is printed; financial progress is
      the dashboard's invoiced share; nothing borrows another period's value
  A2  percentages to two decimals, amounts in full, nothing rounded on the way
  A3  each zone's planned % is its own, from P6's Schedule % Complete
  A4  the critical path table prints P6's Start, Finish and Total Float only
  A6  one duration chart: the dashboard's "DURATION (Working Days)" pie
  A7  the BOQ chart's percentage axis runs 0-100%
"""
import datetime
import importlib
import io
from decimal import Decimal

import openpyxl
from django.test import SimpleTestCase, TestCase
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.units import mm

from apps.accounts.models import Company
from apps.projects.models import Activity, Project, ProjectScope

from .constants import default_config
from .pdf_base import ensure_fonts, format_money, format_quantity
from .pdf_canvas import resolve_chart, resolve_table


def _chart(drawing, kind=VerticalBarChart):
    return next(el for el in drawing.contents if isinstance(el, kind))


# ---------------------------------------------------------------- dashboard

def _dashboard_rows():
    """The airport dashboard's Progress Comparison and Project Tracking
    blocks, cell for cell, with the part-level repeat of both beneath."""
    cells = {
        (13, 30): "Progress Comparison - contract",
        (14, 31): "% Progress previous month", (14, 32): "% Progress Current  month",
        (16, 30): "% Planned ", (16, 31): 0.5938, (16, 32): 0.9445,
        (20, 21): "Planned (C.D 30/07/2026)", (20, 22): 0.9445,
        (20, 30): "% Actual", (20, 31): 0.5938, (20, 32): 0.5955,
        (21, 21): "Actual Invo. (C.D 08/07/2026)", (21, 22): 0.5127864032083451,
        (22, 21): "Earned Value (C.D 30/07/2026)", (22, 22): 0.5955,
        # The part's own block further down: never the one read.
        (33, 21): "Planned (C.D 29/06)", (33, 22): 1,
        (34, 21): "Actual Invo. (C.D 26/10/2025)", (34, 22): "#DIV/0!",
        (34, 31): "% Progress previous month", (34, 32): "% Progress Current  month",
        (36, 30): "% Planned ", (36, 31): 0.1, (36, 32): 0.2,
    }
    height = max(r for r, _ in cells) + 1
    width = max(c for _, c in cells) + 1
    rows = [[None] * width for _ in range(height)]
    for (r, c), value in cells.items():
        rows[r][c] = value
    return rows


class DashboardProgressPanelTests(SimpleTestCase):
    def test_progress_comparison_reads_each_figure_with_its_own_date(self):
        from apps.projects.dashboard_panels import parse_progress

        self.assertEqual(parse_progress(_dashboard_rows()), {
            "planned": {"value": 0.9445, "date": "2026-07-30"},
            "invoiced": {"value": 0.5127864032083451, "date": "2026-07-08"},
            "earned": {"value": 0.5955, "date": "2026-07-30"},
        })

    def test_project_tracking_reads_the_contract_block_only(self):
        from apps.projects.dashboard_panels import parse_tracking

        self.assertEqual(parse_tracking(_dashboard_rows()), {
            "previous": {"planned": 0.5938, "actual": 0.5938},
            "current": {"planned": 0.9445, "actual": 0.5955},
        })


class FinancialProgressAndTrackingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(company=self.company, name="Tower", project_type="commercial")

    def test_financial_progress_is_the_dashboards_invoiced_share(self):
        from .services import _financial_progress

        panel = {"invoiced": {"value": 0.5127864032083451, "date": "2026-07-08"}}
        value, source = _financial_progress(self.project, panel)
        self.assertAlmostEqual(value, 51.27864032083451)
        self.assertEqual(source, {"source": "dashboard", "date": "2026-07-08"})

    def test_without_a_dashboard_it_is_p6_earned_value_and_says_so(self):
        from .services import _financial_progress

        scope = ProjectScope.objects.create(company=self.company, project=self.project, scope_type="zone", name="Z")
        Activity.objects.create(company=self.company, project=self.project, scope=scope, name="T",
                                budgeted_cost=Decimal("1000"), earned_value_cost=Decimal("250"))
        value, source = _financial_progress(self.project, {})
        self.assertEqual((value, source), (25.0, {"source": "p6", "date": None}))

    def test_previous_month_is_never_the_current_months_figure(self):
        from .services import _monthly_tracking

        tracking = _monthly_tracking(94.45, 59.55, None, {})
        self.assertEqual(tracking["previous"], {"planned": None, "actual": None})
        self.assertEqual(tracking["current"], {"planned": 94.45, "actual": 59.55})

    def test_previous_month_comes_from_a_snapshot_then_the_dashboard(self):
        from .services import _monthly_tracking

        panel = {"previous": {"planned": 0.5938, "actual": 0.5938}, "current": {"planned": 0.9, "actual": 0.5}}
        from_dashboard = _monthly_tracking(94.45, 59.55, None, panel)
        self.assertAlmostEqual(from_dashboard["previous"]["planned"], 59.38)
        # P6's own figures stay the current month's.
        self.assertEqual(from_dashboard["current"], {"planned": 94.45, "actual": 59.55})
        snap = {"planned_progress": Decimal("80.10"), "overall_progress": Decimal("55.20")}
        self.assertEqual(_monthly_tracking(94.45, 59.55, snap, panel)["previous"],
                         {"planned": 80.1, "actual": 55.2})


class StatedProjectProgressTests(TestCase):
    """P6's own project-row figures win over Planex's reconstruction of them."""

    def setUp(self):
        from apps.projects.models import ScheduleImport

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(company=self.company, name="Tower", project_type="commercial")
        self.batch = ScheduleImport.objects.create(company=self.company, project=self.project,
                                                   date=datetime.date(2026, 9, 8), source="p6.xlsx")
        scope = ProjectScope.objects.create(company=self.company, project=self.project, scope_type="zone",
                                            name="Z", schedule_import=self.batch)
        # Costs that reconstruct to 59.5489 actual and 94.455 planned.
        Activity.objects.create(company=self.company, project=self.project, scope=scope, name="T",
                                schedule_import=self.batch, weight=Decimal("656013770.42"),
                                budgeted_cost=Decimal("656013770.42"), earned_value_cost=Decimal("390648818.33"),
                                schedule_percent=Decimal("94.46"))

    def test_the_stated_figures_are_the_ones_used(self):
        from apps.projects.services import project_overall_progress

        from .services import _planned_progress

        self.project.imported_progress_percent = Decimal("59.55")
        self.project.imported_planned_progress_percent = Decimal("94.45")
        self.project.save()
        self.assertEqual(project_overall_progress(self.project), 59.55)
        self.assertEqual(_planned_progress(self.project, datetime.date(2026, 7, 30), current=True,
                                           schedule_import=self.batch), 94.45)

    def test_without_a_stated_figure_the_costs_answer(self):
        from apps.projects.services import project_overall_progress

        self.assertAlmostEqual(project_overall_progress(self.project), 59.5489, places=4)

    def test_the_planex_code_import_keeps_the_title_rows_figures(self):
        from apps.projects.imports import import_workbook

        d = datetime.date
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Planex Code", "Activity ID", "Activity Name", "Start", "Finish", "Activity % Complete",
                   "Performance % Complete", "Schedule % Complete", "Budgeted Total Cost", "Earned Value Cost"])
        ws.append([None, "Airport - Revised - July 2026", None, d(2022, 3, 29), d(2026, 12, 9),
                   None, 0.5955, 0.9445, 656013770.42, 390648818.33])
        ws.append(["MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1", "A1", "Seal",
                   d(2026, 1, 1), d(2026, 1, 10), 0.5, 0.5, 1, 1000, 500])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        project = Project.objects.create(company=self.company, name="Coded", project_type="commercial")
        import_workbook(project, buf, source="coded.xlsx")
        project.refresh_from_db()
        self.assertEqual((project.imported_progress_percent, project.imported_planned_progress_percent),
                         (Decimal("59.55"), Decimal("94.45")))


# ---------------------------------------------------------------- zones

class ZonePlannedTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(company=self.company, name="Tower", project_type="commercial")

        def zone(name):
            return ProjectScope.objects.create(company=self.company, project=self.project,
                                               scope_type="zone", name=name)

        costed, uncosted = zone("Level 2"), zone("Walk way")
        Activity.objects.create(company=self.company, project=self.project, scope=costed, name="A",
                                weight=Decimal("300"), budgeted_cost=Decimal("300"),
                                earned_value_cost=Decimal("150"), schedule_percent=Decimal("62.25"))
        # No budget at all, but P6 still states its Schedule % Complete.
        Activity.objects.create(company=self.company, project=self.project, scope=uncosted, name="B",
                                weight=1, progress_percent=100, schedule_percent=Decimal("100"))
        self.costed, self.uncosted = costed, uncosted

    def test_each_zone_has_its_own_planned_figure(self):
        from apps.projects.services import scope_planned_map

        planned = scope_planned_map(self.project)
        self.assertAlmostEqual(planned[str(self.costed.id)], 62.25)
        self.assertEqual(planned[str(self.uncosted.id)], 100.0)

    def test_a_zone_the_schedule_gives_no_planned_figure_stays_on_the_table(self):
        cfg = default_config()
        ctx = {"zones": [{"name": "Level 2", "planned": 62.25, "previous": None, "progress": 45.45},
                         {"name": "Walk way", "planned": None, "previous": None, "progress": 100.0}]}
        table = resolve_table("progress_compare", cfg, ctx, {}, avail_width=180 * mm, raw=True)
        self.assertEqual([r[:2] for r in table["rows"]], [["Level 2", "62.25%"], ["Walk way", "—"]])


class CriticalPathTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(company=self.company, name="Tower", project_type="commercial")
        self.zone = ProjectScope.objects.create(company=self.company, project=self.project,
                                                scope_type="zone", name="Part 2 - Level 2A")
        d = datetime.date
        for start, finish, total_float in ((d(2023, 12, 5), d(2026, 3, 1), 12),
                                           (d(2024, 1, 1), d(2026, 11, 8), -47)):
            Activity.objects.create(company=self.company, project=self.project, scope=self.zone, name="T",
                                    planned_start=start, planned_finish=finish, total_float=total_float)

    def test_rows_are_p6_start_finish_and_controlling_float(self):
        from .services import _critical_path_rows

        rows = _critical_path_rows(self.project, [{"id": str(self.zone.id), "name": self.zone.name}])
        self.assertEqual(rows, [{"name": "Part 2 - Level 2A", "start": datetime.date(2023, 12, 5),
                                 "finish": datetime.date(2026, 11, 8), "total_float": -47}])

    def test_the_table_prints_those_three_and_nothing_estimated(self):
        cfg = default_config()
        ctx = {"critical_path": [{"name": "Part 2 - Level 2A", "start": datetime.date(2023, 12, 5),
                                  "finish": datetime.date(2026, 11, 8), "total_float": -47}]}
        table = resolve_table("critical_path_delays", cfg, ctx, {}, avail_width=180 * mm, raw=True)
        labels = cfg["labels"]
        self.assertEqual(table["header"], [labels["col_zone"], labels["col_start"], labels["col_finish"],
                                           labels["col_total_float"]])
        self.assertEqual(table["rows"], [["Part 2 - Level 2A", "05 Dec 2023", "08 Nov 2026", "-47"]])


# ---------------------------------------------------------------- charts

class ChartPrecisionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()

    def setUp(self):
        self.cfg = default_config()

    def test_bars_carry_the_unrounded_figures_and_print_two_decimals(self):
        from .pdf_charts import _pct_label

        ctx = {"planned": 94.45, "overall": 59.55, "financial_percent_complete": 51.27864032083451,
               "financial_percent_source": {"source": "dashboard", "date": "2026-07-08"}}
        bars = _chart(resolve_chart("progress_comparison", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(bars.data, [[94.45, 59.55, 51.27864032083451]])
        self.assertEqual(_pct_label(51.27864032083451), "51.28%")
        name = bars.categoryAxis.categoryNames[2]
        self.assertIn("08/07/2026", name)

    def test_a_period_no_source_states_draws_no_bar(self):
        ctx = {"monthly_tracking": {"previous": {"planned": None, "actual": None},
                                    "current": {"planned": 94.45, "actual": 59.55}}}
        bars = _chart(resolve_chart("progress_tracking", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(bars.data, [[94.45], [59.55]])

    def test_boq_percentages_sit_on_a_full_axis(self):
        ctx = {"boq_financial_progress": [{"name": "Civil", "budget_share": 4.91, "financial_percent": 28.93,
                                           "budget": 1.0, "earned": 2.0}]}
        bars = _chart(resolve_chart("boq_financial_progress", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual((bars.valueAxis.valueMin, bars.valueAxis.valueMax), (0, 100))

    def test_amounts_are_printed_in_full(self):
        from .pdf_axes import number_format

        self.assertEqual(format_money(685661117.68, "EGP"), "685,661,117.68 EGP")
        self.assertEqual(format_quantity(Decimal("3424.31")), "3,424.31")
        self.assertEqual(format_quantity(1380), "1,380")
        self.assertEqual(number_format(2_750_000_000, 250_000_000, 20 * mm, 6)(2_750_000_000), "2,750,000,000")

    def test_duration_is_the_dashboards_working_days_pie(self):
        ctx = {"duration": {"total": 1380, "elapsed": 1313, "remaining": 67, "delay": -47}}
        pie = _chart(resolve_chart("project_duration", "pie", self.cfg, ctx, {}, 87 * mm, 65 * mm), Pie)
        self.assertEqual([round(v) for v in pie.data], [1380, 1313, 67])
        self.assertEqual(pie.labels, ["1,380", "1,313", "67"])


# ---------------------------------------------------------------- layouts

_merge = importlib.import_module("apps.reports.migrations.0014_duration_pie_replaces_two_charts")


class DurationPieMigrationTests(SimpleTestCase):
    def _page(self):
        return {"pages": [{"id": "p", "name": "تقدم المشروع", "elements": [
            {"id": "old", "type": "chart", "x": 107, "y": 62, "w": 87, "h": 65, "z": 1,
             "props": {"source": "duration", "chart_type": "pie"}},
            {"id": "new", "type": "chart", "x": 107, "y": 211, "w": 87, "h": 55, "z": 0,
             "props": {"source": "project_duration", "chart_type": "column", "show_caption": True}},
        ]}]}

    def test_the_pie_takes_the_removed_charts_place(self):
        layout = self._page()
        self.assertTrue(_merge._rearrange(layout))
        (only,) = layout["pages"][0]["elements"]
        self.assertEqual((only["id"], only["x"], only["y"], only["w"], only["h"]), ("new", 107, 62, 87, 65))
        self.assertEqual(only["props"], {"source": "project_duration", "chart_type": "pie", "show_caption": True})

    def test_a_page_with_only_one_of_them_is_left_alone(self):
        layout = self._page()
        layout["pages"][0]["elements"].pop(0)
        self.assertFalse(_merge._rearrange(layout))
