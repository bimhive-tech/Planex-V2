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
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import Paragraph

from .constants import merged_config
from .pdf_base import BOLD, FONT_NAME, ensure_fonts, hexcolor, resolve_arabic, shape, storage_image_reader
from .pdf_charts import (
    area_progress_chart,
    area_units_chart,
    cashflow_chart,
    cashflow_curve,
    duration_pie,
    gantt_chart,
    overall_donut,
    planned_actual_chart,
    scurve_chart,
    speedometer_chart,
    zone_duration_pie,
)
from .pdf_layout import _draw_contained_image, _period_str
from .pdf_tables import _data_table, _fmt_date, _hierarchy_table, _info_table, _pct_or_dash, _styles, draw_table_in_box

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
    ctx.setdefault("arabic", resolve_arabic(cfg, ctx["project"]))
    ctx.setdefault("_report", report)  # detailed_progress's lazy zone_grids needs report.project/scope_ids

    design = cfg.get("page_design") or {}
    page_w_mm, page_h_mm = _page_size_mm(design)
    master_elements = design.get("master_elements") or []

    buf = BytesIO()
    c = _canvas.Canvas(buf, pagesize=(page_w_mm * mm, page_h_mm * mm))

    instances = expand_pages(cfg, ctx, report)
    # Page numbers are fully known before anything is drawn (expand_pages
    # already assigned them), so a "toc" element can resolve real page
    # numbers in a single pass — no two-pass render needed. One row per
    # distinct page id (a repeat page's many clones collapse to its first).
    toc_map, toc_order, seen = {}, [], set()
    for inst in instances:
        pid = inst.page.get("id")
        if pid not in toc_map:
            toc_map[pid] = inst.number
        if pid not in seen:
            seen.add(pid)
            toc_order.append((pid, inst.page.get("name") or ""))
    ctx["_toc_map"], ctx["_toc_order"] = toc_map, toc_order

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
    # the running header/footer).
    if not inst.page.get("skip_master"):
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
            _draw_image(c, props, x, y, w, h, inst, ctx)
        elif t == "table":
            _draw_table_element(c, props, x, y, w, h, inst, cfg, ctx)
        elif t == "chart":
            _draw_chart_element(c, props, x, y, w, h, inst, cfg, ctx)
        elif t == "toc":
            _draw_toc_element(c, props, x, y, w, h, inst, ctx)
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
    value = resolve_field(props.get("source", ""), ctx, inst.scope, inst.number)
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


def _draw_image(c, props, x, y, w, h, inst: PageInstance, ctx):
    """`repeat.item` binds this box to one photo/attachment in the current
    repeat chunk (props["slot"] indexes inst.scope["items"]) — this is what
    lets a 4-slot "Site Photos" page turn into N real pages. Per-report image
    picking into an arbitrary non-repeat box is deferred (see plan §7.5)."""
    if props.get("source") != "repeat.item":
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
        _draw_contained_image(c, reader, x, y + caption_h, w, h - caption_h)
    _draw_image_border(c, props, x, y + caption_h, w, h - caption_h)
    if show_caption and item.get("caption"):
        style = ParagraphStyle("canvas_caption", fontName=FONT_NAME, fontSize=8, leading=10,
                               textColor=hexcolor("#595959"), alignment=TA_CENTER)
        para = Paragraph(shape(item["caption"]), style)
        para.wrap(w, caption_h)
        para.drawOn(c, x, y)


def _draw_toc_element(c, props, x, y, w, h, inst: PageInstance, ctx):
    """Lists every other page in the template with its real, resolved page
    number and a dotted leader — built from the number map build_canvas_pdf
    computes up front (see build_canvas_pdf's toc_map/toc_order)."""
    toc_map, toc_order = ctx.get("_toc_map") or {}, ctx.get("_toc_order") or []
    own_id = inst.page.get("id")
    exclude_cover = props.get("exclude_cover", True)
    size = float(props.get("size", 11))
    row_h = float(props.get("row_height", 8)) * mm
    color = hexcolor(props.get("color", "#1e2430"))
    rtl = bool(ctx.get("arabic"))

    rows = []
    for pid, name in toc_order:
        if pid == own_id or pid not in toc_map:
            continue
        if exclude_cover and name.strip().lower() in ("cover",):
            continue
        rows.append((name, toc_map[pid]))

    c.setFont(FONT_NAME, size)
    cy = y + h - size
    for name, number in rows:
        if cy < y:
            break
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
    source = props.get("source", "")
    table = resolve_table(source, cfg, ctx, inst.scope)
    if table is None:
        _draw_placeholder(c, x, y, w, h, f"No data: {source}")
        return
    if not draw_table_in_box(c, table, x, y, w, h):
        _draw_placeholder(c, x, y, w, h, f"Table too small: {source}")


def _draw_chart_element(c, props, x, y, w, h, inst: PageInstance, cfg, ctx):
    source = props.get("source", "")
    min_w, min_h = MIN_CHART_W_MM * mm, MIN_CHART_H_MM * mm
    if w < min_w or h < min_h:
        _draw_placeholder(c, x, y, w, h, f"Chart too small: {source}")
        return
    drawing = resolve_chart(source, props.get("chart_type"), cfg, ctx, inst.scope, w, h)
    if drawing is None:
        _draw_placeholder(c, x, y, w, h, f"No data: {source}")
        return
    from reportlab.graphics import renderPDF
    renderPDF.draw(drawing, c, x, y)


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

def resolve_table(source: str, cfg: dict, ctx: dict, scope: dict):
    """Build a ready-to-draw Table flowable for one of reportElements.ts's
    TABLE_SOURCES (plus the item-scoped `item.children`, available on a
    repeating page), reusing the exact row-construction logic and labels the
    legacy renderer uses (pdf.py) — or None when there's nothing to show."""
    styles = _styles(cfg)
    labels = cfg["labels"]
    rtl = bool(ctx.get("arabic"))
    p = ctx.get("project") or {}

    if source == "item.children":
        children = (scope.get("item") or {}).get("children") or []
        if not children:
            return None
        rows = [[c["name"],
                 f"{c['actual']:.1f}%" if c.get("actual") is not None else "—",
                 f"{c['planned']:.1f}%" if c.get("planned") is not None else "—"] for c in children]
        return _data_table(cfg, styles, [labels["col_zone"], labels["col_actual"], labels["col_planned"]],
                            rows, col_widths=[None, 30 * mm, 30 * mm])
    if source.startswith("item."):
        return None  # no other item-scoped table source defined

    if source == "project_info":
        dur = ctx.get("duration") or {}
        rows = [
            (labels["info_name"], p.get("name")),
            (labels.get("info_code", "Code"), p.get("code")),
            (labels["info_client"], p.get("client")),
            (labels["info_consultant"], p.get("consultant")),
            (labels["info_contractor"], p.get("contractor")),
            (labels["info_type"], p.get("type")),
            (labels["info_location"], p.get("location")),
            (labels["info_budget"], f"{p['budget']:,.0f} {p['currency']}" if p.get("budget") else ""),
            (labels.get("info_duration", "Duration"),
             f"{dur['total']} {labels['unit_days']}" if dur.get("total") else ""),
            (labels["info_start"], _fmt_date(p.get("planned_start"))),
            (labels["info_finish"], _fmt_date(p.get("planned_finish"))),
            (labels.get("info_revised", "Forecast finish"),
             _fmt_date(p.get("revised_finish")) if p.get("revised_finish") else ""),
            (labels.get("info_delay", "Delay"), f"{dur['delay']} {labels['unit_days']}" if dur.get("delay") else ""),
            (labels["info_size"], f"{p['size_sqm']:,.0f} {labels['unit_sqm']}" if p.get("size_sqm") else ""),
        ]
        rows = [(k, v) for k, v in rows if v and v != "—"]
        return _info_table(cfg, styles, rows, rtl) if rows else None

    if source == "zone_progress":
        zones = ctx.get("zones") or []
        if not zones:
            return None
        rows = [[z["name"], f"{z['progress']:.1f}%"] for z in zones]
        return _data_table(cfg, styles, [labels["col_zone"], labels["col_progress"]], rows, col_widths=[None, 40 * mm])

    if source == "hierarchy_progress":
        hierarchy = ctx.get("hierarchy") or []
        return _hierarchy_table(cfg, styles, hierarchy, labels, rtl) if hierarchy else None

    if source == "discipline_progress":
        discipline = ctx.get("discipline") or []
        if not discipline:
            return None
        header = [labels["col_unit"], labels["col_concrete"], labels["col_architecture"],
                  labels["col_electrical"], labels["col_mechanical"], labels["col_other"]]
        rows = [[r["name"]] + [_pct_or_dash(r.get(d)) for d in
                               ("concrete", "architecture", "electrical", "mechanical", "other")]
                for r in discipline]
        return _data_table(cfg, styles, header, rows)

    if source == "progress_compare":
        zones = [z for z in (ctx.get("zones") or []) if z.get("planned") is not None]
        if not zones:
            return None
        rows = [[z["name"],
                 f"{z['planned']:.1f}%" if z.get("planned") is not None else "—",
                 f"{z['previous']:.1f}%" if z.get("previous") is not None else "—",
                 f"{z['progress']:.1f}%"] for z in zones]
        return _data_table(cfg, styles,
            [labels["col_zone"], labels["col_planned"], labels["col_previous"], labels["col_actual"]],
            rows, col_widths=[None, 28 * mm, 28 * mm, 28 * mm])

    if source == "milestones":
        milestones = ctx.get("milestones") or []
        if not milestones:
            return None
        rows = [[m["title"], _fmt_date(m["date"]), m["status"].replace("_", " ").title()] for m in milestones]
        return _data_table(cfg, styles, [labels["col_milestone"], labels["col_date"], labels["col_status"]],
                            rows, col_widths=[None, 32 * mm, 34 * mm])

    if source == "invoices":
        invoices = ctx.get("invoices") or []
        if not invoices:
            return None
        rows = [[i["name"], f"{i['value']:,.2f}", _fmt_date(i["date"]) if i["date"] else "—"] for i in invoices]
        rows.append([labels.get("col_total", "Total"), f"{ctx.get('invoices_total', 0):,.2f}", ""])
        return _data_table(cfg, styles,
            [labels.get("col_invoice", "Item"), labels.get("col_value", "Value"), labels["col_date"]],
            rows, col_widths=[None, 36 * mm, 30 * mm])

    if source == "submittals":
        rows = (ctx.get("submittals") or {}).get("rows") or []
        if not rows:
            return None
        return _data_table(cfg, styles,
            [labels.get("col_invoice", "Item"), labels.get("col_type", "Type"),
             labels.get("col_discipline", "Discipline"), labels["col_status"]],
            [[r["title"], r["type"], r["discipline"], r["status"]] for r in rows])

    if source == "delays":
        delays = ctx.get("delays") or []
        if not delays:
            return None
        rows = [[d["title"], str(d["impact_days"]), d["status"].title()] for d in delays]
        return _data_table(cfg, styles, [labels["col_delay"], labels["col_impact"], labels["col_status"]],
                            rows, col_widths=[None, 28 * mm, 28 * mm])

    if source == "detailed_progress":
        return _resolve_detailed_progress_table(cfg, ctx, styles)

    if source == "critical_path_delays":
        rows_data = ctx.get("critical_path") or []
        if not rows_data:
            return None
        rows = [[r["name"], _fmt_date(r["planned_finish"]), _fmt_date(r["forecast_finish"]), str(r["delay_days"])]
                for r in rows_data]
        return _data_table(cfg, styles,
            [labels["col_zone"], labels["info_finish"], labels["col_forecast_finish"], labels["delay_days"]],
            rows, col_widths=[None, 32 * mm, 32 * mm, 28 * mm])

    return None


def _resolve_detailed_progress_table(cfg, ctx, styles):
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
    return _data_table(cfg, styles, header, rows)


# ── Chart binding ────────────────────────────────────────────────────────────

def resolve_chart(source: str, chart_type, cfg: dict, ctx: dict, scope: dict, w: float, h: float):
    """Build a ready-to-draw Drawing for one of reportElements.ts's
    CHART_SOURCES (plus the item-scoped `item.units`/`item.duration`,
    available on a repeating page), at the given box size (points) — or None
    with nothing to show."""
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
        return planned_actual_chart(cfg, ctx, w, labels, height=h)
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
    if source == "gantt":
        return gantt_chart(cfg, ctx.get("gantt") or [], w, labels, height=h)
    return None


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


_REPEAT_SOURCES = {
    "photos": "photos",
    "attachments": "attachments",
    "area_dashboards": "area_dashboards",
    "zones": "zones",
    "areas": "areas",
}


def _repeat_items(source, ctx, report) -> list:
    """Map a repeat source to its ctx list. `report` isn't needed today (every
    source is already computed onto ctx by build_report_context) but is kept
    in the signature in case a future source needs a fresh query."""
    key = _REPEAT_SOURCES.get(source)
    return list(ctx.get(key) or []) if key else []
