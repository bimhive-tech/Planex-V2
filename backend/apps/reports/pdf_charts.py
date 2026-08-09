"""Charts for the report (reportlab.graphics), styled after the reference's
planned/actual bars, duration pie, overall donut, and Time-Performance S-curve.
All built from data we already have (actual + derived planned/previous/duration)."""
import datetime
import math

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String, Wedge
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from .pdf_base import BOLD, FONT_NAME, has_arabic, hexcolor, shape

# The reference gauge's own text is plain Latin sans-serif — Helvetica is a
# standard PDF font (no embedding needed) and reads much closer to it than
# Amiri's serif Latin glyphs. Only used for text confirmed non-Arabic (a
# translated template's band/value labels still need Amiri's Arabic support).
_SANS = "Helvetica"
_SANS_BOLD = "Helvetica-Bold"


def _gauge_font(text, bold=False):
    if has_arabic(text):
        return BOLD if bold else FONT_NAME
    return _SANS_BOLD if bold else _SANS


def _grid(value_axis, cfg):
    """Faint horizontal gridlines behind bars/lines, matching the reference
    dashboard's own charts (all of which grid at every value-axis tick)."""
    value_axis.visibleGrid = 1
    value_axis.gridStrokeColor = hexcolor(cfg["colors"].get("chart_grid", "#D9D9D9"))
    value_axis.gridStrokeWidth = 0.4


def _legend(colors_labels, x, y, font_size=7, vertical=False, deltax=95):
    """Swatch+label legend. Horizontal by default; `vertical=True` stacks the
    entries in one column (used when labels carry values and would otherwise
    collide, e.g. the duration pie)."""
    leg = Legend()
    leg.x, leg.y = x, y
    leg.alignment = "right"
    leg.fontName = FONT_NAME
    leg.fontSize = font_size
    leg.dxTextSpace = 4
    leg.dy = 6
    leg.deltay = 12
    leg.columnMaximum = len(colors_labels) if vertical else 1
    leg.deltax = 0 if vertical else deltax
    leg.colorNamePairs = [(hexcolor(c), shape(label)) for c, label in colors_labels]
    return leg


def zone_progress_chart(cfg, ctx, width, height=None):
    """Actual progress per zone — fallback when no planned baseline exists."""
    zones = ctx["zones"][:12]
    if not zones:
        return None
    height = height or 70 * mm
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
    _grid(chart.valueAxis, cfg)
    chart.barWidth = 8
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[0].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 7
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.nudge = 7
    d.add(chart)
    return d


def planned_actual_chart(cfg, ctx, width, labels, height=None):
    """Grouped planned-vs-actual bars per zone (reference progress charts)."""
    zones = [z for z in ctx["zones"] if z.get("planned") is not None][:10]
    if not zones:
        return zone_progress_chart(cfg, ctx, width, height)
    height = height or 78 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 24, 26
    chart.width, chart.height = width - 48, height - 60  # leave a top strip for the legend
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
    _grid(chart.valueAxis, cfg)
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
                   (cfg["colors"]["chart_actual"], labels["actual"])], width / 2 - 95, height - 12))
    return d


def _unit_bars(cfg, units, width, labels, height=None):
    """Per-unit bars within a zone: grouped planned/actual when a baseline
    exists, else actual-only (most projects carry no per-unit dates yet, so the
    old version drew nothing — now it still shows where each unit stands)."""
    has_planned = any(u.get("planned") is not None for u in units)
    height = height or 78 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 24, 26
    chart.width, chart.height = width - 48, height - 60  # leave a top strip for the legend
    if has_planned:
        chart.data = [[round(u.get("planned") or 0, 1) for u in units],
                      [round(u["actual"], 1) for u in units]]
    else:
        chart.data = [[round(u["actual"], 1) for u in units]]
    chart.categoryAxis.categoryNames = [shape(u["name"]) for u in units]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    chart.groupSpacing = 8
    chart.barSpacing = 1
    chart.bars[0].strokeColor = None
    if has_planned:
        chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
        chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
        chart.bars[1].strokeColor = None
    else:
        chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.nudge = 6
    d.add(chart)
    pairs = ([(cfg["colors"]["chart_planned"], labels["planned"])] if has_planned else []) + \
        [(cfg["colors"]["chart_actual"], labels["actual"])]
    d.add(_legend(pairs, width / 2 - 95, height - 12))
    return d


AREA_CHART_MAX = 15  # a grouped bar chart stops being readable past ~15 bars


def area_progress_chart(cfg, ctx, width, labels, height=None):
    """Planned-vs-actual bars one level below zones (the areas / subzones). Same
    look as the zone chart; capped so it stays legible with many areas."""
    areas = ctx.get("areas") or []
    if not areas:
        return None
    return _unit_bars(cfg, areas[:AREA_CHART_MAX], width, labels, height)


def _completion_histogram(cfg, children, width, labels, height=None):
    """How a zone's sub-units are spread across completion bands — readable at
    any unit count (a per-unit bar chart isn't, past ~15 units). Bar height is
    the number of units in each band; the value label prints that count."""
    bands = [0, 0, 0, 0, 0]  # 0% | 1-49 | 50-74 | 75-99 | 100%
    for u in children:
        p = float(u.get("actual") or 0)
        if p <= 0:
            bands[0] += 1
        elif p < 50:
            bands[1] += 1
        elif p < 75:
            bands[2] += 1
        elif p < 100:
            bands[3] += 1
        else:
            bands[4] += 1
    height = height or 70 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 26, 24
    chart.width, chart.height = width - 52, height - 42
    chart.data = [bands]
    chart.categoryAxis.categoryNames = ["0%", "1-49%", "50-74%", "75-99%", "100%"]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 8
    top = max(bands) or 1
    chart.valueAxis.valueMin, chart.valueAxis.valueMax = 0, top
    chart.valueAxis.valueStep = max(1, -(-top // 5))  # ceil(top/5)
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    chart.barWidth = 14
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[0].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 8
    chart.barLabelFormat = "%d"
    chart.barLabels.nudge = 7
    d.add(chart)
    return d


def area_units_chart(cfg, area, width, labels, height=None):
    """A zone's sub-units visualised for its dashboard page: per-unit bars when
    there are few enough to read, otherwise a completion histogram so the page
    stays informative for zones with dozens/hundreds of units (the old version
    just drew nothing in that case, leaving the page near-empty)."""
    children = area.get("children", [])
    if not children:
        return None
    if len(children) <= 15:
        return _unit_bars(cfg, children, width, labels, height)
    return _completion_histogram(cfg, children, width, labels, height)


def _duration_pie_for(cfg, dur, width, labels, height=None):
    if not dur:
        return None
    height = height or 60 * mm
    pw = 40 * mm
    d = Drawing(width, height)
    pie = Pie()
    pie.x, pie.y = (width - pw) / 2, 4   # centred; values move to the legend below
    pie.width = pie.height = pw
    pie.data = [max(0, dur["total"]), max(0, dur["delay"])]
    pie.labels = ["", ""]                # no numbers on the slices (they overlapped)
    pie.simpleLabels = 1
    pie.slices[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    pie.slices[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    pie.slices.strokeColor = hexcolor("#ffffff")
    d.add(pie)
    # Stacked legend carrying the values, in the clear strip above the pie.
    d.add(_legend([(cfg["colors"]["chart_planned"], f'{labels["duration_days"]}: {dur["total"]}'),
                   (cfg["colors"]["chart_actual"], f'{labels["delay_days"]}: {dur["delay"]}')],
                  10, height - 6, vertical=True))
    return d


def duration_pie(cfg, ctx, width, labels, height=None):
    """Project duration vs delay days (reference duration pie)."""
    return _duration_pie_for(cfg, ctx.get("duration"), width, labels, height)


def zone_duration_pie(cfg, dur, width, labels, height=None):
    """Same pie, for one zone's own duration (the per-area dashboard)."""
    return _duration_pie_for(cfg, dur, width, labels, height)


def overall_donut(cfg, ctx, width, labels, height=None):
    """Overall completion donut with the % in the centre."""
    overall = float(ctx["overall"])
    height = height or 56 * mm
    pw = 42 * mm
    d = Drawing(width, height)
    pie = Pie()
    pie.x, pie.y = (width - pw) / 2, 6   # centred so the % lands in the hole
    pie.width = pie.height = pw
    pie.data = [max(0.1, overall), max(0.1, 100 - overall)]
    pie.innerRadiusFraction = 0.58  # donut
    pie.slices.strokeColor = hexcolor("#ffffff")
    pie.slices[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    pie.slices[1].fillColor = hexcolor(cfg["colors"]["table_row_alt"])
    pie.simpleLabels = 1
    pie.labels = ["", ""]
    d.add(pie)
    cx, cy = pie.x + pw / 2, pie.y + pw / 2
    d.add(String(cx, cy - 5, f"{overall:.1f}%", fontName=FONT_NAME, fontSize=13,
                 fillColor=hexcolor(cfg["colors"]["heading"]), textAnchor="middle"))
    return d


def speedometer_chart(value, width, cfg, *, title=None, max_value=100.0, height=None):
    """Semicircular SPI/completion gauge — 4 labeled bands (Poor/Average/Good/
    Excellent, red->orange->yellow->green) with a needle at `value`
    (0..max_value). `value` is a plain number (not read from ctx) so the
    same drawing serves the project-level overall % and any per-zone/per-
    item % a caller has on hand. Band cutoffs, colors and labels come from
    cfg (gauge_thresholds, colors.gauge_*, labels.gauge_*) so a template can
    move them away from the defaults — modeled pixel-for-pixel on the
    reference dashboard's own SPI speedometer chart: a thin ring (not a
    solid wedge down to the hub), a small needle pivot, the value line
    directly under the arc with the caption below it, and — since that
    reference chart is plain Latin sans-serif — Helvetica text wherever the
    label isn't Arabic."""
    if value is None:
        return None
    height = height or 48 * mm
    d = Drawing(width, height)
    cx = width / 2
    text_h = 24          # room below the hub for the value line + caption
    label_pad = 11        # room above the arc for the band labels
    cy = text_h + 6
    band_font_size = 6.5
    r_label_factor = 1.08

    thresholds = cfg.get("gauge_thresholds") or {}
    low = float(thresholds.get("low", 50))
    mid = float(thresholds.get("mid", 70))
    high = float(thresholds.get("high", 90))
    colors = cfg["colors"]
    labels = cfg.get("labels") or {}
    gauge_bands = [
        (0, low, colors.get("gauge_bad", "#B40000"), labels.get("gauge_poor", "Poor")),
        (low, mid, colors.get("gauge_warn", "#FFC000"), labels.get("gauge_average", "Average")),
        (mid, high, colors.get("gauge_good", "#FFFF00"), labels.get("gauge_good", "Good")),
        (high, max_value, colors.get("gauge_excellent", "#77933C"), labels.get("gauge_excellent", "Excellent")),
    ]
    # The outermost (leftmost/rightmost) band labels are textAnchor="middle"
    # at r_label, so they reach roughly half their own width further out —
    # without this, "Excellent" clips off the right edge of a narrow box.
    widest_label_w = max(
        pdfmetrics.stringWidth(shape(bl), _gauge_font(bl), band_font_size) for *_, bl in gauge_bands
    )
    r_outer = max(8, min(
        (width / 2 - widest_label_w / 2 - 2) / r_label_factor,
        height - cy - label_pad,
    ) * 0.92)
    r_inner = r_outer * 0.80  # thin ring, matched to the reference's own band width
    r_label = r_outer * r_label_factor

    for lo, hi, color, band_label in gauge_bands:
        a0 = 180 - (lo / max_value) * 180
        a1 = 180 - (hi / max_value) * 180
        # reportlab.graphics.shapes.Wedge has no "innerRadius" attribute —
        # the actual inner-cut parameter is "radius1". Passing innerRadius
        # was silently ignored (Wedge has no such AttrMapValue), so this was
        # drawing a full pie wedge down to the center the whole time despite
        # r_inner being computed correctly above.
        d.add(Wedge(cx, cy, r_outer, a1, a0, radius1=r_inner,
                    fillColor=hexcolor(color), strokeColor=hexcolor("#ffffff"), strokeWidth=0.5))
        mid_angle = math.radians((a0 + a1) / 2)
        lx, ly = cx + r_label * math.cos(mid_angle), cy + r_label * math.sin(mid_angle)
        d.add(String(lx, ly, shape(band_label), fontName=_gauge_font(band_label), fontSize=band_font_size,
                     fillColor=hexcolor(cfg["colors"]["muted"]), textAnchor="middle"))

    v = max(0.0, min(max_value, float(value)))
    angle = math.radians(180 - (v / max_value) * 180)
    tip_x, tip_y = cx + r_outer * 0.85 * math.cos(angle), cy + r_outer * 0.85 * math.sin(angle)
    perp = angle + math.pi / 2
    base_w = r_outer * 0.06
    base1 = (cx + base_w * math.cos(perp), cy + base_w * math.sin(perp))
    base2 = (cx - base_w * math.cos(perp), cy - base_w * math.sin(perp))
    needle_color = hexcolor("#1e2430")
    d.add(Polygon([base1[0], base1[1], base2[0], base2[1], tip_x, tip_y],
                  fillColor=needle_color, strokeColor=None))
    d.add(Circle(cx, cy, base_w * 0.6, fillColor=needle_color, strokeColor=None))  # small pivot dot, not a bold hub

    # Value line directly under the hub, caption below that — same top-to-
    # bottom order as the reference (arc, then value, then caption), the
    # reverse of this drawing's earlier title-on-top layout.
    value_text = f"{shape(title)}= {v:.0f}%" if title else f"{v:.0f}%"
    d.add(String(cx, cy - 14, value_text, fontName=_gauge_font(title or ""), fontSize=11,
                 fillColor=hexcolor(cfg["colors"]["text"]), textAnchor="middle"))
    if title:
        d.add(String(cx, cy - 26, shape(title), fontName=_gauge_font(title), fontSize=8,
                     fillColor=hexcolor(cfg["colors"]["muted"]), textAnchor="middle"))
    return d


def scurve_chart(cfg, ctx, width, labels, height=None):
    """Time Performance S-curve: planned vs actual cumulative progress."""
    series = [p for p in ctx.get("scurve", []) if p.get("planned") is not None]
    if len(series) < 2:
        return None
    height = height or 72 * mm
    d = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.x, chart.y = 26, 26
    chart.width, chart.height = width - 52, height - 56  # leave a top strip for the legend
    chart.data = [[p["planned"] for p in series], [p["actual"] for p in series]]
    chart.categoryAxis.categoryNames = [p["date"].strftime("%b %y") for p in series]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    _grid(chart.valueAxis, cfg)
    chart.lines[0].strokeColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.lines[1].strokeColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.lines[0].strokeWidth = chart.lines[1].strokeWidth = 2
    d.add(chart)
    d.add(_legend([(cfg["colors"]["chart_planned"], labels["planned"]),
                   (cfg["colors"]["chart_actual"], labels["actual"])], width / 2 - 95, height - 12))
    return d


def cashflow_chart(cfg, rows, width, labels, height=None):
    """Monthly planned-vs-actual cash bars (the values the user typed in the
    Finances tab — no derivation)."""
    rows = rows[:24]
    if not rows:
        return None
    height = height or 80 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 32, 28
    chart.width, chart.height = width - 60, height - 62
    chart.data = [[r["planned"] for r in rows], [r["actual"] for r in rows]]
    chart.categoryAxis.categoryNames = [r["month"].strftime("%b %y") for r in rows]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    _grid(chart.valueAxis, cfg)
    chart.groupSpacing = 6
    chart.barSpacing = 1
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.bars[0].strokeColor = chart.bars[1].strokeColor = None
    d.add(chart)
    d.add(_legend([(cfg["colors"]["chart_planned"], labels["planned"]),
                   (cfg["colors"]["chart_actual"], labels["actual"])], width / 2 - 95, height - 12))
    return d


def cashflow_curve(cfg, rows, width, labels, height=None):
    """Cumulative cash S-curve (planned vs actual added up month over month)."""
    if len(rows) < 2:
        return None
    height = height or 78 * mm
    d = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.x, chart.y = 32, 26
    chart.width, chart.height = width - 60, height - 56
    chart.data = [[r["cum_planned"] for r in rows], [r["cum_actual"] for r in rows]]
    chart.categoryAxis.categoryNames = [r["month"].strftime("%b %y") for r in rows]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    _grid(chart.valueAxis, cfg)
    chart.lines[0].strokeColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.lines[1].strokeColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.lines[0].strokeWidth = chart.lines[1].strokeWidth = 2
    d.add(chart)
    d.add(_legend([(cfg["colors"]["chart_planned"], labels["planned"]),
                   (cfg["colors"]["chart_actual"], labels["actual"])], width / 2 - 95, height - 12))
    return d


def _add_month(d, months):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return d.replace(year=y, month=m)


def gantt_chart(cfg, rows, width, labels, height=None):
    """Simple Gantt-style schedule printout: one bar per zone/phase row, gray
    baseline = its own planned span, blue fill = its rolled-up actual %
    complete, a red tick marks the revised finish when it slipped past the
    baseline. No predecessor/float/critical-path computation — just the dates
    and % we already have. Capped to a sane row count so a huge project still
    fits on one readable page.

    `height`: when omitted, the drawing grows to fit every row at a fixed
    7mm row height (legacy behaviour). When given (a fixed canvas box), rows
    are compressed to fit — and if that would make them illegible (<4mm),
    rows are dropped instead of squeezed further, same as the too-small-box
    fallback used elsewhere."""
    rows = rows[:25]
    if not rows:
        return None

    label_w = 52 * mm
    chart_x = label_w
    chart_w = width - label_w - 4 * mm
    top_pad = 11 * mm
    bottom_pad = 6 * mm
    min_row_h = 4 * mm
    if height is None:
        row_h = 7 * mm
        height = top_pad + row_h * len(rows) + bottom_pad
    else:
        available = height - top_pad - bottom_pad
        row_h = available / len(rows)
        if row_h < min_row_h:
            max_rows = max(1, int(available / min_row_h))
            rows = rows[:max_rows]
            row_h = available / len(rows)
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
