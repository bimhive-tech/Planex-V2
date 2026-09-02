"""Canvas-driven PDF renderer: reads a ReportTemplate's Page Designer / Report
Configuration layout (config.page_design + config.layout.pages) and draws each
element at its exact position, instead of the flowing Platypus story the
legacy generator (pdf.py) builds from Content & Labels toggles.

No BaseDocTemplate/Frame/story here — the designer already decided where
everything goes, so this just opens a canvas page per PageInstance and draws.
"""
import logging
from functools import partial
from dataclasses import dataclass
from io import BytesIO

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import Frame, Paragraph

from .constants import merged_config
from .pdf_base import BOLD, FONT_NAME, ensure_fonts, format_money, hexcolor, resolve_arabic, shape, storage_image_reader
from .pdf_charts import (
    area_progress_chart,
    area_units_chart,
    boq_financial_progress_chart,
    budget_total_cost_chart,
    cashflow_chart,
    cashflow_curve,
    duration_pie,
    gantt_chart,
    invoice_status_chart,
    overall_donut,
    planned_actual_chart,
    progress_comparison_chart,
    progress_tracking_chart,
    scurve_chart,
    speedometer_chart,
    submittals_breakdown_chart,
    zone_duration_pie,
)
from .pdf_layout import _draw_contained_image, _period_str, draw_fitted_image
from .pdf_tables import (
    _data_table as _data_table_impl, _fmt_date,
    _hierarchy_table_flat as _hierarchy_table_flat_impl,
    _info_table as _info_table_impl, _pct_or_dash, _styles,
    _wrap_shape, apply_table_overrides, draw_table_in_box, enum_label,
    table_style_override,
)

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
    any) it was expanded from — `scope["item"]` is None for a fixed page.

    The last three fields are set only by `_expand_table_overflow` (a table
    element with more rows than fit its box gets continued onto extra
    synthetic pages rather than truncated) — every other caller leaves them
    at their defaults and can ignore them entirely."""
    page: dict
    scope: dict
    number: int
    # Set on a synthetic continuation page: draw ONLY this one element
    # (using `continues_chunk`, already split to fit and guaranteed to),
    # never the rest of the original page's content — that already appeared
    # on the page(s) before it.
    continues_element: dict | None = None
    continues_chunk: object | None = None
    # Set on the ORIGINAL page of a table that overflows: {element_id: first
    # chunk}, so _draw_table_element draws the same pre-split piece
    # _expand_table_overflow already computed instead of resolving and
    # splitting the table a second time.
    table_chunk0: dict | None = None
    # Same idea as table_chunk0/continues_element+continues_chunk above, for
    # a "description" element (see _expand_description_overflow) — a whole
    # pre-paginated *list* of flowables per page (paragraphs + any embedded
    # tables/charts/images), not one Table piece, since a description mixes
    # several flowable types in sequence.
    description_flow0: dict | None = None
    continues_flow: list | None = None
    # Same idea again, for a "toc" element whose real row count (list of
    # captioned tables/figures/images, or the page list itself) runs past
    # its own box — see _expand_toc_overflow. `(start, end)` indices slice
    # the element's full row list (always read fresh from ctx at draw time,
    # never captured as literal rows here — those indices stay valid even
    # though the exact page numbers inside that row list get recomputed
    # after this splicing pass shifts everything, but the SET of rows at
    # each index doesn't move).
    toc_rows0: dict | None = None
    continues_toc_rows: tuple | None = None


def _page_size_mm(design: dict, page: dict | None = None):
    """A page's real size — its own `orientation` override (Phase 4's
    "per-page landscape override": a page's own designer setting, e.g. an
    executive-dashboard page that wants to be landscape while the rest of
    the report stays portrait) when it has one, else the template's default.
    `page=None` (no per-page context, e.g. the outer `build_canvas_pdf` call
    that seeds the initial Canvas size before any real page is known) always
    uses the template default."""
    w, h = PAGE_SIZES_MM.get(design.get("size", "A4"), PAGE_SIZES_MM["A4"])
    orientation = (page or {}).get("orientation") or design.get("orientation")
    if orientation == "landscape":
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


def _master_x(el: dict, page_w_mm: float, default_w_mm: float):
    """Horizontal placement (x, w) in mm for a master element on a page whose
    width differs from the one it was authored against.

    Header and footer bands are laid out against the page EDGES, so an element
    keeps whichever edge it was placed against rather than its absolute x. A
    right-hand logo authored at x=150 on a 210mm portrait page otherwise landed
    two-thirds of the way across a 297mm landscape one, and a centred title sat
    left of centre — which is what "the header still thinks it's in portrait"
    looked like (reported 2026-09-02).

    Full-width rules keep both insets and simply stretch.
    """
    x, w = float(el["x"]), float(el["w"])
    if abs(page_w_mm - default_w_mm) < 0.01:
        return x, w
    right_inset = default_w_mm - (x + w)
    if w >= default_w_mm * 0.9:          # a full-width rule or band
        return x, max(1.0, page_w_mm - x - right_inset)
    centre = x + w / 2
    if centre < default_w_mm / 3:        # anchored left
        return x, w
    if centre > default_w_mm * 2 / 3:    # anchored right
        return max(0.0, page_w_mm - right_inset - w), w
    return max(0.0, (page_w_mm - w) / 2), w   # centred stays centred


def _master_box(el: dict, design: dict, page_w_mm: float, page_h_mm: float,
                default_w_mm: float, default_h_mm: float):
    """(x, y, w, h) in points for one master element on a page whose size may
    differ from the one the master was authored against.

    Header-band elements keep their distance from the TOP; footer-band ones
    keep their distance from the BOTTOM. Anything in between is left on its
    authored y. Horizontally, see _master_x. See _render_page for the bug the
    vertical half of this fixes."""
    x_mm, w_mm = _master_x(el, page_w_mm, default_w_mm)
    if abs(page_h_mm - default_h_mm) < 0.01:
        return (x_mm * mm, (page_h_mm - float(el["y"]) - float(el["h"])) * mm,
                w_mm * mm, float(el["h"]) * mm)
    y, h = float(el["y"]), float(el["h"])
    # "Below the midpoint of the page it was authored for" is the practical
    # test for a footer element — the master only ever holds a header band and
    # a footer band, so there's nothing ambiguous in the middle to misclassify.
    if y + h / 2 > default_h_mm / 2:
        from_bottom = default_h_mm - (y + h)
        return (x_mm * mm, from_bottom * mm, w_mm * mm, h * mm)
    return (x_mm * mm, (page_h_mm - y - h) * mm, w_mm * mm, h * mm)


def _continuation_box(el: dict, design: dict, page_w_mm: float, page_h_mm: float):
    """(x, y, w, h) in points for a table's overflow on a continuation page.

    Keeps the element's own horizontal placement and width — the columns must
    line up with the first part of the table — but moves it to the top of the
    content area and gives it the full height down to the bottom margin, since
    nothing else is on the page. See _render_page for why."""
    margin = float(design.get("margin_mm", 0) or 0)
    header = float(design.get("header_mm", 0) or 0) if design.get("show_header", True) else 0.0
    footer = float(design.get("footer_mm", 0) or 0) if design.get("show_footer", True) else 0.0
    top_mm = margin + header
    avail_h_mm = max(10.0, page_h_mm - top_mm - margin - footer)
    # Centred, not left at the source element's x. The width has to stay the
    # element's own — the chunks were already split and their columns sized
    # against it, so widening here would only stretch the box, not the table —
    # but a table authored on the right-hand half of its source page inherited
    # that offset on every continuation page, leaving the left ~40% dead on 11
    # pages (2026-08-30). Centring spreads the leftover evenly instead.
    x_mm = max(margin, (page_w_mm - float(el["w"])) / 2)
    return (
        x_mm * mm,
        (page_h_mm - top_mm - avail_h_mm) * mm,
        el["w"] * mm,
        avail_h_mm * mm,
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
    ctx.setdefault("arabic", resolve_arabic(cfg, ctx["project"]))
    ctx.setdefault("_report", report)  # detailed_progress's lazy zone_grids needs report.project/scope_ids

    design = cfg.get("page_design") or {}
    page_w_mm, page_h_mm = _page_size_mm(design)
    master_elements = design.get("master_elements") or []

    buf = BytesIO()
    c = _canvas.Canvas(buf, pagesize=(page_w_mm * mm, page_h_mm * mm))

    instances = expand_pages(cfg, ctx, report)
    # A "description" element (or a table) with more content than fits its
    # box continues onto extra pages spliced in right after it, rather than
    # spilling past the box or truncating — renumbers everything after it,
    # so both of these must run before anything below reads `inst.number`.
    # Description runs first; each pass skips whatever the other already
    # claimed (see their own guards), so a page with both an overflowing
    # description AND an overflowing table still gets exactly one of them
    # handled properly rather than double-splicing the same page.
    instances = _expand_description_overflow(instances, cfg, ctx, design)
    instances = _expand_table_overflow(instances, cfg, ctx, design)

    def _index_toc_context(instances):
        # One row per distinct page id (a repeat page's many clones collapse
        # to its first — a table's continuation pages share their original
        # page's id too, so they collapse the same way and never get their
        # own TOC row).
        toc_map, toc_order, seen = {}, [], set()
        for inst in instances:
            pid = inst.page.get("id")
            if pid not in toc_map:
                toc_map[pid] = inst.number
            if pid not in seen:
                seen.add(pid)
                toc_order.append((pid, inst.page.get("name") or ""))
        ctx["_toc_map"], ctx["_toc_order"] = toc_map, toc_order

    # First pass: real row COUNTS for every "toc" element (both the
    # "contents" page list and the captioned-tables/figures/images variants
    # — see _collect_captions) so _expand_toc_overflow below can tell
    # whether/how each one needs to paginate. The exact page NUMBER next to
    # each row can still be stale here — splicing toc-overflow continuation
    # pages shifts numbering for everything after them, so both indexes are
    # rebuilt below on the final, renumbered instances before anything
    # actually draws.
    _index_toc_context(instances)
    _collect_captions(instances, cfg, ctx)
    instances = _expand_toc_overflow(instances, cfg, ctx, design)
    _index_toc_context(instances)
    _collect_captions(instances, cfg, ctx)

    for inst in instances:
        # This exact page's own size — its `orientation` override if it has
        # one, else the template default. ReportLab supports a genuinely
        # variable page size across one Canvas (setPageSize before that
        # page's own showPage), the same mechanism the legacy flowing
        # renderer already uses for its one always-landscape dashboard page
        # — this just makes it a per-page *choice*, not a hardcoded one page.
        pw, ph = _page_size_mm(design, inst.page)
        c.setPageSize((pw * mm, ph * mm))
        _render_page(c, design, master_elements, inst, cfg, ctx, pw, ph)
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
        # Independent of the content margin — a template can pull the frame
        # in tighter to the edge (or push it out) without moving the content.
        # Falls back to margin_mm so a template saved before this field
        # existed renders exactly as it always did.
        offset = design.get("border_offset_mm")
        offset = float(offset if offset is not None else design.get("margin_mm", 0)) * mm
        c.saveState()
        c.setStrokeColor(hexcolor("#000000"))
        c.setLineWidth(0.6)
        c.rect(offset, offset, page_w_mm * mm - 2 * offset, page_h_mm * mm - 2 * offset)
        c.restoreState()

    # Master elements always sit behind page content, in their own z-order —
    # unless this page opts out (e.g. a bespoke cover that shouldn't show
    # the running header/footer). A continuation page still gets the running
    # header/footer like any other page of the report.
    if not inst.page.get("skip_master"):
        # The master is authored against the template's DEFAULT page size. On a
        # page that flips orientation, anything anchored near the bottom (the
        # footer band, and the page number in it) has to keep its distance from
        # the bottom rather than its absolute y — otherwise a footer authored at
        # y=280 on a 297mm portrait page lands off the end of a 210mm landscape
        # one and simply never prints. That's why 13 landscape pages carried a
        # full running header and no page number at all, while the contents and
        # figure lists cited them by number (2026-08-30).
        default_w_mm, default_h_mm = _page_size_mm(design)
        for el in sorted(master_elements, key=lambda e: e.get("z", 0)):
            box = _master_box(el, design, page_w_mm, page_h_mm, default_w_mm, default_h_mm)
            _draw_element(c, el, box, inst, cfg, ctx)

    if inst.continues_element is not None:
        # A synthetic page holding only the overflow of one table — the
        # page's other elements (title, other charts...) already drew on
        # the page(s) before it and shouldn't repeat here.
        #
        # The continuation REFLOWS to the top of the content area instead of
        # reusing the element's own box. A table placed halfway down its
        # source page (under a heading and a chart) would otherwise start
        # halfway down every continuation page too, leaving the top half of
        # each blank — 16 pages of this report were empty to the midpoint
        # with a 10-row fragment below, which reads as a printing fault
        # (2026-08-30). Reflowing also fits ~18 rows per page instead of 10,
        # matching what the reference report's own continuation pages do.
        el = inst.continues_element
        _draw_element(c, el, _continuation_box(el, design, page_w_mm, page_h_mm), inst, cfg, ctx)
        return

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
    # Clockwise degrees around the box's own center — rotate the coordinate
    # system itself so every _draw_* below draws at its normal (x, y, w, h)
    # and just ends up rotated, instead of each one needing its own rotation
    # math. ReportLab's rotate() is counter-clockwise, hence the negation to
    # match the canvas editor's (clockwise, CSS-style) convention.
    rotation = float(el.get("rotation") or 0)
    if rotation:
        c.saveState()
        cx, cy = x + w / 2, y + h / 2
        c.translate(cx, cy)
        c.rotate(-rotation)
        c.translate(-cx, -cy)
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
            _draw_image(c, props, x, y, w, h, inst, ctx, el.get("id"))
        elif t == "table":
            _draw_table_element(c, props, x, y, w, h, inst, cfg, ctx, el.get("id"))
        elif t == "chart":
            _draw_chart_element(c, props, x, y, w, h, inst, cfg, ctx, el.get("id"))
        elif t == "toc":
            _draw_toc_element(c, props, x, y, w, h, inst, ctx, el.get("id"))
        elif t == "description":
            _draw_description_element(c, props, x, y, w, h, inst, cfg, ctx, el.get("id"))
    except Exception:
        # One bad element shouldn't fail the whole report — same principle as
        # _draw_contained_image's existing "skip the one unreadable image".
        logger.exception("canvas element failed to draw (type=%s)", t)
    finally:
        if rotation:
            c.restoreState()


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
    # Shape each line separately, then join with <br/> — shape() bidi-reorders
    # per call, and a multi-line field (e.g. project.description) needs each
    # line reordered on its own, not the whole block as one bidi run.
    body = "<br/>".join(shape(line) for line in text.splitlines()) or shape(text)
    para = Paragraph(body, _text_style(props))
    _, needed_h = para.wrap(w, h)
    para.drawOn(c, x, y + h - min(needed_h, h))


def _draw_field(c, props, x, y, w, h, inst: PageInstance, ctx):
    # A manual override (edited via the Customize tab's canvas) replaces the
    # live-computed value outright — `is not None` so an intentionally
    # blanked-out field stays blank instead of falling back to the real one.
    override = props.get("value_override")
    value = override if override is not None else resolve_field(
        props.get("source", ""), ctx, inst.scope, inst.number, inst.page.get("name") or "",
    )
    label = props.get("label") if props.get("show_label") else None
    text = f"{label}: {value}" if label else value
    _draw_text(c, {**props, "text": text}, x, y, w, h)


# "company"/"project" are the pre-relabel keys (see reportElements.ts phase-0
# fix) — kept so a template saved before that fix still resolves sensibly.
_LOGO_SLOT = {"left": "left", "right": "right", "cover": "cover", "company": "left", "project": "right"}


def _draw_image_border(c, props, x, y, w, h):
    """Opt-in border on an image/logo box — a checkbox in the Properties
    panel instead of the old workaround of stacking a separate rect element
    on top by hand."""
    if not props.get("border"):
        return
    c.saveState()
    c.setStrokeColor(hexcolor(props.get("border_color", "#000000")))
    c.setLineWidth(float(props.get("border_width", 0.3)) * mm)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.restoreState()


def _draw_logo(c, props, x, y, w, h, ctx):
    source = props.get("source", "left")
    if source == "upload":
        _draw_uploaded_image(c, props, x, y, w, h, ctx)
        return
    logos = ctx.get("logos") or {}
    if source == "extra":
        # Beyond the fixed left/right slots — any number of uploaded partner
        # logos, picked by index (same `slot` pattern as a repeat photo box).
        extra = logos.get("extra") or []
        idx = int(props.get("slot", 0) or 0)
        entry = extra[idx] if 0 <= idx < len(extra) else None
    else:
        entry = logos.get(_LOGO_SLOT.get(source, "left"))
    reader = storage_image_reader((entry or {}).get("image"))
    if reader:
        _draw_contained_image(c, reader, x, y, w, h)
    _draw_image_border(c, props, x, y, w, h)


_CAPTION_H = 8 * mm
_TITLE_H = 7 * mm


def _draw_caption_text(c, x, y, w, caption_h, text):
    """Centered caption strip under a table/chart/image box — one shared
    look for every captioned element type."""
    style = ParagraphStyle("canvas_caption", fontName=FONT_NAME, fontSize=8, leading=10,
                           textColor=hexcolor("#595959"), alignment=TA_CENTER)
    # _wrap_shape, not a bare shape(): a caption long enough to wrap was
    # shaped as one string and then re-broken by reportlab left-to-right, so
    # the logically-FIRST words ended up on the LAST line — "رسم توضيحي" sat
    # underneath its own figure number (2026-08-30). Shaping per line after
    # the break points are known is the same rule the table values already
    # follow; see pdf_tables._wrap_shape.
    para = Paragraph(_wrap_shape(text, style.fontName, style.fontSize, w), style)
    para.wrap(w, caption_h)
    para.drawOn(c, x, y)


def _draw_title_text(c, x, y, w, title_h, text):
    """Bold, centered title strip above a table/chart box — see
    _table_or_chart_title's docstring for why this defaults to shown."""
    style = ParagraphStyle("canvas_title", fontName=BOLD, fontSize=9, leading=11,
                           textColor=hexcolor("#1e2430"), alignment=TA_CENTER)
    para = Paragraph(_wrap_shape(text, style.fontName, style.fontSize, w), style)
    para.wrap(w, title_h)
    para.drawOn(c, x, y)


def _table_or_chart_title(props, cfg):
    """The title text a table/chart element draws above its own box, or None
    when explicitly turned off. Defaults to **shown** (missing/unset
    `show_title` counts as on, unlike `show_caption`'s default-off) — every
    chart/table needs a real, visible title rather than relying on
    surrounding page context to say what it is (Phase 5 feedback: a reader
    had no way to tell an SPI gauge from a completion donut from a bar chart
    without one). Text defaults to the same source-name lookup captions
    already use (`cfg["labels"].get(source, source)`), overridable per
    element the same way a caption's text is."""
    if props.get("show_title") is False:
        return None
    return props.get("title_text") or cfg["labels"].get(props.get("source", ""), props.get("source", ""))


def _draw_fitted_image(c, reader, x, y, w, h, props):
    """draw_fitted_image, reading its fit/focal_x/focal_y from this element's
    own props — the "image" element's Properties-panel "Fit" control
    (cover/contain) plus the focal-point crop offset, only meaningful for
    cover (see draw_fitted_image's docstring)."""
    draw_fitted_image(
        c, reader, x, y, w, h,
        fit=str(props.get("fit", "contain")),
        focal_x=float(props.get("focal_x", 50)), focal_y=float(props.get("focal_y", 50)),
    )


def _draw_image(c, props, x, y, w, h, inst: PageInstance, ctx, el_id=None):
    """`repeat.item` binds this box to one photo/attachment in the current
    repeat chunk (props["slot"] indexes inst.scope["items"]) — this is what
    lets a 4-slot "Site Photos" page turn into N real pages. `upload` binds it
    to one specific image uploaded directly to this element (a ReportImage
    with kind=canvas, props["upload_id"] its id) — for a plain non-repeat box
    that isn't a project logo or a repeat photo slot."""
    source = props.get("source")
    if source == "upload":
        _draw_uploaded_image(c, props, x, y, w, h, ctx)
        return
    if source != "repeat.item":
        return
    items = inst.scope.get("items") or []
    slot = int(props.get("slot", 0) or 0)
    if slot >= len(items):
        return
    item = items[slot] or {}
    show_caption = bool(props.get("show_caption"))
    caption_h = _CAPTION_H if show_caption else 0
    reader = storage_image_reader(item.get("image"))
    if reader:
        _draw_fitted_image(c, reader, x, y + caption_h, w, h - caption_h, props)
    _draw_image_border(c, props, x, y + caption_h, w, h - caption_h)
    if show_caption and item.get("caption"):
        # Text (with its running "صورة N:" number) was already assigned by
        # the _collect_captions pre-pass — see build_canvas_pdf.
        text = (ctx.get("_image_caption_text") or {}).get((id(inst), el_id))
        if text:
            _draw_caption_text(c, x, y, w, caption_h, text)


def _draw_uploaded_image(c, props, x, y, w, h, ctx):
    upload_id = props.get("upload_id")
    report = ctx.get("_report")
    if not upload_id or report is None:
        return
    from .models import ReportImage

    try:
        image = ReportImage.objects.get(id=upload_id, report=report)
    except (ReportImage.DoesNotExist, ValueError, TypeError):
        return
    reader = storage_image_reader(image.image.name if image.image else None)
    if reader:
        _draw_fitted_image(c, reader, x, y, w, h, props)
    _draw_image_border(c, props, x, y, w, h)


_TOC_CAPTION_LISTS = {
    "tables": "_table_captions",
    "figures": "_figure_captions",
    "images": "_image_captions",
}


def _toc_rows(props: dict, ctx: dict, inst: PageInstance) -> list:
    """The full, un-paginated `[(name, page_number), ...]` list a "toc"
    element's `variant` resolves to — shared by _draw_toc_element (which may
    only draw a slice of it, see toc_rows0/continues_toc_rows) and
    _expand_toc_overflow (which needs the real total count before it can
    decide whether/how to paginate it at all)."""
    variant = props.get("variant", "contents")
    if variant in _TOC_CAPTION_LISTS:
        return list(ctx.get(_TOC_CAPTION_LISTS[variant]) or [])
    toc_map, toc_order = ctx.get("_toc_map") or {}, ctx.get("_toc_order") or []
    own_id = inst.page.get("id")
    exclude_cover = props.get("exclude_cover", True)
    # A manual override (edited via the Customize tab's canvas) replaces
    # this row's displayed name only — the page's own title elsewhere is
    # untouched, same as a table cell override doesn't change the project
    # data it was read from.
    name_overrides = props.get("name_overrides") or {}
    rows = []
    for pid, name in toc_order:
        if pid == own_id or pid not in toc_map:
            continue
        if exclude_cover and name.strip().lower() in ("cover",):
            continue
        rows.append((name_overrides.get(pid, name), toc_map[pid]))
    return rows


def _toc_capacity(props: dict, h: float) -> int:
    """How many rows fit `h` points of box height at this element's own
    font size/row height — shared by _draw_toc_element and
    _expand_toc_overflow so pagination always splits exactly where the real
    draw pass would anyway have stopped."""
    size = float(props.get("size", 11))
    row_h = float(props.get("row_height", 8)) * mm
    return max(1, int((h - size) // row_h) + 1)


def _draw_toc_element(c, props, x, y, w, h, inst: PageInstance, ctx, el_id=None):
    """`variant` (default "contents") picks what this element lists:
    "contents" — every other page in the template, its real resolved page
    number, from build_canvas_pdf's toc_map/toc_order pre-pass; "tables" /
    "figures" / "images" — every captioned table/chart/photo instead, in
    the order they were drawn (build_canvas_pdf's _collect_captions
    pre-pass). Same dot-leader visual either way — only where `rows` comes
    from differs.

    A list longer than one page's worth continues onto extra synthetic
    pages (see _expand_toc_overflow) exactly like an overflowing table
    does — `toc_rows0`/`continues_toc_rows` (both index ranges into the
    SAME always-fresh-from-ctx row list, never a captured copy) say which
    slice this particular page draws; a page with neither draws the whole
    list, safe on any box that was never going to overflow in the first
    place."""
    size = float(props.get("size", 11))
    row_h = float(props.get("row_height", 8)) * mm
    color = hexcolor(props.get("color", "#1e2430"))
    rtl = bool(ctx.get("arabic"))

    rows = _toc_rows(props, ctx, inst)
    chunk0 = (inst.toc_rows0 or {}).get(el_id) if el_id else None
    if chunk0 is not None:
        rows = rows[chunk0[0]:chunk0[1]]
    elif inst.continues_toc_rows is not None:
        start, end = inst.continues_toc_rows
        rows = rows[start:end]

    c.setFont(FONT_NAME, size)
    cy = y + h - size
    for name, number in rows:
        if cy < y:
            break  # a slice's own last row already accounts for the box's real capacity — this is now just a safety net
        numstr = str(number)
        num_w = stringWidth(numstr, FONT_NAME, size)
        label = shape(name)
        label_w = stringWidth(label, FONT_NAME, size)
        c.setFillColor(color)
        if rtl:
            c.drawRightString(x + w, cy, label)
            c.drawString(x, cy, numstr)
            dot_x0, dot_x1 = x + num_w + 2, x + w - label_w - 2
        else:
            c.drawString(x, cy, label)
            c.drawRightString(x + w, cy, numstr)
            dot_x0, dot_x1 = x + label_w + 2, x + w - num_w - 2
        if dot_x1 > dot_x0:
            c.saveState()
            c.setDash(1, 2)
            c.setStrokeColor(hexcolor("#a0a0a0"))
            c.line(dot_x0, cy + size * 0.15, dot_x1, cy + size * 0.15)
            c.restoreState()
        cy -= row_h


def _draw_placeholder(c, x, y, w, h, label):
    """A visibly-a-placeholder box, for a box whose SIZE is the problem
    ("too small") — a layout mistake the author has to see and fix.

    Deliberately not used for a source that simply resolves to no data: that
    used to print a dashed "No data: zone_progress" box straight into a
    client deliverable (found 2026-08-30 against the client's reference
    report, where no panel is ever empty). Those now draw nothing at all, and
    the signal lives where it's actionable instead — the Customize tab
    resolves every element through this same code and shows a per-element
    "No data" state (see views.chart_svgs / views.table_data)."""
    c.saveState()
    c.setDash(2, 2)
    c.setStrokeColor(hexcolor("#a0a0a0"))
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setFont(FONT_NAME, 7)
    c.setFillColor(hexcolor("#a0a0a0"))
    c.drawCentredString(x + w / 2, y + h / 2, shape(label))
    c.restoreState()


def _draw_table_element(c, props, x, y, w, h, inst: PageInstance, cfg, ctx, el_id=None):
    # A synthetic continuation page (see _expand_table_overflow): the chunk
    # assigned to THIS page is already split to fit this exact box — drawn
    # verbatim, nothing left to resolve or re-split.
    if inst.continues_chunk is not None:
        _, chunk_h = inst.continues_chunk.wrap(w, h)
        inst.continues_chunk.drawOn(c, x, y + h - chunk_h)
        return

    show_caption = bool(props.get("show_caption"))
    caption_h = _CAPTION_H if show_caption else 0
    title = _table_or_chart_title(props, cfg)
    title_h = _TITLE_H if title else 0
    content_h = h - caption_h - title_h

    source = props.get("source", "")
    table = resolve_table(
        source, cfg, ctx, inst.scope, avail_width=w, overrides=props.get("overrides"), style=props,
        scope_zone_id=props.get("scope_zone_id"),
    )
    if table is None:
        return  # nothing real to draw — see _draw_placeholder's docstring

    # This table's first chunk was already computed (and its overflow into
    # continuation pages already spliced in) by _expand_table_overflow —
    # draw that same piece rather than resolving/splitting it again.
    chunk0 = (inst.table_chunk0 or {}).get(el_id) if el_id else None
    if chunk0 is not None:
        _, chunk_h = chunk0.wrap(w, content_h)
        chunk0.drawOn(c, x, y + caption_h + content_h - chunk_h)
    elif not draw_table_in_box(c, table, x, y + caption_h, w, content_h):
        # Same reasoning as the chart case above — an author-facing note must
        # not print into the client's copy.
        return

    if show_caption:
        # Text (with its running "جدول N:" number) was already assigned by
        # the _collect_captions pre-pass — see build_canvas_pdf.
        text = (ctx.get("_table_caption_text") or {}).get((id(inst), el_id))
        if text:
            _draw_caption_text(c, x, y, w, caption_h, text)
    if title:
        _draw_title_text(c, x, y + h - title_h, w, title_h, title)


def _draw_chart_element(c, props, x, y, w, h, inst: PageInstance, cfg, ctx, el_id=None):
    source = props.get("source", "")
    show_caption = bool(props.get("show_caption"))
    caption_h = _CAPTION_H if show_caption else 0
    title = _table_or_chart_title(props, cfg)
    title_h = _TITLE_H if title else 0
    content_h = h - caption_h - title_h
    min_w, min_h = MIN_CHART_W_MM * mm, MIN_CHART_H_MM * mm
    if w < min_w or content_h < min_h:
        # Draw nothing, same as the no-data case: a dashed "Chart too small"
        # box is a note to the report's author, and printing it into the
        # finished document puts it in front of the client instead (found
        # 2026-08-30 — one had already gone out in a draft). The Customize
        # tab flags this per element, where the author can act on it.
        return
    drawing = resolve_chart(
        source, props.get("chart_type"), cfg, ctx, inst.scope, w, content_h, scope_zone_id=props.get("scope_zone_id"),
    )
    if drawing is None:
        return  # nothing real to draw — see _draw_placeholder's docstring
    from reportlab.graphics import renderPDF
    renderPDF.draw(drawing, c, x, y + caption_h)

    if show_caption:
        text = (ctx.get("_figure_caption_text") or {}).get((id(inst), el_id))
        if text:
            _draw_caption_text(c, x, y, w, caption_h, text)
    if title:
        _draw_title_text(c, x, y + h - title_h, w, title_h, title)


def _effective_description_html(props: dict, ctx: dict) -> str:
    """The description element's real html — its own authored content
    (`props.html`) when set, else a live fallback built from the project's
    own `description` field.

    Keeps a report on a not-yet-customized template showing its own real
    project narrative, instead of either a blank box or (the bug this
    replaced, found 2026-08-30) one *specific* project's own description
    text baked directly into the shared, reusable template's default — the
    next report built from that template, for a different project, would
    have silently inherited the wrong client's own words. A report author
    who wants different/richer content (with inline embeds) still just
    double-clicks and types on the canvas — that becomes `props.html` and
    this fallback never runs again for that element."""
    html = props.get("html") or ""
    if html:
        return html
    import html as html_lib

    project = ctx.get("project") or {}
    # The RICH narrative first, and only then the plain-text one. `description`
    # is a tag-stripped copy of `description_html` produced without separators
    # between block elements, so it arrives as one unbroken run: a heading
    # fuses straight into the sentence after it ("نظرة عامة على المشروعبلغت").
    # Worse, wrapping it is what reversed the page: shape() bidi-reorders the
    # WHOLE string, and reportlab then breaks that already-visually-ordered
    # run left-to-right, so the logical END of the text landed on the FIRST
    # line and the opening heading on the last. Feeding the real HTML instead
    # gives html_to_flowables its block boundaries back — each becomes its own
    # short paragraph, shaped individually, in the right order, with headings
    # and lists intact (found 2026-08-30 looking at the rendered page; the
    # extracted text alone reads as mere concatenation and hides the reversal).
    rich = project.get("description_html") or ""
    if rich:
        return rich

    plain = project.get("description") or ""
    lines = [line.strip() for line in plain.split("\n") if line.strip()]
    return "".join(f"<p>{html_lib.escape(line)}</p>" for line in lines)


def _draw_description_element(c, props, x, y, w, h, inst: PageInstance, cfg, ctx, el_id=None):
    """This element's own rich text (`props.html`, or a live fallback — see
    `_effective_description_html`), including any inline table/chart/image
    embeds, flowed top-to-bottom inside this box. Per-element authored
    content, like every other canvas element's own props, not a single
    report-wide field shared across every placement — edited directly on
    the canvas (double-click), not a separate tab.

    A synthetic continuation page (see _expand_description_overflow) draws
    ONLY its own pre-paginated slice of the flow — the rest already drew on
    the page(s) before it. The original page re-resolves the flow fresh
    (same reasoning _draw_table_element's own re-resolve has: simple, and
    cheap enough not to bother caching) but reuses the pre-pass's own first
    page instead of re-paginating, so the split points can't disagree."""
    if inst.continues_flow is not None:
        _draw_flow_in_box(c, inst.continues_flow, x, y, w, h)
        return
    html = _effective_description_html(props, ctx)
    if not html:
        return
    from .richtext import html_to_flowables

    flow = html_to_flowables(html, cfg, _styles(cfg), ctx=ctx, scope=inst.scope, avail_width=w)
    if not flow:
        return
    flow0 = (inst.description_flow0 or {}).get(el_id) if el_id else None
    page0 = flow0 if flow0 is not None else _paginate_flow(flow, w, h)[0]
    _draw_flow_in_box(c, page0, x, y, w, h)


# ── Field binding ────────────────────────────────────────────────────────────

def resolve_field(source: str, ctx: dict, scope: dict, page_no: int, page_title: str = "") -> str:
    """Resolve one of reportElements.ts's FIELD_SOURCES against live ctx data.
    Covers every non-item source; `item.*` sources are phase 2.

    `page_title` (added for "page.title") is this exact page's own
    `page.name` — the same string the TOC lists it under (build_canvas_pdf's
    toc_order is built from that identical field) — so a "page.title" field
    dropped onto an otherwise-blank page reproduces the legacy flowing
    renderer's `dividers` config (a blank section-divider page, heading
    centered, pulled from the section name) without a dedicated page type:
    just this field, centered, in a large size, on a page with nothing else
    on it."""
    if source.startswith("item."):
        return _resolve_item_field(source, scope)
    if source == "report.period":
        return _period_str(ctx, bool(ctx.get("arabic")))
    if source == "page.title":
        return page_title

    project, report = ctx.get("project") or {}, ctx.get("report") or {}
    overall, planned = ctx.get("overall"), ctx.get("planned")
    values = {
        "project.name": project.get("name"),
        "project.code": project.get("code"),
        "project.client": project.get("client"),
        "project.consultant": project.get("consultant"),
        "project.contractor": project.get("contractor"),
        "project.location": project.get("location"),
        "project.description": project.get("description"),
        "report.title": report.get("title"),
        "report.number": report.get("number"),
        "report.date": _fmt_date(report.get("date")) if report.get("date") else "",
        "progress.overall": f"{overall:.1f}%" if overall is not None else "",
        "progress.planned": f"{planned:.1f}%" if planned is not None else "",
        "page.number": str(page_no),
    }
    return str(values.get(source, "") or "")


def _resolve_item_field(source: str, scope: dict) -> str:
    """Repeat-page item.* bindings — resolved against whatever the current
    repeat source's item shape carries (zones/areas/area_dashboards have
    different key names for the same idea, e.g. "progress" vs "actual")."""
    key = source.split(".", 1)[1] if "." in source else ""
    if key == "index":
        return str((scope.get("index") or 0) + 1)  # 1-based, matches page.number
    if key == "count":
        return str(scope.get("count") or 0)
    item = scope.get("item") or {}
    if key == "name":
        return str(item.get("name") or "")
    if key == "caption":
        return str(item.get("caption") or "")
    if key in ("progress", "planned", "previous"):
        # zones use "progress"; areas/area_dashboards use "actual" for the same idea.
        value = item.get(key) if key != "progress" else (item.get("progress") if "progress" in item else item.get("actual"))
        return f"{value:.1f}%" if value is not None else ""
    return ""


# ── Table binding ────────────────────────────────────────────────────────────

def resolve_table(
    source: str, cfg: dict, ctx: dict, scope: dict, avail_width: float = None, raw: bool = False,
    overrides: dict | None = None, style: dict | None = None, scope_zone_id: str | None = None,
):
    """Build a ready-to-draw Table flowable for one of reportElements.ts's
    TABLE_SOURCES (plus the item-scoped `item.children`, available on a
    repeating page), reusing the exact row-construction logic and labels the
    legacy renderer uses (pdf.py) — or None when there's nothing to show.

    `avail_width` is the actual box width (points) this table will be drawn
    into — passed down so long text in an auto-width column wraps correctly
    instead of garbling (see pdf_tables._wrap_shape).

    `raw=True` returns the same header/rows every branch below already
    computes, as plain unshaped strings (a dict — see RAW_KIND per branch),
    *before* handing off to _info_table/_data_table/_hierarchy_table_flat —
    used by the Customize tab's live HTML table (see views.table_data) so
    the canvas renders the exact same values the PDF does without a second,
    separate query/formatting implementation to keep in sync.

    `overrides` (the "table" element's own `overrides` prop, edited via the
    Customize tab's live preview — see pdf_tables.apply_table_overrides) is
    applied to every branch's `header`/`rows` before either the raw or the
    real-table-builder fork, so a manual edit reaches the downloaded PDF
    exactly as edited, never just the canvas preview.

    `style` (the element's own whole `props` dict — its zebra/border/
    header_bg/header_text/text_color/border_color/zebra_color/header_bold/
    font_size/cell_padding, edited via the same tab's Properties panel)
    patches `cfg` once up front (see pdf_tables.table_style_override) so
    every builder below picks it up through the exact same
    cfg["colors"]/cfg["table"]/cfg["fonts"] reads it already had —
    real-table-builder branches draw with it directly; the raw JSON
    branches don't need it themselves (views.table_data derives the
    *effective* style the same way, from this same helper, and ships it
    alongside the raw rows for the canvas to render with).

    `scope_zone_id` (Phase 4's scope-picker) narrows `ctx["zones"]`/
    `ctx["hierarchy"]` to just that one zone — same filter-the-already-
    computed-context approach as resolve_chart's identical parameter, so
    "bind this table to Zone A" and "bind this table's matching chart to
    Zone A" stay trivially consistent (same zone list, same id match)."""
    cfg = table_style_override(cfg, style)
    styles = _styles(cfg)
    labels = cfg["labels"]
    rtl = bool(ctx.get("arabic"))
    p = ctx.get("project") or {}
    # Data-bound rows can't be deleted (they're computed from real project
    # data), but a report author can still hide specific ones from this one
    # report's own view — a row clicked on the canvas (see TablePreview.tsx).
    hidden_rows = (style or {}).get("hidden_rows") or []
    hidden_cols = (style or {}).get("hidden_cols") or []
    # Column widths / row heights dragged on the canvas (TableSizing.tsx),
    # passed down raw — each builder resolves them against its OWN column and
    # row counts (see element_col_widths/element_row_heights). Bound onto the
    # builders once here rather than threaded through every branch below, so
    # the element's own sizing overrides each source's defaults without
    # thirteen near-identical call sites having to know about it.
    _sizing = {"col_widths_frac": (style or {}).get("col_widths"),
               "row_heights_mm": (style or {}).get("row_heights"),
               "hidden_cols": hidden_cols, "hidden_rows": hidden_rows}
    _data_table = partial(_data_table_impl, **_sizing)
    _info_table = partial(_info_table_impl, **_sizing)
    _hierarchy_table_flat = partial(_hierarchy_table_flat_impl, **_sizing)

    if source == "item.children":
        children = (scope.get("item") or {}).get("children") or []
        if not children:
            return None
        rows = [[c["name"],
                 f"{c['actual']:.1f}%" if c.get("actual") is not None else "—",
                 f"{c['planned']:.1f}%" if c.get("planned") is not None else "—"] for c in children]
        header = [labels["col_zone"], labels["col_actual"], labels["col_planned"]]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, col_widths=[None, 30 * mm, 30 * mm], avail_width=avail_width)
    if source.startswith("item."):
        return None  # no other item-scoped table source defined

    if source == "project_info":
        dur = ctx.get("duration") or {}
        # Each field carries its own currency (Project.budget_currency etc —
        # a real project can genuinely have its budget quoted in one
        # currency and an advance payment paid in another); part_amount has
        # no currency of its own (PartScope, a separate model) so it falls
        # back to the project's general-purpose `currency`.
        days = lambda v: f"{v} {labels['unit_days']}" if v or v == 0 else ""  # noqa: E731
        rows = [
            (labels.get("info_progress_as_on", "Progress as on"),
             _fmt_date(ctx.get("report", {}).get("date")) if ctx.get("report", {}).get("date") else ""),
            (labels["info_name"], p.get("name")),
            (labels.get("info_code", "Code"), p.get("code")),
            (labels["info_client"], p.get("client")),
            (labels["info_consultant"], p.get("consultant")),
            (labels["info_contractor"], p.get("contractor")),
            (labels.get("info_contractor_consultant", "Contractor's Consultant"), p.get("contractor_consultant")),
            # Project type is a model enum too — localize like the rest.
            (labels["info_type"], enum_label(cfg, p.get("type"))),
            (labels["info_location"], p.get("location")),
            (labels["info_budget"], format_money(p.get("budget"), p.get("budget_currency"))),
            (labels.get("info_contract_value", "Contract value"),
             format_money(p.get("contract_value"), p.get("contract_value_currency"))),
            (labels.get("info_approved_value", "Approved value"),
             format_money(p.get("approved_value"), p.get("approved_value_currency"))),
            (labels.get("info_forecast_cost", "Forecast cost"),
             format_money(p.get("forecast_cost"), p.get("forecast_cost_currency"))),
            (labels.get("info_advance_payment", "Advance Payment"),
             format_money(p.get("advance_payment"), p.get("advance_payment_currency"))),
            (labels.get("info_duration", "Duration"),
             f"{dur['total']} {labels['unit_days']}" if dur.get("total") else ""),
            (labels["info_start"], _fmt_date(p.get("planned_start"))),
            (labels["info_finish"], _fmt_date(p.get("planned_finish"))),
            (labels.get("info_eot", "EOT (Days)"), days(p.get("eot_days"))),
            (labels.get("info_revised", "Revised finish"),
             _fmt_date(p.get("revised_finish")) if p.get("revised_finish") else ""),
            (labels.get("info_forecast", "Forecast finish"),
             _fmt_date(p.get("forecast_finish")) if p.get("forecast_finish") else ""),
            (labels.get("info_delay", "Delay"), f"{dur['delay']} {labels['unit_days']}" if dur.get("delay") else ""),
            (labels["info_size"], f"{p['size_sqm']:,.0f} {labels['unit_sqm']}" if p.get("size_sqm") else ""),
            # A contracted sub-scope some projects track alongside the whole
            # project — see Project.part_amount's docstring. Grouped at the
            # end so the whole-project figures above stay together.
            (labels.get("info_part_amount", "(Part) Amount"), format_money(p.get("part_amount"), p.get("currency"))),
            (labels.get("info_part_completion_revised", "(Part) Completion Date (Revised Baseline)"),
             _fmt_date(p.get("part_completion_revised")) if p.get("part_completion_revised") else ""),
            (labels.get("info_part_forecast", "(Part) Forecasted Completion Date"),
             _fmt_date(p.get("part_forecast_completion")) if p.get("part_forecast_completion") else ""),
            (labels.get("info_part_delay", "(Part) Delay (Calendar Days)"), days(p.get("part_delay_days"))),
        ]
        # Flags the schedule-risk rows (forecast/delay dates) for _info_table
        # to tint — matches the client's own reference report's own
        # convention of visually calling those out rather than letting them
        # blend into the rest of the table (found 2026-08-26). Resolved
        # from `labels` (not hardcoded English key names) so this still
        # matches after a template overrides any of these to Arabic.
        highlight_labels = {
            labels.get("info_forecast", "Forecast finish"),
            labels.get("info_delay", "Delay"),
            labels.get("info_part_forecast", "(Part) Forecasted Completion Date"),
            labels.get("info_part_delay", "(Part) Delay (Calendar Days)"),
        }
        rows = [[k, v] for k, v in rows if v and v != "—"]
        if not rows:
            return None
        apply_table_overrides("info", None, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "info", "header": None, "rows": rows}
        return _info_table(cfg, styles, rows, rtl, avail_width=avail_width, highlight_labels=highlight_labels)

    if source == "zone_progress":
        zones = ctx.get("zones") or []
        if scope_zone_id:
            zones = [z for z in zones if z.get("id") == scope_zone_id]
        if not zones:
            return None
        rows = [[z["name"], f"{z['progress']:.1f}%"] for z in zones]
        header = [labels["col_zone"], labels["col_progress"]]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, col_widths=[None, 40 * mm], avail_width=avail_width)

    if source == "hierarchy_progress":
        hierarchy = ctx.get("hierarchy") or []
        if scope_zone_id:
            hierarchy = [z for z in hierarchy if z.get("id") == scope_zone_id]
        if not hierarchy:
            return None
        header = [labels["col_zone"], labels["col_actual"], labels["col_previous"], labels["col_planned"]]
        rows = []
        for zone in hierarchy:
            rows.append({"name": zone["name"], "actual": zone["actual"], "previous": zone["previous"],
                         "planned": zone["planned"], "level": 0})
            for child in zone["children"]:
                rows.append({"name": child["name"], "actual": child["actual"], "previous": child["previous"],
                             "planned": child["planned"], "level": 1})
        apply_table_overrides("hierarchy", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "hierarchy", "header": header, "rows": rows}
        return _hierarchy_table_flat(cfg, styles, header, rows, rtl, avail_width=avail_width)

    if source == "progress_sheet":
        # The reference report's own "Progress Sheet" (its page 32): one row per
        # zone, carrying planned, actual-this-month, the month's own movement,
        # actual-last-month, performance factor and variance side by side.
        # Every column is derived from figures ctx already holds — the month's
        # progress is actual - previous, the performance factor is actual over
        # planned, the variance is actual - planned — so this adds no query.
        hierarchy = ctx.get("hierarchy") or []
        if scope_zone_id:
            hierarchy = [z for z in hierarchy if z.get("id") == scope_zone_id]
        rows = []
        for zone in hierarchy:
            planned, actual, previous = zone.get("planned"), zone.get("actual"), zone.get("previous")
            if actual is None:
                continue  # nothing real to report for this zone yet
            this_month = actual - previous if previous is not None else None
            factor = (actual / planned * 100) if planned else None
            variance = actual - planned if planned is not None else None
            rows.append([
                zone["name"],
                _pct_or_dash(planned),
                _pct_or_dash(actual),
                _pct_or_dash(this_month),
                _pct_or_dash(previous),
                _pct_or_dash(factor),
                _pct_or_dash(variance),
            ])
        if not rows:
            return None
        header = [labels["col_zone"], labels["col_planned"], labels.get("col_actual_this", labels["col_actual"]),
                  labels.get("col_this_month", "This month %"), labels["col_previous"],
                  labels.get("col_performance_factor", "Performance factor %"),
                  labels.get("col_variance", "Variance %")]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, avail_width=avail_width)

    if source == "discipline_progress":
        discipline = ctx.get("discipline") or []
        if not discipline:
            return None
        header = [labels["col_unit"], labels["col_concrete"], labels["col_architecture"],
                  labels["col_electrical"], labels["col_mechanical"], labels["col_other"]]
        rows = [[r["name"]] + [_pct_or_dash(r.get(d)) for d in
                               ("concrete", "architecture", "electrical", "mechanical", "other")]
                for r in discipline]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, avail_width=avail_width)

    if source == "progress_compare":
        zones = [z for z in (ctx.get("zones") or []) if z.get("planned") is not None]
        if not zones:
            return None
        rows = [[z["name"],
                 f"{z['planned']:.1f}%" if z.get("planned") is not None else "—",
                 f"{z['previous']:.1f}%" if z.get("previous") is not None else "—",
                 f"{z['progress']:.1f}%"] for z in zones]
        header = [labels["col_zone"], labels["col_planned"], labels["col_previous"], labels["col_actual"]]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, col_widths=[None, 28 * mm, 28 * mm, 28 * mm],
                            avail_width=avail_width)

    if source == "milestones":
        milestones = ctx.get("milestones") or []
        if not milestones:
            return None
        rows = [[m["title"], _fmt_date(m["date"]),
                 enum_label(cfg, m["status"].replace("_", " ").title())] for m in milestones]
        header = [labels["col_milestone"], labels["col_date"], labels["col_status"]]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, col_widths=[None, 32 * mm, 34 * mm], avail_width=avail_width)

    if source == "invoices":
        invoices = ctx.get("invoices") or []
        if not invoices:
            return None
        rows = [[i["name"], f"{i['value']:,.2f}", _fmt_date(i["date"]) if i["date"] else "—"] for i in invoices]
        rows.append([labels.get("col_total", "Total"), f"{ctx.get('invoices_total', 0):,.2f}", ""])
        header = [labels.get("col_invoice", "Item"), labels.get("col_value", "Value"), labels["col_date"]]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, col_widths=[None, 36 * mm, 30 * mm], avail_width=avail_width)

    if source == "submittals":
        sub_rows = (ctx.get("submittals") or {}).get("rows") or []
        if not sub_rows:
            return None
        header = [labels.get("col_invoice", "Item"), labels.get("col_type", "Type"),
                  labels.get("col_discipline", "Discipline"), labels["col_status"]]
        rows = [[r["title"], enum_label(cfg, r["type"]), enum_label(cfg, r["discipline"]),
                 enum_label(cfg, r["status"])] for r in sub_rows]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, avail_width=avail_width)

    if source == "delays":
        delays = ctx.get("delays") or []
        if not delays:
            return None
        # Delay.Status's own choices (apps/projects/models.py) carry only an
        # English display label ("Open"/"Resolved") — `.title()`ing the raw
        # value just capitalizes that English, it doesn't translate it, so a
        # report otherwise entirely in Arabic showed a bare "Open"/"Resolved"
        # in this one column (found 2026-08-25). Real translations for both
        # values live in the labels dict; the raw value survives as a
        # fallback for a status this dict hasn't been told about yet.
        status_labels = {"open": labels.get("status_open", "Open"),
                          "resolved": labels.get("status_resolved", "Resolved")}
        rows = [[d["title"], str(d["impact_days"]), status_labels.get(d["status"], d["status"].title())]
                for d in delays]
        header = [labels["col_delay"], labels["col_impact"], labels["col_status"]]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, col_widths=[None, 28 * mm, 28 * mm], avail_width=avail_width)

    if source == "detailed_progress":
        return _resolve_detailed_progress_table(cfg, ctx, styles, avail_width=avail_width, raw=raw,
                                                 overrides=overrides, hidden_rows=hidden_rows,
                                                 hidden_cols=hidden_cols, sizing=_sizing)

    if source == "activity_schedule":
        return _resolve_activity_schedule_table(cfg, ctx, styles, avail_width=avail_width, raw=raw,
                                                 overrides=overrides, hidden_rows=hidden_rows,
                                                 hidden_cols=hidden_cols, sizing=_sizing)

    if source == "critical_path_delays":
        rows_data = ctx.get("critical_path") or []
        if not rows_data:
            return None
        rows = [[r["name"], _fmt_date(r["planned_finish"]), _fmt_date(r["forecast_finish"]), str(r["delay_days"])]
                for r in rows_data]
        header = [labels["col_zone"], labels["info_finish"], labels["col_forecast_finish"], labels["delay_days"]]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, col_widths=[None, 32 * mm, 32 * mm, 28 * mm],
                            avail_width=avail_width)

    if source == "custom":
        # Free-form table (paste from Excel / built by hand in the Customize
        # tab's Properties panel — see CustomTableEditor.tsx) — reads header/
        # rows straight out of the element's own props instead of ctx, since
        # there's no backend data source to compute; still runs through the
        # exact same overrides/style/"data"-kind path every other table does,
        # so a custom table can't diverge from what the Properties panel's
        # style controls or manual cell overrides do for any other table.
        custom = (style or {}).get("custom_data") or {}
        header = [str(h) for h in (custom.get("columns") or [])]
        if not header:
            return None
        rows = [[str(cell) for cell in row] for row in (custom.get("rows") or [])]
        apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
        if raw:
            return {"kind": "data", "header": header, "rows": rows}
        return _data_table(cfg, styles, header, rows, avail_width=avail_width)

    return None


def _resolve_detailed_progress_table(cfg, ctx, styles, avail_width=None, raw=False, overrides=None,
                                     hidden_rows=None, hidden_cols=None, sizing=None):
    """Detailed activity grid — v1 scope: only the first zone's grid, only its
    first 8 columns (the legacy `_grid_section` splits wide grids across
    multiple pages/columns; reproducing that needs a 2D repeat, deferred)."""
    grids = ctx.get("zone_grids")
    if not grids:
        report = ctx.get("_report")
        project = getattr(report, "project", None)
        if project is None:
            return None
        from .services import _zone_grids
        zone_ids = [z["id"] for z in (ctx.get("zones") or []) if z.get("id")]
        grids = _zone_grids(project, zone_ids, getattr(report, "scope_ids", None), ctx.get("_progress"))
        ctx["zone_grids"] = grids
    if not grids:
        return None
    grid = grids[0]
    labels = cfg["labels"]
    header = [labels.get("col_task", "Task")] + grid["columns"][:8]
    rows = [[r["name"]] + ["" if c is None else f"{c:.1f}%" for c in r["cells"][:8]] for r in grid["rows"]]
    apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
    if raw:
        return {"kind": "data", "header": header, "rows": rows}
    return _data_table_impl(cfg, styles, header, rows, avail_width=avail_width, **(sizing or {}))


def _resolve_activity_schedule_table(cfg, ctx, styles, avail_width=None, raw=False, overrides=None,
                                     hidden_rows=None, hidden_cols=None, sizing=None):
    """Every activity's P6 duration/SPI/schedule-variance columns — computed
    lazily and cached in ctx, the same pattern as the detailed-progress grid
    above, since a real project can carry tens of thousands of activities and
    most report renders never touch this table at all."""
    rows_data = ctx.get("activity_schedule")
    if rows_data is None:
        report = ctx.get("_report")
        project = getattr(report, "project", None)
        if project is None:
            return None
        rows_data = list(project.activities.order_by("sort_order", "name").values(
            "name", "baseline_duration", "original_duration", "actual_duration",
            "remaining_duration", "schedule_performance_index", "schedule_variance",
        ))
        ctx["activity_schedule"] = rows_data
    if not rows_data:
        return None

    labels = cfg["labels"]
    header = [
        labels.get("col_task", "Task"), labels.get("col_bl_duration", "BL Duration"),
        labels.get("col_original_duration", "Original Duration"),
        labels.get("col_actual_duration", "Actual Duration"),
        labels.get("col_remaining_duration", "Remaining Duration"),
        labels.get("col_spi", "SPI"), labels.get("col_schedule_variance", "Schedule Variance"),
    ]

    def n(v, digits=0):
        return "" if v is None else f"{v:,.{digits}f}"

    rows = [
        [r["name"], n(r["baseline_duration"]), n(r["original_duration"]), n(r["actual_duration"]),
         n(r["remaining_duration"]), n(r["schedule_performance_index"], 2), n(r["schedule_variance"])]
        for r in rows_data
    ]
    apply_table_overrides("data", header, rows, overrides, hidden_rows, hidden_cols)
    if raw:
        return {"kind": "data", "header": header, "rows": rows}
    return _data_table_impl(cfg, styles, header, rows, avail_width=avail_width, **(sizing or {}))


# ── Chart binding ────────────────────────────────────────────────────────────

def resolve_chart(source: str, chart_type, cfg: dict, ctx: dict, scope: dict, w: float, h: float,
                  scope_zone_id: str | None = None):
    """Build a ready-to-draw Drawing for one of reportElements.ts's
    CHART_SOURCES (plus the item-scoped `item.units`/`item.duration`,
    available on a repeating page), at the given box size (points) — or None
    with nothing to show.

    `scope_zone_id` (Phase 4's scope-picker — "bind a table/chart's data to
    a specific zone/stage") narrows `ctx["zones"]` to just that one zone
    before handing off to the chart builder, the same "filter the already-
    computed context, don't re-query" approach `resolve_table` uses below.
    Only `zone_progress` reads it today — the other chart sources aren't
    zone-shaped data to begin with."""
    labels = cfg["labels"]

    if source == "item.units":
        item = scope.get("item") or {}
        return area_units_chart(cfg, item, w, labels, height=h)
    if source == "item.duration":
        item = scope.get("item") or {}
        return zone_duration_pie(cfg, item.get("duration"), w, labels, height=h)
    if source == "item.spi":
        item = scope.get("item") or {}
        value = item.get("progress") if "progress" in item else item.get("actual")
        return speedometer_chart(value, w, cfg, title=labels.get("spi", "SPI"), height=h)
    if isinstance(source, str) and source.startswith("item."):
        return None  # no other item-scoped chart source defined

    if source == "spi":
        return speedometer_chart(ctx.get("overall"), w, cfg, title=labels.get("spi", "SPI"), height=h)
    if source == "zone_progress":
        chart_ctx = ctx
        if scope_zone_id:
            chart_ctx = {**ctx, "zones": [z for z in (ctx.get("zones") or []) if z.get("id") == scope_zone_id]}
        return planned_actual_chart(cfg, chart_ctx, w, labels, height=h)
    if source == "area_progress":
        return area_progress_chart(cfg, ctx, w, labels, height=h)
    if source == "scurve":
        return scurve_chart(cfg, ctx, w, labels, height=h)
    if source == "breakdown":
        return overall_donut(cfg, ctx, w, labels, height=h)
    if source == "duration":
        return duration_pie(cfg, ctx, w, labels, height=h)
    if source == "cashflow_monthly":
        return cashflow_chart(cfg, ctx.get("cashflow") or [], w, labels, height=h)
    if source == "cashflow_cumulative":
        return cashflow_curve(cfg, ctx.get("cashflow") or [], w, labels, height=h)
    if source == "invoice_status":
        return invoice_status_chart(cfg, ctx, w, labels, height=h)
    if source == "budget_total_cost":
        return budget_total_cost_chart(cfg, ctx, w, labels, height=h)
    if source == "boq_financial_progress":
        return boq_financial_progress_chart(cfg, ctx, w, labels, height=h)
    if source == "progress_comparison":
        return progress_comparison_chart(cfg, ctx, w, labels, height=h)
    if source == "progress_tracking":
        return progress_tracking_chart(cfg, ctx, w, labels, height=h)
    if source == "gantt":
        return gantt_chart(cfg, ctx.get("gantt") or [], w, labels, height=h)
    if source in ("submittals_material", "submittals_shop_drawing"):
        # "material"/"shop_drawing" mirror apps.projects.models.Submittal.Type's
        # real DB values — ctx["submittals"]["rows"][i]["type_key"] is that
        # raw value (services.py), not the translated display label, so this
        # filter can't drift out of sync with an i18n'd `type` string.
        wanted = "material" if source == "submittals_material" else "shop_drawing"
        rows = [r for r in (ctx.get("submittals") or {}).get("rows") or [] if r.get("type_key") == wanted]
        return submittals_breakdown_chart(cfg, rows, w, labels, height=h)
    return None


# ── Repeating pages (phase 2 fleshes out _repeat_items) ─────────────────────

def expand_pages(cfg, ctx, report) -> list:
    """Turn config.layout.pages into the physical page sequence: a fixed page
    stays one page; a repeating page clones once per item (or per chunk).

    A report's own layout_override can also *pin* a repeating page to exactly
    one of those items/chunks (repeat.pin_index) — that's what the "Customize"
    tab's page-expansion does: instead of one abstract repeating page, the
    report gets N concrete, independently-editable pages, each pinned to the
    item it was expanded from, so what you edit matches the real page count."""
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
        pin = rep.get("pin_index")
        if rep.get("mode") == "chunk":
            size = max(1, int(rep.get("chunk_size") or 4))
            groups = [items[i:i + size] for i in range(0, len(items), size)][:cap]
            if pin is not None:
                groups = groups[pin:pin + 1] if 0 <= pin < len(groups) else []
            for i, g in enumerate(groups):
                n += 1
                out.append(PageInstance(page, {"item": g[0] if g else None, "items": g,
                                               "index": pin if pin is not None else i,
                                               "count": len(groups)}, n))
        else:
            capped = items[:cap]
            if pin is not None:
                capped = capped[pin:pin + 1] if 0 <= pin < len(capped) else []
            for i, item in enumerate(capped):
                n += 1
                out.append(PageInstance(page, {"item": item, "items": [item],
                                               "index": pin if pin is not None else i,
                                               "count": len(capped)}, n))
    return out


def _split_table_chunks(table, w, h, *, rest_h=None, max_chunks=500) -> list:
    """Break a Table flowable into successive pieces that each fit height h.

    `Table.split(w, h)` only ever answers "what fits" + "the remainder" for
    one page — this calls it again on the remainder, and again on ITS
    remainder, the same way a Platypus Frame pages a flowable across as many
    frames as it takes to exhaust it. `max_chunks` is a defensive cap, not a
    real limit — a genuine report table running past 500 pages on its own
    would mean something else is wrong.

    `rest_h` is the height available to every chunk AFTER the first. A
    continuation page carries nothing but this table, so it reflows to the
    full content area (see _continuation_box) and is much taller than the
    source element's own box — splitting every chunk against the source
    height would leave that extra space empty on every continuation page."""
    chunks = []
    remaining = table
    while remaining is not None and len(chunks) < max_chunks:
        h = h if not chunks else (rest_h or h)
        _, natural_h = remaining.wrap(w, h)
        if natural_h <= h:
            chunks.append(remaining)
            break
        pieces = remaining.split(w, h)
        if not pieces:
            # Can't even fit the header row in this box — nothing more to
            # split; caller's draw_table_in_box fallback (the "too small"
            # placeholder) is for exactly this case, not a real table.
            break
        chunks.append(pieces[0])
        remaining = pieces[1] if len(pieces) > 1 else None
    return chunks


# A final chunk shorter than this fraction of its page reads as an orphan.
_ORPHAN_FRACTION = 0.35
# How far the per-page height may be squeezed to even out that last page.
_REBALANCE_STEPS = (0.92, 0.85, 0.78, 0.7)


def _split_table_chunks_balanced(table, w, h, *, rest_h=None, max_chunks=500) -> list:
    """`_split_table_chunks`, retried at slightly reduced page heights when the
    LAST chunk comes out tiny.

    A table whose rows happen to divide badly ends on a page holding one or two
    rows over most of a sheet of white — and when it is the report's final
    table, the whole document ends on that near-blank page (2026-08-30). The
    tail can't be fixed after the fact: reportlab's split() yields immutable
    pieces, so rows can't be pulled back up into the previous chunk. Squeezing
    the per-page height slightly redistributes rows across the SAME number of
    pages, which is what actually evens the tail out.

    Only accepts a retry that keeps the page count identical — trading a thin
    last page for an extra page would be a worse outcome, not a better one."""
    chunks = _split_table_chunks(table, w, h, rest_h=rest_h, max_chunks=max_chunks)
    if len(chunks) < 2:
        return chunks
    page_h = rest_h or h
    _, tail_h = chunks[-1].wrap(w, page_h)
    if tail_h >= page_h * _ORPHAN_FRACTION:
        return chunks

    for factor in _REBALANCE_STEPS:
        # Scale the FIRST chunk's height too, not just the continuation
        # height. Squeezing only rest_h moves rows between continuation pages
        # and never off page one — so a table that put 9 rows on its source
        # page and orphaned the 10th kept doing exactly that, and the retry
        # silently changed nothing (2026-08-30).
        candidate = _split_table_chunks(
            table, w, h * factor, rest_h=page_h * factor, max_chunks=max_chunks)
        if len(candidate) != len(chunks):
            continue
        _, cand_tail = candidate[-1].wrap(w, page_h)
        if cand_tail >= page_h * _ORPHAN_FRACTION:
            return candidate
    return chunks


def _expand_table_overflow(instances: list, cfg: dict, ctx: dict, design: dict) -> list:
    """Splices extra synthetic pages in after any page whose table element
    has more rows than fit its box — mirrors what a normal Platypus flowing
    document gets for free from Frame-based pagination, which this canvas
    renderer doesn't have since it draws each page's elements at fixed
    positions rather than flowing a story through frames. Without this, an
    overflowing table either got silently truncated with a "+N more rows"
    note (draw_table_in_box's fallback — meant for a genuinely tight box,
    not "there's 20 pages more of this") or, in the live Customize-tab
    preview, visibly spilled past the page edge.

    Scope: only the FIRST overflowing table element on a page continues —
    a second overflowing table on the same page still falls back to the old
    truncation note. Two independently-continuing tables interleaved across
    the same run of pages would need page-by-page interleaving logic for
    comparatively rare real-world value; not attempted here.

    Skips any instance _expand_description_overflow (run first, see
    build_canvas_pdf) already claimed for its own continuation — "only one
    overflowing thing per original page, whichever type notices first"
    extended across types, not just within this one."""
    out = []
    for inst in instances:
        if inst.continues_element is not None or inst.description_flow0 is not None:
            out.append(inst)
            continue
        # This instance's own effective page height (its `orientation`
        # override if it has one, else the template default) — a landscape
        # override changes how much vertical room a table's box actually has
        # to work with, same as the real per-page render loop uses.
        _, page_h_mm = _page_size_mm(design, inst.page)
        table_els = [el for el in (inst.page.get("elements") or []) if el.get("type") == "table"]
        overflow_el, chunks = None, None
        for el in table_els:
            props = el.get("props") or {}
            source = props.get("source", "")
            x, y, w, h = el_box(el, page_h_mm)
            # A captioned/titled table reserves _CAPTION_H/_TITLE_H at the
            # bottom/top of its box (see _draw_table_element) — split against
            # that same reduced height so a continuing table's chunk
            # boundaries land exactly where the real draw pass will later
            # need them to. Every chunk (including continuation ones, which
            # don't carry their own caption or title) uses this one reduced
            # height rather than a taller one for the continuation chunks
            # specifically — simpler than re-splitting per chunk, at the
            # cost of a little unused space on continuation pages.
            content_h = h - (_CAPTION_H if props.get("show_caption") else 0) - (_TITLE_H if _table_or_chart_title(props, cfg) else 0)
            table = resolve_table(
                source, cfg, ctx, inst.scope, avail_width=w, overrides=props.get("overrides"), style=props,
                scope_zone_id=props.get("scope_zone_id"),
            )
            if table is None:
                continue
            _, natural_h = table.wrap(w, content_h)
            if natural_h <= content_h:
                continue
            # Continuation pages hold nothing but this table and reflow to
            # the full content area, so they fit far more rows than the
            # source box does — split them against that taller height.
            page_w_mm, _ = _page_size_mm(design, inst.page)
            _, _, _, cont_h = _continuation_box(el, design, page_w_mm, page_h_mm)
            candidate = _split_table_chunks_balanced(table, w, content_h, rest_h=cont_h)
            if len(candidate) > 1:
                overflow_el, chunks = el, candidate
                break

        if overflow_el is None:
            out.append(inst)
            continue

        out.append(PageInstance(
            inst.page, inst.scope, inst.number, table_chunk0={overflow_el["id"]: chunks[0]},
        ))
        for chunk in chunks[1:]:
            out.append(PageInstance(
                inst.page, inst.scope, inst.number, continues_element=overflow_el, continues_chunk=chunk,
            ))

    # Splicing in continuation pages breaks the original run of page
    # numbers expand_pages assigned (one instance per physical page no
    # longer holds) — renumber the final sequence so it's physically
    # sequential again before anything (TOC, "page.number" fields, the
    # running footer) reads `.number`.
    for i, inst in enumerate(out, start=1):
        inst.number = i
    return out


def _expand_toc_overflow(instances: list, cfg: dict, ctx: dict, design: dict) -> list:
    """A "toc" element listing captioned tables/figures/images (or, for the
    "contents" variant, every page in the report) can run past its own
    fixed-height box — e.g. this template's own "List of Figures" page is
    sized for ~26 rows, but a report where every chart/table got a caption
    (2026-08-26) produces 51. Before this, `_draw_toc_element` just silently
    stopped drawing at the box edge (`if cy < y: break`) — real captioned
    figures vanishing from the printed list with no visible sign anything
    was cut, exactly the "silent truncation" failure mode Phase 2's table-
    overflow mechanism was built to rule out for tables. This is that same
    fix, for "toc" elements. Mirrors _expand_table_overflow's own splicing
    pattern almost exactly — see its comments for the parts that are
    identical here (renumbering, one-overflow-per-original-page scope).

    Must run AFTER a first `_collect_captions`/toc_map pass on `instances`
    (so `_toc_rows` can read real row counts from ctx) but every row's
    displayed PAGE NUMBER is still allowed to be stale at that point —
    inserting continuation pages here shifts numbering for everything after
    them, so the caller re-runs both passes on the final, renumbered
    instances afterward. `toc_rows0`/`continues_toc_rows` store index
    ranges into that list, never a captured copy of the rows themselves —
    exactly so they keep pointing at the right rows once the caller's
    second pass corrects the page numbers inside it."""
    out = []
    for inst in instances:
        if inst.continues_element is not None or inst.table_chunk0 is not None or inst.description_flow0 is not None:
            out.append(inst)
            continue
        _, page_h_mm = _page_size_mm(design, inst.page)
        toc_els = [el for el in (inst.page.get("elements") or []) if el.get("type") == "toc"]
        overflow_el, row_chunks = None, None
        for el in toc_els:
            props = el.get("props") or {}
            _, y, _, h = el_box(el, page_h_mm)
            rows = _toc_rows(props, ctx, inst)
            capacity = _toc_capacity(props, h)
            if len(rows) <= capacity:
                continue
            row_chunks = [(i, min(i + capacity, len(rows))) for i in range(0, len(rows), capacity)]
            overflow_el = el
            break

        if overflow_el is None:
            out.append(inst)
            continue

        out.append(PageInstance(
            inst.page, inst.scope, inst.number, toc_rows0={overflow_el["id"]: row_chunks[0]},
        ))
        for chunk in row_chunks[1:]:
            out.append(PageInstance(
                inst.page, inst.scope, inst.number, continues_element=overflow_el, continues_toc_rows=chunk,
            ))

    for i, inst in enumerate(out, start=1):
        inst.number = i
    return out


def _paginate_flow(flowables: list, w: float, h: float, *, max_pages: int = 60) -> list:
    """Break a mixed list of flowables (Paragraphs, Tables, chart Drawings,
    Images — see richtext.html_to_flowables) into successive pages that each
    fit a w×h box, generalizing _split_table_chunks from one Table to a
    whole flow: a real ReportLab Frame decides what fits (against a throwaway
    scratch canvas, never actually output) exactly the way a normal
    Platypus BaseDocTemplate paginates a story — so the page boundaries this
    picks are byte-for-byte the ones _draw_flow_in_box's real draw pass
    (the identical Frame.add call, just against the real canvas) will also
    land on, not a hand-rolled height estimate that could silently disagree
    and lose content. A flowable too tall to fit even a fresh, empty page is
    split via its own .split(w, h) (Paragraph/Table both implement this);
    one that can't even split (a chart Drawing, an Image) moves whole to the
    next page."""
    scratch = _canvas.Canvas(BytesIO())
    pages, remaining = [], list(flowables)
    while remaining and len(pages) < max_pages:
        frame = Frame(0, 0, w, h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
        drawn = []
        while remaining:
            head = remaining[0]
            if frame.add(head, scratch, trySplit=0):
                drawn.append(head)
                remaining.pop(0)
                continue
            avail_h = frame._y - frame._y1p
            if avail_h <= 0:
                break  # this page is full — whatever's left starts the next one
            pieces = head.split(frame._getAvailableWidth(), avail_h)
            if not pieces:
                break  # doesn't fit even a fresh page's worth of room — move on whole
            remaining[0:1] = pieces
        if not drawn:
            break  # nothing fits an entirely empty box — bail, matches _split_table_chunks
        pages.append(drawn)
    return pages


def _draw_flow_in_box(c, flowables: list, x: float, y: float, w: float, h: float) -> None:
    """Draws one already-paginated page's worth of flowables (from
    _paginate_flow) into a box on the real canvas, via the same Frame
    mechanism used to decide they'd fit — nothing left to measure or split
    here, just place them top-to-bottom."""
    if not flowables:
        return
    frame = Frame(x, y, w, h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
    frame.addFromList(list(flowables), c)


def _expand_description_overflow(instances: list, cfg: dict, ctx: dict, design: dict) -> list:
    """Splices extra synthetic pages in after any page whose "description"
    element (the report's rich-text narrative, possibly with inline table/
    chart/image embeds — see _draw_description_element) doesn't fit its box
    in one page — same idea and same reason as _expand_table_overflow
    (this canvas renderer draws fixed boxes, not a flowing Frame/story, so
    pagination across a box's own bottom edge has to be built by hand), just
    generalized from one Table flowable to a whole mixed flow.

    Same one-overflowing-element-per-page scope as _expand_table_overflow,
    and skips anything that pass already claimed (see its own guard)."""
    out = []
    for inst in instances:
        if inst.continues_element is not None or inst.table_chunk0 is not None:
            out.append(inst)
            continue
        _, page_h_mm = _page_size_mm(design, inst.page)
        desc_els = [el for el in (inst.page.get("elements") or []) if el.get("type") == "description"]
        overflow_el, pages = None, None
        for el in desc_els:
            x, y, w, h = el_box(el, page_h_mm)
            html = _effective_description_html(el.get("props") or {}, ctx)
            if not html:
                continue
            from .richtext import html_to_flowables

            flow = html_to_flowables(html, cfg, _styles(cfg), ctx=ctx, scope=inst.scope, avail_width=w)
            if not flow:
                continue
            candidate = _paginate_flow(flow, w, h)
            if len(candidate) > 1:
                overflow_el, pages = el, candidate
                break

        if overflow_el is None:
            out.append(inst)
            continue

        out.append(PageInstance(
            inst.page, inst.scope, inst.number, description_flow0={overflow_el["id"]: pages[0]},
        ))
        for page in pages[1:]:
            out.append(PageInstance(
                inst.page, inst.scope, inst.number, continues_element=overflow_el, continues_flow=page,
            ))

    for i, inst in enumerate(out, start=1):
        inst.number = i
    return out


def _element_will_draw(el, inst, cfg, ctx) -> bool:
    """Whether this table/chart element actually puts something on the page.

    Mirrors the two guards in _draw_chart_element / _draw_table_element: a box
    under the chart minimum draws nothing, and a source with no data draws
    nothing. Used by _collect_captions so a caption number is never spent on
    an element the reader won't find."""
    props = el.get("props") or {}
    source = props.get("source", "")
    w, h = float(el.get("w", 0)) * mm, float(el.get("h", 0)) * mm
    caption_h = _CAPTION_H if props.get("show_caption") else 0
    title_h = _TITLE_H if _table_or_chart_title(props, cfg) else 0
    content_h = h - caption_h - title_h

    # Memoized: _collect_captions runs TWICE (before and after overflow
    # expansion), so an un-cached check here resolved every captioned chart
    # and table two extra times on top of the draw pass — enough to take a
    # ~10 minute render past 37 minutes on this project (2026-08-30). Same
    # source at the same size in the same scope always resolves the same way,
    # so key on exactly that.
    item = (inst.scope or {}).get("item") or {}
    scope_key = item.get("name") or item.get("id") or (inst.scope or {}).get("index")
    key = (el.get("type"), source, props.get("scope_zone_id"), scope_key, round(w, 1), round(content_h, 1))
    cache = ctx.setdefault("_will_draw_cache", {})
    if key in cache:
        return cache[key]

    def _remember(value):
        cache[key] = value
        return value

    try:
        if el.get("type") == "chart":
            if w < MIN_CHART_W_MM * mm or content_h < MIN_CHART_H_MM * mm:
                return _remember(False)
            return _remember(resolve_chart(
                source, props.get("chart_type"), cfg, ctx, inst.scope, w, content_h,
                scope_zone_id=props.get("scope_zone_id")) is not None)
        return _remember(resolve_table(
            source, cfg, ctx, inst.scope, avail_width=w,
            overrides=props.get("overrides"), style=props,
            scope_zone_id=props.get("scope_zone_id")) is not None)
    except Exception:
        # Never let the caption pre-pass be what breaks a render — if this
        # can't be determined, assume it draws and let the draw pass decide.
        return _remember(True)


def _collect_captions(instances: list, cfg: dict, ctx: dict) -> None:
    """Pre-pass, run once before any page is drawn: assigns every captioned
    table/chart/photo its running number ("جدول N"/"شكل N"/"صورة N") and
    records (caption text, page number) for a "List of tables/figures/images"
    TOC variant to read — same reason toc_map/toc_order above are a pre-pass
    rather than computed inline while drawing: a TOC page can come BEFORE the
    elements it lists, and a single forward render pass would still find an
    empty list for it at that point. Scoped to each page's own `elements`
    (not master_elements) — a header/footer repeats on every page, so
    numbering it as a distinct table/figure per page would be meaningless.

    Sets ctx["_table_captions"]/"_figure_captions"/"_image_captions" (ordered
    [(text, page_no), ...] lists, read by _draw_toc_element) and
    ctx["_table_caption_text"]/"_figure_caption_text"/"_image_caption_text"
    (keyed by (id(instance), element_id), read by the matching _draw_*
    function so its live draw pass reuses the exact same text/number instead
    of recomputing — recomputing independently could drift if either side's
    logic ever changed without the other)."""
    seq = {"table": 0, "figure": 0, "image": 0}
    lists = {"table": [], "figure": [], "image": []}
    text_maps = {"table": {}, "figure": {}, "image": {}}

    for inst in instances:
        if inst.continues_chunk is not None:
            continue  # continuation pages don't get their own caption
        for el in inst.page.get("elements") or []:
            props = el.get("props") or {}
            if not props.get("show_caption"):
                continue
            t = el.get("type")
            # An element that won't actually draw must not take a number or a
            # List-of-Tables/Figures line with it. A chart whose source has no
            # data draws nothing (see _draw_chart_element), and it used to
            # still be counted here — leaving "رسم توضيحي 53 - موقف
            # المستخلصات ... 51" pointing at a figure that isn't on page 51
            # (found 2026-08-30 after the invoice pie started returning None).
            # Resolving twice costs a second pass over the same data, which is
            # worth it to keep the numbering honest.
            if t in ("table", "chart") and not _element_will_draw(el, inst, cfg, ctx):
                continue
            if t == "table":
                kind, label_key = "table", "table_caption"
                name = props.get("caption") or cfg["labels"].get(props.get("source", ""), props.get("source", ""))
            elif t == "chart":
                kind, label_key = "figure", "figure"
                name = props.get("caption") or cfg["labels"].get(props.get("source", ""), props.get("source", ""))
            elif t == "image" and props.get("source") == "repeat.item":
                items = inst.scope.get("items") or []
                slot = int(props.get("slot", 0) or 0)
                item = items[slot] if 0 <= slot < len(items) else None
                if not item or not item.get("caption"):
                    continue
                kind, label_key, name = "image", "image_caption", item["caption"]
            else:
                continue

            seq[kind] += 1
            prefix = cfg["labels"].get(label_key, label_key)
            # "N - name" (dash), not "N: name" (colon) — matches the
            # client's own real reference report's caption convention
            # exactly (e.g. "جدول1 - معلومات عن المشروع"), found comparing
            # our output to it directly (2026-08-26).
            text = f"{prefix} {seq[kind]} - {name}" if name else f"{prefix} {seq[kind]}"
            lists[kind].append((text, inst.number))
            text_maps[kind][(id(inst), el.get("id"))] = text

    ctx["_table_captions"], ctx["_figure_captions"], ctx["_image_captions"] = (
        lists["table"], lists["figure"], lists["image"],
    )
    ctx["_table_caption_text"], ctx["_figure_caption_text"], ctx["_image_caption_text"] = (
        text_maps["table"], text_maps["figure"], text_maps["image"],
    )


_REPEAT_SOURCES = {
    "photos": "photos",
    "attachments": "attachments",
    "area_dashboards": "area_dashboards",
    "phase_dashboards": "phase_dashboards",
    "zones": "zones",
    "areas": "areas",
}


def _repeat_items(source, ctx, report) -> list:
    """Map a repeat source to its ctx list. `report` isn't needed today (every
    source is already computed onto ctx by build_report_context) but is kept
    in the signature in case a future source needs a fresh query."""
    key = _REPEAT_SOURCES.get(source)
    return list(ctx.get(key) or []) if key else []
