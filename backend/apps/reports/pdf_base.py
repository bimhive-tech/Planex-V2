"""Shared PDF helpers: font registration, Arabic shaping, color parsing."""
import os
import re
from functools import lru_cache
from io import BytesIO

import arabic_reshaper
from bidi.algorithm import get_display
from django.core.files.storage import default_storage
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
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


def prepared_image(raw, max_dim=1500):
    """Flatten alpha onto white, downscale, and re-encode as JPEG — fast to embed
    and small (raw screenshots with alpha are very slow under reportlab mask=auto)."""
    from PIL import Image as PILImage

    im = PILImage.open(BytesIO(raw))
    if im.mode in ("RGBA", "LA", "P", "PA"):
        im = im.convert("RGBA")
        bg = PILImage.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((max_dim, max_dim))
    out = BytesIO()
    im.save(out, "JPEG", quality=85)
    out.seek(0)
    return out


@lru_cache(maxsize=128)
def cached_image_bytes(key):
    """Read + flatten + downscale an image once per worker. Storage keys are
    immutable UUIDs, so caching by key is safe and avoids repeat R2 fetches."""
    with default_storage.open(key, "rb") as f:
        return prepared_image(f.read()).getvalue()


def storage_image_reader(key):
    """Read a private storage image into ReportLab without exposing its URL."""
    if not key:
        return None
    try:
        return ImageReader(BytesIO(cached_image_bytes(key)))
    except Exception:
        return None


