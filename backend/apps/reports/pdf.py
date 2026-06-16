"""Config-driven PDF rendering for reports (reportlab + Arabic shaping).

Every visual aspect — page, colors, fonts/sizes, cover, TOC, section toggles,
table styling, and labels — comes from the template config so the user controls
the whole document. Arabic text is reshaped + bidi-reordered so it renders RTL."""
import os
import re
from io import BytesIO

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
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

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_NAME = "Amiri"
_FONTS_READY = False

_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def _ensure_fonts():
    """Register the bundled Amiri family once (covers Arabic + Latin)."""
    global _FONTS_READY
    if _FONTS_READY:
        return
    pdfmetrics.registerFont(TTFont(FONT_NAME, os.path.join(FONT_DIR, "Amiri-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(f"{FONT_NAME}-Bold", os.path.join(FONT_DIR, "Amiri-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=f"{FONT_NAME}-Bold")
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


def _hex(value, fallback="#000000"):
    try:
        return colors.HexColor(value)
    except Exception:
        return colors.HexColor(fallback)


class _ReportDoc(BaseDocTemplate):
    """Doc template that notifies the TOC of headings and paints header/footer."""

    def __init__(self, *args, cfg=None, ctx=None, **kwargs):
        self.cfg = cfg
        self.ctx = ctx
        super().__init__(*args, **kwargs)

    def afterFlowable(self, flowable):
        if flowable.__class__.__name__ != "Paragraph":
            return
        style = flowable.style.name
        if style == "TOCHeading":
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))


def _draw_chrome(canvas, doc):
    """Running header (project + report no.) and footer (page number)."""
    cfg, ctx = doc.cfg, doc.ctx
    width, height = doc.pagesize
    margin = doc.leftMargin
    muted = _hex(cfg["colors"]["muted"])
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(muted)

    header = cfg["header"]
    if header.get("enabled"):
        parts = []
        if header.get("show_project"):
            parts.append(ctx["project"]["name"])
        if header.get("show_report_no") and ctx["report"]["number"]:
            parts.append(f"#{ctx['report']['number']}")
        line = "   |   ".join(parts)
        if line:
            canvas.drawRightString(width - margin, height - margin + 6 * mm, shape(line))
            canvas.setStrokeColor(_hex(cfg["colors"]["table_border"]))
            canvas.line(margin, height - margin + 3 * mm, width - margin, height - margin + 3 * mm)

    footer = cfg["footer"]
    if footer.get("enabled"):
        if footer.get("text"):
            canvas.drawString(margin, margin - 8 * mm, shape(footer["text"]))
        if footer.get("show_page_number"):
            canvas.drawRightString(width - margin, margin - 8 * mm, str(doc.page))
    canvas.restoreState()


def _styles(cfg):
    """Build paragraph styles from the config's fonts/colors."""
    f = cfg["fonts"]
    c = cfg["colors"]
    lead = float(f.get("line_spacing", 1.4))
    bold = f"{FONT_NAME}-Bold"

    def mk(name, size, color, *, font=FONT_NAME, align=TA_LEFT, space_before=0, space_after=6):
        return ParagraphStyle(
            name, fontName=font, fontSize=size, textColor=_hex(color),
            leading=size * lead, alignment=align, spaceBefore=space_before, spaceAfter=space_after,
        )

    return {
        "h1": mk("h1", f["h1_size"], c["heading"], font=bold, space_before=10, space_after=10),
        "h2": mk("h2", f["h2_size"], c["heading"], font=bold, space_before=8, space_after=6),
        "h3": mk("h3", f["h3_size"], c["heading"], font=bold, space_after=4),
        "body": mk("body", f["base_size"], c["text"]),
        "muted": mk("muted", f["base_size"] - 1, c["muted"]),
        "toc_heading": ParagraphStyle(
            "TOCHeading", fontName=bold, fontSize=f["h2_size"], textColor=_hex(c["heading"]),
            leading=f["h2_size"] * lead, spaceBefore=10, spaceAfter=10,
        ),
    }


def _aligned(style, text):
    """Right-align Arabic, left-align Latin, off the same base style."""
    s = ParagraphStyle(f"{style.name}_a", parent=style)
    s.alignment = TA_RIGHT if has_arabic(text) else TA_LEFT
    return Paragraph(shape(text), s)


def _fmt_date(d):
    return d.strftime("%d %b %Y") if d else "—"


def _info_table(cfg, styles, rows):
    """Two-column label/value table used for project info."""
    c = cfg["colors"]
    data = [[_aligned(styles["muted"], label), _aligned(styles["body"], value)] for label, value in rows]
    t = Table(data, colWidths=[45 * mm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, _hex(c["table_border"])),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _data_table(cfg, styles, header, rows, col_widths=None):
    """Styled data table (zebra + header fill) honoring the table config."""
    c = cfg["colors"]
    tcfg = cfg["table"]
    head_style = ParagraphStyle(
        "th", parent=styles["body"], fontName=f"{FONT_NAME}-Bold" if tcfg.get("header_bold") else FONT_NAME,
        textColor=_hex(c["table_header_text"]), alignment=TA_CENTER,
    )
    data = [[Paragraph(shape(h), head_style) for h in header]]
    for row in rows:
        data.append([_aligned(styles["body"], cell) for cell in row])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _hex(c["table_header_bg"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    if tcfg.get("border"):
        style.append(("GRID", (0, 0), (-1, -1), 0.4, _hex(c["table_border"])))
    if tcfg.get("zebra"):
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), _hex(c["table_row_alt"])))
    t.setStyle(TableStyle(style))
    return t


def _cover_page(canvas, doc):
    """Full-bleed cover painted directly on the canvas."""
    cfg, ctx = doc.cfg, doc.ctx
    width, height = doc.pagesize
    c = cfg["colors"]
    cover = cfg["cover"]
    canvas.saveState()
    canvas.setFillColor(_hex(c["cover_bg"]))
    canvas.rect(0, 0, width, height, fill=1, stroke=0)

    # Accent band across the top.
    accent = _hex(c["cover_accent"])
    canvas.setFillColor(accent)
    canvas.rect(0, height - 16 * mm, width, 16 * mm, fill=1, stroke=0)
    canvas.rect(0, 0, width, 8 * mm, fill=1, stroke=0)

    cx = width / 2
    canvas.setFillColor(_hex(c["heading"]))
    canvas.setFont(f"{FONT_NAME}-Bold", cfg["fonts"]["cover_title_size"])
    canvas.drawCentredString(cx, height * 0.62, shape(cover.get("title") or ctx["report"]["title"]))

    canvas.setFont(f"{FONT_NAME}-Bold", cfg["fonts"]["h2_size"])
    canvas.setFillColor(accent)
    canvas.drawCentredString(cx, height * 0.55, shape(ctx["project"]["name"]))

    canvas.setFont(FONT_NAME, cfg["fonts"]["base_size"] + 1)
    canvas.setFillColor(_hex(c["muted"]))
    meta = []
    if ctx["report"]["number"]:
        meta.append(f"No. {ctx['report']['number']}")
    if ctx["report"]["period_start"] or ctx["report"]["period_finish"]:
        meta.append(f"{_fmt_date(ctx['report']['period_start'])} – {_fmt_date(ctx['report']['period_finish'])}")
    if cover.get("subtitle"):
        meta.append(cover["subtitle"])
    if meta:
        canvas.drawCentredString(cx, height * 0.50, shape("   •   ".join(meta)))

    if cover.get("show_overall"):
        canvas.setFont(f"{FONT_NAME}-Bold", 46)
        canvas.setFillColor(accent)
        canvas.drawCentredString(cx, height * 0.32, f"{ctx['overall']:.0f}%")
        canvas.setFont(FONT_NAME, cfg["fonts"]["base_size"])
        canvas.setFillColor(_hex(c["muted"]))
        canvas.drawCentredString(cx, height * 0.29, shape(cfg["labels"]["overall_complete"]))
    canvas.restoreState()


def build_report_pdf(report, ctx) -> bytes:
    """Render `ctx` (from services.build_report_context) into PDF bytes."""
    _ensure_fonts()
    cfg = merged_config(report.template.config if report.template else None)
    styles = _styles(cfg)
    labels = cfg["labels"]
    sections = cfg["sections"]

    page = A4
    if cfg["page"].get("orientation") == "landscape":
        page = landscape(A4)
    margin = float(cfg["page"].get("margin_mm", 18)) * mm

    buf = BytesIO()
    doc = _ReportDoc(
        buf, pagesize=page, leftMargin=margin, rightMargin=margin,
        topMargin=margin + 8 * mm, bottomMargin=margin + 8 * mm, cfg=cfg, ctx=ctx,
        title=report.title,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=_cover_page),
        PageTemplate(id="body", frames=[frame], onPage=_draw_chrome),
    ])

    story = []

    if cfg["cover"].get("enabled"):
        story += [NextPageTemplate("body"), PageBreak()]
    else:
        story += [NextPageTemplate("body")]

    # Table of contents.
    if cfg["toc"].get("enabled"):
        story.append(_aligned(styles["h1"], cfg["toc"].get("title") or "Contents"))
        toc = TableOfContents()
        toc.levelStyles = [ParagraphStyle(
            "tocentry", fontName=FONT_NAME, fontSize=cfg["fonts"]["base_size"] + 1,
            leading=(cfg["fonts"]["base_size"] + 1) * 1.6, textColor=_hex(cfg["colors"]["text"]),
        )]
        story.append(toc)
        story.append(PageBreak())

    def heading(text):
        story.append(Paragraph(shape(text), styles["toc_heading"]))

    # Executive summary.
    if sections.get("summary"):
        heading(labels["summary"])
        b = ctx["breakdown"]
        story.append(_aligned(styles["body"],
            f"{ctx['project']['name']} is {ctx['overall']:.1f}% complete across "
            f"{b['total']} {labels['activities']}."))
        story.append(Spacer(1, 4))
        story.append(_data_table(cfg, styles,
            [labels["completed"], labels["in_progress"], labels["not_started"]],
            [[str(b["completed"]), str(b["in_progress"]), str(b["not_started"])]]))
        story.append(Spacer(1, 10))

    # Project information.
    if sections.get("project_info"):
        heading(labels["project_info"])
        p = ctx["project"]
        rows = [
            ("Project", p["name"]),
            ("Code", p["code"]),
            ("Type", p["type"]),
            ("Location", p["location"]),
            ("Client", p["client"]),
            ("Consultant", p["consultant"]),
            ("Contractor", p["contractor"]),
            ("Planned start", _fmt_date(p["planned_start"])),
            ("Planned finish", _fmt_date(p["planned_finish"])),
            ("Size (m²)", str(p["size_sqm"]) if p["size_sqm"] else "—"),
        ]
        rows = [(k, v) for k, v in rows if v and v != "—" or k in ("Planned start", "Planned finish")]
        story.append(_info_table(cfg, styles, rows))
        if p["description"]:
            story.append(Spacer(1, 8))
            story.append(_aligned(styles["body"], p["description"]))
        story.append(Spacer(1, 10))

    # Overall progress.
    if sections.get("progress_overview"):
        heading(labels["progress_overview"])
        story.append(_aligned(styles["h2"], f"{ctx['overall']:.1f}%  {labels['overall_complete']}"))
        story.append(Spacer(1, 10))

    # Progress by zone.
    if sections.get("zone_progress") and ctx["zones"]:
        heading(labels["zone_progress"])
        rows = [[z["name"], f"{z['progress']:.1f}%"] for z in ctx["zones"]]
        story.append(_data_table(cfg, styles, [labels["col_zone"], labels["col_progress"]], rows,
                                 col_widths=[None, 35 * mm]))
        story.append(Spacer(1, 10))

    # Milestones.
    if sections.get("milestones") and ctx["milestones"]:
        heading(labels["milestones"])
        rows = [[m["title"], _fmt_date(m["date"]), m["status"].replace("_", " ").title()]
                for m in ctx["milestones"]]
        story.append(_data_table(cfg, styles,
            [labels["col_milestone"], labels["col_date"], labels["col_status"]], rows,
            col_widths=[None, 30 * mm, 32 * mm]))
        story.append(Spacer(1, 10))

    # Progress timeline.
    if sections.get("timeline") and ctx["snapshots"]:
        heading(labels["timeline"])
        rows = [[_fmt_date(s["date"]), f"{float(s['overall_progress']):.1f}%", s["source"] or "—"]
                for s in ctx["snapshots"]]
        story.append(_data_table(cfg, styles,
            [labels["col_date"], labels["col_progress"], labels["col_source"]], rows,
            col_widths=[32 * mm, 30 * mm, None]))
        story.append(Spacer(1, 10))

    # Notes.
    if sections.get("notes") and ctx["project"]["notes"]:
        heading(labels["notes"])
        story.append(_aligned(styles["body"], ctx["project"]["notes"]))

    doc.multiBuild(story)
    return buf.getvalue()
