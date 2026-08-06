"""Reports tests: config merge, Arabic-aware PDF rendering, and API gating."""
import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, Permission, SeededRole
from apps.accounts.models import Company, Membership, Role, User
from apps.projects.models import Project

from .constants import apply_report_layout_override, default_config, merged_config
from .layout_seed import seed_layout_from_sections
from .models import Report, ReportTemplate
from .pdf import build_report_pdf, has_arabic, shape
from .pdf_canvas import (
    build_canvas_pdf,
    el_box,
    expand_pages,
    has_canvas_layout,
    resolve_chart,
    resolve_field,
    resolve_table,
)

STRONG_PW = "Str0ngPassw0rd!"


def _sample_ctx():
    """A representative context with Arabic data, like a real construction report."""
    return {
        "report": {"title": "Monthly Progress Report", "number": "52",
                   "period_start": datetime.date(2026, 4, 1),
                   "period_finish": datetime.date(2026, 4, 30), "status": "Draft"},
        "project": {"name": "مشروع مدينة سانت كاترين", "code": "SCD-2026-001", "type": "Infrastructure",
                    "location": "Saint Catherine", "description": "وصف المشروع", "client": "NUCA",
                    "consultant": "Dar", "contractor": "Orascom", "planned_start": datetime.date(2025, 1, 1),
                    "planned_finish": datetime.date(2027, 1, 1), "revised_finish": None,
                    "size_sqm": None, "budget": None, "currency": "EGP", "notes": "ملاحظات"},
        "overall": 87.8,
        "breakdown": {"total": 100, "completed": 60, "in_progress": 30, "not_started": 10},
        "zones": [{"name": "المنطقة الأولى", "progress": 90.0}, {"name": "Zone B", "progress": 75.0}],
        "milestones": [{"title": "الأساسات", "date": datetime.date(2026, 3, 1), "status": "completed"}],
        "snapshots": [{"date": datetime.date(2026, 4, 1), "overall_progress": 85.0, "source": "tracker.xlsx"}],
    }


class ConfigTests(SimpleTestCase):
    def test_merged_config_fills_missing_keys(self):
        merged = merged_config({"colors": {"primary": "#ff0000"}})
        self.assertEqual(merged["colors"]["primary"], "#ff0000")  # override kept
        self.assertIn("table_header_bg", merged["colors"])         # default backfilled
        self.assertIn("summary", merged["sections"])

    def test_default_config_is_independent_copy(self):
        a = default_config()
        a["colors"]["primary"] = "#000000"
        self.assertNotEqual(default_config()["colors"]["primary"], "#000000")


class RichTextTests(SimpleTestCase):
    def test_sanitize_drops_scripts_and_unknown_tags(self):
        from .richtext import sanitize_html

        out = sanitize_html('<p>Hi</p><script>alert(1)</script><marquee>x</marquee>')
        self.assertNotIn("script", out)
        self.assertNotIn("alert(1)", out)   # script *contents* dropped too
        self.assertNotIn("marquee", out)    # unknown tag unwrapped
        self.assertIn("x", out)             # ...but its text kept
        self.assertIn("Hi", out)

    def test_sanitize_keeps_formatting_and_strips_handlers(self):
        from .richtext import sanitize_html

        out = sanitize_html('<p style="text-align:right" onclick="x()">'
                            '<b>bold</b> <font color="#c00000" size="5">red</font></p>')
        self.assertIn("<b>bold</b>", out)
        self.assertIn('color="#c00000"', out)
        self.assertNotIn("onclick", out)
        self.assertIn("text-align:right", out)

    def test_html_renders_to_flowables(self):
        from .richtext import html_to_flowables

        cfg = default_config()
        flow = html_to_flowables(
            '<ul><li>أولا</li><li><b>ثانيا</b></li></ul><div>Plain</div>', cfg, {})
        self.assertEqual(len(flow), 3)  # two list items + one paragraph


class PdfTests(SimpleTestCase):
    def test_arabic_detection_and_shaping(self):
        self.assertTrue(has_arabic("مشروع"))
        self.assertFalse(has_arabic("Project"))
        self.assertEqual(shape(None), "")
        self.assertTrue(shape("مشروع"))  # returns a non-empty reshaped string

    def test_resolve_arabic_language_setting_overrides_the_auto_guess(self):
        from .pdf_base import resolve_arabic

        cfg = default_config()
        arabic_project = {"name": "مشروع"}
        english_project = {"name": "Tower"}

        # "auto" (the default) keeps guessing from the project name.
        self.assertTrue(resolve_arabic(cfg, arabic_project))
        self.assertFalse(resolve_arabic(cfg, english_project))

        # An explicit setting wins even when it contradicts the guess.
        cfg["language"] = "en"
        self.assertFalse(resolve_arabic(cfg, arabic_project))
        cfg["language"] = "ar"
        self.assertTrue(resolve_arabic(cfg, english_project))

    def test_builds_pdf_bytes_with_arabic_data(self):
        template = ReportTemplate(name="T", config=default_config())
        report = SimpleNamespace(title="Monthly Progress Report", template=template)
        data = build_report_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 1000)

    def test_respects_section_toggles(self):
        cfg = default_config()
        cfg["sections"] = {k: False for k in cfg["sections"]}
        cfg["cover"]["enabled"] = False
        cfg["toc"]["enabled"] = False
        template = ReportTemplate(name="T", config=cfg)
        report = SimpleNamespace(title="Empty", template=template)
        # Still produces a valid (near-empty) document without error.
        self.assertTrue(build_report_pdf(report, _sample_ctx()).startswith(b"%PDF"))


class CanvasPdfTests(SimpleTestCase):
    """The new canvas-driven renderer (phase 0: page geometry, simple element
    types, and non-item field bindings — tables/charts/repeat land in later
    phases and draw a placeholder / are skipped until then)."""

    def _template(self, layout_pages, master_elements=None, **design_overrides):
        cfg = default_config()
        cfg["page_design"] = {
            "size": "A4", "orientation": "portrait", "margin_mm": 10,
            "header_mm": 0, "footer_mm": 0, "show_header": False, "show_footer": False,
            "show_border": True, "background": "#ffffff",
            "master_elements": master_elements or [],
            **design_overrides,
        }
        cfg["layout"] = {"pages": layout_pages}
        return ReportTemplate(name="Canvas", config=cfg)

    def test_el_box_converts_top_left_mm_to_reportlab_points(self):
        # The single most breakage-prone arithmetic in the feature: canvas is
        # mm-from-top-left, ReportLab is points-from-bottom-left.
        from reportlab.lib.units import mm

        x, y, w, h = el_box({"x": 10, "y": 20, "w": 50, "h": 30}, 297)
        self.assertAlmostEqual(x, 10 * mm)
        self.assertAlmostEqual(y, (297 - 20 - 30) * mm)
        self.assertAlmostEqual(w, 50 * mm)
        self.assertAlmostEqual(h, 30 * mm)

    def test_has_canvas_layout_false_for_default_config(self):
        self.assertFalse(has_canvas_layout(default_config()))

    def test_has_canvas_layout_true_once_a_page_has_an_element(self):
        cfg = default_config()
        cfg["layout"] = {"pages": [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "text", "x": 0, "y": 0, "w": 50, "h": 10, "z": 0, "props": {"text": "Hi"}},
        ]}]}
        self.assertTrue(has_canvas_layout(cfg))

    def test_has_canvas_layout_true_for_an_empty_repeating_page(self):
        cfg = default_config()
        cfg["layout"] = {"pages": [{"id": "p1", "name": "Photos", "elements": [],
                                    "repeat": {"source": "photos", "mode": "chunk"}}]}
        self.assertTrue(has_canvas_layout(cfg))

    def test_builds_canvas_pdf_with_arabic_data(self):
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "text", "x": 10, "y": 10, "w": 100, "h": 12, "z": 0,
             "props": {"text": "Heading", "size": 16, "bold": True}},
            {"id": "e2", "type": "field", "x": 10, "y": 30, "w": 100, "h": 10, "z": 1,
             "props": {"source": "project.name"}},
            {"id": "e3", "type": "rect", "x": 10, "y": 50, "w": 40, "h": 20, "z": 2,
             "props": {"fill": "#eef3f8", "stroke": "#1F4E79", "stroke_width": 0.5}},
            {"id": "e4", "type": "line", "x": 10, "y": 80, "w": 100, "h": 1, "z": 3,
             "props": {"stroke": "#1F4E79", "stroke_width": 0.6}},
        ]}]
        template = self._template(pages)
        report = SimpleNamespace(title="Monthly Progress Report", template=template)
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 500)

    def test_master_elements_repeat_on_every_expanded_page(self):
        master = [{"id": "m1", "type": "field", "x": 5, "y": 5, "w": 30, "h": 8, "z": 0,
                  "props": {"source": "page.number"}}]
        pages = [
            {"id": "p1", "name": "Page 1", "elements": []},
            {"id": "p2", "name": "Page 2", "elements": []},
        ]
        template = self._template(pages, master_elements=master)
        report = SimpleNamespace(title="T", template=template)
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))

    def test_skip_master_page_renders_without_crashing(self):
        """A bespoke page (e.g. a cover) can opt out of the repeating
        header/footer row entirely."""
        master = [{"id": "m1", "type": "field", "x": 5, "y": 5, "w": 30, "h": 8, "z": 0,
                  "props": {"source": "page.number"}}]
        pages = [
            {"id": "cover", "name": "Cover", "elements": [], "skip_master": True},
            {"id": "p2", "name": "Page 2", "elements": []},
        ]
        template = self._template(pages, master_elements=master)
        report = SimpleNamespace(title="T", template=template)
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))

    def test_rotated_elements_render_without_crashing_or_leaking_canvas_state(self):
        """rotation rotates the coordinate system around the element's own
        center via saveState/rotate/restoreState, paired in a finally so an
        unbalanced save/restore stack (which ReportLab errors on at c.save())
        can't leak the rotation onto whatever draws after it."""
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "rect", "x": 20, "y": 20, "w": 30, "h": 15, "z": 0, "rotation": 45,
             "props": {"fill": "#ff0000"}},
            {"id": "e2", "type": "text", "x": 60, "y": 20, "w": 30, "h": 15, "z": 1, "rotation": 315,
             "props": {"text": "tilted"}},
            {"id": "e3", "type": "text", "x": 20, "y": 60, "w": 60, "h": 10, "z": 2,
             "props": {"text": "unrotated, drawn after a rotated element"}},
        ]}]
        template = self._template(pages)
        report = SimpleNamespace(title="T", template=template)
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))

    def test_border_offset_independent_of_margin_renders_without_crashing(self):
        """border_offset_mm decouples the frame from the content margin —
        e.g. a frame pulled in tight to the edge while content keeps its
        own, larger margin."""
        pages = [{"id": "p1", "name": "Page 1", "elements": []}]
        template = self._template(pages, margin_mm=20, border_offset_mm=2)
        report = SimpleNamespace(title="T", template=template)
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))

    def test_table_and_chart_elements_draw_a_placeholder_not_crash(self):
        """Phase 1 fills these in for real — until then they must degrade to a
        visible placeholder, never an exception that kills the whole report."""
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "table", "x": 10, "y": 10, "w": 100, "h": 40, "z": 0,
             "props": {"source": "zone_progress"}},
            {"id": "e2", "type": "chart", "x": 10, "y": 60, "w": 80, "h": 60, "z": 1,
             "props": {"source": "scurve", "chart_type": "line"}},
        ]}]
        template = self._template(pages)
        report = SimpleNamespace(title="T", template=template)
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))

    def test_unknown_element_type_is_skipped_not_fatal(self):
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "not_a_real_type", "x": 0, "y": 0, "w": 10, "h": 10, "z": 0, "props": {}},
        ]}]
        template = self._template(pages)
        report = SimpleNamespace(title="T", template=template)
        self.assertTrue(build_canvas_pdf(report, _sample_ctx()).startswith(b"%PDF"))

    def test_multiline_text_and_description_field_render(self):
        """project.description is real multi-line text — each line must be
        shaped (bidi-reordered) on its own, not the whole block as one run."""
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "text", "x": 10, "y": 10, "w": 100, "h": 40, "z": 0,
             "props": {"text": "Line one\nLine two\nثلاثة"}},
            {"id": "e2", "type": "field", "x": 10, "y": 60, "w": 100, "h": 30, "z": 1,
             "props": {"source": "project.description"}},
        ]}]
        template = self._template(pages)
        report = SimpleNamespace(title="T", template=template)
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))


class ResolveFieldTests(SimpleTestCase):
    """`resolve_field` covers every non-item entry FIELD_SOURCES declares
    (frontend/src/lib/reportElements.ts) — a missing mapping is otherwise
    silent breakage (the field just renders blank in the PDF)."""

    NON_ITEM_SOURCES = [
        "project.name", "project.code", "project.client", "project.consultant",
        "project.contractor", "project.location", "project.description",
        "report.title", "report.number",
        "report.period", "report.date", "progress.overall", "progress.planned", "page.number",
    ]

    def test_covers_every_declared_source(self):
        ctx = _sample_ctx()
        ctx["arabic"] = True
        for source in self.NON_ITEM_SOURCES:
            value = resolve_field(source, ctx, {"item": None}, page_no=3)
            self.assertIsNotNone(value, source)

    def test_page_number_reflects_the_expanded_instance(self):
        self.assertEqual(resolve_field("page.number", _sample_ctx(), {}, page_no=7), "7")

    def test_project_fields_read_from_ctx(self):
        ctx = _sample_ctx()
        self.assertEqual(resolve_field("project.client", ctx, {}, page_no=1), "NUCA")
        self.assertEqual(resolve_field("project.contractor", ctx, {}, page_no=1), "Orascom")

    def test_unknown_source_returns_empty_string_not_none(self):
        self.assertEqual(resolve_field("not.a.real.source", _sample_ctx(), {}, page_no=1), "")


def _full_ctx():
    """_sample_ctx() plus every key resolve_table/resolve_chart read, so each
    of the 10 table sources and 8 chart sources has real data to resolve."""
    ctx = _sample_ctx()
    ctx["arabic"] = True
    ctx["planned"] = 82.0
    ctx["zones"][0]["planned"] = 88.0
    ctx["zones"][0]["previous"] = 85.0
    ctx["zones"][1]["planned"] = 70.0
    ctx["zones"][1]["previous"] = 65.0
    ctx["areas"] = [{"name": "Area 1", "planned": 80.0, "actual": 75.0},
                    {"name": "Area 2", "planned": 60.0, "actual": 55.0}]
    ctx["hierarchy"] = [{"name": "المنطقة الأولى", "actual": 90.0, "previous": 85.0, "planned": 92.0,
                        "children": [{"name": "Sub A", "actual": 88.0, "previous": 80.0, "planned": 90.0}]}]
    ctx["discipline"] = [{"name": "Zone A", "concrete": 90.0, "architecture": 70.0,
                          "electrical": 50.0, "mechanical": 40.0, "other": None}]
    ctx["duration"] = {"total": 400, "elapsed": 200, "remaining": 200, "delay": 15}
    ctx["cashflow"] = [
        {"month": datetime.date(2026, 1, 1), "planned": 100.0, "actual": 90.0,
         "cum_planned": 100.0, "cum_actual": 90.0},
        {"month": datetime.date(2026, 2, 1), "planned": 120.0, "actual": 110.0,
         "cum_planned": 220.0, "cum_actual": 200.0},
    ]
    ctx["invoices"] = [{"name": "Invoice 1", "value": 5000.0, "date": datetime.date(2026, 2, 1)}]
    ctx["invoices_total"] = 5000.0
    ctx["submittals"] = {
        "rows": [{"title": "Shop drawing 1", "type": "Drawing", "discipline": "Architecture", "status": "Approved"}],
        "summary": [{"status": "Approved", "key": "approved", "count": 1}],
    }
    ctx["delays"] = [{"title": "Late materials", "impact_days": 5, "status": "open"}]
    ctx["critical_path"] = [
        {"name": "Zone A", "planned_finish": datetime.date(2026, 6, 1),
         "forecast_finish": datetime.date(2026, 6, 20), "delay_days": 19},
    ]
    ctx["gantt"] = [
        {"name": "Zone A", "level": 0, "start": datetime.date(2026, 1, 1), "finish": datetime.date(2026, 6, 1),
         "revised_finish": None, "progress": 60.0},
        {"name": "Zone B", "level": 0, "start": datetime.date(2026, 2, 1), "finish": datetime.date(2026, 7, 1),
         "revised_finish": None, "progress": 40.0},
    ]
    ctx["scurve"] = [
        {"date": datetime.date(2026, 1, 1), "actual": 20.0, "planned": 25.0},
        {"date": datetime.date(2026, 2, 1), "actual": 40.0, "planned": 50.0},
    ]
    return ctx


class ResolveTableTests(SimpleTestCase):
    """`resolve_table` for every TABLE_SOURCES entry (reportElements.ts) —
    reuses the exact same row logic pdf.py's flowing renderer uses."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from .pdf_base import ensure_fonts
        ensure_fonts()  # normally done by build_canvas_pdf before any Paragraph is built

    SOURCES_WITH_DATA = [
        "project_info", "zone_progress", "hierarchy_progress", "discipline_progress",
        "progress_compare", "milestones", "invoices", "submittals", "delays",
        "critical_path_delays",
    ]

    def test_every_source_with_data_returns_a_table(self):
        cfg = default_config()
        ctx = _full_ctx()
        for source in self.SOURCES_WITH_DATA:
            table = resolve_table(source, cfg, ctx, {"item": None})
            self.assertIsNotNone(table, source)

    def test_missing_data_returns_none_not_a_crash(self):
        cfg = default_config()
        ctx = _sample_ctx()  # no hierarchy/discipline/invoices/submittals/delays
        for source in ("hierarchy_progress", "discipline_progress", "invoices", "submittals", "delays",
                       "critical_path_delays"):
            self.assertIsNone(resolve_table(source, cfg, ctx, {"item": None}), source)

    def test_detailed_progress_without_a_real_project_returns_none(self):
        # No DB project attached (ctx["_report"] absent) -> can't lazily compute
        # zone_grids -> None, not an exception.
        cfg = default_config()
        self.assertIsNone(resolve_table("detailed_progress", cfg, _full_ctx(), {"item": None}))

    def test_unknown_source_returns_none(self):
        self.assertIsNone(resolve_table("not_a_real_source", default_config(), _full_ctx(), {"item": None}))

    def test_item_scoped_source_returns_none_until_phase_2(self):
        self.assertIsNone(resolve_table("item.children", default_config(), _full_ctx(), {"item": None}))


class ResolveChartTests(SimpleTestCase):
    """`resolve_chart` for every CHART_SOURCES entry (reportElements.ts)."""

    SOURCES_WITH_DATA = [
        "zone_progress", "area_progress", "scurve", "breakdown", "duration",
        "cashflow_monthly", "cashflow_cumulative", "gantt", "spi",
    ]

    def test_item_spi_reads_the_current_item(self):
        drawing = resolve_chart("item.spi", "gauge", default_config(), _full_ctx(),
                                {"item": {"name": "Zone A", "progress": 62.0}}, 100, 70)
        self.assertIsNotNone(drawing)

    def test_every_source_with_data_returns_a_drawing(self):
        cfg = default_config()
        ctx = _full_ctx()
        for source in self.SOURCES_WITH_DATA:
            drawing = resolve_chart(source, "bar", cfg, ctx, {"item": None}, 120, 70)
            self.assertIsNotNone(drawing, source)

    def test_explicit_height_is_respected(self):
        cfg = default_config()
        drawing = resolve_chart("breakdown", "donut", cfg, _full_ctx(), {"item": None}, 120, 90)
        self.assertEqual(drawing.height, 90)

    def test_unknown_source_returns_none(self):
        self.assertIsNone(resolve_chart("not_a_real_source", "bar", default_config(), _full_ctx(), {"item": None}, 100, 70))

    def test_item_scoped_source_returns_none_until_phase_2(self):
        self.assertIsNone(resolve_chart("item.units", "bar", default_config(), _full_ctx(), {"item": None}, 100, 70))

    def test_spi_gauge_returns_none_without_a_value(self):
        from .pdf_charts import speedometer_chart

        self.assertIsNone(speedometer_chart(None, 100, default_config()))

    def test_spi_gauge_clamps_out_of_range_values(self):
        from .pdf_charts import speedometer_chart

        # 140% shouldn't push the needle/label past the gauge's 100% end.
        drawing = speedometer_chart(140, 100, default_config())
        self.assertIsNotNone(drawing)

    def test_spi_gauge_bands_come_from_config_not_a_hardcoded_constant(self):
        from reportlab.graphics.shapes import Wedge

        from .pdf_base import hexcolor
        from .pdf_charts import speedometer_chart

        cfg = default_config()
        cfg["gauge_thresholds"] = {"low": 20, "high": 40}
        cfg["colors"]["gauge_bad"] = "#111111"
        cfg["colors"]["gauge_warn"] = "#222222"
        cfg["colors"]["gauge_good"] = "#333333"

        drawing = speedometer_chart(90, 100, cfg)
        wedges = [el for el in drawing.contents if isinstance(el, Wedge)]
        self.assertEqual([w.fillColor for w in wedges],
                          [hexcolor("#111111"), hexcolor("#222222"), hexcolor("#333333")])


class TocTests(SimpleTestCase):
    """The "toc" element needs real page numbers, known only after repeat
    pages are expanded — build_canvas_pdf computes them up front (one row per
    distinct page id, so a repeat page's clones collapse to its first
    occurrence) rather than needing a second render pass."""

    def test_toc_map_collapses_repeat_clones_to_first_occurrence(self):
        pages = [
            {"id": "cover", "name": "Cover", "elements": []},
            {"id": "info", "name": "Project Info", "elements": []},
            {"id": "photos", "name": "Photos", "elements": [],
             "repeat": {"source": "photos", "mode": "chunk", "chunk_size": 4}},
            {"id": "end", "name": "Attachments", "elements": []},
        ]
        cfg = default_config()
        cfg["layout"] = {"pages": pages}
        ctx = _sample_ctx()
        ctx["photos"] = [{"image": None, "caption": f"P{i}"} for i in range(9)]  # -> 3 repeat pages
        template = ReportTemplate(name="T", config=cfg)
        report = SimpleNamespace(title="T", template=template, scope_ids=[])

        build_canvas_pdf(report, ctx)

        self.assertEqual(ctx["_toc_map"], {"cover": 1, "info": 2, "photos": 3, "end": 6})
        self.assertEqual(ctx["_toc_order"],
                         [("cover", "Cover"), ("info", "Project Info"),
                          ("photos", "Photos"), ("end", "Attachments")])

    def test_toc_element_renders_without_crashing(self):
        cfg = default_config()
        cfg["page_design"] = {
            "size": "A4", "orientation": "portrait", "margin_mm": 10,
            "header_mm": 0, "footer_mm": 0, "show_header": False, "show_footer": False,
            "show_border": True, "background": "#ffffff", "master_elements": [],
        }
        cfg["layout"] = {"pages": [
            {"id": "toc", "name": "Contents", "elements": [
                {"id": "e1", "type": "toc", "x": 10, "y": 10, "w": 150, "h": 200, "z": 0,
                 "props": {"size": 11, "row_height": 8, "exclude_cover": True}},
            ]},
            {"id": "p2", "name": "Project Info", "elements": []},
        ]}
        template = ReportTemplate(name="T", config=cfg)
        report = SimpleNamespace(title="T", template=template, scope_ids=[])
        data = build_canvas_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))


class ExpandPagesTests(SimpleTestCase):
    """`expand_pages` for both fixed (non-repeat) and repeating pages."""

    def test_fixed_pages_yield_one_instance_each_in_order(self):
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "A", "elements": []},
            {"id": "b", "name": "B", "elements": []},
        ]}}
        instances = expand_pages(cfg, _sample_ctx(), report=None)
        self.assertEqual([i.page["id"] for i in instances], ["a", "b"])
        self.assertEqual([i.number for i in instances], [1, 2])
        self.assertEqual(instances[0].scope["item"], None)

    def test_no_pages_yields_no_instances(self):
        self.assertEqual(expand_pages({"layout": {"pages": []}}, _sample_ctx(), report=None), [])

    def test_skip_master_flag_survives_expansion(self):
        cfg = {"layout": {"pages": [
            {"id": "cover", "name": "Cover", "elements": [], "skip_master": True},
            {"id": "b", "name": "B", "elements": []},
        ]}}
        instances = expand_pages(cfg, _sample_ctx(), report=None)
        self.assertTrue(instances[0].page.get("skip_master"))
        self.assertFalse(instances[1].page.get("skip_master"))

    def test_repeat_page_with_empty_source_is_skipped(self):
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "Photos", "elements": [], "repeat": {"source": "photos", "mode": "chunk"}},
        ]}}
        self.assertEqual(expand_pages(cfg, _sample_ctx(), report=None), [])

    def test_chunk_mode_splits_photos_four_per_page(self):
        ctx = _sample_ctx()
        ctx["photos"] = [{"image": f"k{i}", "caption": f"Photo {i}"} for i in range(9)]
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "Photos", "elements": [],
             "repeat": {"source": "photos", "mode": "chunk", "chunk_size": 4}},
        ]}}
        instances = expand_pages(cfg, ctx, report=None)
        self.assertEqual(len(instances), 3)  # 9 photos / 4 per page -> 3 pages
        self.assertEqual(len(instances[0].scope["items"]), 4)
        self.assertEqual(len(instances[1].scope["items"]), 4)
        self.assertEqual(len(instances[2].scope["items"]), 1)  # last page: the remainder
        self.assertEqual(instances[0].scope["items"][0]["caption"], "Photo 0")
        self.assertEqual(instances[2].scope["items"][0]["caption"], "Photo 8")
        self.assertEqual([i.number for i in instances], [1, 2, 3])

    def test_one_per_item_yields_one_instance_per_zone(self):
        ctx = _sample_ctx()  # already has 2 zones
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "Zone", "elements": [], "repeat": {"source": "zones", "mode": "one_per_item"}},
        ]}}
        instances = expand_pages(cfg, ctx, report=None)
        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0].scope["item"]["name"], "المنطقة الأولى")
        self.assertEqual(instances[1].scope["item"]["name"], "Zone B")
        self.assertEqual(instances[0].scope["count"], 2)

    def test_max_pages_caps_runaway_expansion(self):
        ctx = _sample_ctx()
        ctx["photos"] = [{"image": f"k{i}", "caption": ""} for i in range(500)]
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "Photos", "elements": [],
             "repeat": {"source": "photos", "mode": "chunk", "chunk_size": 4, "max_pages": 5}},
        ]}}
        self.assertEqual(len(expand_pages(cfg, ctx, report=None)), 5)

    def test_pin_index_yields_only_that_one_item(self):
        ctx = _sample_ctx()  # already has 2 zones
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "Zone", "elements": [],
             "repeat": {"source": "zones", "mode": "one_per_item", "pin_index": 1}},
        ]}}
        instances = expand_pages(cfg, ctx, report=None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].scope["item"]["name"], "Zone B")
        self.assertEqual(instances[0].scope["index"], 1)  # keeps the real position, not 0

    def test_pin_index_out_of_range_yields_nothing(self):
        ctx = _sample_ctx()  # 2 zones -> valid indices are 0-1
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "Zone", "elements": [],
             "repeat": {"source": "zones", "mode": "one_per_item", "pin_index": 5}},
        ]}}
        self.assertEqual(expand_pages(cfg, ctx, report=None), [])

    def test_pin_index_selects_one_chunk(self):
        ctx = _sample_ctx()
        ctx["photos"] = [{"image": f"k{i}", "caption": f"Photo {i}"} for i in range(9)]
        cfg = {"layout": {"pages": [
            {"id": "a", "name": "Photos", "elements": [],
             "repeat": {"source": "photos", "mode": "chunk", "chunk_size": 4, "pin_index": 2}},
        ]}}
        instances = expand_pages(cfg, ctx, report=None)
        self.assertEqual(len(instances), 1)
        self.assertEqual(len(instances[0].scope["items"]), 1)  # the last (remainder) chunk
        self.assertEqual(instances[0].scope["items"][0]["caption"], "Photo 8")

    def test_mixed_fixed_and_repeat_pages_keep_document_order(self):
        ctx = _sample_ctx()
        ctx["photos"] = [{"image": "k1", "caption": ""}, {"image": "k2", "caption": ""}]
        cfg = {"layout": {"pages": [
            {"id": "cover", "name": "Cover", "elements": []},
            {"id": "photos", "name": "Photos", "elements": [],
             "repeat": {"source": "photos", "mode": "chunk", "chunk_size": 1}},
            {"id": "back", "name": "Back cover", "elements": []},
        ]}}
        instances = expand_pages(cfg, ctx, report=None)
        self.assertEqual([i.page["id"] for i in instances], ["cover", "photos", "photos", "back"])
        self.assertEqual([i.number for i in instances], [1, 2, 3, 4])


class RepeatBindingTests(SimpleTestCase):
    """Item-scoped bindings (`item.*`) resolved against the current repeat
    scope — the piece that makes a designed page template show each item's
    own data instead of repeating the first one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from .pdf_base import ensure_fonts
        ensure_fonts()

    def test_item_name_and_progress_from_a_zone(self):
        scope = {"item": {"name": "Zone A", "progress": 88.5}, "index": 0, "count": 2}
        self.assertEqual(resolve_field("item.name", {}, scope, page_no=1), "Zone A")
        self.assertEqual(resolve_field("item.progress", {}, scope, page_no=1), "88.5%")

    def test_item_progress_falls_back_to_actual_for_area_dashboards(self):
        scope = {"item": {"name": "Zone A", "actual": 72.0}, "index": 0, "count": 1}
        self.assertEqual(resolve_field("item.progress", {}, scope, page_no=1), "72.0%")

    def test_item_index_is_one_based_and_item_count_reflects_total(self):
        scope = {"item": {"name": "X"}, "index": 2, "count": 5}
        self.assertEqual(resolve_field("item.index", {}, scope, page_no=1), "3")
        self.assertEqual(resolve_field("item.count", {}, scope, page_no=1), "5")

    def test_item_caption_from_a_photo(self):
        scope = {"item": {"image": "k1", "caption": "Foundation works"}, "index": 0, "count": 1}
        self.assertEqual(resolve_field("item.caption", {}, scope, page_no=1), "Foundation works")

    def test_item_children_table_from_area_dashboard_item(self):
        cfg = default_config()
        scope = {"item": {"name": "Zone A", "children": [
            {"name": "Sub 1", "actual": 90.0, "planned": 92.0},
            {"name": "Sub 2", "actual": 60.0, "planned": None},
        ]}}
        table = resolve_table("item.children", cfg, _sample_ctx(), scope)
        self.assertIsNotNone(table)

    def test_item_children_table_none_when_item_has_no_children(self):
        cfg = default_config()
        self.assertIsNone(resolve_table("item.children", cfg, _sample_ctx(), {"item": {"name": "Zone A"}}))

    def test_item_units_chart_from_area_dashboard_item(self):
        from .pdf_base import ensure_fonts
        ensure_fonts()
        cfg = default_config()
        scope = {"item": {"name": "Zone A", "children": [
            {"name": "Unit 1", "actual": 80.0}, {"name": "Unit 2", "actual": 60.0},
        ]}}
        drawing = resolve_chart("item.units", "bar", cfg, _sample_ctx(), scope, 100, 70)
        self.assertIsNotNone(drawing)

    def test_item_duration_chart_from_area_dashboard_item(self):
        cfg = default_config()
        scope = {"item": {"name": "Zone A", "duration": {"total": 300, "delay": 10}}}
        drawing = resolve_chart("item.duration", "pie", cfg, _sample_ctx(), scope, 100, 70)
        self.assertIsNotNone(drawing)


class HierarchyRowsTests(TestCase):
    """`_hierarchy_rows` rolls up Project -> Zone -> Subzone (one level deeper
    than the existing zone table), using each scope's own dates when set."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31))
        self.zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A")
        self.sub = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 1",
            parent=self.zone, planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 7, 1))
        Activity.objects.create(
            company=self.company, project=self.project, scope=self.sub,
            name="Task", weight=1, progress_percent=40)

    def test_rolls_up_zone_and_subzone_with_own_dates(self):
        from .services import _hierarchy_rows

        as_of = datetime.date(2026, 4, 1)  # 91/181 days into Building 1's own span
        rows = _hierarchy_rows(self.project, as_of=as_of)
        self.assertEqual(len(rows), 1)
        zone_row = rows[0]
        self.assertEqual(zone_row["name"], "Zone A")
        self.assertEqual(zone_row["actual"], 40.0)
        self.assertEqual(len(zone_row["children"]), 1)
        sub_row = zone_row["children"][0]
        self.assertEqual(sub_row["name"], "Building 1")
        self.assertEqual(sub_row["actual"], 40.0)
        self.assertAlmostEqual(sub_row["planned"], 49.7, delta=0.5)  # 90/181 days

    def test_uses_previous_scopes_map_when_given(self):
        from .services import _hierarchy_rows

        rows = _hierarchy_rows(self.project, prev_scopes={str(self.sub.id): 25.0})
        self.assertEqual(rows[0]["children"][0]["previous"], 25.0)
        self.assertIsNone(rows[0]["previous"])  # zone itself wasn't in the map


class PlannedProgressOverrideTests(TestCase):
    """A real P6 export states its own Schedule % Complete (planned, time-based)
    alongside Performance % Complete (actual). `_planned_progress` should prefer
    it for the report's single "current" figure, the same way
    `project_overall_progress` already prefers the imported actual figure."""

    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31),
            imported_planned_progress_percent=95.0)

    def test_current_view_prefers_the_imported_planned_figure(self):
        from .services import _planned_progress

        # 2026-04-01 is ~25% through the contract calendar -- the imported 95%
        # only comes through if the override actually wins.
        planned = _planned_progress(self.project, datetime.date(2026, 4, 1), use_imported=True)
        self.assertEqual(planned, 95.0)

    def test_series_call_ignores_the_imported_planned_figure(self):
        """The S-curve computes one point per historical snapshot date; without
        `use_imported`, every point must stay live, not flatten to one number."""
        from .services import _planned_progress

        planned = _planned_progress(self.project, datetime.date(2026, 4, 1))
        self.assertNotEqual(planned, 95.0)

    def test_falls_back_to_computed_without_a_stated_figure(self):
        from .services import _planned_progress

        self.project.imported_planned_progress_percent = None
        self.project.save(update_fields=["imported_planned_progress_percent"])

        planned = _planned_progress(self.project, datetime.date(2026, 4, 1), use_imported=True)
        self.assertNotEqual(planned, 95.0)


class DisciplineRowsTests(TestCase):
    """`_discipline_rows` splits one unit's progress by trade, using each
    activity's phase's discipline tag (a phase's direct parent is the unit)."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A")
        self.unit = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 1", parent=zone)
        concrete_phase = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="phase", name="Concrete works",
            parent=self.unit, discipline="concrete")
        electrical_phase = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="phase", name="Electrical works",
            parent=self.unit, discipline="electrical")
        untagged_phase = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="phase", name="Misc", parent=self.unit)
        Activity.objects.create(company=self.company, project=self.project, scope=concrete_phase,
                                name="Pour", weight=1, progress_percent=80)
        Activity.objects.create(company=self.company, project=self.project, scope=electrical_phase,
                                name="Wiring", weight=1, progress_percent=20)
        Activity.objects.create(company=self.company, project=self.project, scope=untagged_phase,
                                name="Other work", weight=1, progress_percent=100)

    def test_splits_progress_by_phase_discipline(self):
        from .services import _discipline_rows

        rows = _discipline_rows(self.project)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], "Building 1")
        self.assertEqual(row["concrete"], 80.0)
        self.assertEqual(row["electrical"], 20.0)
        self.assertIsNone(row["architecture"])
        self.assertIsNone(row["mechanical"])  # untagged phase's work isn't guessed into a column


class AreaDashboardsTests(TestCase):
    """`_area_dashboards` adds each zone's own duration (falling back to the
    project's) and recent subtree photos on top of the hierarchy rows."""

    def setUp(self):
        from apps.projects.models import Activity, ProgressEntry, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31))
        self.zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A",
            planned_start=datetime.date(2026, 2, 1), planned_finish=datetime.date(2026, 8, 1))
        activity = Activity.objects.create(
            company=self.company, project=self.project, scope=self.zone,
            name="Task", weight=1, progress_percent=50)
        entry = ProgressEntry.objects.create(
            company=self.company, project=self.project, activity=activity,
            date=datetime.date(2026, 4, 1), progress_percent=50)
        from apps.projects.models import ProgressImage
        ProgressImage.objects.create(company=self.company, entry=entry, caption="Pour")

    def test_uses_zone_dates_and_finds_subtree_photos(self):
        from .services import _area_dashboards, _hierarchy_rows

        as_of = datetime.date(2026, 5, 1)
        hierarchy = _hierarchy_rows(self.project, as_of=as_of)
        areas = _area_dashboards(self.project, hierarchy, as_of)
        self.assertEqual(len(areas), 1)
        area = areas[0]
        self.assertEqual(area["name"], "Zone A")
        self.assertEqual(area["duration"]["total"], 181)  # Zone A's own Feb-Aug span, not the project's
        self.assertEqual(len(area["photos"]), 1)
        self.assertEqual(area["photos"][0]["caption"], "Pour")

    def test_zone_without_own_dates_has_no_duration(self):
        """A dateless zone shows no duration pie (it would just repeat the
        project's numbers on every page); it still appears with its children."""
        from apps.projects.models import Activity, ProjectScope
        from .services import _area_dashboards, _hierarchy_rows

        dateless = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone B")
        unit = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Bldg", parent=dateless)
        Activity.objects.create(company=self.company, project=self.project, scope=unit,
                                name="W", weight=1, progress_percent=30)

        as_of = datetime.date(2026, 5, 1)
        hierarchy = _hierarchy_rows(self.project, as_of=as_of)
        areas = {a["name"]: a for a in _area_dashboards(self.project, hierarchy, as_of)}
        self.assertIsNone(areas["Zone B"]["duration"])      # dateless -> no pie
        self.assertIsNotNone(areas["Zone A"]["duration"])   # has own dates -> kept

    def test_context_areas_and_area_chart(self):
        # A subzone under a zone is exposed as an "area" and drives the chart.
        from apps.projects.models import Activity, ProjectScope
        from .constants import default_config
        from .pdf_charts import area_progress_chart
        from .services import build_report_context

        unit = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Bldg 1", parent=self.zone)
        Activity.objects.create(company=self.company, project=self.project, scope=unit,
                                name="W", weight=1, progress_percent=40)
        report = Report.objects.create(company=self.company, project=self.project, title="R")

        ctx = build_report_context(report)
        names = [a["name"] for a in ctx["areas"]]
        self.assertIn("Bldg 1", names)
        # The chart renders (returns a Drawing, not None) when areas exist.
        self.assertIsNotNone(area_progress_chart(default_config(), ctx, 400, default_config()["labels"]))


class CriticalPathRowsTests(TestCase):
    """`_critical_path_rows` — only zones with their own P6-imported schedule
    carry a delay figure; a dateless zone is skipped, not zero-filled."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31))
        self.zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A",
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 6, 1))
        self.dateless = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone B")
        # `_hierarchy_rows` (which supplies critical_path's zone list) skips any
        # zone with zero rolled-up weight — a bare ProjectScope with no
        # activities never appears, dated or not.
        Activity.objects.create(company=self.company, project=self.project, scope=self.zone,
                                name="Task", weight=1, progress_percent=50)
        Activity.objects.create(company=self.company, project=self.project, scope=self.dateless,
                                name="Task", weight=1, progress_percent=50)

    def test_zone_with_revised_finish_reports_that_delay(self):
        from .services import _critical_path_rows, _hierarchy_rows

        self.zone.revised_finish = datetime.date(2026, 6, 20)
        self.zone.save(update_fields=["revised_finish"])
        as_of = datetime.date(2026, 5, 1)
        hierarchy = _hierarchy_rows(self.project, as_of=as_of)
        rows = {r["name"]: r for r in _critical_path_rows(self.project, hierarchy, as_of)}
        self.assertEqual(rows["Zone A"]["planned_finish"], datetime.date(2026, 6, 1))
        self.assertEqual(rows["Zone A"]["forecast_finish"], datetime.date(2026, 6, 20))
        self.assertEqual(rows["Zone A"]["delay_days"], 19)
        self.assertNotIn("Zone B", rows)  # no own schedule -> skipped

    def test_overdue_zone_without_revised_finish_derives_forecast_from_as_of(self):
        from .services import _critical_path_rows, _hierarchy_rows

        as_of = datetime.date(2026, 6, 11)  # 10 days past Zone A's planned finish
        hierarchy = _hierarchy_rows(self.project, as_of=as_of)
        rows = {r["name"]: r for r in _critical_path_rows(self.project, hierarchy, as_of)}
        self.assertEqual(rows["Zone A"]["delay_days"], 10)
        self.assertEqual(rows["Zone A"]["forecast_finish"], datetime.date(2026, 6, 11))

    def test_on_time_zone_has_zero_delay_and_forecast_equals_planned(self):
        from .services import _critical_path_rows, _hierarchy_rows

        as_of = datetime.date(2026, 3, 1)  # well before Zone A's planned finish
        hierarchy = _hierarchy_rows(self.project, as_of=as_of)
        rows = {r["name"]: r for r in _critical_path_rows(self.project, hierarchy, as_of)}
        self.assertEqual(rows["Zone A"]["delay_days"], 0)
        self.assertEqual(rows["Zone A"]["forecast_finish"], datetime.date(2026, 6, 1))


class GanttRowsTests(TestCase):
    """`_gantt_rows` builds zone+child Gantt bars from each scope's OWN dates
    (no project-date fallback, since every bar would otherwise be identical)."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31))
        self.zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A",
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 6, 1))
        self.dated_child = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 1",
            parent=self.zone, planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 3, 1),
            revised_finish=datetime.date(2026, 4, 1))
        self.undated_child = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 2", parent=self.zone)
        Activity.objects.create(
            company=self.company, project=self.project, scope=self.dated_child,
            name="Task", weight=1, progress_percent=50)
        Activity.objects.create(
            company=self.company, project=self.project, scope=self.undated_child,
            name="Task 2", weight=1, progress_percent=100)

    def test_omits_scopes_without_own_dates(self):
        from .services import _gantt_rows

        rows = _gantt_rows(self.project)
        names = [r["name"] for r in rows]
        self.assertIn("Zone A", names)        # has its own dates
        self.assertIn("Building 1", names)    # has its own dates
        self.assertNotIn("Building 2", names)  # no dates -> omitted

    def test_rolls_up_progress_and_keeps_revised_finish(self):
        from .services import _gantt_rows

        rows = _gantt_rows(self.project)
        child = next(r for r in rows if r["name"] == "Building 1")
        self.assertEqual(child["level"], 1)
        self.assertEqual(child["progress"], 50.0)
        self.assertEqual(child["revised_finish"], datetime.date(2026, 4, 1))

        zone_row = next(r for r in rows if r["name"] == "Zone A")
        self.assertEqual(zone_row["level"], 0)
        # Zone's own weight (0) + child's weight(1)*50 + untracked child's weight(1)*100 -> 75 overall
        self.assertEqual(zone_row["progress"], 75.0)


class FinanceReportTests(TestCase):
    """Cash flow, invoices and submittals flow into the report context and PDF."""

    def setUp(self):
        from apps.projects.models import CashFlowEntry, Invoice, Submittal

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL, currency="EGP")
        CashFlowEntry.objects.create(company=self.company, project=self.project,
                                     month=datetime.date(2026, 1, 1), planned=100, actual=80)
        CashFlowEntry.objects.create(company=self.company, project=self.project,
                                     month=datetime.date(2026, 2, 1), planned=200, actual=150)
        Invoice.objects.create(company=self.company, project=self.project, name="Extract 1", value=1500)
        Invoice.objects.create(company=self.company, project=self.project, name="Extract 2", value=2500)
        Submittal.objects.create(company=self.company, project=self.project, title="Rebar shop dwg",
                                 submittal_type="shop_drawing", discipline="concrete", status="approved")
        Submittal.objects.create(company=self.company, project=self.project, title="Paint sample",
                                 submittal_type="material", discipline="architecture", status="pending")

    def test_context_aggregates_finances(self):
        from .services import build_report_context

        rep = Report.objects.create(company=self.company, project=self.project, title="M", report_number="1")
        ctx = build_report_context(rep)
        self.assertEqual(len(ctx["cashflow"]), 2)
        self.assertEqual(ctx["cashflow"][1]["cum_actual"], 230.0)  # 80 + 150
        self.assertEqual(ctx["invoices_total"], 4000.0)
        self.assertEqual(len(ctx["submittals"]["rows"]), 2)
        approved = next(s for s in ctx["submittals"]["summary"] if s["key"] == "approved")
        self.assertEqual(approved["count"], 1)

    def test_pdf_renders_with_finance_sections(self):
        from .services import build_report_context

        rep = Report.objects.create(company=self.company, project=self.project, title="Monthly", report_number="1")
        ctx = build_report_context(rep)
        rep.template = ReportTemplate(name="T", config=default_config())
        data = build_report_pdf(rep, ctx)
        self.assertTrue(data.startswith(b"%PDF"))


class ProjectInfoCostAndDateFieldsTests(TestCase):
    """contract_value/approved_value/forecast_cost and the now-distinct
    revised_finish/forecast_finish rows — added because the project_info
    table used to collapse revised and forecast into a single mislabeled
    row and had no cost breakdown beyond the general "budget" figure."""

    def setUp(self):
        self.company = Company.objects.create(name="Acme")

    def test_context_carries_the_new_project_fields(self):
        from .services import build_report_context

        project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            revised_finish=datetime.date(2026, 6, 1), forecast_finish=datetime.date(2026, 8, 1),
            contract_value=1_000_000, approved_value=1_050_000, forecast_cost=1_100_000)
        report = Report.objects.create(company=self.company, project=project, title="R")
        ctx = build_report_context(report)

        self.assertEqual(ctx["project"]["revised_finish"], datetime.date(2026, 6, 1))
        self.assertEqual(ctx["project"]["forecast_finish"], datetime.date(2026, 8, 1))
        self.assertEqual(ctx["project"]["contract_value"], 1_000_000)
        self.assertEqual(ctx["project"]["approved_value"], 1_050_000)
        self.assertEqual(ctx["project"]["forecast_cost"], 1_100_000)

    def test_project_info_table_grows_a_row_per_field_present(self):
        from .pdf_base import ensure_fonts
        from .pdf_canvas import resolve_table

        ensure_fonts()  # normally done by build_canvas_pdf before any Paragraph is built
        cfg = default_config()
        base_ctx = {"project": {"name": "Tower", "currency": "EGP"}, "arabic": False, "duration": {}}
        empty_table = resolve_table("project_info", cfg, base_ctx, {"item": None})
        empty_rows = len(empty_table._cellvalues) if empty_table else 0

        full_ctx = {
            "project": {
                "name": "Tower", "currency": "EGP",
                "contract_value": 1_000_000, "approved_value": 1_050_000, "forecast_cost": 1_100_000,
                "revised_finish": datetime.date(2026, 6, 1), "forecast_finish": datetime.date(2026, 8, 1),
            },
            "arabic": False, "duration": {},
        }
        full_table = resolve_table("project_info", cfg, full_ctx, {"item": None})
        self.assertEqual(len(full_table._cellvalues), empty_rows + 5)


class LogosContextTests(TestCase):
    """A project can carry more than the two fixed left/right header logos —
    any number of extras, ordered by sort_order, resolved as ctx["logos"]["extra"]
    and picked in the canvas by index (mirrors a repeat photo slot)."""

    def setUp(self):
        from apps.projects.models import ProjectImage

        self.ProjectImage = ProjectImage
        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)

    def test_extra_logos_ordered_by_sort_order(self):
        from .services import build_report_context

        ProjectImage = self.ProjectImage
        ProjectImage.objects.create(company=self.company, project=self.project,
                                    image_type=ProjectImage.ImageType.LOGO, caption="Funder", sort_order=1)
        ProjectImage.objects.create(company=self.company, project=self.project,
                                    image_type=ProjectImage.ImageType.LOGO, caption="Authority", sort_order=0)
        ProjectImage.objects.create(company=self.company, project=self.project,
                                    image_type=ProjectImage.ImageType.LOGO_LEFT, caption="Main")

        report = Report.objects.create(company=self.company, project=self.project, title="R")
        ctx = build_report_context(report)

        extra = ctx["logos"]["extra"]
        self.assertEqual([e["caption"] for e in extra], ["Authority", "Funder"])  # sort_order, not creation order
        self.assertEqual(ctx["logos"]["left"]["caption"], "Main")  # fixed slots unaffected

    def test_no_extra_logos_is_an_empty_list_not_none(self):
        from .services import build_report_context

        report = Report.objects.create(company=self.company, project=self.project, title="R")
        ctx = build_report_context(report)
        self.assertEqual(ctx["logos"]["extra"], [])

    def test_draw_logo_extra_slot_renders_without_crashing(self):
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "logo", "x": 10, "y": 10, "w": 30, "h": 15, "z": 0,
             "props": {"source": "extra", "slot": 1}},
            {"id": "e2", "type": "logo", "x": 50, "y": 10, "w": 30, "h": 15, "z": 1,
             "props": {"source": "extra", "slot": 99}},  # out of range -> skipped, not fatal
        ]}]
        cfg = default_config()
        cfg["page_design"] = {
            "size": "A4", "orientation": "portrait", "margin_mm": 10,
            "header_mm": 0, "footer_mm": 0, "show_header": False, "show_footer": False,
            "show_border": True, "background": "#ffffff", "master_elements": [],
        }
        cfg["layout"] = {"pages": pages}
        template = ReportTemplate(name="T", config=cfg)
        report = SimpleNamespace(title="T", template=template, scope_ids=[])
        ctx = _sample_ctx()
        ctx["logos"] = {"left": None, "right": None, "cover": None,
                        "extra": [{"image": None, "caption": "A"}, {"image": None, "caption": "B"}]}
        data = build_canvas_pdf(report, ctx)
        self.assertTrue(data.startswith(b"%PDF"))

    def test_image_and_logo_border_props_render_without_crashing(self):
        """The border is a per-element toggle now (props.border/_color/_width)
        instead of requiring a separate rect stacked on top by hand."""
        pages = [{"id": "p1", "name": "Page 1", "elements": [
            {"id": "e1", "type": "logo", "x": 10, "y": 10, "w": 30, "h": 15, "z": 0,
             "props": {"source": "left", "border": True, "border_color": "#000000", "border_width": 0.5}},
            {"id": "e2", "type": "image", "x": 50, "y": 10, "w": 30, "h": 20, "z": 1,
             "props": {"source": "repeat.item", "slot": 0, "show_caption": True,
                       "border": True, "border_color": "#333333", "border_width": 0.3}},
        ], "repeat": {"source": "photos", "mode": "chunk", "chunk_size": 1}}]
        cfg = default_config()
        cfg["page_design"] = {
            "size": "A4", "orientation": "portrait", "margin_mm": 10,
            "header_mm": 0, "footer_mm": 0, "show_header": False, "show_footer": False,
            "show_border": True, "background": "#ffffff", "master_elements": [],
        }
        cfg["layout"] = {"pages": pages}
        template = ReportTemplate(name="T", config=cfg)
        report = SimpleNamespace(title="T", template=template, scope_ids=[])
        ctx = _sample_ctx()
        ctx["logos"] = {"left": None, "right": None, "cover": None, "extra": []}
        ctx["photos"] = [{"image": None, "caption": "Site"}]
        data = build_canvas_pdf(report, ctx)
        self.assertTrue(data.startswith(b"%PDF"))


class ReportLayoutOverrideTests(TestCase):
    """A report can diverge from its template's pages/content (added a page,
    dropped a photo somewhere the template doesn't have one, etc.) via
    Report.layout_override — without that override, it renders identically
    to every other report on the same template, as always."""

    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        self.template = ReportTemplate.objects.create(company=self.company, name="T", config=default_config())

    def test_no_override_leaves_cfg_untouched(self):
        report = Report.objects.create(company=self.company, project=self.project, template=self.template)
        cfg = merged_config(self.template.config)
        result = apply_report_layout_override(cfg, report)
        self.assertIs(result, cfg)  # no copy made when there's nothing to override

    def test_override_replaces_only_page_design_and_layout(self):
        report = Report.objects.create(
            company=self.company, project=self.project, template=self.template,
            layout_override={
                "page_design": {"size": "A3", "orientation": "landscape", "margin_mm": 5,
                                "master_elements": []},
                "layout": {"pages": [{"id": "extra", "name": "Extra Page", "elements": []}]},
            })
        cfg = merged_config(self.template.config)
        original_colors = cfg["colors"]
        result = apply_report_layout_override(cfg, report)

        self.assertEqual(result["page_design"]["size"], "A3")
        self.assertEqual(result["layout"]["pages"][0]["name"], "Extra Page")
        # Styling stays template-controlled — the report only overrides content.
        self.assertEqual(result["colors"], original_colors)
        # Original cfg dict must not be mutated (deepcopy, not in-place) —
        # default_config() has no page_design at all until something sets one.
        self.assertNotIn("page_design", cfg)

    def test_pdf_endpoint_renders_the_report_override_not_the_template(self):
        role = Role.objects.create(
            company=self.company, name=SeededRole.COMPANY_ADMIN, permissions=COMPANY_ADMIN_PERMISSIONS)
        user = User.objects.create_user(email="admin@acme.com", password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=user, role=role)

        override_pages = [{"id": "only", "name": "Only Page", "elements": [
            {"id": "e1", "type": "text", "x": 10, "y": 10, "w": 100, "h": 20, "z": 0,
             "props": {"text": "from the report override, not the template"}},
        ]}]
        report = Report.objects.create(
            company=self.company, project=self.project, template=self.template, title="M",
            layout_override={
                "page_design": {
                    "size": "A4", "orientation": "portrait", "margin_mm": 10,
                    "header_mm": 0, "footer_mm": 0, "show_header": False, "show_footer": False,
                    "show_border": False, "background": "#ffffff", "master_elements": [],
                },
                "layout": {"pages": override_pages},
            })

        client = APIClient()
        client.force_authenticate(user)
        resp = client.get(f"/api/reports/{report.id}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
        # One page, matching the override — not the template's multi-section
        # default (cover, dashboard, tables, ...) — a real signal the override
        # drove the render rather than merely not crashing.
        import fitz
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(doc.page_count, 1)


class LayoutSeedTests(SimpleTestCase):
    """seed_layout_from_sections is pure config -> config logic (no DB/ctx
    needed) — the "Start from my current sections" starting point for
    templates authored before the canvas engine existed."""

    def test_default_config_seeds_a_canvas_layout(self):
        cfg = default_config()
        seeded = seed_layout_from_sections(cfg)
        cfg["page_design"] = seeded["page_design"]
        cfg["layout"] = seeded["layout"]
        self.assertTrue(has_canvas_layout(cfg))

    def test_one_page_per_enabled_section_plus_cover(self):
        cfg = default_config()
        seeded = seed_layout_from_sections(cfg)
        names = [p["name"] for p in seeded["layout"]["pages"]]
        self.assertEqual(names[0], "Cover")  # cover.enabled defaults True
        # area_progress_chart defaults off — every other default-on section
        # should have produced exactly one page (repeat pages count as one
        # entry here; they expand at render time, not at seed time).
        self.assertNotIn("Planned vs Actual by Area", names)
        self.assertIn("Project Info", names)
        self.assertIn("Site Photos", names)
        self.assertIn("Attachments", names)

    def test_cover_skips_master_elements_to_avoid_a_duplicate_logo(self):
        """The cover has its own logo placement; the master header (which
        also carries a logo) would otherwise draw a second one on top of it."""
        cfg = default_config()
        seeded = seed_layout_from_sections(cfg)
        cover = seeded["layout"]["pages"][0]
        self.assertEqual(cover["name"], "Cover")
        self.assertTrue(cover.get("skip_master"))

    def test_everything_off_yields_one_blank_page(self):
        cfg = default_config()
        cfg["cover"]["enabled"] = False
        for key in cfg["sections"]:
            cfg["sections"][key] = False
        seeded = seed_layout_from_sections(cfg)
        pages = seeded["layout"]["pages"]
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["elements"], [])

    def test_repeat_pages_carry_the_right_repeat_rule(self):
        cfg = default_config()
        seeded = seed_layout_from_sections(cfg)
        by_name = {p["name"]: p for p in seeded["layout"]["pages"]}
        self.assertEqual(by_name["Site Photos"]["repeat"],
                         {"source": "photos", "mode": "chunk", "chunk_size": 4})
        self.assertEqual(by_name["Attachments"]["repeat"],
                         {"source": "attachments", "mode": "chunk", "chunk_size": 1})
        self.assertEqual(by_name["Area Dashboards"]["repeat"],
                         {"source": "area_dashboards", "mode": "one_per_item"})

    def test_page_design_follows_page_config(self):
        cfg = default_config()
        cfg["page"] = {"size": "A3", "orientation": "landscape", "margin_mm": 20}
        seeded = seed_layout_from_sections(cfg)
        design = seeded["page_design"]
        self.assertEqual(design["size"], "A3")
        self.assertEqual(design["orientation"], "landscape")
        self.assertEqual(design["margin_mm"], 20)

    def test_no_element_escapes_the_page_bounds(self):
        """Every seeded element's box should sit inside the page it belongs
        to — catches the `_info_table`-in-a-narrow-box overflow class of bug
        (an element whose declared box exceeds the page, not just a Table's
        internal auto-sizing quirk)."""
        cfg = default_config()
        seeded = seed_layout_from_sections(cfg)
        design = seeded["page_design"]
        from .pdf_canvas import _page_size_mm
        pw, ph = _page_size_mm(design)
        for page in seeded["layout"]["pages"]:
            for el in page["elements"] + design["master_elements"]:
                self.assertGreaterEqual(el["x"], 0)
                self.assertGreaterEqual(el["y"], 0)
                self.assertLessEqual(round(el["x"] + el["w"], 1), pw)
                self.assertLessEqual(round(el["y"] + el["h"], 1), ph)


class ReportsApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        admin_role = Role.objects.create(
            company=self.company, name=SeededRole.COMPANY_ADMIN, permissions=COMPANY_ADMIN_PERMISSIONS)
        self.admin = User.objects.create_user(email="admin@acme.com", password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=self.admin, role=admin_role)

        viewer_role = Role.objects.create(
            company=self.company, name="Viewer", permissions=[Permission.VIEW_PROJECTS.value])
        self.viewer = User.objects.create_user(email="viewer@acme.com", password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=self.viewer, role=viewer_role)

        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        self.client = APIClient()

    def test_viewer_cannot_create_template(self):
        self.client.force_authenticate(self.viewer)
        res = self.client.post("/api/report-templates/", {"name": "X"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_admin_creates_template_with_default_config(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/report-templates/", {"name": "Standard"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertIn("colors", res.data["config"])

    def test_report_create_and_pdf_download(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/reports/",
            {"project": str(self.project.id), "title": "Monthly", "report_number": "1"},
            format="json")
        self.assertEqual(res.status_code, 201)
        report_id = res.data["id"]

        pdf = self.client.get(f"/api/reports/{report_id}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(pdf.streaming_content if hasattr(pdf, "streaming_content") else [pdf.content]).startswith(b"%PDF"))

    def test_data_action_trims_repeat_sources_to_light_metadata(self):
        """The Customize tab's page-expansion only needs enough to count and
        label a repeating page's real instances (caption/name) — not the
        underlying image storage key, which this endpoint never exposed."""
        photo = self._progress_image("Poured slab", "2026-01-01")
        report = Report.objects.create(
            company=self.company, project=self.project, title="R", progress_image_ids=[str(photo.id)])

        self.client.force_authenticate(self.admin)
        data = self.client.get(f"/api/reports/{report.id}/data/")
        self.assertEqual(data.status_code, 200)
        self.assertEqual(data.data["photos"], [{"caption": "Poured slab"}])
        self.assertNotIn("logos", data.data)
        self.assertNotIn("_progress", data.data)
        self.assertNotIn("zone_grids", data.data)
        for attachment in data.data["attachments"]:
            self.assertEqual(set(attachment.keys()), {"caption"})
        for area in data.data["area_dashboards"]:
            self.assertEqual(set(area.keys()), {"name"})

    def _progress_image(self, caption, when):
        import datetime as _dt

        from apps.projects.models import Activity, ProgressEntry, ProgressImage, ProjectScope
        zone = ProjectScope.objects.create(company=self.company, project=self.project, scope_type="zone", name="Z")
        act = Activity.objects.create(company=self.company, project=self.project, scope=zone, name="Pour", weight=1)
        entry = ProgressEntry.objects.create(
            company=self.company, project=self.project, activity=act,
            date=_dt.date.fromisoformat(when), progress_percent=50)
        return ProgressImage.objects.create(company=self.company, entry=entry, caption=caption)

    def test_progress_image_picker_select_and_orders_by_date(self):
        # Two schedule photos on different dates; the report should render them
        # earliest-first once selected.
        later = self._progress_image("Later", "2026-03-01")
        earlier = self._progress_image("Earlier", "2026-01-01")
        report = Report.objects.create(company=self.company, project=self.project, title="R")

        self.client.force_authenticate(self.admin)
        listing = self.client.get(f"/api/reports/{report.id}/progress-images/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([p["caption"] for p in listing.data], ["Earlier", "Later"])  # date asc
        self.assertFalse(any(p["selected"] for p in listing.data))

        # Select both (in reverse order) — persisted, then re-sorted by date in PDF.
        put = self.client.put(f"/api/reports/{report.id}/progress-images/",
                              {"selected_ids": [str(later.id), str(earlier.id)]}, format="json")
        self.assertEqual(put.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(set(report.progress_image_ids), {str(later.id), str(earlier.id)})

        from .services import build_report_context
        photos = build_report_context(report)["photos"]
        self.assertEqual([p["caption"] for p in photos], ["Earlier", "Later"])  # earliest first

    def test_reports_need_export_permission(self):
        # A VIEW_PROJECTS-only user can't even read reports — EXPORT_REPORTS gates
        # all report access now (view + download + edit).
        report = Report.objects.create(company=self.company, project=self.project, title="R")
        self.client.force_authenticate(self.viewer)  # VIEW_PROJECTS only
        self.assertEqual(self.client.get("/api/reports/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/reports/{report.id}/pdf/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/reports/{report.id}/progress-images/").status_code, 403)
        put = self.client.put(f"/api/reports/{report.id}/progress-images/",
                              {"selected_ids": []}, format="json")
        self.assertEqual(put.status_code, 403)

    def test_progress_image_picker_rejects_foreign_ids(self):
        report = Report.objects.create(company=self.company, project=self.project, title="R")
        self.client.force_authenticate(self.admin)
        put = self.client.put(f"/api/reports/{report.id}/progress-images/",
                              {"selected_ids": ["not-a-uuid", str(self.project.id)]}, format="json")
        self.assertEqual(put.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.progress_image_ids, [])  # junk + non-progress IDs dropped

    def test_tenant_isolation_on_reports(self):
        other = Company.objects.create(name="Other")
        other_user = User.objects.create_user(email="o@other.com", password=STRONG_PW, company=other)
        role = Role.objects.create(company=other, name="A", permissions=[Permission.EXPORT_REPORTS.value])
        Membership.objects.create(company=other, user=other_user, role=role)
        Report.objects.create(company=self.company, project=self.project, title="Mine")

        self.client.force_authenticate(other_user)
        res = self.client.get("/api/reports/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 0)  # can't see Acme's report

    def test_seed_layout_populates_canvas_from_sections(self):
        template = ReportTemplate.objects.create(company=self.company, name="Legacy MCG")
        self.client.force_authenticate(self.admin)
        res = self.client.post(f"/api/report-templates/{template.id}/seed-layout/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("layout", res.data["config"])
        self.assertIn("page_design", res.data["config"])
        template.refresh_from_db()
        self.assertTrue(has_canvas_layout(merged_config(template.config)))
        # The template's own labels/colors carry through unchanged — seeding
        # only adds page_design/layout, it doesn't touch the rest of config.
        self.assertIn("colors", template.config)

    def test_seed_layout_needs_export_permission(self):
        template = ReportTemplate.objects.create(company=self.company, name="Legacy MCG")
        self.client.force_authenticate(self.viewer)
        res = self.client.post(f"/api/report-templates/{template.id}/seed-layout/")
        self.assertEqual(res.status_code, 403)
