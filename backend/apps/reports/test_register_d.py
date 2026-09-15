"""Register section D: chart look and editing.

  D1  charts keep their own text inside their box and their bars get the room
      — the submittal panels and the pies, at the sizes they are placed at
  D2  a chart element sets its value axis, bar and line sizing, legend
      position, decimals and gauge bands, and names its palette colours
  D3  the canvas can redraw only the charts an edit touched, and knows the
      size each drawing was made for
"""
from django.test import SimpleTestCase, TestCase
from reportlab.graphics.charts.barcharts import BarChart, HorizontalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.units import mm
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, SeededRole
from apps.accounts.models import Company, Membership, Role, User
from apps.projects.models import Project

from .constants import default_config
from .pdf_base import ensure_fonts
from .pdf_canvas import chart_series_names, resolve_chart
from .pdf_charts import _LegendGroup, chart_style_override

# The Cairo dashboard's shop-drawing grid.
SHOP_DRAWINGS = [
    {"discipline": "CIVIL", "submitted": 426, "approved": 424, "rejected": 2, "pending": 0},
    {"discipline": "MECHANICAL", "submitted": 82, "approved": 82, "rejected": 0, "pending": 0},
    {"discipline": "ELECTRICAL", "submitted": 100, "approved": 100, "rejected": 0, "pending": 0},
]


def _bars(drawing):
    return next(c for c in drawing.contents if isinstance(c, HorizontalBarChart))


class ChartsFitTheirBoxTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()

    def setUp(self):
        self.cfg = default_config()

    def _submittals(self, grid, w, h):
        ctx = {"dashboard": {"submittals": {"shop_drawing": grid}}, "submittals": []}
        return resolve_chart("submittals_shop_drawing", "bar", self.cfg, ctx, {}, w * mm, h * mm)

    def test_the_submittal_axis_numbers_have_room_under_the_bars(self):
        drawing = self._submittals(SHOP_DRAWINGS, 80, 75)
        bars = _bars(drawing)
        # The count labels print a line under the axis; the plot starts above
        # them rather than leaving them outside the drawing.
        self.assertGreaterEqual(bars.y, bars.valueAxis.labels.fontSize + 6)

    def test_the_bars_keep_most_of_a_summary_panel(self):
        drawing = self._submittals(SHOP_DRAWINGS, 80, 75)
        bars = _bars(drawing)
        plot_w = drawing.width - bars.x - 8
        self.assertGreaterEqual(bars.width, 0.7 * plot_w)

    def test_long_discipline_names_put_the_legend_under_the_bars(self):
        grid = [dict(line, discipline=f"{line['discipline']} AND FINISHING WORKS") for line in SHOP_DRAWINGS]
        drawing = self._submittals(grid, 80, 75)
        bars = _bars(drawing)
        self.assertAlmostEqual(bars.width, drawing.width - bars.x - 8)
        # The legend rows sit below the axis labels, inside the drawing.
        self.assertGreater(bars.y, bars.valueAxis.labels.fontSize + 6)
        x0, y0, x1, _ = drawing.getBounds()
        self.assertGreaterEqual(y0, 0)
        self.assertLessEqual(x1, drawing.width + 1)

    def test_pie_value_labels_stay_inside_the_drawing(self):
        ctx = {"duration": {"total": 1380, "elapsed": 1313, "remaining": 67, "delay": 0}}
        for w, h in [(87, 65), (131, 75), (60, 100), (180, 56)]:
            drawing = resolve_chart("project_duration", "pie", self.cfg, ctx, {}, w * mm, h * mm)
            x0, y0, x1, y1 = drawing.getBounds()
            with self.subTest(size=(w, h)):
                self.assertGreaterEqual(y0, 0)
                self.assertLessEqual(y1, drawing.height)
                self.assertLessEqual(x1, drawing.width)


ZONES = [{"id": "a", "name": "A", "progress": 40.0, "planned": 60.0},
         {"id": "b", "name": "B", "progress": 70.0, "planned": 75.0}]


def _find(group, kind):
    for child in getattr(group, "contents", []):
        if isinstance(child, kind):
            return child
        found = _find(child, kind)
        if found is not None:
            return found
    return None


class ChartControlsTests(SimpleTestCase):
    """D2: every control is read where the chart is built, so the PDF and the
    canvas draw it the same way."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()

    def setUp(self):
        self.cfg = default_config()

    def _zones(self, **props):
        drawing = resolve_chart("zone_progress", "column", self.cfg, {"zones": ZONES}, {},
                                131 * mm, 75 * mm, props=props)
        return drawing, _find(drawing, BarChart)

    def test_the_value_axis_takes_the_elements_range_and_step(self):
        _, bars = self._zones(axis_min=0, axis_max=80, axis_step=20)
        axis = bars.valueAxis
        self.assertEqual((axis.valueMin, axis.valueMax, axis.valueStep), (0, 80, 20))

    def test_an_unusable_axis_choice_leaves_the_chart_as_designed(self):
        _, default = self._zones()
        _, bars = self._zones(axis_min=90, axis_max=10, axis_step=0.001)
        self.assertEqual((bars.valueAxis.valueMin, bars.valueAxis.valueMax, bars.valueAxis.valueStep),
                         (default.valueAxis.valueMin, default.valueAxis.valueMax,
                          default.valueAxis.valueStep))

    def test_a_smaller_bar_gap_draws_thicker_bars(self):
        _, default = self._zones()
        _, thick = self._zones(bar_gap=20)
        self.assertLess(thick.groupSpacing, default.groupSpacing)

    def test_decimals_apply_to_the_printed_values(self):
        _, bars = self._zones(decimals=0)
        formats = bars.barLabelFormat if isinstance(bars.barLabelFormat, list) else [bars.barLabelFormat]
        printed = [f(60.456) for f in formats if callable(f)]
        self.assertTrue(printed)
        self.assertTrue(all(text == "60%" for text in printed))

    def test_the_legend_moves_to_the_top_of_a_pie(self):
        ctx = {"duration": {"total": 1380, "elapsed": 1313, "remaining": 67, "delay": 0}}
        drawing = resolve_chart("project_duration", "pie", self.cfg, ctx, {}, 87 * mm, 65 * mm,
                                props={"legend_position": "top"})
        legend = _find(drawing, _LegendGroup)
        pie = _find(drawing, Pie)
        legend_group = next(g for g in drawing.contents if _find(g, _LegendGroup) is not None
                            or isinstance(g, _LegendGroup))
        pie_group = next(g for g in drawing.contents if g is not legend_group)
        self.assertIsNotNone(legend)
        self.assertIsNotNone(pie)
        self.assertGreaterEqual(legend_group.getBounds()[1], pie_group.getBounds()[3] - 1)

    def test_gauge_bands_come_from_the_element_and_must_rise(self):
        cfg = chart_style_override(self.cfg, {"gauge_low": 0.5, "gauge_mid": 0.7, "gauge_high": 0.95,
                                              "gauge_max": 2, "color_gauge_bad": "#000000"})
        self.assertEqual(cfg["spi_thresholds"], {"low": 0.5, "mid": 0.7, "high": 0.95})
        self.assertEqual(cfg["spi_max"], 2)
        self.assertEqual(cfg["colors"]["gauge_bad"], "#000000")
        # Out of order: the report's own bands stay.
        kept = chart_style_override(self.cfg, {"gauge_low": 0.9, "gauge_mid": 0.2})
        self.assertEqual(kept["spi_thresholds"], self.cfg["spi_thresholds"])
        # The report's config itself is never touched.
        self.assertNotEqual(self.cfg["spi_thresholds"].get("low"), 0.5)

    def test_submittal_palette_colours_are_named_by_discipline(self):
        ctx = {"dashboard": {"submittals": {"material": [{"discipline": "CIVIL"}, {"discipline": "MEP"}]}}}
        self.assertEqual(chart_series_names("submittals_material", self.cfg, ctx), ["CIVIL", "MEP"])
        self.assertIsNone(chart_series_names("zone_progress", self.cfg, ctx))


class ChartRedrawTests(TestCase):
    """D3: the canvas asks for just the charts an edit touched."""

    def setUp(self):
        company = Company.objects.create(name="Acme")
        role = Role.objects.create(company=company, name=SeededRole.COMPANY_ADMIN,
                                   permissions=COMPANY_ADMIN_PERMISSIONS)
        admin = User.objects.create_user(email="admin@acme.com", password="Str0ngPassw0rd!", company=company)
        Membership.objects.create(company=company, user=admin, role=role)
        project = Project.objects.create(company=company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        self.client = APIClient()
        self.client.force_authenticate(admin)
        res = self.client.post("/api/reports/", {"project": str(project.id), "title": "Monthly",
                                                 "report_number": "1"}, format="json")
        self.report_id = res.data["id"]

    def test_only_the_named_charts_are_drawn_with_their_size(self):
        chart = {"type": "chart", "x": 10, "y": 10, "w": 120, "h": 80, "z": 0,
                 "props": {"source": "spi", "chart_type": "gauge"}}
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {**chart, "id": "c1"}, {**chart, "id": "c2", "w": 100}]}]
        res = self.client.post(f"/api/reports/{self.report_id}/chart-svgs/",
                               {"layout_override": {"layout": {"pages": pages}}, "only": ["c2"]},
                               format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(res.data["charts"]), {"c2"})
        drawn = res.data["charts"]["c2"]
        if drawn["status"] == "ok":
            self.assertEqual((drawn["w"], drawn["h"]), (100, 80))
