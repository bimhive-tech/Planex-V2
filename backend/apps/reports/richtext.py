"""Rich-text description: sanitize the builder's HTML and render it to reportlab
flowables, preserving bold / italic / underline / color / size, bullet & numbered
lists, and alignment — including correct right-to-left shaping for Arabic.

Arabic can't be bidi-shaped per inline run and naively concatenated (the runs end
up out of order). Instead, for a right-to-left line we reverse the run order and
shape each run on its own; format boundaries fall on spaces in practice, so glyph
joining is preserved. This was verified to match a fully-shaped reference line.

Also supports inline embeds — a table/chart/image dropped into the flowing text
(see CustomTableEditor.tsx's sibling in RichTextEditor.tsx, the "Insert
table/chart/image" toolbar buttons) — stored as a `<div data-embed="table|chart|
image" data-spec="{...json...}">` marker the sanitizer keeps verbatim (its own
children are ignored; the marker is self-describing) and html_to_flowables
resolves into a real Table/Drawing/Image flowable via the exact same
resolve_table/resolve_chart every canvas table/chart element already uses (see
_resolve_embed below) — so an embedded table/chart can't render a different look
than a standalone one would."""
import json
import re
from html import escape
from html.parser import HTMLParser

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph

from .pdf_base import FONT_NAME, ensure_fonts, has_arabic, hexcolor, shape, storage_image_reader
# resolve_table/resolve_chart live in pdf_canvas.py, which never imports this
# module back (any drawing code that needs html_to_flowables imports it
# locally, inside the function that calls it) — so this stays a one-way
# dependency, not a cycle.
from .pdf_canvas import resolve_chart, resolve_table

# Tags we keep when sanitizing; everything else is unwrapped (text kept, tag dropped).
_INLINE = {"b", "strong", "i", "em", "u", "span", "font"}
_BLOCK = {"p", "div", "li"}
_LIST = {"ul", "ol"}
_KEEP = _INLINE | _BLOCK | _LIST | {"br"}
# Tags whose contents are discarded wholesale (never just unwrapped).
_DROP = {"script", "style", "head", "title", "noscript", "iframe", "object", "embed"}
# A `<div data-embed="...">` in one of these carries a self-contained JSON spec
# in `data-spec` (see _resolve_embed) instead of text content — its own
# children (a display label the editor shows for its own UI) are dropped on
# sanitize and never read on render, so there's nothing to keep in sync.
_EMBED_KINDS = {"table", "chart", "image"}

# HTML <font size> 1–7 → point sizes (roughly Word's small→huge scale).
_SIZE_MAP = {"1": 8, "2": 10, "3": 11, "4": 13, "5": 16, "6": 20, "7": 26}
# Safe CSS properties we read off `style="…"`.
_STYLE_PROPS = {"color", "font-size", "font-weight", "font-style", "text-decoration", "text-align"}


class _Node:
    __slots__ = ("tag", "attrs", "children", "data")

    def __init__(self, tag=None, attrs=None, data=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.data = data


class _DOM(HTMLParser):
    """Tiny, forgiving HTML→tree parser for the editor's output."""

    VOID = {"br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        top = self.stack[-1].tag
        # Auto-close an open block when a sibling block opens (contentEditable is
        # usually balanced, but be forgiving about <li>/<p> without a close tag).
        if tag in _BLOCK | _LIST and top in _BLOCK:
            self.stack.pop()
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag.lower(), dict(attrs)))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(_Node(None, data=data))


def _parse_style(raw):
    out = {}
    for part in (raw or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            k = k.strip().lower()
            if k in _STYLE_PROPS:
                out[k] = v.strip().lower()
    return out


def _clean_color(value):
    """Accept #rgb/#rrggbb or rgb(…); return a #rrggbb hex or None."""
    v = (value or "").strip()
    if v.startswith("#") and len(v) in (4, 7):
        return v
    if v.startswith("rgb"):
        nums = [int(n) for n in re.findall(r"\d+", v)[:3]]
        if len(nums) == 3:
            return "#%02x%02x%02x" % tuple(nums)
    return None


def _px_to_pt(value):
    try:
        n = float("".join(c for c in value if (c.isdigit() or c == ".")))
    except ValueError:
        return None
    if not n:
        return None
    return round(n * 0.75, 1) if "px" in value else round(n, 1)


def _merge_format(fmt, node):
    """Inherit `fmt` and layer this node's formatting on top."""
    f = dict(fmt)
    t = node.tag
    if t in ("b", "strong"):
        f["bold"] = True
    elif t in ("i", "em"):
        f["italic"] = True
    elif t == "u":
        f["underline"] = True
    elif t == "font":
        if _clean_color(node.attrs.get("color", "")):
            f["color"] = _clean_color(node.attrs["color"])
        if node.attrs.get("size") in _SIZE_MAP:
            f["size"] = _SIZE_MAP[node.attrs["size"]]
    style = _parse_style(node.attrs.get("style", ""))
    if _clean_color(style.get("color", "")):
        f["color"] = _clean_color(style["color"])
    fw = style.get("font-weight", "")
    if "bold" in fw or fw in ("600", "700", "800", "900"):
        f["bold"] = True
    if style.get("font-style") == "italic":
        f["italic"] = True
    if "underline" in style.get("text-decoration", ""):
        f["underline"] = True
    if "font-size" in style:
        pt = _px_to_pt(style["font-size"])
        if pt:
            f["size"] = pt
    return f


def _block_align(node):
    style = _parse_style(node.attrs.get("style", ""))
    a = style.get("text-align") or (node.attrs.get("align") or "").lower()
    return {"left": TA_LEFT, "right": TA_RIGHT, "center": TA_CENTER, "justify": TA_LEFT}.get(a)


def _collect_runs(node, fmt, runs):
    """Flatten a block's inline content into (text, format) runs in logical order;
    <br> becomes a '\\n' marker so we can split the block into visual lines."""
    for ch in node.children:
        if ch.tag is None:
            if ch.data:
                runs.append((ch.data, fmt))
        elif ch.tag == "br":
            runs.append(("\n", fmt))
        elif ch.tag == "div" and ch.attrs.get("data-embed") in _EMBED_KINDS:
            # An embed can't become a text run — in practice the sanitizer's
            # own auto-close-on-sibling-block parsing (_DOM.handle_starttag)
            # already promotes it to a top-level sibling (html_to_flowables'
            # own loop handles it there), so reaching it here only happens
            # for a genuinely stray nested case; skip rather than absorb it
            # as blank text.
            continue
        elif ch.tag in _INLINE:
            _collect_runs(ch, _merge_format(fmt, ch), runs)
        elif ch.tag in _BLOCK | _LIST:
            # Stray nested block — flatten with a line break around it.
            runs.append(("\n", fmt))
            _collect_runs(ch, fmt, runs)
            runs.append(("\n", fmt))


def _split_lines(runs):
    lines, cur = [], []
    for text, fmt in runs:
        if text == "\n":
            lines.append(cur)
            cur = []
        else:
            cur.append((text, fmt))
    lines.append(cur)
    return [ln for ln in lines if any(t.strip() for t, _ in ln)]


def _esc(text):
    return escape(text, quote=False)


def _wrap(s, f):
    if f.get("color") or f.get("size"):
        attrs = ""
        if f.get("color"):
            attrs += f' color="{f["color"]}"'
        if f.get("size"):
            attrs += f' size="{f["size"]:g}"'
        s = f"<font{attrs}>{s}</font>"
    if f.get("bold"):
        s = f"<b>{s}</b>"
    if f.get("italic"):
        s = f"<i>{s}</i>"
    if f.get("underline"):
        s = f"<u>{s}</u>"
    return s


def _line_markup(line_runs, rtl, prefix=""):
    """Reportlab markup for one visual line. For RTL we reverse the run order and
    shape each run independently (see module docstring). reportlab lays the markup
    out left→right, so a list marker goes at the *end* for RTL (its right edge)
    and at the *start* for LTR (its left edge)."""
    seq = list(reversed(line_runs)) if rtl else list(line_runs)
    core = "".join(_wrap(_esc(shape(text)), f) for text, f in seq if text)
    if not prefix:
        return core
    marker = _esc(prefix)
    gap = "&nbsp;&nbsp;"
    return f"{core}{gap}{marker}" if rtl else f"{marker}{gap}{core}"


def _line_para(line_runs, cfg, base_size, default_color, default_align, prefix=""):
    plain = "".join(t for t, _ in line_runs)
    rtl = has_arabic(plain)
    align = default_align if default_align is not None else (TA_RIGHT if rtl else TA_LEFT)
    size = max([f.get("size", base_size) for _, f in line_runs] or [base_size])
    lead = float(cfg["fonts"].get("line_spacing", 1.5))
    markup = _line_markup(line_runs, rtl, prefix)
    st = ParagraphStyle("rt", fontName=FONT_NAME, fontSize=size, leading=size * lead,
                        textColor=hexcolor(default_color), alignment=align, spaceAfter=4)
    return Paragraph(markup or "&nbsp;", st)


def _resolve_embed(node, cfg, ctx, scope, avail_width):
    """One `<div data-embed="table|chart|image" data-spec="{...}">` marker ->
    a real flowable, or None if the spec is malformed/unresolvable (dropped
    silently, same "genuinely nothing to show" contract resolve_table/
    resolve_chart already have — never a broken PDF over one bad embed).

    `data-spec` is `{"kind": ..., "props": {...}}` — `props` is the exact
    same shape a canvas table/chart element's own `props` would be (source,
    style, overrides, scope_zone_id, chart_type, custom_data...), so an
    embedded table/chart is resolved through the identical resolve_table/
    resolve_chart every standalone table/chart element already uses — it
    can't end up looking different just because it's inline."""
    if ctx is None:
        return None
    try:
        spec = json.loads(node.attrs.get("data-spec") or "{}")
    except (TypeError, ValueError):
        return None
    kind, props = spec.get("kind"), spec.get("props") or {}
    scope = scope if scope is not None else {"item": None}

    if kind == "table":
        return resolve_table(
            props.get("source", ""), cfg, ctx, scope, avail_width=avail_width,
            overrides=props.get("overrides"), style=props, scope_zone_id=props.get("scope_zone_id"),
        )
    if kind == "chart":
        height = float(props.get("embed_height_mm", 80)) * mm
        return resolve_chart(
            props.get("source", ""), props.get("chart_type"), cfg, ctx, scope,
            avail_width, height, scope_zone_id=props.get("scope_zone_id"),
        )
    if kind == "image":
        upload_id, report = props.get("upload_id"), ctx.get("_report")
        if not upload_id or report is None:
            return None
        from .models import ReportImage

        try:
            image = ReportImage.objects.get(id=upload_id, report=report)
        except (ReportImage.DoesNotExist, ValueError, TypeError):
            return None
        reader = storage_image_reader(image.image.name if image.image else None)
        if not reader:
            return None
        iw, ih = reader.getSize()
        if not iw or not ih:
            return None
        width = avail_width or iw
        height = width * (ih / iw)
        max_h = float(props.get("max_height_mm", 120)) * mm
        if height > max_h:
            height, width = max_h, max_h * (iw / ih)
        return Image(reader, width=width, height=height)
    return None


def _render_block(node, cfg, base_size, default_color, flow, ctx=None, scope=None, avail_width=None):
    """Emit flowable(s) for one top-level node (block, list, embed, or stray
    inline)."""
    if node.tag == "div" and node.attrs.get("data-embed") in _EMBED_KINDS:
        flowable = _resolve_embed(node, cfg, ctx, scope, avail_width)
        if flowable is not None:
            flow.append(flowable)
        return

    if node.tag is None:
        if node.data and node.data.strip():
            flow.append(_line_para([(node.data, {})], cfg, base_size, default_color, None))
        return

    if node.tag in _LIST:
        ordered = node.tag == "ol"
        list_align = _block_align(node)  # alignment set on the <ul>/<ol> itself
        idx = 0
        for li in node.children:
            if li.tag != "li":
                continue
            idx += 1
            runs = []
            _collect_runs(li, {}, runs)
            lines = _split_lines(runs) or [[("", {})]]
            align = _block_align(li)
            if align is None:
                align = list_align
            prefix = f"{idx}." if ordered else "•"
            for i, ln in enumerate(lines):
                flow.append(_line_para(ln, cfg, base_size, default_color, align,
                                       prefix=prefix if i == 0 else ""))
        return

    # Paragraph / div / stray inline → one or more lines. For a stray inline tag
    # the node's own formatting must seed the run format.
    runs = []
    seed = _merge_format({}, node) if node.tag in _INLINE else {}
    _collect_runs(node, seed, runs)
    align = _block_align(node)
    for ln in _split_lines(runs):
        flow.append(_line_para(ln, cfg, base_size, default_color, align))


def html_to_flowables(html, cfg, styles, *, ctx=None, scope=None, avail_width=None):
    """Render sanitized description HTML into reportlab flowables.

    `ctx`/`scope`/`avail_width` are only needed to resolve an inline table/
    chart/image embed (see _resolve_embed) — omitted (the default), any
    embed marker in `html` is silently dropped rather than resolved, so a
    caller with no report context (there is none today) still gets valid
    plain-text flowables instead of a crash."""
    ensure_fonts()  # Paragraphs use the Amiri family; register it if not already
    ds = cfg.get("description", {})
    base_size = float(ds.get("size", cfg["fonts"]["base_size"]))
    default_color = ds.get("color", cfg["colors"]["text"])
    dom = _DOM()
    dom.feed(html or "")
    flow = []
    for node in dom.root.children:
        _render_block(node, cfg, base_size, default_color, flow, ctx=ctx, scope=scope, avail_width=avail_width)
    return flow


# --- sanitization (storage + browser safety) --------------------------------

def _safe_attrs(tag, attrs):
    out = {}
    if tag == "div" and attrs.get("data-embed") in _EMBED_KINDS:
        # Self-describing marker — keep exactly these two attrs, nothing
        # else (no style/align; an embed box isn't formatted like text).
        out["data-embed"] = attrs["data-embed"]
        out["data-spec"] = attrs.get("data-spec") or "{}"
        return out
    if tag == "font":
        if _clean_color(attrs.get("color", "")):
            out["color"] = _clean_color(attrs["color"])
        if attrs.get("size") in _SIZE_MAP:
            out["size"] = attrs["size"]
    style = _parse_style(attrs.get("style", ""))
    # Keep alignment on blocks; keep text styling on inline.
    keep = {k: v for k, v in style.items() if k in _STYLE_PROPS}
    if keep:
        out["style"] = ";".join(f"{k}:{v}" for k, v in keep.items())
    if tag in _BLOCK and attrs.get("align", "").lower() in ("left", "right", "center", "justify"):
        out.setdefault("align", attrs["align"].lower())
    return out


def _serialize(node, parts):
    if node.tag is None:
        if node.data:
            parts.append(_esc(node.data))
        return
    if node.tag == "br":
        parts.append("<br/>")
        return
    if node.tag in _DROP:
        return
    if node.tag not in _KEEP:
        for ch in node.children:  # unwrap: drop tag, keep contents
            _serialize(ch, parts)
        return
    attrs = _safe_attrs(node.tag, node.attrs)
    attr_str = "".join(f' {k}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
    parts.append(f"<{node.tag}{attr_str}>")
    # An embed's children are the editor's own display chip (an icon/label
    # for its non-editable UI, no real content) — the marker's data-spec
    # attribute is the entire source of truth, so children are never stored.
    if not (node.tag == "div" and node.attrs.get("data-embed") in _EMBED_KINDS):
        for ch in node.children:
            _serialize(ch, parts)
    parts.append(f"</{node.tag}>")


def sanitize_html(raw):
    """Whitelist the editor's HTML to a safe, canonical subset for storage and for
    re-loading into the browser editor. Drops scripts, handlers, unknown tags."""
    if not raw:
        return ""
    dom = _DOM()
    dom.feed(raw)
    parts = []
    for node in dom.root.children:
        _serialize(node, parts)
    return "".join(parts).strip()


def sanitize_layout_html(layout):
    """Sanitizes every "description" element's `props.html` in place across a
    template `config` or a report `layout_override` — both share the same
    `{page_design: {master_elements}, layout: {pages: [{elements}]}}` shape
    (see ReportTemplateSerializer.validate_config / ReportWriteSerializer.
    validate_layout_override, the only two callers). A description element's
    rich text lives per-element now (edited directly on the canvas), not in
    one report-wide `description_html` field, but it still needs the exact
    same whitelist that field always got before it's stored or rendered —
    moving *where* the content lives doesn't relax *what* HTML reaches the
    renderer/database."""
    def sanitize_elements(elements):
        for el in elements or []:
            if not isinstance(el, dict) or el.get("type") != "description":
                continue
            props = el.get("props")
            if isinstance(props, dict) and "html" in props:
                props["html"] = sanitize_html(props["html"])

    sanitize_elements((layout.get("page_design") or {}).get("master_elements"))
    for page in (layout.get("layout") or {}).get("pages") or []:
        if isinstance(page, dict):
            sanitize_elements(page.get("elements"))
    return layout
