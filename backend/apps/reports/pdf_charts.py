"""Charts for the report (reportlab.graphics), styled after the reference's
planned/actual bars, duration pie, overall donut, and Time-Performance S-curve.
All built from data we already have (actual + derived planned/previous/duration)."""
import datetime

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib.units import mm

from .pdf_base import BOLD, FONT_NAME, hexcolor, shape


def _legend(colors_labels, x, y, font_size=7):
    leg = Legend()
    leg.x, leg.y = x, y
    leg.alignment = "right"
    leg.fontName = FONT_NAME
    leg.fontSize = font_size
    leg.dxTextSpace = 4
    leg.columnMaximum = 1
    leg.deltax = 70
    leg.colorNamePairs = [(hexcolor(c), shape(label)) for c, label in colors_labels]
    return leg


def zone_progress_chart(cfg, ctx, width):
    """Actual progress per zone — fallback when no planned baseline exists."""
    zones = ctx["zones"][:12]
    if not zones:
        return None
    height = 70 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 22, 26
    chart.width, chart.height = width - 44, height - 50
    chart.data = [[round(z["progress"], 1) for z in zones]]
    chart.categoryAxis.categoryNames = [shape(z["name"]) for z in zones]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    chart.barWidth = 8
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[0].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 7
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.nudge = 7
    d.add(chart)
    return d


def planned_actual_chart(cfg, ctx, width, labels):
    """Grouped planned-vs-actual bars per zone (reference progress charts)."""
    zones = [z for z in ctx["zones"] if z.get("planned") is not None][:10]
    if not zones:
        return zone_progress_chart(cfg, ctx, width)
    height = 78 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 24, 30
    chart.width, chart.height = width - 48, height - 54
    chart.data = [
        [round(z["planned"], 1) for z in zones],
        [round(z["progress"], 1) for z in zones],
    ]
    chart.categoryAxis.categoryNames = [shape(z["name"]) for z in zones]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    chart.groupSpacing = 8
    chart.barSpacing = 1
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.bars[0].strokeColor = chart.bars[1].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.nudge = 6
    d.add(chart)
    d.add(_legend([(cfg["colors"]["chart_planned"], labels["planned"]),
                   (cfg["colors"]["chart_actual"], labels["actual"])], width - 150, height - 8))
    return d


def area_units_chart(cfg, area, width, labels):
    """Grouped planned-vs-actual bars per sub-unit within one zone (the
    per-area dashboard's chart) — same shape as `planned_actual_chart`, just
    sourced from one zone's children instead of the project's top-level zones.
    Skipped above a sane bar count (a zone with hundreds of subzones would
    just produce an unreadable chart; the breakdown table already covers it)."""
    units = [u for u in area.get("children", []) if u.get("planned") is not None][:15]
    if not units or len(area.get("children", [])) > 30:
        return None
    height = 78 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 24, 30
    chart.width, chart.height = width - 48, height - 54
    chart.data = [
        [round(u["planned"], 1) for u in units],
        [round(u["actual"], 1) for u in units],
    ]
    chart.categoryAxis.categoryNames = [shape(u["name"]) for u in units]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    chart.groupSpacing = 8
    chart.barSpacing = 1
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.bars[0].strokeColor = chart.bars[1].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.nudge = 6
    d.add(chart)
    d.add(_legend([(cfg["colors"]["chart_planned"], labels["planned"]),
                   (cfg["colors"]["chart_actual"], labels["actual"])], width - 150, height - 8))
    return d


def _duration_pie_for(cfg, dur, width, labels):
    if not dur:
        return None
    height = 62 * mm
    d = Drawing(width, height)
    pie = Pie()
    pie.x, pie.y = width / 2 - 28, 8
    pie.width = pie.height = 46 * mm
    pie.data = [max(0, dur["total"]), max(0, dur["delay"])]
    pie.labels = [str(dur["total"]), str(dur["delay"])]
    pie.slices.fontName = FONT_NAME
    pie.slices.fontSize = 8
    pie.slices[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    pie.slices[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    pie.slices.strokeColor = hexcolor("#ffffff")
    d.add(pie)
    d.add(_legend([(cfg["colors"]["chart_planned"], labels["duration_days"]),
                   (cfg["colors"]["chart_actual"], labels["delay_days"])], width - 150, height - 8))
    return d


def duration_pie(cfg, ctx, width, labels):
    """Project duration vs delay days (reference duration pie)."""
    return _duration_pie_for(cfg, ctx.get("duration"), width, labels)


def zone_duration_pie(cfg, dur, width, labels):
    """Same pie, for one zone's own duration (the per-area dashboard)."""
    return _duration_pie_for(cfg, dur, width, labels)


def overall_donut(cfg, ctx, width, labels):
    """Overall completion donut with the % in the centre."""
    overall = float(ctx["overall"])
    height = 56 * mm
    d = Drawing(width, height)
    pie = Pie()
    pie.x, pie.y = width / 2 - 24, 6
    pie.width = pie.height = 42 * mm
    pie.data = [max(0.1, overall), max(0.1, 100 - overall)]
    pie.innerRadiusFraction = 0.58  # donut
    pie.slices.strokeColor = hexcolor("#ffffff")
    pie.slices[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    pie.slices[1].fillColor = hexcolor(cfg["colors"]["table_row_alt"])
    pie.simpleLabels = 1
    pie.labels = ["", ""]
    d.add(pie)
    d.add(String(width / 2, height / 2 - 2, f"{overall:.1f}%", fontName=FONT_NAME, fontSize=13,
                 fillColor=hexcolor(cfg["colors"]["heading"]), textAnchor="middle"))
    return d


def scurve_chart(cfg, ctx, width, labels):
    """Time Performance S-curve: planned vs actual cumulative progress."""
    series = [p for p in ctx.get("scurve", []) if p.get("planned") is not None]
    if len(series) < 2:
        return None
    height = 72 * mm
    d = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.x, chart.y = 26, 28
    chart.width, chart.height = width - 52, height - 50
    chart.data = [[p["planned"] for p in series], [p["actual"] for p in series]]
    chart.categoryAxis.categoryNames = [p["date"].strftime("%b %y") for p in series]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    chart.lines[0].strokeColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.lines[1].strokeColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.lines[0].strokeWidth = chart.lines[1].strokeWidth = 2
    d.add(chart)
    d.add(_legend([(cfg["colors"]["chart_planned"], labels["planned"]),
                   (cfg["colors"]["chart_actual"], labels["actual"])], width - 150, height - 8))
    return d


def _add_month(d, months):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return d.replace(year=y, month=m)


def gantt_chart(cfg, rows, width, labels):
    """Simple Gantt-style schedule printout: one bar per zone/phase row, gray
    baseline = its own planned span, blue fill = its rolled-up actual %
    complete, a red tick marks the revised finish when it slipped past the
    baseline. No predecessor/float/critical-path computation — just the dates
    and % we already have. Capped to a sane row count so a huge project still
    fits on one readable page."""
    rows = rows[:25]
    if not rows:
        return None

    label_w = 52 * mm
    chart_x = label_w
    chart_w = width - label_w - 4 * mm
    row_h = 7 * mm
    top_pad = 11 * mm
    bottom_pad = 6 * mm
    height = top_pad + row_h * len(rows) + bottom_pad
    chart_top = height - top_pad

    min_d = min(r["start"] for r in rows)
    max_d = max(r["revised_finish"] or r["finish"] for r in rows)
    span_days = max(1, (max_d - min_d).days)

    def x(dt):
        return chart_x + (dt - min_d).days / span_days * chart_w

    d = Drawing(width, height)
    c = cfg["colors"]
    baseline_color = hexcolor(c["chart_planned"])
    fill_color = hexcolor(c["chart_actual"])
    delay_color = hexcolor("#C0504D")
    has_slip = False

    months_span = max(1, span_days // 30)
    step = max(1, round(months_span / 10))  # aim for ~10 gridlines regardless of span
    cur = min_d.replace(day=1)
    while cur <= max_d:
        gx = x(max(cur, min_d))
        d.add(Line(gx, bottom_pad - 4, gx, chart_top, strokeColor=hexcolor(c["table_border"]), strokeWidth=0.3))
        d.add(String(gx + 2, chart_top + 3, cur.strftime("%b %y"), fontName=FONT_NAME, fontSize=6,
                     fillColor=hexcolor(c["muted"])))
        cur = _add_month(cur, step)

    for i, r in enumerate(rows):
        row_top = chart_top - i * row_h
        y = row_top - row_h + 1.2 * mm
        bar_h = row_h - 2.4 * mm
        x0, x1 = x(r["start"]), x(r["finish"])
        d.add(Rect(x0, y, max(1, x1 - x0), bar_h, fillColor=baseline_color, strokeColor=None))
        span = (r["finish"] - r["start"]).days
        filled = round(span * r["progress"] / 100)
        fx1 = x(r["start"] + datetime.timedelta(days=min(span, filled)))
        if fx1 > x0:
            d.add(Rect(x0, y, fx1 - x0, bar_h, fillColor=fill_color, strokeColor=None))
        if r.get("revised_finish") and r["revised_finish"] > r["finish"]:
            has_slip = True
            rx = x(r["revised_finish"])
            d.add(Line(rx, y, rx, y + bar_h, strokeColor=delay_color, strokeWidth=1.3))
        raw_name = r["name"] if r["level"] == 0 else "    " + r["name"]
        d.add(String(2, row_top - row_h / 2 - 2, shape(raw_name[:42]),
                     fontName=BOLD if r["level"] == 0 else FONT_NAME, fontSize=7,
                     fillColor=hexcolor(c["text"])))

    d.add(_legend([(c["chart_planned"], labels["planned"]), (c["chart_actual"], labels["actual"])],
                  width - 150, height - 6, font_size=7))
    if has_slip:
        d.add(String(width - 150, height - 16, "— " + shape(labels.get("gantt_revised", "Revised finish")),
                     fontName=FONT_NAME, fontSize=7, fillColor=delay_color))
    return d
