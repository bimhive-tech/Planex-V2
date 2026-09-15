"""A chart Drawing as SVG for the Customize canvas — the same drawing the PDF
prints, with its text made to read in a browser exactly as it prints.

Three things differ between a PDF viewer and a browser (register C1/C2/C4):

  direction  reportlab text is already shaped and put in display order
             (pdf_base.shape). A PDF draws it as given; a browser runs its own
             bidi pass over Arabic and reversed every label a second time. The
             text is pinned left-to-right with bidi override so the browser
             lays it out as given, like the PDF.
  fonts      reportlab names fonts by PDF name — "Amiri-Bold",
             "Helvetica-Bold", "Times-Roman" — which no browser recognises, so
             bold labels and the gauge's Latin text fell back to a different
             face. Each is mapped to the family and weight it stands for.
  ids        every drawing names its clip path "clip". A PDF page draws each
             chart on its own; a web page holds them all in one document, where
             url(#clip) finds the FIRST chart's clip — so every later chart on
             the page was cut to the first one's size. Ids are made unique to
             the drawing.
  clipping   renderSVG clips the drawing to its own bounds; the PDF never does,
             so a label placed just outside the box (a small pie slice's value)
             printed but vanished from the canvas. The clip is dropped.
"""
import hashlib
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
_ID = re.compile(r'\bid="([^"]+)"')
_CLIP_STYLE = re.compile(r'\s*style="clip-path: url\(#[^)]+\)"')


def _text_style(match):
    style = _FONT_FAMILY.sub(lambda m: _FONTS.get(m.group(1).strip(), m.group(0).rstrip(";")) + ";",
                             match.group(2))
    return f"{match.group(1)}direction: ltr; unicode-bidi: bidi-override; {style}{match.group(3)}"


def _unique_ids(svg: str) -> str:
    """Suffix every id, and each reference to it, with a digest of the SVG —
    stable for the same chart, distinct between charts. Two charts that come
    out identical share ids, which is harmless: their clip paths are the same."""
    ids = set(_ID.findall(svg))
    if not ids:
        return svg
    suffix = hashlib.md5(svg.encode("utf-8")).hexdigest()[:10]
    names = "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True))
    svg = re.sub(rf'\bid="({names})"', lambda m: f'id="{m.group(1)}-{suffix}"', svg)
    return re.sub(rf'(url\(#|href="#)({names})([)"])',
                  lambda m: f"{m.group(1)}{m.group(2)}-{suffix}{m.group(3)}", svg)


def drawing_to_canvas_svg(drawing) -> str:
    """`drawing` as an SVG string that renders in a browser the way the PDF
    prints it."""
    svg = _CLIP_STYLE.sub("", renderSVG.drawToString(drawing), count=1)
    return _unique_ids(_TEXT_STYLE.sub(_text_style, svg))
