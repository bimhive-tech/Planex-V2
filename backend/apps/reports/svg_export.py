"""A chart Drawing as SVG for the Customize canvas — the same drawing the PDF
prints, with its text made to read in a browser exactly as it prints.

Two things differ between a PDF viewer and a browser (register C1/C2):

  direction  reportlab text is already shaped and put in display order
             (pdf_base.shape). A PDF draws it as given; a browser runs its own
             bidi pass over Arabic and reversed every label a second time. The
             text is pinned left-to-right with bidi override so the browser
             lays it out as given, like the PDF.
  fonts      reportlab names fonts by PDF name — "Amiri-Bold",
             "Helvetica-Bold", "Times-Roman" — which no browser recognises, so
             bold labels and the gauge's Latin text fell back to a different
             face. Each is mapped to the family and weight it stands for.
"""
import re

from reportlab.graphics import renderSVG

# PDF font name -> CSS declarations, for every font the charts draw with.
_FONTS = {
    "Amiri": "font-family: Amiri, serif",
    "Amiri-Bold": "font-family: Amiri, serif; font-weight: 700",
    "Helvetica": "font-family: Helvetica, Arial, sans-serif",
    "Helvetica-Bold": "font-family: Helvetica, Arial, sans-serif; font-weight: 700",
    "Times-Roman": "font-family: 'Times New Roman', Times, serif",
    "Times-Bold": "font-family: 'Times New Roman', Times, serif; font-weight: 700",
}

_FONT_FAMILY = re.compile(r"font-family: ([^;\"]+);?")
_TEXT_STYLE = re.compile(r'(<text\b[^>]*\bstyle=")([^"]*)(")')


def _text_style(match):
    style = _FONT_FAMILY.sub(lambda m: _FONTS.get(m.group(1).strip(), m.group(0).rstrip(";")) + ";",
                             match.group(2))
    return f"{match.group(1)}direction: ltr; unicode-bidi: bidi-override; {style}{match.group(3)}"


def drawing_to_canvas_svg(drawing) -> str:
    """`drawing` as an SVG string that renders in a browser the way the PDF
    prints it."""
    return _TEXT_STYLE.sub(_text_style, renderSVG.drawToString(drawing))
