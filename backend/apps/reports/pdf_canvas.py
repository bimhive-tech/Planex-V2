"""Canvas-driven PDF renderer: reads a ReportTemplate's Page Designer / Report
Configuration layout (config.page_design + config.layout.pages) and draws each
element at its exact position, instead of the flowing Platypus story the
legacy generator (pdf.py) builds from Content & Labels toggles.

No BaseDocTemplate/Frame/story here — the designer already decided where
everything goes, so this just opens a canvas page per PageInstance and draws.
"""
import logging
from dataclasses import dataclass
from io import BytesIO

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import Paragraph

from .constants import merged_config
from .pdf_base import BOLD, FONT_NAME, ensure_fonts, has_arabic, hexcolor, shape, storage_image_reader
from .pdf_layout import _draw_contained_image, _period_str
from .pdf_tables import _fmt_date

logger = logging.getLogger(__name__)

# Mirrors PAGE_SIZES in frontend/src/lib/reportLayout.ts (portrait, mm).
PAGE_SIZES_MM = {"A4": (210, 297), "A3": (297, 420), "Letter": (216, 279)}

_ALIGN = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}

# Below this box size a chart's internal padding goes negative and ReportLab
# draws garbage rather than a chart — see pdf_charts.py's absolute-point
# padding. Enforced in _draw_chart_element (added in phase 1).
MIN_CHART_W_MM, MIN_CHART_H_MM = 45, 45


@dataclass
class PageInstance:
    """One physical page to render: a LayoutPage plus the repeat context (if
    any) it was expanded from — `scope["item"]` is None for a fixed page."""
    page: dict
    scope: dict
    number: int


def _page_size_mm(design: dict):
    w, h = PAGE_SIZES_MM.get(design.get("size", "A4"), PAGE_SIZES_MM["A4"])
    if design.get("orientation") == "landscape":
        w, h = h, w
    return w, h


def el_box(el: dict, page_h_mm: float):
    """(x, y, w, h) in points, y measured from the page bottom — the one
    conversion that must be exactly right: the designer's canvas is
    mm-from-top-left, ReportLab is points-from-bottom-left."""
    return (
        el["x"] * mm,
        (page_h_mm - el["y"] - el["h"]) * mm,
        el["w"] * mm,
        el["h"] * mm,
    )


def has_canvas_layout(cfg: dict) -> bool:
    """True once a template's canvas has real content — at least one page
    with an element or a repeat rule. Drives the legacy-renderer fallback:
    a template stays on the old Content & Labels engine until its own author
    places the first thing on the canvas."""
    pages = ((cfg.get("layout") or {}).get("pages")) or []
    return any(p.get("elements") or p.get("repeat") for p in pages)


def build_canvas_pdf(report, ctx, *, cfg=None, out_pages=None) -> bytes:
    """Render `ctx` (from services.build_report_context) using the template's
    canvas layout. Mirrors build_report_pdf's signature so views.py can swap
    engines with one branch."""
    ensure_fonts()
    if cfg is None:
        cfg = merged_config(report.template.config if report.template else None)
    ctx.setdefault("arabic", has_arabic(ctx["project"]["name"]) or has_arabic(cfg["labels"].get("summary")))

    design = cfg.get("page_design") or {}
    page_w_mm, page_h_mm = _page_size_mm(design)
    master_elements = design.get("master_elements") or []

    buf = BytesIO()
    c = _canvas.Canvas(buf, pagesize=(page_w_mm * mm, page_h_mm * mm))

    instances = expand_pages(cfg, ctx, report)
    for inst in instances:
        _render_page(c, design, master_elements, inst, cfg, ctx, page_w_mm, page_h_mm)
        c.showPage()
    c.save()

    if out_pages is not None:
        out_pages.update(_anchor_map(instances))
    return buf.getvalue()


def _render_page(c, design, master_elements, inst: PageInstance, cfg, ctx, page_w_mm, page_h_mm):
    bg = design.get("background") or "#ffffff"
    c.setFillColor(hexcolor(bg))
    c.rect(0, 0, page_w_mm * mm, page_h_mm * mm, fill=1, stroke=0)

    if design.get("show_border", True):
        margin = float(design.get("margin_mm", 0)) * mm
        c.saveState()
        c.setStrokeColor(hexcolor("#000000"))
        c.setLineWidth(0.6)
        c.rect(margin, margin, page_w_mm * mm - 2 * margin, page_h_mm * mm - 2 * margin)
        c.restoreState()

    # Master elements always sit behind page content, in their own z-order.
    for el in sorted(master_elements, key=lambda e: e.get("z", 0)):
        _draw_element(c, el, el_box(el, page_h_mm), inst, cfg, ctx)
    for el in sorted(inst.page.get("elements") or [], key=lambda e: e.get("z", 0)):
        _draw_element(c, el, el_box(el, page_h_mm), inst, cfg, ctx)


def _anchor_map(instances: list) -> dict:
    """Best-effort tab->page map for X-Section-Pages (drives ReportDetail.tsx's
    scroll-to-tab). Real source-matching lands in phase 1; for now just anchor
    the cover so the preview doesn't error on a missing key."""
    return {"tab_cover": 1} if instances else {}


# ── Element dispatch ────────────────────────────────────────────────────────

def _draw_element(c, el: dict, box, inst: PageInstance, cfg, ctx):
    x, y, w, h = box
    props = el.get("props") or {}
    t = el.get("type")
    try:
        if t == "rect":
            _draw_rect(c, props, x, y, w, h)
        elif t == "ellipse":
            _draw_ellipse(c, props, x, y, w, h)
        elif t == "line":
            _draw_line(c, props, x, y, w, h)
        elif t == "text":
            _draw_text(c, props, x, y, w, h)
        elif t == "field":
            _draw_field(c, props, x, y, w, h, inst, ctx)
        elif t == "logo":
            _draw_logo(c, props, x, y, w, h, ctx)
        elif t == "image":
            _draw_image(c, props, x, y, w, h, inst, ctx)
        elif t == "table":
            _draw_table_element(c, props, x, y, w, h, inst, cfg, ctx)
        elif t == "chart":
            _draw_chart_element(c, props, x, y, w, h, inst, cfg, ctx)
    except Exception:
        # One bad element shouldn't fail the whole report — same principle as
        # _draw_contained_image's existing "skip the one unreadable image".
        logger.exception("canvas element failed to draw (type=%s)", t)


def _draw_rect(c, props, x, y, w, h):
    fill, stroke = props.get("fill"), props.get("stroke")
    radius = float(props.get("radius", 0)) * mm
    c.saveState()
    if fill:
        c.setFillColor(hexcolor(fill))
    if stroke:
        c.setStrokeColor(hexcolor(stroke))
        c.setLineWidth(float(props.get("stroke_width", 0.5)) * mm)
    if radius:
        c.roundRect(x, y, w, h, radius, fill=1 if fill else 0, stroke=1 if stroke else 0)
    else:
        c.rect(x, y, w, h, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()


def _draw_ellipse(c, props, x, y, w, h):
    fill, stroke = props.get("fill"), props.get("stroke")
    c.saveState()
    if fill:
        c.setFillColor(hexcolor(fill))
    if stroke:
        c.setStrokeColor(hexcolor(stroke))
        c.setLineWidth(float(props.get("stroke_width", 0.5)) * mm)
    c.ellipse(x, y, x + w, y + h, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()


def _draw_line(c, props, x, y, w, h):
    """A `line` element is a thin box on the canvas — draw through its
    vertical centre, spanning its full width."""
    c.saveState()
    c.setStrokeColor(hexcolor(props.get("stroke", "#000000")))
    c.setLineWidth(float(props.get("stroke_width", 0.5)) * mm)
    cy = y + h / 2
    c.line(x, cy, x + w, cy)
    c.restoreState()


def _text_style(props, *, name="canvas_text"):
    size = float(props.get("size", 11))
    return ParagraphStyle(
        name, fontName=BOLD if props.get("bold") else FONT_NAME, fontSize=size, leading=size * 1.3,
        textColor=hexcolor(props.get("color", "#1e2430")),
        alignment=_ALIGN.get(props.get("align", "left"), TA_LEFT),
    )


def _draw_text(c, props, x, y, w, h):
    text = str(props.get("text") or "")
    if not text:
        return
    para = Paragraph(shape(text), _text_style(props))
    _, needed_h = para.wrap(w, h)
    para.drawOn(c, x, y + h - min(needed_h, h))


def _draw_field(c, props, x, y, w, h, inst: PageInstance, ctx):
    value = resolve_field(props.get("source", ""), ctx, inst.scope, inst.number)
    label = props.get("label") if props.get("show_label") else None
    text = f"{label}: {value}" if label else value
    _draw_text(c, {**props, "text": text}, x, y, w, h)


# "company"/"project" are the pre-relabel keys (see reportElements.ts phase-0
# fix) — kept so a template saved before that fix still resolves sensibly.
_LOGO_SLOT = {"left": "left", "right": "right", "cover": "cover", "company": "left", "project": "right"}


def _draw_logo(c, props, x, y, w, h, ctx):
    slot = _LOGO_SLOT.get(props.get("source", "left"), "left")
    entry = (ctx.get("logos") or {}).get(slot)
    reader = storage_image_reader((entry or {}).get("image"))
    if reader:
        _draw_contained_image(c, reader, x, y, w, h)


def _draw_image(c, props, x, y, w, h, inst: PageInstance, ctx):
    """Phase 0: no repeat-item slot yet (phase 2) and no per-report image
    picking (deferred — see plan §7.5). Nothing to draw yet, safe no-op."""
    if props.get("source") == "repeat.item":
        return  # phase 2: scope["items"][props["slot"]]
    return


def _draw_placeholder(c, x, y, w, h, label):
    """A visibly-a-placeholder box — used when a table/chart can't be drawn
    (too small, or not yet implemented) so the gap is obvious, not silent."""
    c.saveState()
    c.setDash(2, 2)
    c.setStrokeColor(hexcolor("#a0a0a0"))
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setFont(FONT_NAME, 7)
    c.setFillColor(hexcolor("#a0a0a0"))
    c.drawCentredString(x + w / 2, y + h / 2, shape(label))
    c.restoreState()


def _draw_table_element(c, props, x, y, w, h, inst: PageInstance, cfg, ctx):
    """Phase 1 fills this in (resolve_table + draw_table_in_box)."""
    _draw_placeholder(c, x, y, w, h, f"Table: {props.get('source', '')}")


def _draw_chart_element(c, props, x, y, w, h, inst: PageInstance, cfg, ctx):
    """Phase 1 fills this in (resolve_chart + renderPDF.draw)."""
    _draw_placeholder(c, x, y, w, h, f"Chart: {props.get('source', '')}")


# ── Field binding ────────────────────────────────────────────────────────────

def resolve_field(source: str, ctx: dict, scope: dict, page_no: int) -> str:
    """Resolve one of reportElements.ts's FIELD_SOURCES against live ctx data.
    Covers every non-item source; `item.*` sources are phase 2."""
    if source.startswith("item."):
        return _resolve_item_field(source, scope)
    if source == "report.period":
        return _period_str(ctx, bool(ctx.get("arabic")))

    project, report = ctx.get("project") or {}, ctx.get("report") or {}
    overall, planned = ctx.get("overall"), ctx.get("planned")
    values = {
        "project.name": project.get("name"),
        "project.code": project.get("code"),
        "project.client": project.get("client"),
        "project.consultant": project.get("consultant"),
        "project.contractor": project.get("contractor"),
        "project.location": project.get("location"),
        "report.title": report.get("title"),
        "report.number": report.get("number"),
        "report.date": _fmt_date(report.get("date")) if report.get("date") else "",
        "progress.overall": f"{overall:.1f}%" if overall is not None else "",
        "progress.planned": f"{planned:.1f}%" if planned is not None else "",
        "page.number": str(page_no),
    }
    return str(values.get(source, "") or "")


def _resolve_item_field(source: str, scope: dict) -> str:
    """Phase 2 fills this in (repeat-page item.* bindings)."""
    return ""


# ── Repeating pages (phase 2 fleshes out _repeat_items) ─────────────────────

def expand_pages(cfg, ctx, report) -> list:
    """Turn config.layout.pages into the physical page sequence: a fixed page
    stays one page; a repeating page clones once per item (or per chunk)."""
    out, n = [], 0
    for page in (cfg.get("layout") or {}).get("pages", []):
        rep = page.get("repeat")
        if not rep:
            n += 1
            out.append(PageInstance(page, {"item": None, "items": [], "index": 0, "count": 1}, n))
            continue
        items = _repeat_items(rep.get("source"), ctx, report)
        if not items:
            continue  # empty source -> page skipped entirely, matches legacy behavior
        cap = int(rep.get("max_pages") or 60)
        if rep.get("mode") == "chunk":
            size = max(1, int(rep.get("chunk_size") or 4))
            groups = [items[i:i + size] for i in range(0, len(items), size)][:cap]
            for i, g in enumerate(groups):
                n += 1
                out.append(PageInstance(page, {"item": g[0] if g else None, "items": g,
                                               "index": i, "count": len(groups)}, n))
        else:
            capped = items[:cap]
            for i, item in enumerate(capped):
                n += 1
                out.append(PageInstance(page, {"item": item, "items": [item], "index": i,
                                               "count": len(capped)}, n))
    return out


def _repeat_items(source, ctx, report) -> list:
    """Phase 2 fills this in — maps a repeat source to its ctx list
    (photos/attachments/area_dashboards/zones/areas)."""
    return []
