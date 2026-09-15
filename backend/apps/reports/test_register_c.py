"""Register section C: the Customize preview shows what the PDF prints.

  C1  chart text in the canvas SVG is laid out as given, not re-reversed by
      the browser's bidi pass
  C2  chart fonts are named the way a browser recognises them
  C3  a right-to-left paragraph wraps in reading order in the PDF
"""
from django.test import SimpleTestCase
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib.units import mm

from .constants import default_config
from .pdf_base import BOLD, FONT_NAME, ensure_fonts, shape


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
