"""Canvas-painted page furniture: full page border, the boxed 3-cell header
(logo | project | logo) with a report-line sub-row, the footer page number,
and the cover page — all matching the reference monthly report."""
from reportlab.lib.units import mm

from .pdf_base import BOLD, FONT_NAME, hexcolor, shape

# Geometry (kept here so the doc frame in pdf.py can mirror it).
BORDER_INSET = 10 * mm
HEADER_H = 17 * mm
SUBROW_H = 7 * mm
FOOTER_H = 9 * mm
FRAME_PAD = 4 * mm
GAP = 3 * mm

AR_MONTHS = ["يناير", "فبراير", "مارس", "ابريل", "مايو", "يونيو",
             "يوليو", "اغسطس", "سبتمبر", "اكتوبر", "نوفمبر", "ديسمبر"]


def frame_rect(pagesize):
    """(x, y, w, h) of the content frame, inside the border + header."""
    w, h = pagesize
    x = BORDER_INSET + FRAME_PAD
    top = h - (BORDER_INSET + HEADER_H + SUBROW_H + GAP)
    bottom = BORDER_INSET + FOOTER_H
    return x, bottom, w - 2 * x, top - bottom


def _period_str(ctx, arabic):
    d = ctx["report"]["period_finish"] or ctx["report"]["period_start"]
    if not d:
        return ""
    if arabic:
        return f"{AR_MONTHS[d.month - 1]} {d.year}"
    return d.strftime("%B %Y")


def _report_line(ctx, arabic):
    parts = []
    title = ctx["report"]["title"]
    if title:
        parts.append(title)
    if ctx["report"]["number"]:
        parts.append(f"({ctx['report']['number']})")
    line = " ".join(parts)
    period = _period_str(ctx, arabic)
    if period:
        line = f"{line} – {period}" if line else period
    return line


def draw_page_furniture(canvas, doc):
    """Border + header + footer painted on every body page."""
    cfg, ctx = doc.cfg, doc.ctx
    w, h = doc.pagesize
    arabic = bool(ctx.get("arabic"))
    border = hexcolor(cfg["colors"]["page_border"])
    canvas.saveState()

    if cfg.get("page_border", {}).get("enabled", True):
        canvas.setStrokeColor(border)
        canvas.setLineWidth(1)
        canvas.rect(BORDER_INSET, BORDER_INSET, w - 2 * BORDER_INSET, h - 2 * BORDER_INSET)

    header = cfg["header"]
    inner_x = BORDER_INSET
    inner_w = w - 2 * BORDER_INSET
    if header.get("enabled"):
        hy = h - BORDER_INSET - HEADER_H
        # 3 cells: side logo cells + a wide center cell for the project name.
        left_w = inner_w * 0.28
        right_w = inner_w * 0.24
        center_w = inner_w - left_w - right_w
        canvas.setStrokeColor(hexcolor(cfg["colors"]["header_border"]))
        canvas.setLineWidth(0.8)
        canvas.rect(inner_x, hy, inner_w, HEADER_H)
        canvas.line(inner_x + left_w, hy, inner_x + left_w, hy + HEADER_H)
        canvas.line(inner_x + left_w + center_w, hy, inner_x + left_w + center_w, hy + HEADER_H)

        # Logo cells: text stand-ins (no logo images in our data).
        canvas.setFillColor(hexcolor(cfg["colors"]["primary"]))
        canvas.setFont(BOLD, 12)
        if header.get("org_left"):
            canvas.drawCentredString(inner_x + left_w / 2, hy + HEADER_H / 2 - 4, shape(header["org_left"]))
        if header.get("org_right"):
            canvas.drawCentredString(inner_x + left_w + center_w + right_w / 2, hy + HEADER_H / 2 - 4, shape(header["org_right"]))

        # Center: project name, bold, wrapped to two lines if needed.
        if header.get("show_project"):
            canvas.setFillColor(hexcolor(cfg["colors"]["heading"]))
            _centered_wrapped(canvas, shape(ctx["project"]["name"]), inner_x + left_w, center_w, hy, HEADER_H, BOLD, 12)

        # Sub-row: the report line, centered.
        if header.get("show_report_no"):
            sy = hy - SUBROW_H
            canvas.setStrokeColor(hexcolor(cfg["colors"]["header_border"]))
            canvas.rect(inner_x, sy, inner_w, SUBROW_H)
            canvas.setFillColor(hexcolor(cfg["colors"]["text"]))
            canvas.setFont(FONT_NAME, 9)
            canvas.drawCentredString(w / 2, sy + SUBROW_H / 2 - 3, shape(_report_line(ctx, arabic)))

    footer = cfg["footer"]
    if footer.get("enabled"):
        canvas.setFillColor(hexcolor(cfg["colors"]["muted"]))
        canvas.setFont(FONT_NAME, 9)
        if footer.get("show_page_number"):
            canvas.drawCentredString(w / 2, BORDER_INSET + 3 * mm, str(doc.page))
        if footer.get("text"):
            canvas.drawString(BORDER_INSET + FRAME_PAD, BORDER_INSET + 3 * mm, shape(footer["text"]))
    canvas.restoreState()


def _centered_wrapped(canvas, text, x, width, y, height, font, size):
    """Draw text centered in a cell, wrapping to two lines on width overflow."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    canvas.setFont(font, size)
    cx = x + width / 2
    if stringWidth(text, font, size) <= width - 6:
        canvas.drawCentredString(cx, y + height / 2 - size / 3, text)
        return
    words = text.split(" ")
    mid = len(words) // 2 or 1
    line1, line2 = " ".join(words[:mid]), " ".join(words[mid:])
    canvas.drawCentredString(cx, y + height / 2 + 2, line1)
    canvas.drawCentredString(cx, y + height / 2 - size, line2)


def draw_cover(canvas, doc):
    """Cover page: maroon accent, report-number block, prepared-by, project title."""
    cfg, ctx = doc.cfg, doc.ctx
    w, h = doc.pagesize
    arabic = bool(ctx.get("arabic"))
    cover = cfg["cover"]
    accent = hexcolor(cfg["colors"]["cover_accent"])
    canvas.saveState()
    canvas.setFillColor(hexcolor(cfg["colors"]["cover_bg"]))
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Maroon vertical accent bar on the right, with a small tick.
    bx = w - BORDER_INSET - 14 * mm
    canvas.setFillColor(accent)
    canvas.rect(bx, h * 0.30, 1.6 * mm, h * 0.32, fill=1, stroke=0)
    canvas.rect(bx - 10 * mm, h * 0.46, 10 * mm, 1.6 * mm, fill=1, stroke=0)

    # Top-left org / logo stand-in.
    org = cfg["header"].get("org_left") or cover.get("org")
    if org:
        canvas.setFillColor(hexcolor(cfg["colors"]["primary"]))
        canvas.setFont(BOLD, 18)
        canvas.drawString(BORDER_INSET + 6 * mm, h - BORDER_INSET - 16 * mm, shape(org))

    # Report number + month, right-aligned near the accent bar.
    rx = bx - 6 * mm
    canvas.setFillColor(hexcolor(cfg["colors"]["text"]))
    canvas.setFont(BOLD, cfg["fonts"]["cover_title_size"])
    title = cover.get("title") or ctx["report"]["title"]
    no = ctx["report"]["number"]
    canvas.drawRightString(rx, h * 0.60, shape(f"{title} ({no})" if no else title))
    canvas.setFont(BOLD, cfg["fonts"]["h2_size"])
    period = _period_str(ctx, arabic)
    if period:
        canvas.drawRightString(rx, h * 0.555, shape(period))

    # Prepared-by block.
    if cover.get("prepared_by"):
        canvas.setFillColor(hexcolor(cfg["colors"]["muted"]))
        canvas.setFont(FONT_NAME, cfg["fonts"]["base_size"] + 1)
        canvas.drawRightString(rx, h * 0.47, shape(cover["prepared_by"]))
        if cover.get("org"):
            canvas.setFont(BOLD, cfg["fonts"]["base_size"] + 1)
            canvas.setFillColor(hexcolor(cfg["colors"]["primary"]))
            canvas.drawRightString(rx, h * 0.43, shape(cover["org"]))

    # Project title at the bottom, maroon, centered, wrapped.
    canvas.setFillColor(accent)
    _centered_wrapped(canvas, shape(ctx["project"]["name"]), BORDER_INSET, w - 2 * BORDER_INSET,
                      h * 0.12, 24 * mm, BOLD, cfg["fonts"]["cover_title_size"] + 2)

    # Overall % marker.
    if cover.get("show_overall"):
        canvas.setFillColor(accent)
        canvas.setFont(BOLD, 40)
        canvas.drawCentredString(w / 2, h * 0.04 + 8 * mm, f"{ctx['overall']:.0f}%")
    canvas.restoreState()
