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
    """Every String in the drawing, inside groups too (legends are grouped)."""
    out = []
    for el in getattr(drawing, "contents", []):
        if isinstance(el, String):
            out.append(el.text)
        else:
            out.extend(_texts(el))
    return out


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

    def test_project_duration_is_the_dashboards_working_days_pie(self):
        from reportlab.graphics.charts.piecharts import Pie

        ctx = {"duration": _dashboard_duration(PANEL_DURATION)}
        pie = _chart(resolve_chart("project_duration", "pie", self.cfg, ctx, {}, 131 * mm, 75 * mm), Pie)
        self.assertEqual(pie.labels, ["1,380", "1,313", "67"])

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

    def test_the_progress_pie_is_the_dashboards_three_wedges(self):
        """Planned, earned and the variance, each a wedge sized by its
        magnitude and labelled with its sign — the panel the planners read."""
        from reportlab.graphics.charts.piecharts import Pie

        ctx = {"overall": 59.55, "planned": 94.45}
        drawing = resolve_chart("breakdown", "donut", self.cfg, ctx, {}, 80 * mm, 75 * mm)
        pie = _chart(drawing, Pie)
        self.assertEqual([round(v, 2) for v in pie.data], [94.45, 59.55, 34.9])
        self.assertEqual(pie.labels, ["94.45%", "59.55%", "-34.90%"])
        planned = self.cfg["labels"].get("planned", "Planned")
        self.assertIn(planned, _texts(drawing))

    def test_the_boq_chart_states_percent_by_default_and_money_on_request(self):
        rows = [{"name": "Civil", "budget_share": 25.0, "financial_percent": 12.5,
                 "budget": 250.0, "earned": 125.0}]
        ctx = {"boq_financial_progress": rows, "project": {"currency": "EGP"}}
        percent = _chart(resolve_chart("boq_financial_progress", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(percent.data, [[25.0], [12.5]])
        money = _chart(resolve_chart("boq_financial_progress", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm,
                                     props={"value_mode": "money"}))
        self.assertEqual(money.data, [[250.0], [125.0]])

    def test_progress_by_phase_draws_planned_beside_actual(self):
        ctx = {"work_progress": [{"name": "Civil Works", "progress": 100.0, "planned": 100.0},
                                 {"name": "MEP Works", "progress": 50.14, "planned": 88.76}],
               "zones": [{"name": "Zone A", "progress": 10.0, "planned": 20.0}]}
        bars = _chart(resolve_chart("work_progress", "column", self.cfg, ctx, {}, 131 * mm, 75 * mm))
        self.assertEqual(bars.data, [[100.0, 88.76], [100.0, 50.14]])


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


class ChartStyleTests(SimpleTestCase):
    """A chart element's own colours, wording, text size and toggles reach
    the drawing (pdf_charts.chart_style_override / chart_options)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()

    def setUp(self):
        self.cfg = default_config()
        self.ctx = {"zones": [{"name": "Zone A", "progress": 40.0, "planned": 90.0},
                              {"name": "Zone B", "progress": 70.0, "planned": 95.0}]}

    def _bars(self, props=None):
        drawing = resolve_chart("zone_progress", "column", self.cfg, self.ctx, {}, 131 * mm, 75 * mm, props=props)
        return drawing, _chart(drawing)

    def test_series_colours_and_wording_are_the_elements_own(self):
        _, plain = self._bars()
        drawing, bars = self._bars({"color_a": "#112233", "color_b": "#445566",
                                    "text_labels": {"planned": "Baseline"}})
        self.assertEqual(plain.bars[0].fillColor.hexval(), "0x4f81bd")
        self.assertEqual((bars.bars[0].fillColor.hexval(), bars.bars[1].fillColor.hexval()), ("0x112233", "0x445566"))
        self.assertIn("Baseline", _texts(drawing))
        self.assertNotIn(self.cfg["labels"]["planned"], _texts(drawing))

    def test_text_size_scales_every_font_in_the_chart(self):
        _, plain = self._bars()
        _, bigger = self._bars({"font_size": 10.5})
        self.assertAlmostEqual(bigger.categoryAxis.labels.fontSize, plain.categoryAxis.labels.fontSize * 1.5)
        self.assertAlmostEqual(bigger.valueAxis.labels.fontSize, plain.valueAxis.labels.fontSize * 1.5)

    def test_legend_and_values_can_be_turned_off(self):
        drawing, bars = self._bars({"legend": False, "show_values": False})
        self.assertEqual(_texts(drawing), [])
        self.assertIsNone(bars.barLabelFormat)

    def test_untouched_props_leave_the_report_config_alone(self):
        from .pdf_charts import chart_style_override

        self.assertIs(chart_style_override(self.cfg, {"source": "scurve", "legend": True}), self.cfg)
        patched = chart_style_override(self.cfg, {"color_3": "#abcdef"})
        self.assertEqual(patched["colors"]["chart_palette"][2], "#abcdef")
        self.assertEqual(self.cfg["colors"]["chart_palette"][2], "#9BBB59")


class CanvasChartSizeTests(SimpleTestCase):
    """The Customize canvas asks for a chart at the size the PDF draws it:
    the box minus the title and caption strips."""

    def test_the_canvas_and_the_pdf_take_the_same_strips_off_a_box(self):
        from .pdf_canvas import _CAPTION_H, _TITLE_H, chart_box_content

        cfg = default_config()
        h = 75 * mm
        both, caption_h, title_h = chart_box_content({"source": "scurve", "show_caption": True}, cfg, h)
        self.assertEqual((both, caption_h, title_h), (h - _CAPTION_H - _TITLE_H, _CAPTION_H, _TITLE_H))
        bare, _, _ = chart_box_content({"source": "scurve", "show_title": False}, cfg, h)
        self.assertEqual(bare, h)


_wording = importlib.import_module("apps.reports.migrations.0011_wording_on_saved_reports")
_split = importlib.import_module("apps.reports.migrations.0012_summary_over_two_pages")
_duration = importlib.import_module("apps.reports.migrations.0013_dashboard_duration_charts")


def _progress_page(orientation=None, zone_w=87):
    def chart(source, x, y, w, h):
        return {"id": source, "type": "chart", "x": x, "y": y, "w": w, "h": h,
                "props": {"source": source, "chart_type": "column", "show_caption": True}}
    page = {"id": "p", "name": "تقدم المشروع", "elements": [
        chart("spi", 16, 62, 87, 65), chart("duration", 107, 62, 87, 65),
        chart("zone_progress", 16, 152, zone_w, 115),
    ]}
    if orientation:
        page["orientation"] = orientation
    return page


class DurationChartsMigrationTests(SimpleTestCase):
    def test_places_both_charts_in_the_free_half_beside_the_zone_bars(self):
        layout = {"pages": [_progress_page()]}
        self.assertTrue(_duration._rearrange(layout, "portrait"))
        charts = {(el["props"]["source"]): el for el in layout["pages"][0]["elements"]}
        self.assertEqual(set(charts), {"spi", "duration", "zone_progress", "time_performance", "project_duration"})
        top, bottom = charts["time_performance"], charts["project_duration"]
        self.assertEqual((top["x"], top["w"], top["y"]), (107, 87, 152))
        self.assertEqual(bottom["y"], top["y"] + top["h"] + 4)
        self.assertAlmostEqual(bottom["y"] + bottom["h"], 152 + 115)
        self.assertTrue(top["props"]["show_caption"])      # as the page's other charts

    def test_a_page_with_no_room_beside_the_bars_is_left_alone(self):
        layout = {"pages": [_progress_page(zone_w=178)]}
        self.assertFalse(_duration._rearrange(layout, "portrait"))
        self.assertEqual(len(layout["pages"][0]["elements"]), 3)

    def test_running_twice_adds_nothing(self):
        layout = {"pages": [_progress_page()]}
        _duration._rearrange(layout, "portrait")
        self.assertFalse(_duration._rearrange(layout, "portrait"))
        self.assertEqual(len(layout["pages"][0]["elements"]), 5)


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
