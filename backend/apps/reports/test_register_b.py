"""Register section B: report content (planner review, 2026-09-14).

  B1  the progress-by-area chart comes off the area page
  B2  that page becomes the summary's third page; its charts keep their size
      and move up
  B3  the time-performance bars come off the progress page, and the zone
      chart takes the freed space without covering anything
  B5  an S-curve series the source never filled in is not drawn
"""
import importlib

from django.test import SimpleTestCase
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.lib.units import mm

from .constants import default_config
from .pdf_base import ensure_fonts
from .pdf_canvas import resolve_chart

_b = importlib.import_module("apps.reports.migrations.0015_register_b_report_content")


def _chart(source, x, y, w, h, **props):
    return {"id": source, "type": "chart", "x": x, "y": y, "w": w, "h": h,
            "props": {"source": source, "chart_type": "column", **props}}


def _area_page():
    return {"id": "p4", "name": "تقدم المشروع حسب المنطقة", "orientation": "landscape", "elements": [
        {"id": "h", "type": "text", "x": 16, "y": 20, "w": 265, "h": 12, "props": {"text": "تقدم المشروع حسب المنطقة"}},
        {"id": "l", "type": "line", "x": 112.9, "y": 31, "w": 71.2, "h": 1.2, "props": {}},
        _chart("area_progress", 16, 36, 265, 94),
        _chart("progress_comparison", 16, 134, 180, 56, show_caption=True),
        _chart("progress_tracking", 200, 134, 81, 56, show_caption=True),
    ]}


def _progress_page(beside_zone=None):
    elements = [
        {"id": "h", "type": "text", "x": 16, "y": 46, "w": 178, "h": 12, "props": {"text": "تقدم المشروع"}},
        _chart("spi", 16, 62, 87, 65),
        _chart("project_duration", 107, 62, 87, 65),
        _chart("zone_progress", 16, 152.1, 87, 114.9),
        _chart("time_performance", 107, 152.1, 87, 55.5),
    ]
    if beside_zone:
        elements.append(_chart(beside_zone, 107, 152.1, 87, 114.9))
    return {"id": "p7", "name": "تقدم المشروع", "elements": elements}


def _by_source(page):
    return {(el.get("props") or {}).get("source"): el for el in page["elements"] if el["type"] == "chart"}


class AreaPageFoldsIntoSummaryTests(SimpleTestCase):
    def test_area_chart_goes_and_the_page_becomes_the_third_summary_page(self):
        page = _area_page()
        self.assertTrue(_b._fold_area_page(page))
        self.assertEqual(page["name"], "الملخص (3)")
        self.assertEqual(page["elements"][0]["props"]["text"], "الملخص")
        charts = _by_source(page)
        self.assertNotIn("area_progress", charts)
        # Same size, moved up into the space the area chart held.
        self.assertEqual((charts["progress_comparison"]["x"], charts["progress_comparison"]["y"],
                          charts["progress_comparison"]["w"], charts["progress_comparison"]["h"]), (16, 36, 180, 56))
        self.assertEqual((charts["progress_tracking"]["x"], charts["progress_tracking"]["y"],
                          charts["progress_tracking"]["w"], charts["progress_tracking"]["h"]), (200, 36, 81, 56))

    def test_a_page_without_those_charts_is_left_alone(self):
        page = {"id": "p", "name": "تقدم المشروع حسب المنطقة", "elements": [_chart("area_progress", 16, 36, 265, 94)]}
        self.assertFalse(_b._fold_area_page(page))
        self.assertEqual(page["name"], "تقدم المشروع حسب المنطقة")


class ProgressPageSpaceTests(SimpleTestCase):
    def test_zone_chart_takes_the_freed_space_without_covering_anything(self):
        page = _progress_page()
        self.assertTrue(_b._drop_time_performance(page))
        charts = _by_source(page)
        self.assertNotIn("time_performance", charts)
        zone = charts["zone_progress"]
        # Just under the SPI gauge (62 + 65 + 4) and across to the pie's right
        # edge (107 + 87), keeping its own bottom edge.
        self.assertEqual((zone["x"], zone["y"], zone["w"]), (16, 131, 178))
        self.assertAlmostEqual(zone["y"] + zone["h"], 152.1 + 114.9)

    def test_it_does_not_widen_over_a_chart_beside_it(self):
        page = _progress_page(beside_zone="scurve")
        _b._drop_time_performance(page)
        zone = _by_source(page)["zone_progress"]
        self.assertEqual(zone["w"], 87)

    def test_running_twice_changes_nothing_more(self):
        page = _progress_page()
        _b._drop_time_performance(page)
        self.assertFalse(_b._drop_time_performance(page))


class EmptyCurveSeriesTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()

    def test_a_series_that_is_zero_every_month_is_not_drawn(self):
        import datetime

        points = [{"date": datetime.date(2025, m, 1), "planned": 10.0 * m, "late_planned": 0.0,
                   "actual": 8.0 * m, "forecast": None} for m in range(1, 7)]
        ctx = {"scurve": points, "scurve_source": "imported"}
        drawing = resolve_chart("scurve", "line", default_config(), ctx, {}, 131 * mm, 75 * mm)
        chart = next(el for el in drawing.contents if isinstance(el, HorizontalLineChart))
        self.assertEqual(len(chart.data), 2)          # early planned and actual only
