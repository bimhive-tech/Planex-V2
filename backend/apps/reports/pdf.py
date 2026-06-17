"""Config-driven PDF rendering for reports, matching the reference monthly
construction report: bordered pages, boxed header, blue underlined section
headings, a bordered project-info table, RTL bullet lists, and progress charts.
Arabic text is reshaped + bidi-reordered so it renders right-to-left."""
from io import BytesIO

from django.core.files.storage import default_storage
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
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
from .pdf_base import BOLD, FONT_NAME, ensure_fonts, has_arabic, hexcolor, shape
from .pdf_charts import (
    duration_pie,
    overall_donut,
    planned_actual_chart,
    scurve_chart,
    zone_progress_chart,
)
from .pdf_layout import BORDER_INSET, draw_cover, draw_page_furniture, frame_rect


class _ReportDoc(BaseDocTemplate):
    """Notifies the TOC of section headings; carries cfg/ctx for the canvas."""

    def __init__(self, *args, cfg=None, ctx=None, **kwargs):
        self.cfg = cfg
        self.ctx = ctx
        super().__init__(*args, **kwargs)

    def afterFlowable(self, flowable):
        if getattr(flowable, "style", None) and flowable.style.name == "SectionHeading":
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))


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


def _heading(styles, text):
    """Centered blue heading with an underline rule — the section title look."""
    return [Paragraph(shape(text), styles["section"]),
            HRFlowable(width="40%", thickness=1.1, color=styles["section"].textColor,
                       spaceBefore=1, spaceAfter=8, hAlign="CENTER")]


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


def _storage_image_flowable(key, max_width, max_height):
    """Build a contained ReportLab Image flowable from private storage."""
    if not key:
        return None
    try:
        with default_storage.open(key, "rb") as f:
            data = f.read()
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


def _photo_section(cfg, styles, photos, width, height, heading_text):
    """Progress-photo pages — 4 photos (2×2) per page, like the reference."""
    flow = []
    for page_i in range(0, len(photos), 4):
        chunk = photos[page_i:page_i + 4]
        flow.append(PageBreak())  # each set of 4 gets its own page
        flow += _heading(styles, heading_text)  # fresh flowables per page
        flow.append(_photo_page_table(cfg, styles, chunk, width, height - 24 * mm))
    return flow


def _attachment_section(cfg, styles, attachments, width, height, heading_text):
    """Attachments — one image per page, scaled to fill it."""
    flow = []
    for i, att in enumerate(attachments):
        flow.append(PageBreak())
        if i == 0:
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
            flow += _heading(styles, labels["detailed_progress"])
            flow.append(t)
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
    flow += [NextPageTemplate("body"), PageBreak()]
    return flow


def build_report_pdf(report, ctx) -> bytes:
    """Render `ctx` (from services.build_report_context) into PDF bytes."""
    ensure_fonts()
    cfg = merged_config(report.template.config if report.template else None)
    ctx["arabic"] = has_arabic(ctx["project"]["name"]) or has_arabic(cfg["labels"].get("summary"))
    rtl = ctx["arabic"]
    styles = _styles(cfg)
    labels, sections = cfg["labels"], cfg["sections"]

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
        toc = TableOfContents()
        toc.dotsMinLevel = 0  # dotted leaders + page numbers on level-0 entries
        lvl = ParagraphStyle("toc", fontName=FONT_NAME, fontSize=cfg["fonts"]["base_size"] + 1,
                             leading=(cfg["fonts"]["base_size"] + 1) * 1.9,
                             textColor=hexcolor(cfg["colors"]["text"]))
        if rtl:
            lvl.wordWrap = "RTL"  # mirrors leader + page number to the left
        toc.levelStyles = [lvl]
        story += [toc, PageBreak()]

    p = ctx["project"]

    if sections.get("summary"):
        story += _heading(styles, labels["summary"])
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
        story += _heading(styles, labels["project_info"])
        rows = [
            (labels["info_name"], p["name"]),
            (labels["info_client"], p["client"]),
            (labels["info_consultant"], p["consultant"]),
            (labels["info_contractor"], p["contractor"]),
            (labels["info_type"], p["type"]),
            (labels["info_location"], p["location"]),
            (labels["info_budget"], f"{p['budget']:,.0f} {p['currency']}" if p["budget"] else ""),
            (labels["info_start"], _fmt_date(p["planned_start"])),
            (labels["info_finish"], _fmt_date(p["planned_finish"])),
            (labels["info_size"], f"{p['size_sqm']:,.0f}" if p["size_sqm"] else ""),
        ]
        rows = [(k, v) for k, v in rows if v and v != "—"]
        story.append(_info_table(cfg, styles, rows, rtl))
        story.append(Spacer(1, 10))

    if sections.get("description") and p["description"]:
        story += _heading(styles, labels["description"])
        lines = [ln.strip() for ln in p["description"].splitlines() if ln.strip()]
        story += _bullets(styles, lines, rtl) if len(lines) > 1 else [_aligned(styles["body"], p["description"])]
        story.append(Spacer(1, 10))

    if sections.get("progress_overview"):
        if cfg.get("dividers"):
            story += _divider(styles, labels["progress_overview"])
        story += _heading(styles, labels["progress_overview"])
        story.append(_aligned(styles["sub"], f"{ctx['overall']:.1f}%  {labels['overall_complete']}",
                              force=TA_CENTER))
        donut = overall_donut(cfg, ctx, fw, labels)
        if donut:
            story += [donut, Spacer(1, 6)]

    if sections.get("dashboard"):
        story += _dashboard_section(cfg, styles, ctx, labels, rtl, lfw)

    if sections.get("progress_chart"):
        chart = planned_actual_chart(cfg, ctx, fw, labels)
        if chart:
            story.append(KeepTogether(_heading(styles, labels["progress_chart"]) + [chart, Spacer(1, 10)]))

    if sections.get("duration") and ctx.get("duration"):
        dur = ctx["duration"]
        pie = duration_pie(cfg, ctx, fw, labels)
        table = _data_table(cfg, styles,
            [labels["duration_days"], labels["duration_elapsed"], labels["duration_remaining"], labels["delay_days"]],
            [[str(dur["total"]), str(dur["elapsed"]), str(dur["remaining"]), str(dur["delay"])]])
        story.append(KeepTogether(_heading(styles, labels["duration_section"]) + [pie or Spacer(1, 1), table, Spacer(1, 10)]))

    if sections.get("scurve"):
        curve = scurve_chart(cfg, ctx, fw, labels)
        if curve:
            story.append(KeepTogether(_heading(styles, labels["scurve"]) + [curve, Spacer(1, 10)]))

    if sections.get("progress_compare") and any(z.get("planned") is not None for z in ctx["zones"]):
        rows = [[z["name"],
                 f"{z['planned']:.1f}%" if z.get("planned") is not None else "—",
                 f"{z['previous']:.1f}%" if z.get("previous") is not None else "—",
                 f"{z['progress']:.1f}%"] for z in ctx["zones"]]
        story.append(KeepTogether(_heading(styles, labels["progress_compare"]) + [
            _data_table(cfg, styles,
                [labels["col_zone"], labels["col_planned"], labels["col_previous"], labels["col_actual"]],
                rows, col_widths=[None, 28 * mm, 28 * mm, 28 * mm]),
            Spacer(1, 10)]))

    if sections.get("zone_progress") and ctx["zones"]:
        story += _heading(styles, labels["zone_progress"])
        rows = [[z["name"], f"{z['progress']:.1f}%"] for z in ctx["zones"]]
        story.append(_data_table(cfg, styles, [labels["col_zone"], labels["col_progress"]], rows,
                                 col_widths=[None, 40 * mm]))
        story.append(Spacer(1, 10))

    if sections.get("detailed_progress") and ctx.get("zone_grids"):
        story += _grid_section(cfg, styles, ctx["zone_grids"], fw, labels, rtl)

    if sections.get("delays") and ctx.get("delays"):
        rows = [[d["title"], str(d["impact_days"]), d["status"].title()] for d in ctx["delays"]]
        story.append(KeepTogether(_heading(styles, labels["delays"]) + [
            _data_table(cfg, styles, [labels["col_delay"], labels["col_impact"], labels["col_status"]],
                        rows, col_widths=[None, 28 * mm, 28 * mm]),
            Spacer(1, 10)]))

    if sections.get("milestones") and ctx["milestones"]:
        story += _heading(styles, labels["milestones"])
        rows = [[m["title"], _fmt_date(m["date"]), m["status"].replace("_", " ").title()] for m in ctx["milestones"]]
        story.append(_data_table(cfg, styles, [labels["col_milestone"], labels["col_date"], labels["col_status"]],
                                 rows, col_widths=[None, 32 * mm, 34 * mm]))
        story.append(Spacer(1, 10))

    if sections.get("timeline") and ctx["snapshots"]:
        rows = [[_fmt_date(s["date"]), f"{float(s['overall_progress']):.1f}%", s["source"] or "—"] for s in ctx["snapshots"]]
        story.append(KeepTogether(
            _heading(styles, labels["timeline"]) + [
                _data_table(cfg, styles, [labels["col_date"], labels["col_progress"], labels["col_source"]],
                            rows, col_widths=[34 * mm, 32 * mm, None]),
                Spacer(1, 10),
            ]
        ))

    if sections.get("notes") and p["notes"]:
        story.append(KeepTogether(_heading(styles, labels["notes"]) + [_aligned(styles["body"], p["notes"])]))

    if sections.get("photos") and ctx.get("photos"):
        story += _photo_section(cfg, styles, ctx["photos"], fw, fh, labels["photos"])

    if sections.get("attachments") and ctx.get("attachments"):
        story += _attachment_section(cfg, styles, ctx["attachments"], fw, fh,
                                     labels.get("attachments", "Attachments"))

    doc.multiBuild(story)
    return buf.getvalue()
