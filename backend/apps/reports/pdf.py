"""Config-driven PDF rendering for reports, matching the reference monthly
construction report: bordered pages, boxed header, blue underlined section
headings, a bordered project-info table, RTL bullet lists, and progress charts.
Arabic text is reshaped + bidi-reordered so it renders right-to-left."""
from io import BytesIO

from django.core.files.storage import default_storage
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from .constants import merged_config
from .richtext import html_to_flowables
from .services import _zone_grids
from .pdf_base import BOLD, FONT_NAME, cached_image_bytes, ensure_fonts, has_arabic, hexcolor, shape
from .pdf_charts import (
    area_units_chart,
    duration_pie,
    gantt_chart,
    overall_donut,
    planned_actual_chart,
    scurve_chart,
    zone_duration_pie,
    zone_progress_chart,
)
from .pdf_layout import BORDER_INSET, draw_cover, draw_page_furniture, frame_rect


class _ReportDoc(BaseDocTemplate):
    """Notifies the TOC of section headings; carries cfg/ctx for the canvas."""

    def __init__(self, *args, cfg=None, ctx=None, **kwargs):
        self.cfg = cfg
        self.ctx = ctx
        self._toc_seq = 0
        self.anchor_pages = {}  # tab anchor name -> page number (final pass wins)
        super().__init__(*args, **kwargs)

    def beforeDocument(self):
        # Reset per build pass so bookmark keys + anchor pages are stable.
        self._toc_seq = 0
        self.anchor_pages = {}

    def afterFlowable(self, flowable):
        if isinstance(flowable, _Anchor):
            self.anchor_pages[flowable.name] = self.page
        elif getattr(flowable, "style", None) and flowable.style.name == "SectionHeading":
            # Bookmark the heading and pass the key so the TOC entry is a live link.
            key = f"sec{self._toc_seq}"
            self._toc_seq += 1
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page, key))


class _Anchor(Flowable):
    """Zero-size flowable that names a PDF destination on the page it lands on,
    so the builder's tabs can scroll the preview to a section."""

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.width = self.height = 0

    def wrap(self, *args):
        return (0, 0)

    def draw(self):
        self.canv.bookmarkPage(self.name)


class _RtlTOC(TableOfContents):
    """Table of contents laid out for Arabic: each entry's text sits flush right
    and its page number on the far left, with a dotted leader between. reportlab's
    stock TOC always pins the page number to the right edge, so we render the rows
    ourselves. Entry text is already bidi-shaped, so the `<onDraw>` marker goes at
    the start of the (right-aligned) line — that's its visual left edge, where the
    number + leader are drawn."""

    def wrap(self, availWidth, availHeight):
        entries = self._lastEntries or [(0, "—", 0, None)]

        def draw_end(canvas, kind, label):
            page, level, _ = label.split(",", 2)
            style = self.getLevelStyle(int(level))
            text_left = canvas._curr_tx_info["cur_x"]  # left edge of the right-aligned text
            y = canvas._curr_tx_info["cur_y"]
            pagestr = str(int(page))
            pagew = stringWidth(pagestr, style.fontName, style.fontSize)
            dot = " . "
            dotw = stringWidth(dot, style.fontName, style.fontSize)
            n = max(0, int((text_left - pagew) / dotw)) if dotw else 0
            tx = canvas.beginText(0, y)
            tx.setFont(style.fontName, style.fontSize)
            tx.setFillColor(style.textColor)
            tx.textLine(pagestr + " " + n * dot)
            canvas.drawText(tx)
        self.canv.drawTOCEntryEnd = draw_end

        data = []
        for (level, text, page_num, key) in entries:
            style = self.getLevelStyle(level)
            if key:
                text = '<a href="#%s">%s</a>' % (key, text)
                key_val = repr(key).replace(",", "\\x2c").replace('"', "\\x2c")
            else:
                key_val = None
            # onDraw FIRST so its callback fires at the text line's visual left edge.
            para = Paragraph('<onDraw name="drawTOCEntryEnd" label="%d,%d,%s"/>%s'
                             % (page_num, level, key_val, text), style)
            if style.spaceBefore:
                data.append([Spacer(1, style.spaceBefore)])
            data.append([para])
        self._table = Table(data, colWidths=(availWidth,), style=self.tableStyle)
        self.width, self.height = self._table.wrapOn(self.canv, availWidth, availHeight)
        return (self.width, self.height)


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


def _aligned(style, text, *, force=None):
    s = ParagraphStyle(f"{style.name}_a", parent=style)
    s.alignment = force if force is not None else (TA_RIGHT if has_arabic(text) else TA_LEFT)
    return Paragraph(shape(text), s)


def _heading(styles, text, *, listed=True):
    """Centered blue heading with an underline rule — the section title look.
    When listed=False the style is renamed so afterFlowable does NOT add a TOC
    entry (used for continuation pages of a multi-page section)."""
    s = styles["section"] if listed else ParagraphStyle("SectionHeadingPlain", parent=styles["section"])
    return [Paragraph(shape(text), s),
            HRFlowable(width="40%", thickness=1.1, color=s.textColor,
                       spaceBefore=1, spaceAfter=8, hAlign="CENTER")]


def _description_flow(cfg, styles, text, rtl):
    """Render the description with the template's Word-like formatting:
    alignment, size, color, bold, underline, and optional bullets."""
    ds = cfg.get("description", {})
    align = {"right": TA_RIGHT, "left": TA_LEFT, "center": TA_CENTER}.get(ds.get("align"))
    font = BOLD if ds.get("bold") else FONT_NAME
    lead = float(cfg["fonts"].get("line_spacing", 1.5))
    size = float(ds.get("size", cfg["fonts"]["base_size"]))
    bullets = ds.get("bullets", True)
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out = []
    for ln in lines:
        a = align if align is not None else (TA_RIGHT if has_arabic(ln) else TA_LEFT)
        body = f"<u>{shape(ln)}</u>" if ds.get("underline") else shape(ln)
        if bullets:
            body = f"{body} •" if a == TA_RIGHT else f"• {body}"
        st = ParagraphStyle("desc", fontName=font, fontSize=size, leading=size * lead,
                            textColor=hexcolor(ds.get("color", cfg["colors"]["text"])),
                            alignment=a, spaceAfter=4)
        out.append(Paragraph(body, st))
    return out


def _sub_heading(styles, text):
    """A smaller centered heading that is NOT listed in the TOC (style name
    differs from 'SectionHeading', which afterFlowable notifies)."""
    s = ParagraphStyle("SubHeading", parent=styles["section"], fontSize=styles["section"].fontSize - 2)
    return [Paragraph(shape(text), s),
            HRFlowable(width="28%", thickness=1, color=s.textColor, spaceBefore=1, spaceAfter=6, hAlign="CENTER")]


def _divider(styles, text):
    """A blank 'section divider' page with the heading centered (reference look)."""
    ds = ParagraphStyle("Divider", parent=styles["section"])  # non-TOC style name
    return [
        PageBreak(), Spacer(1, 95 * mm),
        Paragraph(shape(text), ds),
        HRFlowable(width="35%", thickness=1.1, color=ds.textColor, spaceBefore=2, hAlign="CENTER"),
        PageBreak(),
    ]


def _bullets(styles, items, rtl):
    out = []
    align = TA_RIGHT if rtl else TA_LEFT
    for it in items:
        s = ParagraphStyle("b", parent=styles["bullet"], alignment=align,
                           leftIndent=0 if rtl else 12, rightIndent=12 if rtl else 0,
                           bulletIndent=0 if rtl else 2)
        marker = " •" if rtl else "• "
        text = f"{shape(it)} {marker}" if rtl else f"{marker}{shape(it)}"
        out.append(Paragraph(text, s))
    return out


def _fmt_date(d):
    return d.strftime("%d %b %Y") if d else "—"


def _info_table(cfg, styles, rows, rtl):
    """Bordered 2-col table: ■ label on the right, value on the left (RTL look)."""
    c = cfg["colors"]
    label_style = ParagraphStyle("lbl", parent=styles["value"], alignment=TA_RIGHT)
    data = []
    for label, value in rows:
        lbl = Paragraph(f"{shape(label)} ■", label_style)
        val = _aligned(styles["body"], value, force=TA_RIGHT if rtl else TA_LEFT)
        data.append([val, lbl] if rtl else [lbl, val])
    widths = [None, 58 * mm] if rtl else [58 * mm, None]
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, hexcolor(c["table_border"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (1 if rtl else 0, 0), (1 if rtl else 0, -1), hexcolor(c["table_row_alt"])),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _data_table(cfg, styles, header, rows, col_widths=None):
    c, tcfg = cfg["colors"], cfg["table"]
    head = ParagraphStyle("th", parent=styles["body"], fontName=BOLD if tcfg.get("header_bold") else FONT_NAME,
                          textColor=hexcolor(c["table_header_text"]), alignment=TA_CENTER)
    data = [[Paragraph(shape(h), head) for h in header]]
    for row in rows:
        data.append([_aligned(styles["body"], cell, force=TA_CENTER) for cell in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hexcolor(c["table_header_bg"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if tcfg.get("border"):
        style.append(("GRID", (0, 0), (-1, -1), 0.6, hexcolor(c["table_border"])))
    if tcfg.get("zebra"):
        for i in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), hexcolor(c["table_row_alt"])))
    t.setStyle(TableStyle(style))
    return t


def _pct_or_dash(v):
    return f"{v:.1f}%" if v is not None else "—"


def _hierarchy_table(cfg, styles, rows, labels, rtl):
    """Project -> Zone -> Subzone rollup. Zone rows are bold; subzone rows are
    indented one level — same shape as the report's nested breakdown table."""
    c, tcfg = cfg["colors"], cfg["table"]
    head = ParagraphStyle("hih", parent=styles["body"], fontName=BOLD,
                          textColor=hexcolor(c["table_header_text"]), alignment=TA_CENTER)
    name_style = ParagraphStyle("hin", parent=styles["body"], alignment=TA_RIGHT if rtl else TA_LEFT)
    name_bold = ParagraphStyle("hinb", parent=name_style, fontName=BOLD)
    pct_style = ParagraphStyle("hip", parent=styles["body"], alignment=TA_CENTER)

    header = [labels["col_zone"], labels["col_actual"], labels["col_previous"], labels["col_planned"]]
    data = [[Paragraph(shape(h), head) for h in header]]
    zebra_rows = []
    for zone in rows:
        zebra_rows.append(len(data))
        data.append([
            Paragraph(shape(zone["name"]), name_bold),
            Paragraph(_pct_or_dash(zone["actual"]), pct_style),
            Paragraph(_pct_or_dash(zone["previous"]), pct_style),
            Paragraph(_pct_or_dash(zone["planned"]), pct_style),
        ])
        for child in zone["children"]:
            indented = "    " + shape(child["name"])
            data.append([
                Paragraph(indented, name_style),
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


def _storage_image_flowable(key, max_width, max_height):
    """Build a contained ReportLab Image flowable from private storage."""
    if not key:
        return None
    try:
        data = cached_image_bytes(key)  # cached: flatten + downscale + JPEG
        reader = ImageReader(BytesIO(data))
        iw, ih = reader.getSize()
        scale = min(max_width / iw, max_height / ih)
        return Image(BytesIO(data), width=iw * scale, height=ih * scale)
    except Exception:
        return None


def _caption_style(styles):
    return ParagraphStyle("photoCaption", parent=styles["muted"], alignment=TA_CENTER, fontSize=8, leading=11)


def _photo_page_table(cfg, styles, photos, width, height):
    """One 2×2 bordered photo grid (up to 4 photos) sized to fill the page."""
    c = cfg["colors"]
    cell_w = (width - 6 * mm) / 2
    cell_h = (height - 14 * mm) / 2  # two rows fill the frame below the heading
    rows = []
    for i in range(0, len(photos), 2):
        row = []
        for photo in photos[i:i + 2]:
            img = _storage_image_flowable(photo.get("image"), cell_w - 6 * mm, cell_h - 12 * mm)
            caption = Paragraph(shape(photo.get("caption") or ""), _caption_style(styles))
            row.append([img or Paragraph("", styles["body"]), caption])
        if len(row) == 1:
            row.append([Spacer(1, 1)])  # pad odd last row (a flowable, not a str)
        rows.append(row)
    table = Table(rows, colWidths=[cell_w, cell_w], rowHeights=[cell_h] * len(rows), hAlign="CENTER")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, hexcolor(c["table_border"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _photo_section(cfg, styles, photos, width, height, heading_text, anchor=None):
    """Progress-photo pages — 4 photos (2×2) per page, like the reference."""
    flow = []
    for page_i in range(0, len(photos), 4):
        chunk = photos[page_i:page_i + 4]
        flow.append(PageBreak())  # each set of 4 gets its own page
        if page_i == 0 and anchor:
            flow.append(_Anchor(anchor))
        flow += _heading(styles, heading_text)  # fresh flowables per page
        flow.append(_photo_page_table(cfg, styles, chunk, width, height - 24 * mm))
    return flow


def _attachment_section(cfg, styles, attachments, width, height, heading_text, anchor=None):
    """Attachments — one image per page, scaled to fill it."""
    flow = []
    for i, att in enumerate(attachments):
        flow.append(PageBreak())
        if i == 0:
            if anchor:
                flow.append(_Anchor(anchor))
            flow += _heading(styles, heading_text)
        img = _storage_image_flowable(att.get("image"), width, height - 30 * mm)
        flow.append(img or Paragraph("", styles["body"]))
        if att.get("caption"):
            flow += [Spacer(1, 4), Paragraph(shape(att["caption"]), _caption_style(styles))]
    return flow


def _grid_section(cfg, styles, grids, width, labels, rtl):
    """Schedule-style grid per zone: zone name header, subzone columns, phase/task
    rows, progress cells. Wide grids split their columns across pages."""
    c = cfg["colors"]
    max_cols = 8  # subzone columns per page before splitting
    th = ParagraphStyle("gh", parent=styles["body"], fontName=BOLD, fontSize=7,
                        textColor=hexcolor(c["table_header_text"]), alignment=TA_CENTER)
    cell = ParagraphStyle("gc", parent=styles["body"], fontSize=7, alignment=TA_CENTER)
    task = ParagraphStyle("gt", parent=styles["body"], fontSize=7, alignment=TA_RIGHT if rtl else TA_LEFT)
    phase = ParagraphStyle("gp", parent=styles["value"], fontSize=7.5, alignment=TA_RIGHT if rtl else TA_LEFT)

    flow = []
    first = True  # only the first grid page is a TOC-listed heading
    for g in grids:
        cols, rows = g["columns"], g["rows"]
        for start in range(0, len(cols), max_cols):
            chunk = cols[start:start + max_cols]
            n = len(chunk)
            task_w = 46 * mm
            sub_w = (width - task_w) / max(1, n)
            data = [[Paragraph(shape(g["zone_name"]), th)] + [""] * n,
                    [Paragraph(shape(labels["col_task"]), th)] + [Paragraph(shape(s), th) for s in chunk]]
            extra = [("SPAN", (0, 0), (-1, 0))]
            r = 2
            current = None
            for row in rows:
                if row["phase"] != current:
                    current = row["phase"]
                    data.append([Paragraph(shape(current), phase)] + [""] * n)
                    extra += [("SPAN", (0, r), (-1, r)),
                              ("BACKGROUND", (0, r), (-1, r), hexcolor(c["table_row_alt"]))]
                    r += 1
                vals = row["cells"][start:start + max_cols]
                data.append([Paragraph(shape(row["name"]), task)] +
                            [Paragraph(f"{v:.0f}%" if v is not None else "", cell) for v in vals])
                r += 1
            t = Table(data, colWidths=[task_w] + [sub_w] * n, repeatRows=2)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 1), hexcolor(c["table_header_bg"])),
                ("GRID", (0, 0), (-1, -1), 0.4, hexcolor(c["table_border"])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ] + extra))
            flow.append(PageBreak())
            flow += _heading(styles, labels["detailed_progress"], listed=first)
            first = False
            flow.append(t)
    return flow


def _area_dashboard_section(cfg, styles, areas, width, labels):
    """One page per zone: a planned-vs-actual bar for its sub-units, a duration
    pie (the zone's own dates when set, else the project's), and a few recent
    photos from its subtree. Only the first zone's heading is TOC-listed (one
    entry per zone would clutter it on projects with many zones) — same trick
    as the detailed grid section."""
    flow = []
    for i, area in enumerate(areas):
        flow.append(PageBreak())
        flow += _heading(styles, labels.get("area_dashboards", "Area Dashboards"), listed=(i == 0))
        flow += _sub_heading(styles, area["name"])
        chart = area_units_chart(cfg, area, width, labels)
        if chart:
            flow += [chart, Spacer(1, 6)]
        dur = area.get("duration")
        if dur:
            pie = zone_duration_pie(cfg, dur, width, labels)
            table = _data_table(cfg, styles,
                [labels["duration_days"], labels["duration_elapsed"], labels["duration_remaining"], labels["delay_days"]],
                [[str(dur["total"]), str(dur["elapsed"]), str(dur["remaining"]), str(dur["delay"])]])
            flow += [pie or Spacer(1, 1), table, Spacer(1, 8)]
        if area.get("photos"):
            flow.append(_photo_page_table(cfg, styles, area["photos"], width, 70 * mm))
    return flow


def draw_dash(canvas, doc):
    """Landscape page chrome for the executive dashboard: border + title + page #."""
    cfg, ctx = doc.cfg, doc.ctx
    w, h = landscape(A4)
    canvas.setPageSize((w, h))
    canvas.saveState()
    canvas.setStrokeColor(hexcolor(cfg["colors"]["page_border"]))
    canvas.setLineWidth(1)
    canvas.rect(BORDER_INSET, BORDER_INSET, w - 2 * BORDER_INSET, h - 2 * BORDER_INSET)
    canvas.setFont(BOLD, 11)
    canvas.setFillColor(hexcolor(cfg["colors"]["heading"]))
    canvas.drawCentredString(w / 2, h - BORDER_INSET - 7 * mm, shape(ctx["project"]["name"]))
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(hexcolor(cfg["colors"]["muted"]))
    canvas.drawCentredString(w / 2, BORDER_INSET + 3 * mm, str(doc.page))
    canvas.restoreState()


def _dashboard_section(cfg, styles, ctx, labels, rtl, w):
    """Reference-style landscape executive dashboard: progress + duration gauges,
    a project-info panel, planned/actual bars, the S-curve, and a photo strip."""
    flow = [NextPageTemplate("dash"), PageBreak()]
    flow += _heading(styles, labels.get("dashboard", "Executive Dashboard"))

    p = ctx["project"]
    info_rows = [
        (labels["info_client"], p["client"]), (labels["info_consultant"], p["consultant"]),
        (labels["info_contractor"], p["contractor"]),
        (labels["info_budget"], f"{p['budget']:,.0f} {p['currency']}" if p["budget"] else ""),
        (labels["info_finish"], _fmt_date(p["planned_finish"])),
    ]
    if ctx.get("duration"):
        info_rows.append((labels["delay_days"], str(ctx["duration"]["delay"])))
    info_rows = [(k, v) for k, v in info_rows if v]
    info = _info_table(cfg, styles, info_rows, rtl)

    donut = overall_donut(cfg, ctx, 0.26 * w, labels) or Spacer(1, 1)
    dur = duration_pie(cfg, ctx, 0.34 * w, labels) or Spacer(1, 1)
    top = Table([[donut, dur, info]], colWidths=[0.28 * w, 0.34 * w, 0.38 * w])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    bars = planned_actual_chart(cfg, ctx, 0.5 * w, labels) or Spacer(1, 1)
    curve = scurve_chart(cfg, ctx, 0.48 * w, labels) or Spacer(1, 1)
    mid = Table([[bars, curve]], colWidths=[0.5 * w, 0.5 * w])
    mid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    flow += [top, Spacer(1, 6), mid]
    # Return to portrait; the next section's page break applies the body template.
    flow += [NextPageTemplate("body")]
    return flow


def build_report_pdf(report, ctx, out_pages=None) -> bytes:
    """Render `ctx` (from services.build_report_context) into PDF bytes."""
    ensure_fonts()
    cfg = merged_config(report.template.config if report.template else None)
    ctx["arabic"] = has_arabic(ctx["project"]["name"]) or has_arabic(cfg["labels"].get("summary"))
    rtl = ctx["arabic"]
    styles = _styles(cfg)
    labels, sections = cfg["labels"], cfg["sections"]

    # Build the (heavy) detailed grid only when that section is enabled.
    if sections.get("detailed_progress") and not ctx.get("zone_grids") and getattr(report, "project", None):
        ctx["zone_grids"] = _zone_grids(report.project, [z["id"] for z in ctx["zones"]],
                                        getattr(report, "scope_ids", None), ctx.get("_progress"))

    page = landscape(A4) if cfg["page"].get("orientation") == "landscape" else A4
    fx, fy, fw, fh = frame_rect(page)

    buf = BytesIO()
    doc = _ReportDoc(buf, pagesize=page, cfg=cfg, ctx=ctx, title=report.title,
                     leftMargin=fx, rightMargin=fx, topMargin=page[1] - (fy + fh), bottomMargin=fy)
    frame = Frame(fx, fy, fw, fh, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    # Landscape frame for the dashboard — taller than frame_rect (no header band).
    land = landscape(A4)
    lw, lh = land
    lfx = BORDER_INSET + 4 * mm
    lfy = BORDER_INSET + 9 * mm
    lfw = lw - 2 * lfx
    lfh = (lh - BORDER_INSET - 14 * mm) - lfy
    lframe = Frame(lfx, lfy, lfw, lfh, id="dash", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=draw_cover),
        PageTemplate(id="body", frames=[frame], onPage=draw_page_furniture),
        PageTemplate(id="dash", frames=[lframe], onPage=draw_dash),
    ])

    story = [NextPageTemplate("body")]
    if cfg["cover"].get("enabled"):
        story.append(PageBreak())

    if cfg["toc"].get("enabled"):
        # Title uses a non-"SectionHeading" style so it isn't listed in itself.
        tt = ParagraphStyle("TocTitle", parent=styles["section"])
        story.append(Paragraph(shape(cfg["toc"].get("title") or "Contents"), tt))
        story.append(HRFlowable(width="40%", thickness=1.1, color=tt.textColor,
                                spaceBefore=1, spaceAfter=10, hAlign="CENTER"))
        toc = _RtlTOC() if rtl else TableOfContents()
        toc.dotsMinLevel = 0  # dotted leaders + page numbers on level-0 entries
        lvl = ParagraphStyle("toc", fontName=FONT_NAME, fontSize=cfg["fonts"]["base_size"] + 1,
                             leading=(cfg["fonts"]["base_size"] + 1) * 1.9,
                             textColor=hexcolor(cfg["colors"]["text"]))
        if rtl:
            # Text flush right; _RtlTOC draws the page number + leader on the left.
            lvl.alignment = TA_RIGHT
        toc.levelStyles = [lvl]
        story += [toc]

    p = ctx["project"]

    def major(label, anchor=None):
        """Start a major (TOC-listed) section on a fresh page; `anchor` names a
        destination the builder tabs can scroll to."""
        out = [PageBreak()]
        if cfg.get("dividers"):
            out += _divider(styles, label)
        if anchor:
            out.append(_Anchor(anchor))
        out += _heading(styles, label)
        return out

    if sections.get("summary"):
        story += major(labels["summary"])
        b = ctx["breakdown"]
        story.append(_aligned(styles["body"],
            f"{p['name']} — {ctx['overall']:.1f}% — {b['total']} {labels['activities']}.",
            force=TA_RIGHT if rtl else TA_LEFT))
        story.append(Spacer(1, 4))
        story.append(_data_table(cfg, styles,
            [labels["completed"], labels["in_progress"], labels["not_started"]],
            [[str(b["completed"]), str(b["in_progress"]), str(b["not_started"])]]))
        story.append(Spacer(1, 10))

    if sections.get("project_info"):
        story += major(labels["project_info"], anchor="tab_info")
        dur = ctx.get("duration") or {}
        rows = [
            (labels["info_name"], p["name"]),
            (labels.get("info_code", "Code"), p.get("code")),
            (labels["info_client"], p["client"]),
            (labels["info_consultant"], p["consultant"]),
            (labels["info_contractor"], p["contractor"]),
            (labels["info_type"], p["type"]),
            (labels["info_location"], p["location"]),
            (labels["info_budget"], f"{p['budget']:,.0f} {p['currency']}" if p["budget"] else ""),
            (labels.get("info_duration", "Duration"), str(dur["total"]) if dur.get("total") else ""),
            (labels["info_start"], _fmt_date(p["planned_start"])),
            (labels["info_finish"], _fmt_date(p["planned_finish"])),
            (labels.get("info_revised", "Forecast finish"), _fmt_date(p["revised_finish"]) if p.get("revised_finish") else ""),
            (labels.get("info_delay", "Delay"), str(dur["delay"]) if dur.get("delay") else ""),
            (labels["info_size"], f"{p['size_sqm']:,.0f}" if p["size_sqm"] else ""),
        ]
        rows = [(k, v) for k, v in rows if v and v != "—"]
        story.append(_info_table(cfg, styles, rows, rtl))

    if sections.get("description") and (p.get("description_html") or p["description"]):
        story += major(labels["description"], anchor="tab_description")
        if p.get("description_html"):
            # Rich text from the builder (per-run bold/italic/underline/color/size,
            # lists, alignment) — overrides the template's uniform formatting.
            story += html_to_flowables(p["description_html"], cfg, styles)
        else:
            story += _description_flow(cfg, styles, p["description"], rtl)

    progress_anchored = False
    if sections.get("dashboard"):
        dash = _dashboard_section(cfg, styles, ctx, labels, rtl, lfw)
        dash[2:2] = [_Anchor("tab_progress")]  # after NextPageTemplate + PageBreak
        story += dash
        progress_anchored = True

    # Project Progress Report — one TOC entry; the charts are sub-headings.
    progress_on = any(sections.get(k) for k in
                      ("progress_overview", "progress_chart", "duration", "scurve", "progress_compare"))
    if progress_on:
        story += major(labels.get("progress_report", "Project Progress Report"),
                       anchor=None if progress_anchored else "tab_progress")
        if sections.get("progress_overview"):
            story.append(_aligned(styles["sub"], f"{ctx['overall']:.1f}%  {labels['overall_complete']}", force=TA_CENTER))
            donut = overall_donut(cfg, ctx, fw, labels)
            if donut:
                story += [donut, Spacer(1, 8)]
        if sections.get("progress_chart"):
            chart = planned_actual_chart(cfg, ctx, fw, labels)
            if chart:
                story.append(KeepTogether(_sub_heading(styles, labels["progress_chart"]) + [chart, Spacer(1, 10)]))
        if sections.get("duration") and ctx.get("duration"):
            dur = ctx["duration"]
            pie = duration_pie(cfg, ctx, fw, labels)
            table = _data_table(cfg, styles,
                [labels["duration_days"], labels["duration_elapsed"], labels["duration_remaining"], labels["delay_days"]],
                [[str(dur["total"]), str(dur["elapsed"]), str(dur["remaining"]), str(dur["delay"])]])
            story.append(KeepTogether(_sub_heading(styles, labels["duration_section"]) + [pie or Spacer(1, 1), table, Spacer(1, 10)]))
        if sections.get("scurve"):
            curve = scurve_chart(cfg, ctx, fw, labels)
            if curve:
                story.append(KeepTogether(_sub_heading(styles, labels["scurve"]) + [curve, Spacer(1, 10)]))
        if sections.get("progress_compare") and any(z.get("planned") is not None for z in ctx["zones"]):
            rows = [[z["name"],
                     f"{z['planned']:.1f}%" if z.get("planned") is not None else "—",
                     f"{z['previous']:.1f}%" if z.get("previous") is not None else "—",
                     f"{z['progress']:.1f}%"] for z in ctx["zones"]]
            story.append(KeepTogether(_sub_heading(styles, labels["progress_compare"]) + [
                _data_table(cfg, styles,
                    [labels["col_zone"], labels["col_planned"], labels["col_previous"], labels["col_actual"]],
                    rows, col_widths=[None, 28 * mm, 28 * mm, 28 * mm]), Spacer(1, 10)]))

    if sections.get("zone_progress") and ctx["zones"]:
        story += major(labels["zone_progress"])
        rows = [[z["name"], f"{z['progress']:.1f}%"] for z in ctx["zones"]]
        story.append(_data_table(cfg, styles, [labels["col_zone"], labels["col_progress"]], rows,
                                 col_widths=[None, 40 * mm]))

    if sections.get("hierarchy_progress") and ctx.get("hierarchy"):
        story += major(labels["hierarchy_progress"])
        story.append(_hierarchy_table(cfg, styles, ctx["hierarchy"], labels, rtl))

    if sections.get("discipline_progress") and ctx.get("discipline"):
        story += major(labels["discipline_progress"])
        disc_header = [labels["col_unit"], labels["col_concrete"], labels["col_architecture"],
                       labels["col_electrical"], labels["col_mechanical"], labels["col_other"]]
        disc_rows = [
            [r["name"]] + [_pct_or_dash(r.get(d)) for d in ("concrete", "architecture", "electrical", "mechanical", "other")]
            for r in ctx["discipline"]
        ]
        story.append(_data_table(cfg, styles, disc_header, disc_rows))

    if sections.get("area_dashboards") and ctx.get("area_dashboards"):
        story += _area_dashboard_section(cfg, styles, ctx["area_dashboards"], fw, labels)

    if sections.get("detailed_progress") and ctx.get("zone_grids"):
        story += _grid_section(cfg, styles, ctx["zone_grids"], fw, labels, rtl)

    if sections.get("gantt_schedule") and ctx.get("gantt"):
        story += major(labels.get("gantt_schedule", "Project Schedule (Gantt)"))
        chart = gantt_chart(cfg, ctx["gantt"], fw, labels)
        if chart:
            story.append(chart)

    if sections.get("delays") and ctx.get("delays"):
        story += major(labels["delays"])
        rows = [[d["title"], str(d["impact_days"]), d["status"].title()] for d in ctx["delays"]]
        story.append(_data_table(cfg, styles, [labels["col_delay"], labels["col_impact"], labels["col_status"]],
                                 rows, col_widths=[None, 28 * mm, 28 * mm]))

    if sections.get("milestones") and ctx["milestones"]:
        story += major(labels["milestones"])
        rows = [[m["title"], _fmt_date(m["date"]), m["status"].replace("_", " ").title()] for m in ctx["milestones"]]
        story.append(_data_table(cfg, styles, [labels["col_milestone"], labels["col_date"], labels["col_status"]],
                                 rows, col_widths=[None, 32 * mm, 34 * mm]))

    if sections.get("timeline") and ctx["snapshots"]:
        story += major(labels["timeline"])
        rows = [[_fmt_date(s["date"]), f"{float(s['overall_progress']):.1f}%", s["source"] or "—"] for s in ctx["snapshots"]]
        story.append(_data_table(cfg, styles, [labels["col_date"], labels["col_progress"], labels["col_source"]],
                                 rows, col_widths=[34 * mm, 32 * mm, None]))

    if sections.get("notes") and p["notes"]:
        story += major(labels["notes"])
        story.append(_aligned(styles["body"], p["notes"]))

    if sections.get("photos") and ctx.get("photos"):
        story += _photo_section(cfg, styles, ctx["photos"], fw, fh, labels["photos"], anchor="tab_photos")

    if sections.get("attachments") and ctx.get("attachments"):
        story += _attachment_section(cfg, styles, ctx["attachments"], fw, fh,
                                     labels.get("attachments", "Attachments"), anchor="tab_attachments")

    doc.multiBuild(story)
    if out_pages is not None:
        out_pages.update(doc.anchor_pages)
        if cfg["cover"].get("enabled"):
            out_pages.setdefault("tab_cover", 1)
    return buf.getvalue()
