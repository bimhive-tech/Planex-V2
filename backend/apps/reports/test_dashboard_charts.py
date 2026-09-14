"""Section F of the planners' register: the charts drawn from the dashboard
workbook (F3-F5), the progress pie's planned figure (F2), progress by phase
(F6) and the summary spread over two pages (F7)."""
import datetime
import importlib

from django.test import SimpleTestCase, TestCase
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import String
from reportlab.lib.units import mm

from apps.accounts.models import Company
from apps.projects.models import Project

from .constants import default_config
from .pdf_base import ensure_fonts
from .pdf_canvas import resolve_chart
from .services import _dashboard_boq_rows, _dashboard_duration


def _chart(drawing, kind=VerticalBarChart):
    return next(el for el in drawing.contents if isinstance(el, kind))


def _texts(drawing):
    return [el.text for el in drawing.contents if isinstance(el, String)]


PANEL_DURATION = {"project_days": 1380.0, "completed_days": 1313.0, "remaining_days": 67.0,
                  "elapsed_pct": 0.9514492753623188, "remaining_pct": 0.04855072463768116,
                  "delay_days": -47.0}


class DashboardContextTests(SimpleTestCase):
    def test_the_duration_block_takes_the_shape_the_report_draws(self):
        self.assertEqual(_dashboard_duration(PANEL_DURATION), {
            "total": 1380.0, "elapsed": 1313.0, "remaining": 67.0, "delay": -47.0,
            "elapsed_pct": 0.9514492753623188, "remaining_pct": 0.04855072463768116,
        })

    def test_no_project_duration_means_no_dashboard_duration(self):
        self.assertIsNone(_dashboard_duration({"completed_days": 5.0}))
        self.assertIsNone(_dashboard_duration(None))

    def test_boq_shares_become_money_against_the_contract_total(self):
        rows = _dashboard_boq_rows({"total": 1000.0, "rows": [
            {"category": "Civil", "budget_share": 0.25, "financial_percent": 0.125},
            {"category": "Blank", "budget_share": None, "financial_percent": None},
        ]})
        self.assertEqual(rows, [{"name": "Civil", "budget_share": 25.0, "financial_percent": 12.5,
                                 "budget": 250.0, "earned": 125.0}])

    def test_boq_without_a_total_keeps_only_the_shares(self):
        rows = _dashboard_boq_rows({"total": None, "rows": [
            {"category": "Civil", "budget_share": 0.25, "financial_percent": 0.125}]})
        self.assertNotIn("budget", rows[0])


class DashboardChartTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()          # the legends measure their text in the report font

    def setUp(self):
        self.cfg = default_config()

    def test_time_performance_plots_the_sheet_fractions(self):
        ctx = {"duration": _dashboard_duration(PANEL_DURATION)}
        bars = _chart(resolve_chart("time_performance", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(bars.data, [[95.14492753623188, 4.855072463768116]])
        self.assertEqual((bars.valueAxis.valueMin, bars.valueAxis.valueMax), (0, 100))

    def test_time_performance_derives_the_split_from_days_without_a_dashboard(self):
        ctx = {"duration": {"total": 200, "elapsed": 150, "remaining": 50, "delay": 0}}
        bars = _chart(resolve_chart("time_performance", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(bars.data, [[75.0, 25.0]])

    def test_time_performance_with_no_duration_draws_nothing(self):
        self.assertIsNone(resolve_chart("time_performance", "column", self.cfg, {}, {}, 131 * mm, 75 * mm))

    def test_project_duration_reaches_below_zero_for_an_early_finish(self):
        ctx = {"duration": _dashboard_duration(PANEL_DURATION)}
        bars = _chart(resolve_chart("project_duration", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(bars.data, [[1380.0, -47.0]])
        self.assertLess(bars.valueAxis.valueMin, -47)

    def test_submittal_counts_come_from_the_dashboard_grid(self):
        ctx = {"dashboard": {"submittals": {"shop_drawing": [
            {"discipline": "CIVIL", "submitted": 426, "approved": 424, "rejected": 2, "pending": 0},
            {"discipline": "MECHANICAL", "submitted": 82, "approved": 82, "rejected": 0, "pending": 0},
        ]}}, "submittals": []}
        drawing = resolve_chart("submittals_shop_drawing", "bar", self.cfg, ctx, {}, 131 * mm, 75 * mm)
        bars = _chart(drawing, HorizontalBarChart)
        # One row per discipline, one column per status: the SUBMITTED total
        # the sheet states, then approved/rejected/pending.
        self.assertEqual(bars.data, [[426, 424, 2, 0], [82, 82, 0, 0]])

    def test_the_progress_pie_states_its_planned_figure(self):
        ctx = {"overall": 59.55, "planned": 94.46}
        drawing = resolve_chart("breakdown", "donut", self.cfg, ctx, {}, 80 * mm, 75 * mm)
        planned = self.cfg["labels"].get("planned", "Planned")
        self.assertIn(f"{planned} 94.46%", _texts(drawing))

    def test_progress_by_phase_draws_planned_beside_actual(self):
        ctx = {"work_progress": [{"name": "Civil Works", "progress": 100.0, "planned": 100.0},
                                 {"name": "MEP Works", "progress": 50.14, "planned": 88.76}],
               "zones": [{"name": "Zone A", "progress": 10.0, "planned": 20.0}]}
        bars = _chart(resolve_chart("work_progress", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(bars.data, [[100.0, 88.8], [100.0, 50.1]])


class WorkRowsTests(TestCase):
    """F6: progress per trade, grouped by the top WORK level over each
    activity whatever place levels sit above it."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)

        def scope(kind, name, parent=None, order=0):
            return ProjectScope.objects.create(company=self.company, project=self.project,
                                               scope_type=kind, name=name, parent=parent, sort_order=order)

        def activity(parent, weight, progress):
            Activity.objects.create(company=self.company, project=self.project, scope=parent,
                                    name="Task", weight=weight, progress_percent=progress)

        for z, zone_name in enumerate(("Zone A", "Zone B")):
            zone = scope("zone", zone_name, order=z)
            civil = scope("discipline", "Civil Works", zone, order=1)
            activity(scope("sub_discipline", "Concrete", civil), 1, 100)
            activity(scope("discipline", "MEP Works", zone, order=2), 3, 40 if z == 0 else 20)

    def test_groups_merge_by_name_across_the_tree(self):
        from .services import _work_rows

        rows = _work_rows(self.project)
        self.assertEqual([r["name"] for r in rows], ["Civil Works", "MEP Works"])
        self.assertEqual(rows[0]["progress"], 100.0)
        self.assertEqual(rows[1]["progress"], 30.0)

    def test_live_progress_overrides_the_stored_figure(self):
        from apps.projects.models import Activity

        from .services import _work_rows

        mep = Activity.objects.filter(project=self.project, weight=3)
        progress = {str(a.id): 80.0 for a in mep}
        self.assertEqual(_work_rows(self.project, progress=progress)[1]["progress"], 80.0)


_wording = importlib.import_module("apps.reports.migrations.0011_wording_on_saved_reports")
_split = importlib.import_module("apps.reports.migrations.0012_summary_over_two_pages")


def _summary_layout():
    def chart(source):
        return {"id": source, "type": "chart", "x": 0, "y": 0, "w": 52, "h": 50,
                "props": {"source": source, "chart_type": "column"}}
    return {"pages": [
        {"id": "cover", "name": "الغلاف", "elements": []},
        {"id": "s", "name": "الملخص", "orientation": "landscape", "elements": [
            {"id": "h", "type": "text", "props": {"text": "الملخص"}},
            {"id": "info", "type": "table", "props": {"source": "project_info"}},
            chart("spi"), chart("breakdown"), chart("scurve"), chart("cashflow_monthly"),
            chart("submittals_material"), chart("submittals_shop_drawing"), chart("zone_progress"),
        ]},
    ]}


class SummarySplitMigrationTests(SimpleTestCase):
    def test_splits_the_summary_into_two_readable_pages(self):
        layout = _summary_layout()
        self.assertTrue(_split._rearrange(layout))
        first, second = layout["pages"][1], layout["pages"][2]
        self.assertEqual(second["name"], "الملخص (2)")
        self.assertEqual(second["orientation"], "landscape")
        self.assertEqual(sorted(el["props"].get("source") for el in first["elements"] if el["type"] != "text"),
                         ["breakdown", "project_info", "spi", "submittals_material", "submittals_shop_drawing"])
        charts = {el["props"]["source"]: el for el in second["elements"] if el["type"] == "chart"}
        self.assertEqual(sorted(charts), ["cashflow_monthly", "scurve", "work_progress", "zone_progress"])
        self.assertEqual({el["w"] for el in charts.values()}, {131})
        self.assertEqual(charts["scurve"]["id"], "scurve")          # moved, not recreated
        self.assertTrue(any(el["type"] == "text" for el in second["elements"]))

    def test_running_twice_does_not_split_again(self):
        layout = _summary_layout()
        _split._rearrange(layout)
        self.assertFalse(_split._rearrange(layout))
        self.assertEqual(len(layout["pages"]), 3)

    def test_a_rebuilt_summary_is_left_alone(self):
        layout = {"pages": [{"id": "s", "name": "الملخص", "elements": [
            {"id": "c", "type": "chart", "props": {"source": "scurve"}}]}]}
        self.assertFalse(_split._rearrange(layout))


class SavedReportMigrationTests(TestCase):
    """A report keeps its layout under "layout" in layout_override — the level
    0009 missed, which left every customised report on the old wording."""

    def setUp(self):
        from .models import Report

        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower",
                                         project_type=Project.ProjectType.COMMERCIAL)
        layout = _summary_layout()
        layout["pages"][1]["name"] = "الملخص التنفيذي"
        layout["pages"].append({"id": "sheet", "name": "ورقة متابعة الإنجاز", "elements": []})
        self.report = Report.objects.create(
            company=company, project=project, title="July",
            period_start=datetime.date(2026, 7, 1), period_finish=datetime.date(2026, 7, 31),
            layout_override={"layout": layout, "page_design": {}})

    def test_wording_then_split_reach_a_saved_report(self):
        from django.apps import apps

        _wording.forwards(apps, None)
        _split.forwards(apps, None)
        self.report.refresh_from_db()
        names = [p["name"] for p in self.report.layout_override["layout"]["pages"]]
        self.assertEqual(names, ["الغلاف", "الملخص", "الملخص (2)"])
