"""Table builders shared by both PDF renderers (the legacy flowing generator in
pdf.py and the canvas-box renderer in pdf_canvas.py). Moved out of pdf.py
verbatim — same styling/behavior, just relocated so pdf_canvas.py doesn't need
to import the whole flowing-document module to build a table."""
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

from .pdf_base import BOLD, FONT_NAME, has_arabic, hexcolor, shape

NOTE_HEIGHT = 4 * mm  # space reserved under a truncated table for the "+N more" note


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


def _fmt_date(d):
    return d.strftime("%d %b %Y") if d else "—"


def _pct_or_dash(v):
    return f"{v:.1f}%" if v is not None else "—"


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
            indented = "    " + shape(child["name"])
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
