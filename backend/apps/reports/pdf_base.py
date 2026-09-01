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


def resolve_arabic(cfg, project) -> bool:
    """Is this report Arabic (RTL, Arabic month names, etc.)? cfg["language"]
    pins it explicitly ("ar"/"en"); "auto" (the default, for templates saved
    before this setting existed) falls back to guessing from the project
    name or the "summary" label — the guess can be wrong for a template that
    mixes languages, which is exactly why the explicit setting exists."""
    language = cfg.get("language", "auto")
    if language == "ar":
        return True
    if language == "en":
        return False
    return has_arabic(project.get("name")) or has_arabic(cfg["labels"].get("summary"))


# A Latin run that carries its own brackets, inside otherwise-Arabic text.
# Matched so it can be pinned left-to-right before the bidi pass — see shape().
# Must START with a Latin letter. Anchoring on [A-Za-z0-9] instead swallowed
# the digits in front of an Arabic-context bracket too, so the report number in
# "مشروع المنصورة 6 (53)" got pinned along with its preceding "6" and the
# header re-ordered to "مشروع المنصورة(53) 6". A code like "Z(A)" or
# "Building 12(B)" always leads with a letter; a bare "(53)" after Arabic does
# not, and never needed pinning because it has no Latin run to keep it with.
_LTR_BRACKETED = re.compile(r"[A-Za-z][A-Za-z0-9 \-_/.]*[\(\[\{][^\)\]\}]*[\)\]\}]")
_LRM = "‎"  # LEFT-TO-RIGHT MARK


def _pin_ltr_runs(text: str) -> str:
    """Bracket the Latin-with-parens runs in LRM so bidi keeps them intact.

    A closing bracket at the END of a Latin run inside an RTL line has no
    strong character after it, so it takes the paragraph's direction, gets
    mirrored to its opposite, and is reordered to the far side: a zone called
    "PH1 - Z(A)" printed as "(PH1 - Z(A" on every line of the contents page
    (2026-08-30). An LRM either side pins the run left-to-right so its own
    brackets resolve against it instead of against the Arabic around it.

    Only runs that actually contain a bracket are touched — plain Latin words
    inside Arabic already resolve correctly, and marking those would be churn
    for no gain."""
    return _LTR_BRACKETED.sub(lambda m: f"{_LRM}{m.group(0)}{_LRM}", text)


def shape(text) -> str:
    """Reshape + bidi-reorder so Arabic renders correctly; safe for Latin too."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    # The LRM marks exist only to steer the bidi pass; once get_display has
    # produced the visual order they carry no meaning, and Amiri has no glyph
    # for them — left in, they draw as notdef boxes. Strip them afterwards.
    return get_display(arabic_reshaper.reshape(_pin_ltr_runs(text))).replace(_LRM, "")


def format_money(value, currency: str | None) -> str:
    """A money value with its own currency code, e.g. "2,433,242,562.77 EGP".

    Each contract-KPI field (budget/advance payment/contract/approved/
    forecast) carries its OWN currency on Project — a real project can
    genuinely have its budget quoted in EGP and an advance payment paid in
    USD, so this never converts between currencies or assumes one shared
    project-wide currency; it just formats whatever amount+currency pair
    it's given. Both renderers' project_info row list (pdf.py and
    pdf_canvas.py's resolve_table — see Phase 2's "two separate
    implementations" note) call this the same way so the two can't drift."""
    if not value:
        return ""
    return f"{value:,.0f} {currency or ''}".strip()


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


