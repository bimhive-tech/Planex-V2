"""Register section C: the Customize preview shows what the PDF prints.

  C1  chart text in the canvas SVG is laid out as given, not re-reversed by
      the browser's bidi pass
  C2  chart fonts are named the way a browser recognises them
  C3  a right-to-left paragraph wraps in reading order in the PDF
  C4  the canvas is given what the PDF draws with: numbered captions, field
      values, the description's text style, and each table's colours,
      leading, direction and column widths
"""
from django.test import SimpleTestCase, TestCase
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib.units import mm
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, SeededRole
from apps.accounts.models import Company, Membership, Role, User
from apps.projects.models import Project

from .constants import default_config
from .pdf_base import BOLD, FONT_NAME, ensure_fonts, shape
from .pdf_canvas import _source_col_fractions
from .pdf_tables import INFO_LABEL_COL_MM


class CanvasSvgTextTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()

    def _svg(self, *strings):
        from .svg_export import drawing_to_canvas_svg

        d = Drawing(200, 50)
        for s in strings:
            d.add(s)
        return drawing_to_canvas_svg(d)

    def test_every_label_is_pinned_left_to_right(self):
        svg = self._svg(String(10, 10, shape("المخططة"), fontName=FONT_NAME, fontSize=7))
        self.assertIn("direction: ltr; unicode-bidi: bidi-override;", svg)
        # The shaped text itself is untouched.
        self.assertIn(shape("المخططة"), svg)

    def test_pdf_font_names_become_browser_fonts(self):
        svg = self._svg(String(10, 10, "a", fontName=BOLD, fontSize=7),
                        String(10, 20, "b", fontName="Helvetica-Bold", fontSize=7))
        self.assertIn("font-family: Amiri, serif; font-weight: 700", svg)
        self.assertIn("font-family: Helvetica, Arial, sans-serif; font-weight: 700", svg)
        self.assertNotIn("font-family: Amiri-Bold", svg)


class CanvasSvgIdTests(SimpleTestCase):
    """C4: two charts on one canvas page don't share ids, and neither is
    clipped to its box — the PDF clips neither."""

    def test_each_drawing_gets_its_own_ids_and_no_clip(self):
        import re

        from reportlab.graphics.shapes import Rect

        from .svg_export import drawing_to_canvas_svg

        small, large = Drawing(100, 50), Drawing(400, 300)
        small.add(Rect(0, 0, 10, 10))
        large.add(Rect(0, 0, 300, 200))
        a, b = drawing_to_canvas_svg(small), drawing_to_canvas_svg(large)
        clip_a = re.search(r'<clipPath id="([^"]+)"', a).group(1)
        clip_b = re.search(r'<clipPath id="([^"]+)"', b).group(1)
        self.assertNotEqual(clip_a, clip_b)
        self.assertNotIn("clip-path", a + b)


class RightToLeftParagraphWrapTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()

    def test_a_wrapped_arabic_paragraph_starts_with_its_first_words(self):
        from .richtext import html_to_flowables

        text = ("يشمل مشروع تطوير مطار القاهرة توسعة وتطوير منطقة السفر الدولي بمبنى الركاب رقم (3) "
                "اعمال تشطيبات والكتروميكانيك والتيار الخفيف واعمال الجداريات والفرش.")
        cfg = default_config()
        (para,) = html_to_flowables(f"<p>{text}</p>", cfg, None, avail_width=120 * mm)
        lines = para.text.split("<br/>")
        self.assertGreater(len(lines), 1)
        # Each visual line is shaped on its own, in reading order: the first
        # line is the opening words, the last line the closing ones.
        self.assertEqual(lines[0], shape(" ".join(text.split(" ")[:len(lines[0].split(" "))])))
        self.assertTrue(lines[-1].startswith(shape("والفرش.")) or shape("والفرش.") in lines[-1])

    def test_without_a_width_nothing_is_pre_wrapped(self):
        from .richtext import html_to_flowables

        (para,) = html_to_flowables("<p>نص قصير</p>", default_config(), None)
        self.assertNotIn("<br/>", para.text)


class CanvasParityDataTests(TestCase):
    """C4: the endpoints the Customize canvas draws from carry the PDF's own
    text and table style, so the canvas stops approximating them."""

    def setUp(self):
        company = Company.objects.create(name="Acme")
        role = Role.objects.create(company=company, name=SeededRole.COMPANY_ADMIN,
                                   permissions=COMPANY_ADMIN_PERMISSIONS)
        admin = User.objects.create_user(email="admin@acme.com", password="Str0ngPassw0rd!", company=company)
        Membership.objects.create(company=company, user=admin, role=role)
        project = Project.objects.create(company=company, name="برج", project_type=Project.ProjectType.COMMERCIAL)
        self.client = APIClient()
        self.client.force_authenticate(admin)
        res = self.client.post("/api/reports/", {"project": str(project.id), "title": "Monthly",
                                                 "report_number": "1"}, format="json")
        self.report_id = res.data["id"]

    def _override(self, elements):
        return {"layout_override": {"layout": {"pages": [{"id": "p1", "name": "Page 1", "elements": elements}]}}}

    def test_toc_entries_carry_numbered_captions_field_values_and_description_style(self):
        elements = [
            {"id": "tbl", "type": "table", "x": 10, "y": 10, "w": 100, "h": 60, "z": 0,
             "props": {"source": "project_info", "show_caption": True, "caption": "Info"}},
            {"id": "fld", "type": "field", "x": 10, "y": 80, "w": 60, "h": 10, "z": 0,
             "props": {"source": "project.name"}},
            {"id": "pg", "type": "field", "x": 10, "y": 95, "w": 60, "h": 10, "z": 0,
             "props": {"source": "page.number"}},
        ]
        res = self.client.post(f"/api/reports/{self.report_id}/toc-entries/", self._override(elements),
                               format="json")
        self.assertEqual(res.status_code, 200)
        # The caption with its running number, as printed under the table.
        self.assertIn("tbl", res.data["captions"])
        self.assertIn("1", res.data["captions"]["tbl"])
        self.assertIn("Info", res.data["captions"]["tbl"])
        self.assertEqual(res.data["field_values"]["project.name"], "برج")
        # Page-dependent sources stay the canvas's own.
        self.assertNotIn("page.number", res.data["field_values"])
        style = res.data["description_style"]
        self.assertEqual(style["size"], default_config()["fonts"]["base_size"])
        self.assertEqual(style["line_spacing"], float(default_config()["fonts"].get("line_spacing", 1.5)))

    def test_table_style_carries_text_colours_leading_and_direction(self):
        elements = [{"id": "tbl", "type": "table", "x": 10, "y": 10, "w": 100, "h": 60, "z": 0,
                     "props": {"source": "project_info"}}]
        res = self.client.post(f"/api/reports/{self.report_id}/table-data/", self._override(elements),
                               format="json")
        self.assertEqual(res.status_code, 200)
        table = res.data["tables"]["tbl"]
        cfg = default_config()
        self.assertEqual(table["style"]["text_color"], cfg["colors"]["text"])
        self.assertEqual(table["style"]["label_color"], cfg["colors"]["heading"])
        self.assertTrue(table["style"]["rtl"])  # an Arabic project name
        # The info table's label column is the PDF's 50mm, not a browser guess.
        self.assertAlmostEqual(table["col_widths"][0], INFO_LABEL_COL_MM / 100, places=4)

    def test_a_split_table_says_how_many_rows_its_own_page_prints(self):
        elements = [{"id": "tbl", "type": "table", "x": 10, "y": 10, "w": 100, "h": 9, "z": 0,
                     "props": {"source": "project_info", "show_title": False}}]
        body = self._override(elements)
        full = self.client.post(f"/api/reports/{self.report_id}/table-data/", body, format="json")
        total = len(full.data["tables"]["tbl"]["rows"])
        res = self.client.post(f"/api/reports/{self.report_id}/table-overflow/", body, format="json")
        self.assertEqual(res.status_code, 200)
        chunks = res.data["continuations"].get("tbl")
        self.assertTrue(chunks, "a 9mm box holds one row of the info table")
        first = res.data["first_rows"]["tbl"]
        self.assertGreater(first, 0)
        # The page's rows plus every continuation's add up to the table.
        self.assertEqual(first + sum(len(c["rows"]) for c in chunks), total)
        # A continuation page is styled like the page it continues.
        self.assertTrue(chunks[0]["style"]["rtl"])

    def test_info_label_column_fraction_follows_the_box_width(self):
        self.assertEqual(_source_col_fractions("project_info", 200 * mm), [0.25, 0.75])
