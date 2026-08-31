"""Table builders shared by both PDF renderers (the legacy flowing generator in
pdf.py and the canvas-box renderer in pdf_canvas.py). Moved out of pdf.py
verbatim — same styling/behavior, just relocated so pdf_canvas.py doesn't need
to import the whole flowing-document module to build a table."""
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, Table, TableStyle

from .pdf_base import BOLD, FONT_NAME, has_arabic, hexcolor, shape

NOTE_HEIGHT = 4 * mm  # space reserved under a truncated table for the "+N more" note
CELL_H_PADDING = 16  # LEFTPADDING + RIGHTPADDING as set on every table style below
MIN_COL_WIDTH = 15 * mm


TABLE_STYLE_PROP_KEYS = (
    "zebra", "border", "header_bg", "header_text", "text_color", "border_color", "zebra_color",
    "header_bold", "font_size", "cell_padding",
)


def table_style_override(cfg: dict, props: dict | None) -> dict:
    """A table element's own style props (`zebra`/`border`/`header_bg`/
    `header_text`/`text_color`/`border_color`/`zebra_color`/`header_bold`/
    `font_size`/`cell_padding` — edited via the Customize tab's Properties
    panel, same flat-prop convention every other element type already uses)
    layered over the report's global table defaults, as a patched copy of
    `cfg` — every table builder below (and `_styles`) reads
    `cfg["colors"]`/`cfg["table"]`/`cfg["fonts"]` exactly as it always did,
    so this is the only place that needs to know these prop names; nothing
    downstream needs a second code path. `props` is the element's *whole*
    props dict (it also carries `source`/`overrides`/etc, ignored here) —
    `None` or a table with none of TABLE_STYLE_PROP_KEYS set returns `cfg`
    completely untouched, which is the overwhelming majority of tables.

    These same props existed before this function did, wired into the
    Properties panel — but were never actually read by the real PDF
    (_draw_table_element only ever read `source`), so toggling them changed
    nothing anyone could see. This is what makes them real.

    Deliberately per-table-element, not per-cell/column: this mirrors the
    real PDF table builders' own granularity (one shared style per table),
    not a spreadsheet-style per-cell format model, which none of
    _info_table/_data_table/_hierarchy_table_flat are built to express."""
    if not props or not any(k in props for k in TABLE_STYLE_PROP_KEYS):
        return cfg
    colors = {**cfg["colors"]}
    tcfg = {**cfg["table"]}
    fonts = {**cfg["fonts"]}
    if props.get("header_bg"):
        colors["table_header_bg"] = props["header_bg"]
    if props.get("header_text"):
        colors["table_header_text"] = props["header_text"]
    if props.get("text_color"):
        colors["text"] = props["text_color"]
    if props.get("border_color"):
        colors["table_border"] = props["border_color"]
    if props.get("zebra_color"):
        colors["table_row_alt"] = props["zebra_color"]
    if "border" in props:
        tcfg["border"] = bool(props["border"])
    if "zebra" in props:
        tcfg["zebra"] = bool(props["zebra"])
    if "header_bold" in props:
        tcfg["header_bold"] = bool(props["header_bold"])
    if props.get("cell_padding") is not None:
        tcfg["cell_padding"] = props["cell_padding"]
    if props.get("font_size"):
        fonts["base_size"] = props["font_size"]
    return {**cfg, "colors": colors, "table": tcfg, "fonts": fonts}


def _styles(cfg):
    f, c = cfg["fonts"], cfg["colors"]
    lead = float(f.get("line_spacing", 1.5))

    def mk(name, size, color, *, font=FONT_NAME, align=TA_LEFT, sb=0, sa=6):
        return ParagraphStyle(name, fontName=font, fontSize=size, textColor=hexcolor(color),
                              leading=size * lead, alignment=align, spaceBefore=sb, spaceAfter=sa)

    return {
        "section": ParagraphStyle("SectionHeading", fontName=BOLD, fontSize=f["h2_size"],
                                  textColor=hexcolor(c["section_heading"]), alignment=TA_CENTER,
                                  leading=f["h2_size"] * 1.3, spaceBefore=4, spaceAfter=4),
        "sub": mk("sub", f["h3_size"], c["section_heading"], font=BOLD, sb=8, sa=4),
        "body": mk("body", f["base_size"], c["text"]),
        "bullet": mk("bullet", f["base_size"], c["text"], sa=3),
        "muted": mk("muted", f["base_size"] - 1, c["muted"]),
        "value": mk("value", f["base_size"], c["text"], font=BOLD),
    }


def _wrap_shape(text, font_name, font_size, max_width) -> str:
    """Break `text` into lines that fit `max_width` when rendered, shaping
    (reshape + bidi-reorder) each line separately, then join with <br/>.

    Arabic must be shaped *after* it's known where each line breaks — shaping
    the whole string first and then letting ReportLab's own word-wrap re-break
    the already bidi-reordered result garbles the text (the visible symptom:
    long Arabic values in a narrow table column render as cut-off fragments).
    Shaping line-by-line up front means Paragraph never needs to re-wrap.
    """
    text = str(text or "")
    if not text:
        return ""
    words = text.split(" ")
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = current + [word]
        trial_shaped = shape(" ".join(trial))
        if current and stringWidth(trial_shaped, font_name, font_size) > max_width:
            lines.append(shape(" ".join(current)))
            current = [word]
        else:
            current = trial
    if current:
        lines.append(shape(" ".join(current)))
    return "<br/>".join(lines)


def _aligned(style, text, *, force=None, max_width=None):
    s = ParagraphStyle(f"{style.name}_a", parent=style)
    s.alignment = force if force is not None else (TA_RIGHT if has_arabic(text) else TA_LEFT)
    if max_width and has_arabic(text):
        return Paragraph(_wrap_shape(text, s.fontName, s.fontSize, max_width), s)
    return Paragraph(shape(text), s)


def enum_label(cfg, text):
    """Translate a model enum's English display label through the template's
    own `labels` (see the "enum_*" keys). The models keep English labels
    because the UI and API depend on them, so a fully-Arabic report has to
    localise them at render time or print English inside Arabic tables.
    Anything without a key falls through unchanged, so an enum added later
    degrades to its English label rather than breaking."""
    raw = str(text or "")
    if not raw:
        return raw
    key = "enum_" + raw.strip().lower().replace(" ", "_")
    return cfg.get("labels", {}).get(key, raw)


def _fmt_date(d):
    return d.strftime("%d %b %Y") if d else "—"


def _pct_or_dash(v):
    return f"{v:.1f}%" if v is not None else "—"


def apply_table_overrides(kind, header, rows, overrides, hidden_rows=None, hidden_cols=None):
    """Substitute cell text with a report's own manual overrides (the
    "table" element's `overrides` prop, edited via the Customize tab's
    live table preview) — mutates `header`/`rows` in place *before* either
    the raw JSON path (views.table_data) or a real _xxx_table builder sees
    them, so an edit is never just a cosmetic preview trick: the exact same
    substituted value is what the downloaded PDF draws too.

    Keys: `hc{col}` for a header cell, `r{row}c{col}` for a body cell.
    "hierarchy" rows are dicts, not lists — `col` there is a fixed
    0=name/1=actual/2=previous/3=planned mapping, matching the raw JSON
    shape (see resolve_table's hierarchy_progress branch).

    `hidden_rows` (the element's own `hidden_rows` prop — a data-bound
    table's rows can't be deleted like a custom table's can, since they're
    computed from real project data, but a report author can still choose
    to drop specific ones from this one report's view) is a list/set of
    *original* row indices to remove entirely — applied last, after cell
    overrides, so a hidden row's own overrides (if any) are simply
    discarded with it rather than shifting onto a different row.

    `hidden_cols` is the same idea for columns (2026-08-30): a bound table
    often carries more columns than the page can hold, and until now the only
    remedies were shrinking the font or turning the page landscape. Applied
    after cell overrides for the same reason — so a dropped column's
    overrides go with it instead of sliding onto its neighbour. "hierarchy"
    rows are dicts with a fixed column meaning, so dropping a column there
    would change what the remaining values mean; it's ignored for that kind."""
    if overrides:
        if header:
            for j in range(len(header)):
                key = f"hc{j}"
                if key in overrides:
                    header[j] = overrides[key]
        if kind == "hierarchy":
            cols = ("name", "actual", "previous", "planned")
            for i, row in enumerate(rows):
                for j, col in enumerate(cols):
                    key = f"r{i}c{j}"
                    if key in overrides:
                        row[col] = overrides[key]
        else:
            for i, row in enumerate(rows):
                for j in range(len(row)):
                    key = f"r{i}c{j}"
                    if key in overrides:
                        row[j] = overrides[key]
    if hidden_rows:
        hidden = set(hidden_rows)
        rows[:] = [row for i, row in enumerate(rows) if i not in hidden]
    # Never applied to "hierarchy": its rows are dicts whose columns carry
    # fixed meanings (name/actual/previous/planned), so removing one would
    # silently change what the rest represent.
    if hidden_cols and kind != "hierarchy":
        drop = set(hidden_cols)
        if header:
            header[:] = [h for j, h in enumerate(header) if j not in drop]
        for i, row in enumerate(rows):
            rows[i] = [c for j, c in enumerate(row) if j not in drop]


def _info_table(cfg, styles, rows, rtl, avail_width=None, highlight_labels=None):
    """Bordered 2-col table: label on the right, value on the left (RTL look).

    `avail_width` (the box/frame width this table will actually be drawn
    into, in points) lets the value column wrap long text correctly instead
    of relying on ReportLab to shrink-then-rewrap the auto ("None") column,
    which is what garbles long Arabic values — see `_wrap_shape`.

    `highlight_labels` (a set of already-resolved label strings, e.g.
    `{labels["info_delay"], labels["info_forecast"]}`) tints a whole row —
    matches the client's own reference report's own convention of visually
    flagging its schedule-risk rows (forecast/delay dates) rather than
    letting them blend into the rest of the table, found comparing our
    build to that reference directly (2026-08-26). `None`/empty highlights
    nothing, unchanged from before this parameter existed.
    """
    c, tcfg = cfg["colors"], cfg["table"]
    # Dedicated compact leading (1.15x) instead of the shared prose styles'
    # 1.5x: a spec table's row height is dominated by wrapped-label line
    # count, not paragraph spacing (spaceAfter has no effect on Table cell
    # height — reportlab only applies it in frame/story flow). At the
    # default 1.5x leading, a project with every optional field populated
    # (contract value, approved value, forecast cost, advance payment, all
    # 4 (Part) fields — 26 rows total) can't fit even at font_size=7; at
    # 1.15x + a narrower 50mm label column it fits with margin at
    # font_size=8, matching the reference's own denser convention. Confirmed
    # empirically 2026-08-26.
    size = cfg["fonts"]["base_size"]
    lead = size * 1.15
    # Blue label text on a plain white cell — the reference report's own
    # project-info table (جدول 1) styles its labels by colour, not by a
    # filled column, and reads far lighter for it (2026-08-30).
    label_style = ParagraphStyle("lbl", fontName=BOLD, fontSize=size, textColor=hexcolor(c["heading"]),
                                  leading=lead, alignment=TA_RIGHT)
    body_style = ParagraphStyle("bodyc", fontName=styles["body"].fontName, fontSize=size,
                                 textColor=hexcolor(c["text"]), leading=lead)
    label_highlight_style = ParagraphStyle("lblh", parent=label_style, fontName=BOLD)
    body_highlight_style = ParagraphStyle("bodyh", parent=body_style, fontName=BOLD)
    label_w = 50 * mm
    value_max_width = max(avail_width - label_w - CELL_H_PADDING, MIN_COL_WIDTH) if avail_width else None
    highlight_labels = highlight_labels or set()
    data = []
    highlight_rows = []
    for label, value in rows:
        is_highlighted = label in highlight_labels
        if is_highlighted:
            highlight_rows.append(len(data))
        # No bullet/marker before the label — matches the reference report's
        # own plain "LABEL: value" convention exactly (found 2026-08-26; an
        # earlier session used a bullet here since Amiri has no glyph for a
        # real ■, but the reference doesn't use any marker at all).
        lbl = Paragraph(shape(label), label_highlight_style if is_highlighted else label_style)
        val = _aligned(
            body_highlight_style if is_highlighted else body_style, value,
            force=TA_RIGHT if rtl else TA_LEFT, max_width=value_max_width,
        )
        data.append([val, lbl] if rtl else [lbl, val])
    widths = [None, label_w] if rtl else [label_w, None]
    pad = float(tcfg.get("cell_padding", 6))
    t = Table(data, colWidths=widths)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # No fill behind the label column — see label_style above.
        ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    for r in highlight_rows:
        style.append(("BACKGROUND", (0, r), (-1, r), hexcolor(c["table_highlight"])))
    # Always bordered historically (no toggle existed) — default stays True
    # so an untouched template renders exactly as before; now overridable
    # like every other table kind's border.
    if tcfg.get("border", True):
        style.append(("GRID", (0, 0), (-1, -1), 0.7, hexcolor(c["table_border"])))
    t.setStyle(TableStyle(style))
    return t


def _auto_col_max_widths(col_widths, n_cols, avail_width):
    """For whichever columns have no fixed width (None, or col_widths omitted
    entirely), split the leftover space between them — the width each such
    column's text needs to wrap correctly. None when there's nothing to
    compute (no avail_width, or every column already has a fixed width)."""
    if not avail_width:
        return None
    widths = col_widths if col_widths is not None else [None] * n_cols
    fixed_sum = sum(w for w in widths if w is not None)
    none_count = sum(1 for w in widths if w is None)
    if not none_count:
        return None
    share = max((avail_width - fixed_sum) / none_count - CELL_H_PADDING, MIN_COL_WIDTH)
    return [share if w is None else None for w in widths]


def _data_table(cfg, styles, header, rows, col_widths=None, avail_width=None):
    c, tcfg = cfg["colors"], cfg["table"]
    head = ParagraphStyle("th", parent=styles["body"], fontName=BOLD if tcfg.get("header_bold") else FONT_NAME,
                          textColor=hexcolor(c["table_header_text"]), alignment=TA_CENTER)
    max_widths = _auto_col_max_widths(col_widths, len(header), avail_width)
    # Header cells wrap-shape too. A header long enough to break ("نهاية
    # المشروع التعاقدية") was shaped whole and then re-wrapped by reportlab
    # left-to-right, putting its first word on the last line — the same defect
    # the body values were already protected from (2026-08-30).
    data = [[Paragraph(_wrap_shape(h, head.fontName, head.fontSize, max_widths[i])
                       if max_widths and max_widths[i] else shape(h), head)
             for i, h in enumerate(header)]]
    for row in rows:
        data.append([
            _aligned(styles["body"], cell, force=TA_CENTER, max_width=(max_widths[i] if max_widths else None))
            for i, cell in enumerate(row)
        ])
    pad = float(tcfg.get("cell_padding", 6))
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hexcolor(c["table_header_bg"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]
    if tcfg.get("border"):
        style.append(("GRID", (0, 0), (-1, -1), 0.6, hexcolor(c["table_border"])))
    if tcfg.get("zebra"):
        for i in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), hexcolor(c["table_row_alt"])))
    t.setStyle(TableStyle(style))
    return t


def _hierarchy_table(cfg, styles, rows, labels, rtl, avail_width=None):
    """Project -> Zone -> Subzone rollup. Zone rows are bold; subzone rows are
    indented one level — same shape as the report's nested breakdown table."""
    c, tcfg = cfg["colors"], cfg["table"]
    head = ParagraphStyle("hih", parent=styles["body"], fontName=BOLD,
                          textColor=hexcolor(c["table_header_text"]), alignment=TA_CENTER)
    name_style = ParagraphStyle("hin", parent=styles["body"], alignment=TA_RIGHT if rtl else TA_LEFT)
    name_bold = ParagraphStyle("hinb", parent=name_style, fontName=BOLD)
    pct_style = ParagraphStyle("hip", parent=styles["body"], alignment=TA_CENTER)
    name_max_width = (
        max(avail_width - 3 * 28 * mm - CELL_H_PADDING, MIN_COL_WIDTH) if avail_width else None
    )

    def name_para(text, style, *, indent=""):
        if name_max_width and has_arabic(text):
            return Paragraph(indent + _wrap_shape(text, style.fontName, style.fontSize, name_max_width), style)
        return Paragraph(indent + shape(text), style)

    header = [labels["col_zone"], labels["col_actual"], labels["col_previous"], labels["col_planned"]]
    data = [[Paragraph(shape(h), head) for h in header]]
    zebra_rows = []
    for zone in rows:
        zebra_rows.append(len(data))
        data.append([
            name_para(zone["name"], name_bold),
            Paragraph(_pct_or_dash(zone["actual"]), pct_style),
            Paragraph(_pct_or_dash(zone["previous"]), pct_style),
            Paragraph(_pct_or_dash(zone["planned"]), pct_style),
        ])
        for child in zone["children"]:
            data.append([
                name_para(child["name"], name_style, indent="    "),
                Paragraph(_pct_or_dash(child["actual"]), pct_style),
                Paragraph(_pct_or_dash(child["previous"]), pct_style),
                Paragraph(_pct_or_dash(child["planned"]), pct_style),
            ])

    t = Table(data, colWidths=[None, 28 * mm, 28 * mm, 28 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hexcolor(c["table_header_bg"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for r in zebra_rows:
        style.append(("BACKGROUND", (0, r), (-1, r), hexcolor(c["table_row_alt"])))
    if tcfg.get("border"):
        style.append(("GRID", (0, 0), (-1, -1), 0.6, hexcolor(c["table_border"])))
    t.setStyle(TableStyle(style))
    return t


def _hierarchy_table_flat(cfg, styles, header, rows, rtl, avail_width=None):
    """Same visual shape as `_hierarchy_table` (zone rows bold+shaded,
    child rows indented one level), but built from the already-flattened,
    already override-applied `rows`/`header` resolve_table's raw=True mode
    produces — used only by the canvas path (pdf_canvas.py), so a manually
    overridden cell (see apply_table_overrides) draws here exactly as
    edited. The legacy flowing renderer (pdf.py) still uses the original
    `_hierarchy_table` against its own nested `ctx["hierarchy"]` shape,
    untouched by this — no shared code to keep the two paths in sync since
    neither one duplicates the other's row-computation logic."""
    c, tcfg = cfg["colors"], cfg["table"]
    head = ParagraphStyle("hihf", parent=styles["body"], fontName=BOLD,
                          textColor=hexcolor(c["table_header_text"]), alignment=TA_CENTER)
    name_style = ParagraphStyle("hinf", parent=styles["body"], alignment=TA_RIGHT if rtl else TA_LEFT)
    name_bold = ParagraphStyle("hinbf", parent=name_style, fontName=BOLD)
    pct_style = ParagraphStyle("hipf", parent=styles["body"], alignment=TA_CENTER)
    name_max_width = (
        max(avail_width - 3 * 28 * mm - CELL_H_PADDING, MIN_COL_WIDTH) if avail_width else None
    )

    def name_para(text, style, *, indent=""):
        if name_max_width and has_arabic(text):
            return Paragraph(indent + _wrap_shape(text, style.fontName, style.fontSize, name_max_width), style)
        return Paragraph(indent + shape(text), style)

    def cell(v):
        # An override replaces the numeric value with an already-final
        # display string — draw it verbatim instead of re-formatting.
        return v if isinstance(v, str) else _pct_or_dash(v)

    data = [[Paragraph(shape(h), head) for h in header]]
    zebra_rows = []
    for row in rows:
        style_ = name_bold if row.get("level", 0) == 0 else name_style
        indent = "" if row.get("level", 0) == 0 else "    "
        if row.get("level", 0) == 0:
            zebra_rows.append(len(data))
        data.append([
            name_para(row["name"], style_, indent=indent),
            Paragraph(cell(row["actual"]), pct_style),
            Paragraph(cell(row["previous"]), pct_style),
            Paragraph(cell(row["planned"]), pct_style),
        ])

    pad = float(tcfg.get("cell_padding", 5))
    t = Table(data, colWidths=[None, 28 * mm, 28 * mm, 28 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hexcolor(c["table_header_bg"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]
    for r in zebra_rows:
        style.append(("BACKGROUND", (0, r), (-1, r), hexcolor(c["table_row_alt"])))
    if tcfg.get("border"):
        style.append(("GRID", (0, 0), (-1, -1), 0.6, hexcolor(c["table_border"])))
    t.setStyle(TableStyle(style))
    return t


def draw_table_in_box(c, table, x, y, w, h, *, note_color="#595959") -> bool:
    """Fit a Platypus Table into a fixed box on an open canvas page.

    `Table.split(w, h)` asks ReportLab's own layout engine "how much of this
    fits in this height" rather than us re-deriving row-fitting logic — it
    returns the parts that fit as a list of (possibly one) Table flowables.
    If rows had to be dropped, draws a small "+N more rows" note under the
    table rather than silently losing data. Returns False when even the
    header alone doesn't fit the box (caller draws a placeholder instead).
    """
    total_rows = len(table._cellvalues)
    _, natural_h = table.wrap(w, h)
    if natural_h <= h:
        table.drawOn(c, x, y + h - natural_h)
        return True

    pieces = table.split(w, h - NOTE_HEIGHT)
    if not pieces:
        return False
    fitted = pieces[0]
    _, fitted_h = fitted.wrap(w, h - NOTE_HEIGHT)
    fitted.drawOn(c, x, y + h - fitted_h)

    # repeatRows=1 means the header re-appears in `fitted` on top of the rows
    # it kept — subtract it once so the count reflects data rows only.
    dropped = total_rows - len(fitted._cellvalues)
    if dropped > 0:
        c.saveState()
        c.setFont(FONT_NAME, 7)
        c.setFillColor(hexcolor(note_color))
        c.drawString(x, y + h - fitted_h - NOTE_HEIGHT + 1, f"+{dropped} more rows")
        c.restoreState()
    return True
