"""Shared PDF helpers: font registration, Arabic shaping, color parsing."""
import os
import re

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_NAME = "Amiri"
BOLD = f"{FONT_NAME}-Bold"
_FONTS_READY = False

_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def ensure_fonts():
    """Register the bundled Amiri family once (covers Arabic + Latin)."""
    global _FONTS_READY
    if _FONTS_READY:
        return
    pdfmetrics.registerFont(TTFont(FONT_NAME, os.path.join(FONT_DIR, "Amiri-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, os.path.join(FONT_DIR, "Amiri-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=BOLD)
    _FONTS_READY = True


def has_arabic(text) -> bool:
    return bool(text) and bool(_ARABIC_RE.search(str(text)))


def shape(text) -> str:
    """Reshape + bidi-reorder so Arabic renders correctly; safe for Latin too."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(text))


def hexcolor(value, fallback="#000000"):
    try:
        return colors.HexColor(value)
    except Exception:
        return colors.HexColor(fallback)
