"""Charts for the report (reportlab.graphics), styled after the reference's
planned/actual bars, duration pie, overall donut, and Time-Performance S-curve.
All built from data we already have (actual + derived planned/previous/duration)."""
import datetime
import math

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String, Wedge
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from .pdf_axes import (calendar_ticks, date_unit_labels, horizontal_number_axis, number_axis,
                       percent_axis, text_width)
from .pdf_base import _LRM, BOLD, FONT_NAME, has_arabic, hexcolor, shape

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


# Bar thickness, in the reference workbook's own terms.
#
# Excel sizes bars with `gapWidth`: the gap between category slots as a
# percentage of ONE bar's width. gapWidth=150 therefore means the bar is
# 1/(1+1.5) = 40% of its slot. `overlap` does the same job inside a cluster,
# and a negative value pushes the series apart by that percentage.
#
# reportlab reads barWidth/groupSpacing/barSpacing as relative weights and
# scales them to fill the axis (unless useAbsolute is set), so the workbook's
# ratios transfer across unchanged -- which is why these are expressed against
# a nominal bar width rather than in points. Its defaults (barWidth 10,
# groupSpacing 5) leave a stacked bar filling 67% of its slot; the reference
# never goes above 50%, which is what made our bars read as fat next to it.
_BAR_UNIT = 10.0

# gapWidth/overlap as read out of "Dashboard template 02-08-2026.xlsx", per
# panel. Named rather than inlined so a chart says which reference panel it is
# copying, and so the two clustered families stay distinguishable.
GAP_STACKED = 150       # MATERIAL SUBMITTALS / SHOP DRAWING / Time Performance
GAP_CLUSTERED = 100     # Progress Comparison, Project Tracking
GAP_WIDE = 219          # Project Progress Area, Financial Progress (BOQ), Cash flow
OVERLAP_CLUSTERED = -24
OVERLAP_WIDE = -27


def _bar_geometry(chart, gap_width=GAP_CLUSTERED, overlap=0):
    """Size `chart`'s bars the way the reference workbook sizes its own.

    `gap_width`/`overlap` are Excel's units (see above) so the call site can
    quote the reference panel it matches. A positive `overlap` (stacked bars
    ride on top of each other) needs no in-cluster spacing at all.
    """
    chart.barWidth = _BAR_UNIT
    chart.groupSpacing = _BAR_UNIT * gap_width / 100.0
    chart.barSpacing = _BAR_UNIT * max(0.0, -overlap) / 100.0


def _grid(value_axis, cfg):
    """Faint horizontal gridlines behind bars/lines, matching the reference
    dashboard's own charts (all of which grid at every value-axis tick)."""
    value_axis.visibleGrid = 1
    value_axis.gridStrokeColor = hexcolor(cfg["colors"].get("chart_grid", "#D9D9D9"))
    value_axis.gridStrokeWidth = 0.4


def _thinned_labels(names, avail_width, font_size=7, angled=True, vertical=False):
    """Blank out category-axis labels beyond what `avail_width` can legibly
    fit, keeping every Nth one — a long monthly series (e.g. a multi-year
    S-curve with 50+ points) otherwise draws a label at every single point
    and they overlap into a solid, unreadable smear. Ticks still mark every
    data point; only the text on the skipped ones is left blank. Angled
    (rotated ~30 degrees) labels overlap far less per pixel of width than
    horizontal ones, so they get a smaller per-label budget.

    `vertical` is for labels rotated a full 90 degrees, where the text runs
    DOWN the page: such a label occupies only its own line height across the
    axis, whatever it says, so the budget is per-label rather than per-
    character. Charging them by length dropped 60 of a stage's 74 building
    names on a chart with room for every one (2026-09-03)."""
    if not names:
        return names
    if vertical:
        per_label = font_size * 1.25          # line height, plus a little air
    else:
        avg_chars = max(1.0, sum(len(n) for n in names) / len(names))
        per_label = avg_chars * font_size * (0.42 if angled else 0.62)
    max_labels = max(1, int(avail_width / per_label))
    if len(names) <= max_labels:
        return names
    step = -(-len(names) // max_labels)  # ceil division
    return [n if i % step == 0 else "" for i, n in enumerate(names)]


def _date_category_axis(axis, dates, avail_width, font_size=6):
    """Label a one-point-per-date category axis at the calendar unit that
    fits `avail_width` (pdf_axes.date_unit_labels), hiding the tick marks
    whenever some points go unlabelled. Ticks are drawn at every data point
    regardless of whether its label survived, so a 50-point monthly series in
    a narrow panel renders a solid black band along the axis where the ticks
    merge (found 2026-08-30 comparing the S-curve against the client's
    reference report, whose own charts carry no category ticks at all)."""
    _, names = date_unit_labels(dates, avail_width, font_size)
    axis.categoryNames = names
    if any(n == "" for n in names):
        axis.visibleTicks = 0
    return names


# Chart builders are callable directly (tests, the chart_svgs preview path)
# without `ensure_fonts()` having run, and a metrics lookup on an unregistered
# font raises rather than degrading — so every layout measurement goes through
# the fallback-aware helper.
_text_width = text_width


_ELLIPSIS = "\u2026"


def _vertical_names(raw_names, height, font_size=7, min_font_size=5, pad=10, share=0.45):
    """(shaped names, bottom inset, font size) for a category axis with labels
    rotated to 90 degrees: a vertical label is as tall as the text is long, so
    the fixed ~26pt that suited 30-degree labels clipped them to "ilding 6"
    (found 2026-08-30 after switching these axes to the reference's vertical
    convention).

    The inset is capped at a share of the chart's own height so a long name
    can't squeeze the plot away. A fixed 64pt cap was right for building
    numbers and wrong for "Level 2A - Architectural Works", which ran 45pt
    past it into the figure caption on a full-width chart that had the room.

    Names that don't fit the cap are set smaller first, down to
    `min_font_size`, and only then cut — with an ellipsis, and before shaping
    so an Arabic name loses its end rather than its start. Cutting first
    turned "Part 1 - Level 2A" into "Part 1 - Level 2", the name of another
    bar on the same chart, and four bars became two pairs of twins
    (2026-09-14)."""
    cap = max(26, height * share)
    raw_names = [str(n) for n in raw_names]
    for size in range(font_size, min_font_size - 1, -1):
        if all(_text_width(shape(n), size) + pad <= cap for n in raw_names):
            break
    names = []
    for text in raw_names:
        if _text_width(shape(text), size) + pad > cap:
            while len(text) > 1 and _text_width(shape(text + _ELLIPSIS), size) + pad > cap:
                text = text[:-1]
            text = text.rstrip() + _ELLIPSIS
        names.append(shape(text))
    widest = max((_text_width(n, size) for n in names if n), default=0)
    return names, min(cap, widest + pad), size


# Bar value labels are the widest they get at "100%".
_WIDEST_BAR_LABEL = "100%"


def _value_labels(chart, categories, font_size, series):
    """Whether the LAST series' bars can carry a printed value, and the
    sideways nudge that keeps it off the bar beside them.

    The value sits centred over its own bar, and on a planned/actual pair
    that bar is a fifth of the category: a label wider than it spilled onto
    the planned bar to its left, black on blue. Nudged right by the excess,
    it starts at its own bar's left edge and runs into the group gap
    instead, which is empty — so the room it needs is the bar plus that gap,
    and it is left out only when even that is too narrow (2026-09-14)."""
    per_category = chart.width / max(1, categories)
    units = series * chart.barWidth + (series - 1) * chart.barSpacing + chart.groupSpacing
    bar_w = per_category * chart.barWidth / units
    gap_w = per_category * chart.groupSpacing / units
    label_w = _text_width(_WIDEST_BAR_LABEL, font_size)
    fits = label_w <= bar_w + gap_w
    nudge = max(0.0, (label_w - bar_w) / 2) if series > 1 else 0.0
    return fits, nudge


def _top_legend(d, swatches, width, y_top, font_size=7):
    """A legend centred along the top of a chart while it fits on one row,
    wrapping from the left edge when it doesn't. reportlab's own Legend
    spaces entries a fixed 95pt apart from a fixed x, which put the first
    swatch outside a small chart's own box (2026-09-14)."""
    # Twice the space between entries as within one, so each swatch reads as
    # belonging to the label beside it rather than to its neighbour.
    swatch, gap, item_gap = 6, 3, 16
    row = sum(swatch + gap + _text_width(shape(label), font_size) + item_gap
              for _, label in swatches) - item_gap
    x0 = max(2, (width - row) / 2) if row <= width - 4 else 2
    _draw_wrapped_legend(d, swatches, x0, y_top, width - 2, font_size=font_size,
                         swatch_size=swatch, gap=gap, item_gap=item_gap)


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


def _reference_pie(cfg, slices, width, height, *, value_fmt="{:,.0f}", popout=4, extra_legend=()):
    """Pie drawn the way every pie in the client's reference report is drawn:
    slices pulled slightly apart, each one's value printed just outside its
    own wedge, and a wrapped swatch legend underneath (2026-08-30, matching
    the reference's PROGRESS / DURATION / Earned Progress / Invoice Status
    panels). Replaces the older "values live in a side legend" treatment,
    which read nothing like the reference.

    `slices` is [(label, value, color), ...]. Zero-valued slices keep their
    legend entry — the reference shows "0" rather than dropping the series —
    but are given no popout, so they don't push a visible gap into the ring.

    `extra_legend` is [(color, text), ...] for a figure the reader needs that
    is not a wedge of its own — the planned baseline the progress pie's
    wedges add up to. It joins the same legend, after the slices.
    """
    if not slices:
        return None
    d = Drawing(width, height)
    legend = [(c, n) for n, _, c in slices] + list(extra_legend)
    legend_rows = _wrapped_legend_rows(legend, width - 16)
    legend_h = 6 + legend_rows * 8
    # Leave room on all sides for the outside value labels, which sit at
    # 1.15x the radius and would otherwise run off the drawing.
    pw = max(18 * mm, min(height - legend_h - 14, width * 0.56))
    pie = Pie()
    pie.x, pie.y = (width - pw) / 2, legend_h + 6
    pie.width = pie.height = pw
    pie.data = [max(0.0001, float(v)) for _, v, _ in slices]
    pie.labels = [value_fmt.format(v) for _, v, _ in slices]
    pie.simpleLabels = 0
    pie.sideLabels = 0
    pie.slices.labelRadius = 1.15
    pie.slices.fontName = FONT_NAME
    pie.slices.fontSize = 6
    pie.slices.strokeColor = hexcolor("#ffffff")
    pie.slices.strokeWidth = 0.75
    for i, (_, value, color) in enumerate(slices):
        pie.slices[i].fillColor = hexcolor(color)
        if float(value) > 0:
            pie.slices[i].popout = popout
    d.add(pie)
    _draw_wrapped_legend(d, legend, 8, legend_h, width - 16)
    return d


def zone_progress_chart(cfg, ctx, width, height=None):
    """Actual progress per zone — fallback when no planned baseline exists."""
    # Uncapped, same reasoning as planned_actual_chart above — a silently
    # truncated zone chart hides whichever zones fall past the cut.
    zones = ctx["zones"]
    if not zones:
        return None
    height = height or 70 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    names, chart.y, name_size = _vertical_names([z["name"] for z in zones], height)
    chart.x = 22
    chart.width, chart.height = width - 44, height - chart.y - 24
    chart.data = [[round(z["progress"], 1) for z in zones]]
    chart.categoryAxis.categoryNames = _thinned_labels(names, chart.width, font_size=name_size, vertical=True)
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = name_size
    # 90-degree labels, matching the reference report's own per-unit progress
    # charts — vertical labels are what let it fit ~75 buildings on one chart
    # where angled ones would collide (2026-08-30). The value axis keeps the
    # reference's 10% steps at the default size and coarsens or refines as the
    # chart is resized (pdf_axes).
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.boxAnchor = "e"
    percent_axis(chart.valueAxis, chart.height, 7)
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_WIDE, OVERLAP_WIDE)  # "Project Progress Area"
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[0].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 7
    fits, chart.barLabels.dx = _value_labels(chart, len(zones), 7, series=1)
    chart.barLabelFormat = "%0.0f%%" if fits else None
    chart.barLabels.nudge = 7
    d.add(chart)
    return d


def planned_actual_chart(cfg, ctx, width, labels, height=None):
    """Grouped planned-vs-actual bars per zone (reference progress charts).

    `planned` comes from the schedule's own baseline figure (P6 "Schedule %
    Complete"; see `services._scope_planned_progress`), so on an overdue
    project every zone reads 100%. Both series are drawn anyway: the client's
    own dashboard plots the flat 100% planned bar beside each actual one, and
    the gap between them IS the message. An earlier version collapsed this to
    actual-only with a note, which hid the comparison the chart exists to make
    (reported 2026-09-02)."""
    # Every zone, uncapped. This used to take the first 10, which on this
    # project silently dropped zones 11-15 — and those included the THREE
    # WORST in the whole job (54%, 61%, 67%). A truncated bar chart on the
    # executive status page made the project look materially better than it
    # was, with nothing on the page saying anything had been left out
    # (2026-08-30 critic pass). A chart with too many bars is a legibility
    # problem; a chart that hides the bad news is a correctness one.
    zones = [z for z in ctx["zones"] if z.get("planned") is not None]
    if not zones:
        return zone_progress_chart(cfg, ctx, width, height)
    height = height or 78 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    names, chart.y, name_size = _vertical_names([z["name"] for z in zones], height)  # room for 90-degree labels
    chart.x = 24
    chart.width, chart.height = width - 48, height - chart.y - 34  # top strip for the legend
    chart.data = [
        [round(z["planned"], 1) for z in zones],
        [round(z["progress"], 1) for z in zones],
    ]
    chart.categoryAxis.categoryNames = _thinned_labels(names, chart.width, font_size=name_size, vertical=True)
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = name_size
    # 90-degree labels, matching the reference report's own per-unit progress
    # charts — vertical labels are what let it fit ~75 buildings on one chart
    # where angled ones would collide (2026-08-30). The value axis keeps the
    # reference's 10% steps at the default size and coarsens or refines as the
    # chart is resized (pdf_axes).
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.boxAnchor = "e"
    percent_axis(chart.valueAxis, chart.height, 7)
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_WIDE, OVERLAP_WIDE)  # "Project Progress Area"
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.bars[0].strokeColor = chart.bars[1].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    chart.barLabels.nudge = 6
    # See _unit_bars: planned is flat, so only actual gets a printed value —
    # and only while the bars are wide enough to hold one.
    fits, chart.barLabels.dx = _value_labels(chart, len(zones), 6, series=2)
    chart.barLabelFormat = [None, "%0.0f%%" if fits else None]
    d.add(chart)
    _top_legend(d, [(cfg["colors"]["chart_planned"], labels["planned"]),
                    (cfg["colors"]["chart_actual"], labels["actual"])], width, height - 6)
    return d


def _unit_bars(cfg, units, width, labels, height=None):
    """Per-unit bars within a zone: grouped planned/actual when a baseline
    exists, else actual-only (most projects carry no per-unit dates yet, so the
    old version drew nothing — now it still shows where each unit stands).

    Both series are drawn whenever a baseline exists, even when every unit sits
    at 100% planned: that is exactly the client's own dashboard chart
    («مقارنة بين نسب الانجاز المخططة والفعلية»), where the flat planned bar beside
    each actual one is what shows the shortfall (2026-09-02)."""
    has_planned = any(u.get("planned") is not None for u in units)
    height = height or 78 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    names, chart.y, name_size = _vertical_names([u["name"] for u in units], height)  # room for 90-degree labels
    chart.x = 24
    chart.width, chart.height = width - 48, height - chart.y - 34  # top strip for the legend
    if has_planned:
        chart.data = [[round(u.get("planned") or 0, 1) for u in units],
                      [round(u["actual"], 1) for u in units]]
    else:
        chart.data = [[round(u["actual"], 1) for u in units]]
    chart.categoryAxis.categoryNames = _thinned_labels(names, chart.width, font_size=name_size, vertical=True)
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = name_size
    # 90-degree labels, matching the reference report's own per-unit progress
    # charts — vertical labels are what let it fit ~75 buildings on one chart
    # where angled ones would collide (2026-08-30). The value axis keeps the
    # reference's 10% steps at the default size and coarsens or refines as the
    # chart is resized (pdf_axes).
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.boxAnchor = "e"
    percent_axis(chart.valueAxis, chart.height, 7)
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_WIDE, OVERLAP_WIDE)  # "Project Progress (Unit)"
    chart.bars[0].strokeColor = None
    if has_planned:
        chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
        chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
        chart.bars[1].strokeColor = None
    else:
        chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    chart.barLabels.nudge = 6
    # Only the ACTUAL bars carry a printed value (reportlab takes one format
    # per series). Planned is a flat 100% across the whole chart, so labelling
    # it stacked "100%" over every bar in one colliding row along the top and
    # told the reader nothing the axis didn't already.
    #
    # Past a certain density no label fits either: a stage with 74 buildings
    # printed "98989898…" as one unreadable smear along the top, and the
    # reference's own chart at that width carries no values at all.
    labelled, chart.barLabels.dx = _value_labels(chart, len(units), 6, series=2 if has_planned else 1)
    fmt = "%0.0f%%" if labelled else None
    chart.barLabelFormat = [None, fmt] if has_planned else [fmt]
    d.add(chart)
    pairs = ([(cfg["colors"]["chart_planned"], labels["planned"])] if has_planned else [])
    pairs = pairs + [(cfg["colors"]["chart_actual"], labels["actual"])]
    _top_legend(d, pairs, width, height - 6)
    return d


# Above this many areas a project-wide bar chart is a wall of hairlines, so the
# summary chart rolls the areas up to their zones instead of plotting them.
AREA_CHART_MAX = 40


def area_progress_chart(cfg, ctx, width, labels, height=None):
    """Planned-vs-actual bars one level below zones, over the WHOLE project.

    This used to plot `areas[:15]` — the first fifteen of 251 buildings, which
    on a real project are all in one zone of one stage. Nothing on the page said
    so, so a summary chart claiming to show the project actually showed 6% of
    it, and always the same 6% (reported 2026-09-03).

    Every area is now covered. Past `AREA_CHART_MAX` a per-building chart is a
    wall of hairlines, so the areas are rolled up to their zones — still the
    whole project, at the granularity the page can actually carry. Below that
    threshold the buildings are plotted individually.
    """
    areas = ctx.get("areas") or []
    if not areas:
        return None
    if len(areas) <= AREA_CHART_MAX:
        return _unit_bars(cfg, areas, width, labels, height)
    zones = [z for z in (ctx.get("zones") or []) if z.get("planned") is not None]
    if not zones:
        return None
    rolled = [{"name": z["name"], "planned": z["planned"], "actual": z["progress"]}
              for z in zones]
    return _unit_bars(cfg, rolled, width, labels, height)


def area_units_chart(cfg, area, width, labels, height=None):
    """The item's sub-units visualised for its dashboard page.

    Prefers an explicit `areas` list when the item carries one. A STAGE's direct
    children are zones, but the reference dashboard's planned-vs-actual chart
    plots one pair per AREA — the buildings a level further down — so
    `_phase_rows` collects those separately and they win here (2026-09-03). A
    zone item has no `areas`, and its own children already ARE the areas, so it
    falls through to them unchanged.

    Always drawn as per-unit bars. The old 15-unit cap fell back to a
    completion histogram, which on a real zone said only "33 buildings are
    75-99% done" — every unit in one bucket, telling the reader nothing about
    which building is behind (the client couldn't read it, 2026-09-03). It
    existed because the axis could only label a handful of bars; now that a
    90-degree label is budgeted by its line height rather than its length
    (see _thinned_labels) a zone's units label and read fine, and the
    histogram has nothing left to solve, so it is gone rather than left as
    dead code."""
    children = area.get("areas") or area.get("children") or []
    if not children:
        return None
    return _unit_bars(cfg, children, width, labels, height)


def _duration_pie_for(cfg, dur, width, labels, height=None):
    """Phase / completed / remaining duration in days — the three slices the
    reference report's own DURATION pie carries (2026-08-30), replacing the
    previous total-vs-delay pair.

    Note the reference plots the phase total alongside the elapsed and
    remaining parts that already sum to it, so the wedges intentionally
    double-count; that is the client's established format, kept here so our
    output reads the same as the report they already issue."""
    if not dur:
        return None
    height = height or 60 * mm
    grey = cfg["colors"].get("muted", "#A5A5A5")
    total = dur.get("total")
    if total is None:
        return None
    # elapsed/remaining come from _duration_for, but a caller can hand over a
    # partial duration dict (only total + delay). Fall back to the older
    # total-vs-delay pair rather than raising on the missing keys.
    if dur.get("elapsed") is None or dur.get("remaining") is None:
        slices = [
            (labels.get("duration_days", "Project duration"), total, cfg["colors"]["chart_planned"]),
            (labels.get("delay_days", "Delay"), dur.get("delay") or 0, cfg["colors"]["chart_actual"]),
        ]
    else:
        # Elapsed vs remaining only. The reference plots the phase TOTAL as a
        # third slice beside the two parts that already sum to it, which makes
        # the total exactly half the disc by construction — every such pie is
        # a 50/50 two-tone circle no matter what the project is doing (worst
        # case here: 1,200 / 1,200 / 0). Same defect as the invoice pie, and
        # matching the reference's own mistake isn't worth a chart that can
        # never convey anything (2026-08-30 critic pass). The total stays
        # available as the caption/legend figure.
        slices = [
            (labels.get("duration_elapsed", "Completed"), dur["elapsed"], cfg["colors"]["chart_actual"]),
            (labels.get("duration_remaining", "Remaining"), dur["remaining"], grey),
        ]
        if not any(v > 0 for _, v, _ in slices):
            return None
    return _reference_pie(cfg, slices, width, height, value_fmt="{:,.0f}")


def item_progress_pie(cfg, item, width, labels, height=None):
    """Planned vs actual vs variance for one stage — the reference dashboard's
    PROGRESS pie (its "PLANNED PROGRESS (Baseline)" / "ACTUAL PROGRESS" /
    "Variance" panel).

    Plotted as achieved-vs-shortfall so the wedges sum to the baseline: the
    variance slice IS the gap the panel exists to show. `None` when the stage
    has no planned figure to compare against, rather than drawing a full circle
    that silently means "nothing known"."""
    if not item:
        return None
    planned, actual = item.get("planned"), item.get("actual")
    if planned is None or actual is None:
        return None
    variance = max(0.0, float(planned) - float(actual))
    slices = [
        (labels.get("actual", "Actual"), round(float(actual), 2), cfg["colors"]["chart_actual"]),
        (labels.get("variance", "Variance"), round(variance, 2), cfg["colors"].get("muted", "#A5A5A5")),
    ]
    return _reference_pie(cfg, slices, width, height or 60 * mm, value_fmt="{:,.2f}%")


def item_earned_pie(cfg, item, width, labels, height=None):
    """Budgeted vs earned vs remaining value for one stage — the reference
    dashboard's "Earned Progress" pie (PLANNED VALUE COST / EARNED VALUE COST /
    REMAINING VALUE COST).

    Straight from P6's own EVM columns, summed over the stage's whole subtree.
    `None` when the schedule carried no cost columns, rather than drawing an
    empty circle."""
    if not item:
        return None
    budget = float(item.get("budgeted_cost") or 0)
    earned = float(item.get("earned_value_cost") or 0)
    if not budget:
        return None
    remaining = max(0.0, budget - earned)
    palette = cfg["colors"].get("chart_palette") or []
    slices = [
        (labels.get("budget_planned_value", "Planned value"), round(budget, 2),
         cfg["colors"]["chart_planned"]),
        (labels.get("budget_earned_value", "Earned value"), round(earned, 2),
         cfg["colors"]["chart_actual"]),
        (labels.get("budget_remaining_value", "Remaining value"), round(remaining, 2),
         palette[2] if len(palette) > 2 else cfg["colors"].get("muted", "#A5A5A5")),
    ]
    return _reference_pie(cfg, slices, width, height or 60 * mm)


def duration_pie(cfg, ctx, width, labels, height=None):
    """Project duration vs delay days (reference duration pie)."""
    return _duration_pie_for(cfg, ctx.get("duration"), width, labels, height)


def zone_duration_pie(cfg, dur, width, labels, height=None):
    """Same pie, for one zone's own duration (the per-area dashboard)."""
    return _duration_pie_for(cfg, dur, width, labels, height)


def invoice_status_chart(cfg, ctx, width, labels, height=None):
    """Invoiced vs remaining, against the project's own contract total —
    the reference dashboard's "Invoice Status" pie (2026-08-30). The
    reference splits this by main/sub contractor; `Invoice` here carries no
    such field, so this is one combined pie over every real invoice rather
    than a fabricated split. `None` when either side of the comparison is
    genuinely absent (no contract total to compare against, or literally no
    invoices yet) rather than drawing a pie against a stand-in value."""
    proj = ctx.get("project") or {}
    total = proj.get("contract_value") or proj.get("budget")
    invoiced = ctx.get("invoices_total")
    if not total or not invoiced:
        return None
    total, invoiced = float(total), float(invoiced)
    remaining = max(0.0, total - invoiced)
    # Invoiced already at or past the contract total leaves nothing to compare
    # against: the pie collapses to a single full-circle slice, which renders
    # as a featureless coloured disc with its value label sitting on top of
    # the legend (found 2026-08-30 in a critic pass — this project's invoices
    # sum well past its contract value). Same rule as budget_total_cost: a
    # one-slice pie carries no information, so draw nothing and let the
    # invoices table beside it tell the story.
    if remaining <= 0:
        return None
    height = height or 60 * mm
    # Two slices, not the reference's three: its Invoice Status pie plots the
    # contract total as a wedge *alongside* the invoiced/remaining wedges that
    # already sum to it, which makes every angle on it meaningless. Styling
    # (popout, on-slice values, legend beneath) matches the reference; the
    # slices stay the two that actually partition the total.
    slices = [
        (labels.get("invoice_invoiced", "Invoiced"), invoiced, cfg["colors"]["chart_actual"]),
        (labels.get("invoice_remaining", "Remaining"), remaining, cfg["colors"]["chart_planned"]),
    ]
    return _reference_pie(cfg, slices, width, height, value_fmt="{:,.0f}")


def boq_financial_progress_chart(cfg, ctx, width, labels, height=None):
    """Budgeted vs earned cost per BOQ phase — the reference dashboard's
    "Financial Progress according to BOQ" grouped bars. Data assembled in
    services._boq_financial_progress.

    Plotted as MONEY, not percentages. This is a budget line, and a reader
    comparing trades wants to know that finishes are 2.4bn against 1.1bn
    earned, not that they are "45% vs 39%" of something they then have to
    multiply back out (the client asked for the amounts, 2026-09-03). The
    percentages are still what services computes and what the value axis
    ordering follows; they're just not what the bars are labelled with.

    `None` (not an empty chart) when the project has no P6 cost import."""
    rows = ctx.get("boq_financial_progress") or []
    if not rows:
        return None
    # Fall back to the percentages for data captured before the money was
    # carried through, so an older saved context still renders something.
    money = all(r.get("budget") is not None for r in rows)
    key_planned, key_actual = ("budget", "earned") if money else ("budget_share", "financial_percent")
    height = height or 78 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    names = [shape(r["name"]) for r in rows]
    # A name at 30 degrees drops half its length below the axis; a fixed 26pt
    # let the longest category run out of the chart's box when it was small.
    widest = max((_text_width(n, 7) for n in names), default=0)
    chart.y = min(max(26, height * 0.35), max(26, widest * 0.5 + 12))
    chart.height = height - chart.y - 34
    chart.data = [
        [r[key_planned] for r in rows],
        [r[key_actual] for r in rows],
    ]
    top = max(max(r[key_planned], r[key_actual]) for r in rows) or 1
    # Money written in full while the chart is wide enough for it, in K/M/B
    # once it isn't; the plot is inset by exactly what those labels need.
    fmt, label_w = number_axis(chart.valueAxis, 0, top, chart.height, 7, width, headroom=1.15)
    if not money:
        chart.valueAxis.labelTextFormat = lambda v: f"{fmt(v)}%"
        label_w += _text_width("%", 7)
    chart.x = max(24, label_w + 8)
    chart.width = width - chart.x - 24
    chart.categoryAxis.categoryNames = _thinned_labels(names, chart.width)
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    cur = (ctx.get("project") or {}).get("currency") or ""
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_WIDE, OVERLAP_WIDE)  # "Financial Progress according to BOQ"
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.bars[0].strokeColor = chart.bars[1].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    # Millions, so a nine-figure budget doesn't print a number wider than its
    # own bar; the axis carries the full scale.
    chart.barLabelFormat = (lambda v: f"{v / 1e6:,.1f}M" if v else "") if money else "%0.0f%%"
    chart.barLabels.nudge = 6
    chart.barLabels.angle = 90 if money else 0
    if money:
        # A label turned upright starts at the bar top and runs up the page.
        # Centred on the top instead, its first digits were drawn inside the
        # bar and read "98.3M" for 198.3M (2026-09-14).
        chart.barLabels.boxAnchor = "w"
    d.add(chart)
    if money and cur:
        # The currency belongs on the axis, said once — every tick and bar
        # label would otherwise repeat "EGP" down the side of the chart. The
        # ticks carry their own scale (full figures, or a K/M/B suffix).
        d.add(String(4, chart.y + chart.height + 4, shape(cur),
                     fontName=FONT_NAME, fontSize=6,
                     fillColor=hexcolor(cfg["colors"].get("muted", "#A5A5A5"))))
    keys = (("budget_planned_value", "Budget"), ("budget_earned_value", "Earned value")) if money         else (("budget_share", "Budget"), ("financial_percent", "Actual"))
    _top_legend(d, [
        (cfg["colors"]["chart_planned"], labels.get(keys[0][0], keys[0][1])),
        (cfg["colors"]["chart_actual"], labels.get(keys[1][0], keys[1][1])),
    ], width, height - 6)
    return d


def _single_series_bars(cfg, bars, width, height, *, value_min, value_max, bar_fmt, percent):
    """One bar per figure, each in its own colour — the shape the dashboard's
    Time Performance and Project Duration panels share. `bars` is
    [(label, value, colour)]; `percent` picks a 0-100% axis over a count one.

    One series with N categories, not N one-value series: reportlab spaces the
    latter as N separate groups (see progress_comparison_chart)."""
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.y = 26
    chart.height = max(10, height - 40)
    chart.x = 30
    if percent:
        percent_axis(chart.valueAxis, chart.height, 7, lo=value_min, hi=value_max)
    else:
        _, label_w = number_axis(chart.valueAxis, value_min, value_max, chart.height, 7, width)
        chart.x = max(chart.x, label_w + 8)
    chart.width = max(10, width - chart.x - 14)
    chart.data = [[value for _, value, _ in bars]]
    chart.categoryAxis.categoryNames = [shape(label) for label, _, _ in bars]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    # Along the bottom of the plot, not on the zero line: a negative delay
    # bar hangs below zero, and its name and value were drawn over it.
    chart.categoryAxis.joinAxisMode = "bottom"
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_CLUSTERED, OVERLAP_CLUSTERED)
    for i, (_, _, colour) in enumerate(bars):
        chart.bars[(0, i)].fillColor = hexcolor(colour)
        chart.bars[(0, i)].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 7
    chart.barLabelFormat = bar_fmt
    chart.barLabels.nudge = 7
    d.add(chart)
    return d


def time_performance_chart(cfg, ctx, width, labels, height=None):
    """Elapsed vs remaining share of the project's duration — the dashboard's
    own Time Performance panel (register F3).

    Plots the fractions the dashboard states when it was imported, and
    otherwise derives the same two from the day counts, so a project with no
    dashboard still gets the chart. `None` when there is no duration at all."""
    from .constants import PERCENT_DECIMALS

    dur = ctx.get("duration") or {}
    elapsed, remaining = dur.get("elapsed_pct"), dur.get("remaining_pct")
    total = dur.get("total")
    if elapsed is None and total and dur.get("elapsed") is not None:
        elapsed = dur["elapsed"] / total
        remaining = (dur.get("remaining") or 0) / total
    if elapsed is None:
        return None
    grey = cfg["colors"].get("muted", "#A5A5A5")
    bars = [
        (labels.get("time_elapsed", "Elapsed duration"), elapsed * 100, cfg["colors"]["chart_actual"]),
        (labels.get("time_remaining", "Remaining duration"), (remaining or 0) * 100, grey),
    ]
    return _single_series_bars(
        cfg, bars, width, height or 60 * mm, value_min=0, value_max=100,
        bar_fmt=f"%0.{PERCENT_DECIMALS}f%%", percent=True)


def project_duration_chart(cfg, ctx, width, labels, height=None):
    """The project's duration beside its delay, in days — the dashboard's
    Project Duration panel (register F3).

    A delay can be negative — the dashboard writes an early finish as -47 —
    so the axis reaches below zero whenever it has to, rather than clipping
    that bar away. `None` when there is no duration at all."""
    dur = ctx.get("duration") or {}
    total = dur.get("total")
    if total is None:
        return None
    delay = dur.get("delay") or 0
    bars = [
        (labels.get("duration_days", "Project duration"), total, cfg["colors"]["chart_planned"]),
        (labels.get("delay_days", "Delay (days)"), delay, cfg["colors"]["chart_actual"]),
    ]
    low, high = min(0, total, delay), max(0, total, delay)
    pad = (high - low) * 0.12 or 1
    return _single_series_bars(
        cfg, bars, width, height or 60 * mm,
        value_min=low - (pad if low < 0 else 0), value_max=high + pad,
        bar_fmt="%d", percent=False)


def progress_comparison_chart(cfg, ctx, width, labels, height=None):
    """Planned % vs. physical actual % vs. financial (earned value) % —
    reference dashboard's "Progress Comparison" bars (2026-08-30). The
    first two are the report's own already-established time-based
    `planned` and physical `overall` figures (shown everywhere else too,
    e.g. the S-curve); the third is new: `ctx["financial_percent_complete"]`
    (services._financial_percent_complete) — the real, non-fabricated,
    cost-weighted % complete, distinct from physical progress (confirmed
    they diverge slightly in this project's own real data: 88.0% physical
    vs ~87.6% financial). Draws 2 bars, not 3, when the project has no P6
    cost import — the same graceful-degradation shape `planned_actual_chart`
    already uses for its own optional series."""
    planned, actual = ctx.get("planned"), ctx.get("overall")
    if planned is None or actual is None:
        return None
    earned = ctx.get("financial_percent_complete")
    height = height or 60 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 24, 26
    chart.width, chart.height = width - 48, height - 46
    series = [("planned", labels.get("planned", "Planned"), round(float(planned), 1), cfg["colors"]["chart_planned"]),
              ("actual", labels.get("actual", "Actual"), round(float(actual), 1), cfg["colors"]["chart_actual"])]
    if earned is not None:
        palette = cfg["colors"].get("chart_palette") or []
        color = palette[2] if len(palette) > 2 else cfg["colors"]["chart_actual"]
        series.append(("earned", labels.get("financial_percent", "Earned Value"), round(float(earned), 1), color))
    # One series, N categories (one bar per category) — NOT N series of one
    # value each, which reportlab would space out as N *grouped* categories
    # instead of N adjacent same-group bars. Per-bar color needs the
    # tuple-indexed override (`bars[(0, i)]`), not `bars[i]` (that indexes
    # series, and there's only one).
    chart.data = [[s[2] for s in series]]
    chart.categoryAxis.categoryNames = [shape(s[1]) for s in series]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    percent_axis(chart.valueAxis, chart.height, 7)
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_CLUSTERED, OVERLAP_CLUSTERED)  # "Progress Comparison"
    for i, s in enumerate(series):
        chart.bars[(0, i)].fillColor = hexcolor(s[3])
        chart.bars[(0, i)].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 7
    chart.barLabelFormat = "%0.1f%%"
    chart.barLabels.nudge = 7
    d.add(chart)
    return d


def progress_tracking_chart(cfg, ctx, width, labels, height=None):
    """Planned vs. actual, previous month vs. current month — reference
    dashboard's "Project Tracking" bars (2026-08-30). Reuses ctx
    ["monthly_tracking"] (services.build_report_context) — `previous.actual`
    is the most recent real ProgressSnapshot strictly before the report's
    as-of date (the same "previous" already used for zone-level tracking
    elsewhere), `current.actual` is today's live figure. A period only
    shows `None` — not a fabricated 0 — when there's genuinely no snapshot
    behind it yet (e.g. a project's very first report); when that happens
    for BOTH periods there's nothing real to draw at all."""
    tracking = ctx.get("monthly_tracking") or {}
    prev, cur = tracking.get("previous") or {}, tracking.get("current") or {}
    if prev.get("actual") is None and cur.get("actual") is None:
        return None
    height = height or 60 * mm
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 24, 26
    # Reserve a real strip for the legend above the plot. At -46 the plot top
    # sat 8pt under the legend baseline, so a 100% bar's own value label
    # collided with the legend text (found 2026-08-30 on the summary page).
    chart.width, chart.height = width - 48, height - 58
    periods = [p for p in (("previous", prev), ("current", cur)) if p[1].get("actual") is not None]
    chart.data = [
        [round(float(p["planned"]), 1) if p.get("planned") is not None else 0.0 for _, p in periods],
        [round(float(p["actual"]), 1) for _, p in periods],
    ]
    names = {"previous": labels.get("tracking_previous", "Previous month"),
             "current": labels.get("tracking_current", "Current month")}
    chart.categoryAxis.categoryNames = [shape(names[key]) for key, _ in periods]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    percent_axis(chart.valueAxis, chart.height, 7)
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_CLUSTERED, OVERLAP_CLUSTERED)  # "Project Tracking"
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.bars[0].strokeColor = chart.bars[1].strokeColor = None
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.nudge = 6
    d.add(chart)
    # Wrapped legend, not reportlab's fixed-pitch Legend: this panel is narrow
    # (~81mm on the summary page) and a fixed deltax overflows or collides.
    _draw_wrapped_legend(d, [(cfg["colors"]["chart_planned"], labels.get("planned", "Planned")),
                             (cfg["colors"]["chart_actual"], labels.get("actual", "Actual"))],
                         chart.x, height - 4, chart.width)
    return d


def budget_total_cost_chart(cfg, ctx, width, labels, height=None):
    """Contract amount vs. approved cost variations ("new items") vs. the
    active Part's own budget — the reference dashboard's "Budget Total
    Cost" pie (2026-08-30). Every slice is a real, already-tracked number
    (`Variation` kind=cost/status=approved for "new items", `PartScope.
    amount` for "for part") — a project with no approved variations and no
    Part budget genuinely renders as a single contract-amount slice rather
    than three fabricated ones; that's an honest reflection of the data,
    not a bug. `None` only when there's no contract total to draw at all."""
    proj = ctx.get("project") or {}
    contract = proj.get("contract_value") or proj.get("budget")
    if not contract:
        return None
    new_items = float(ctx.get("variations_cost_approved_total") or 0)
    for_part = float(proj.get("part_amount") or 0)
    palette = cfg["colors"].get("chart_palette") or [cfg["colors"]["chart_planned"], cfg["colors"]["chart_actual"]]
    slices = [(labels.get("budget_contract", "Contract amount"), float(contract), palette[0])]
    if new_items:
        slices.append((labels.get("budget_new_items", "New items"), new_items, palette[1]))
    if for_part:
        slices.append((labels.get("budget_for_part", "For part"), for_part, palette[2 % len(palette)]))
    # A lone contract-amount slice is a filled circle carrying no information
    # beyond its own caption — the reference has no such panel, so render
    # nothing rather than a decorative disc (2026-08-30).
    if len(slices) < 2:
        return None
    height = height or 60 * mm
    return _reference_pie(cfg, slices, width, height, value_fmt="{:,.0f}")


def overall_donut(cfg, ctx, width, labels, height=None):
    """Planned / actual / variance — the three slices the reference report's
    own PROGRESS pie carries (2026-08-30). Was a two-slice done-vs-remaining
    donut, which matched nothing in the reference; variance is simply
    planned - actual, both already in ctx. Falls back to the two real slices
    when there's no planned baseline to compare against."""
    overall = float(ctx["overall"])
    planned = ctx.get("planned")
    grey = cfg["colors"].get("muted", "#A5A5A5")
    height = height or 56 * mm
    if planned is None:
        slices = [(labels.get("actual", "Actual"), overall, cfg["colors"]["chart_actual"]),
                  (labels.get("not_started", "Remaining"), max(0.0, 100 - overall), grey)]
    else:
        planned = float(planned)
        # Actual + variance, which together ARE the planned figure — not
        # planned plotted beside them as a third slice. That was the same
        # self-defeating shape the duration pie had: the total takes half the
        # disc by construction, so the pie says the same thing whatever the
        # project is doing (here 100 beside 88 + 12). The planned figure is
        # still the one the variance is measured against, and it reads off the
        # legend (2026-08-30 critic pass).
        slices = [
            (labels.get("actual", "Actual"), overall, cfg["colors"]["chart_actual"]),
            (labels.get("variance", "Variance"), max(0.0, planned - overall), grey),
        ]
        # ...but it has to be ON the chart. The comment above said planned
        # "reads off the legend", and the legend held only Actual and Variance,
        # so the baseline the whole pie is measured against appeared nowhere —
        # the planners flagged exactly that (register F2). Stated with its
        # value, since it is not a wedge that carries one of its own.
        from .constants import PERCENT_DECIMALS

        # The figure is pinned left-to-right: bidi otherwise moves a trailing
        # "%" to the front of the number inside Arabic text ("%94.46").
        planned_text = (f"{labels.get('planned', 'Planned')} "
                        f"{_LRM}{planned:.{PERCENT_DECIMALS}f}%{_LRM}")
        return _reference_pie(
            cfg, slices, width, height, value_fmt="{:,.2f}%",
            extra_legend=[(cfg["colors"]["chart_planned"], planned_text)])
    return _reference_pie(cfg, slices, width, height, value_fmt="{:,.2f}%")


def speedometer_chart(value, width, cfg, *, title=None, max_value=100.0, height=None,
                      thresholds=None, value_fmt="{:.0f}%"):
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

    # Band cutoffs are in the same units as `max_value`, so a ratio dial has to
    # bring its own — the completion gauge's 50/70/90 are percentages.
    thresholds = thresholds or cfg.get("gauge_thresholds") or {}
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
    # shape() the whole composed string, not the Arabic title alone with a
    # plain "= N%" tacked on after — concatenating raw text onto an already
    # bidi-reordered string is the same gotcha documented for table cells
    # (pdf_tables.py's _wrap_shape docstring): the reorder has to see the
    # full logical string to place the trailing "=", not just the title.
    reading = value_fmt.format(v)
    value_text = shape(f"{title}= {reading}") if title else reading
    d.add(String(cx, cy - 14, value_text, fontName=_gauge_font(title or ""), fontSize=11,
                 fillColor=hexcolor(cfg["colors"]["text"]), textAnchor="middle"))
    if title:
        d.add(String(cx, cy - 26, shape(title), fontName=_gauge_font(title), fontSize=8,
                     fillColor=hexcolor(cfg["colors"]["muted"]), textAnchor="middle"))
    return d


# How close two end-of-line callouts have to be, in points, before the second
# is stacked above the first (6pt text, "100.00%" wide).
_CALLOUT_MIN_DX = 26
_CALLOUT_MIN_DY = 7


def _finish_scurve(d, chart, series, swatches, cfg, width, height):
    """Axes, line colours, end-of-line callouts and legend — shared by the
    dashboard's own four-series curve and the snapshot-derived one."""
    _date_category_axis(chart.categoryAxis, [p["date"] for p in series], chart.width)
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.boxAnchor = "e"
    # A 0-100 range in the reference's 10% steps at the default size, finer or
    # coarser as the chart is resized.
    percent_axis(chart.valueAxis, chart.height, 6)
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    _grid(chart.valueAxis, cfg)
    for i, (color, _) in enumerate(swatches):
        chart.lines[i].strokeColor = hexcolor(color)
        chart.lines[i].strokeWidth = 2
    d.add(chart)

    # Call out where each line ends, the way the reference's own Progress Curve
    # does ("83.70%", "100.00%"). Reading a final value off a 10%-step axis is
    # guesswork otherwise, and that end figure is the number the report is
    # actually about.
    step = chart.width / max(1, len(series) - 1)
    placed = []                      # (x, y) of every callout already drawn
    for row, (color, _) in enumerate(swatches):
        values = chart.data[row]
        last = next((i for i in range(len(values) - 1, -1, -1) if values[i] is not None), None)
        if last is None:
            continue
        value = values[last]
        x = chart.x + last * step
        y = chart.y + chart.height * (min(100.0, max(0.0, value)) / 100.0)
        # Two lines can end at the same figure — a planned curve and a
        # remaining curve both reach 100% — and their callouts then printed
        # over each other as "100.00%100.00%". Stack a colliding one above
        # its neighbour rather than dropping it: which line each belongs to
        # is still readable from its colour.
        while any(abs(x - px) < _CALLOUT_MIN_DX and abs(y - py) < _CALLOUT_MIN_DY
                  for px, py in placed):
            y += _CALLOUT_MIN_DY
        placed.append((x, y))
        # Nudge in from the right edge so a final-column label isn't clipped.
        anchor = "end" if last >= len(values) - 1 else "start"
        d.add(String(x + (-2 if anchor == "end" else 2), y + 3, "%.2f%%" % value,
                     fontName=_SANS_BOLD, fontSize=6,
                     fillColor=hexcolor(color), textAnchor=anchor))
    _draw_wrapped_legend(d, swatches, chart.x, height - 4, chart.width)
    return d


def scurve_chart(cfg, ctx, width, labels, height=None):
    """Time Performance S-curve: planned vs actual cumulative progress, plus
    the forecast continuation the reference report's own Progress Curve
    carries (2026-08-30) — its actual line stops at today and a differently
    coloured segment runs on from there to 100% at the forecast finish.

    The forecast is drawn as a third series that is `None` everywhere before
    today, so it starts exactly where `actual` stops instead of being a
    separate floating line. It's a straight run-out from today's real actual
    to 100%, which is the only forecast this data supports: the project
    stores forecast/revised *dates*, not a month-by-month projected curve.
    Nothing is drawn when there's no forecast date to aim at."""
    points = ctx.get("scurve", [])
    # The dashboard's own four-series curve, when its workbook supplied one
    # (services.build_report_context). Each series covers a different span —
    # the planned pair stops at the baseline finish, actual at the data date,
    # remaining only runs on from there — so unlike the derived curve below it
    # must keep every month, not just the ones carrying a planned value.
    has_curve = ctx.get("scurve_source") == "imported"
    series = points if has_curve else [p for p in points if p.get("planned") is not None]
    if len(series) < 2:
        return None
    height = height or 72 * mm
    d = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.x, chart.y = 30, 26
    chart.width, chart.height = width - 56, height - 56  # leave a top strip for the legend

    actual = [p.get("actual") for p in series]
    swatches = [(cfg["colors"]["chart_planned"], labels["planned"]),
                (cfg["colors"]["chart_actual"], labels["actual"])]

    if has_curve:
        # Drawn exactly as the source sheet plots it: four cumulative series,
        # each with its own gaps. No run-out is synthesized — the workbook
        # carries its own remaining curve, so inventing one could only
        # contradict it.
        palette = cfg["colors"].get("chart_palette") or []
        late_color = palette[2] if len(palette) > 2 else cfg["colors"].get("gauge_average", "#9BBB59")
        remaining_color = palette[5] if len(palette) > 5 else cfg["colors"].get("gauge_warn", "#F79646")
        # Only the series the sheet actually filled. A workbook can carry any
        # subset — the planned pair stops at the baseline finish, remaining
        # only starts after the data date, and one arrived with nothing but
        # its actual line — and an all-empty row is a legend entry naming a
        # line that was never drawn.
        candidates = [
            ([p.get("planned") for p in series], cfg["colors"]["chart_planned"],
             labels.get("scurve_early_planned", "Cummulative Early Planned %")),
            ([p.get("late_planned") for p in series], late_color,
             labels.get("scurve_late_planned", "Cummulative Late Planned %")),
            (actual, cfg["colors"]["chart_actual"],
             labels.get("scurve_actual", "Cummulative Actual %")),
            ([p.get("forecast") for p in series], remaining_color,
             labels.get("scurve_remaining", "Cummulative Remaining %")),
        ]
        drawn = [(values, color, label) for values, color, label in candidates
                 if any(v is not None for v in values)]
        if not drawn:
            return None
        chart.data = [values for values, _, _ in drawn]
        swatches = [(color, label) for _, color, label in drawn]
        return _finish_scurve(d, chart, series, swatches, cfg, width, height)

    # Split at the report's as-of date, not at the last snapshot: a project
    # can carry snapshots dated past the report period, and drawing those as
    # "actual" would claim progress the report doesn't cover. Everything at
    # or before as-of stays actual; the rest becomes the forecast run-out.
    as_of = ctx.get("as_of")
    cut = None
    if as_of is not None:
        past = [i for i, p in enumerate(series) if p["date"] <= as_of]
        if past and len(past) < len(series):
            cut = past[-1]

    # The schedule's OWN forecast curve, when the source carried one. Only
    # meaningful from the cut onwards — before it, the actual line is the truth.
    stored_forecast = [p.get("forecast") for p in series]
    has_stored_forecast = any(v is not None for v in stored_forecast)

    if cut is None and not has_stored_forecast:
        data = [[p["planned"] for p in series], actual]
    else:
        anchor = actual[cut] if cut is not None else actual[-1]
        data = [[p["planned"] for p in series],
                [v if (cut is None or i <= cut) else None for i, v in enumerate(actual)]]
        forecast = None
        if has_stored_forecast:
            # Real values, joined to the actual line at the cut so the two read
            # as one continuous curve rather than a floating segment.
            forecast = [v if (cut is None or i >= cut) else None
                        for i, v in enumerate(stored_forecast)]
            if cut is not None and forecast[cut] is None:
                forecast[cut] = anchor
        elif anchor is not None and cut is not None and len(series) - 1 > cut:
            # No stored curve: a straight run-out from today's real actual to
            # 100% at the end of the series, which is the only forecast the
            # remaining data supports (the project stores forecast/revised
            # *dates*, not a month-by-month projection).
            forecast = [None] * len(series)
            span = len(series) - 1 - cut
            for i in range(cut, len(series)):
                forecast[i] = anchor + (100.0 - anchor) * ((i - cut) / span)
        if forecast is not None:
            data.append(forecast)
            palette = cfg["colors"].get("chart_palette") or []
            forecast_color = palette[5] if len(palette) > 5 else cfg["colors"].get("gauge_warn", "#F79646")
            swatches.append((forecast_color, labels.get("scurve_forecast", "Forecast")))

    chart.data = data
    return _finish_scurve(d, chart, series, swatches, cfg, width, height)


# Six years of monthly bars still resolve on an A4-width panel; past that the
# axis is unreadable whatever we do, so the oldest months give way.
_CASHFLOW_MAX_MONTHS = 72


def cashflow_chart(cfg, rows, width, labels, height=None):
    """The reference report's Cash flow panel: monthly planned/actual as bars
    AND cumulative planned/actual as lines, sharing one value axis
    (2026-08-30). Previously these were two separate charts on two panels;
    the reference draws all four series together, which is what makes the
    monthly spend readable against the cumulative curve it rolls up into.

    Both sub-charts are given the same explicit valueMin/valueMax/x/width, so
    the lines land on the same scale and gridlines as the bars — reportlab
    has no combo primitive, so a shared scale has to be imposed by hand
    rather than left to each chart's own auto-ranging."""
    # Kept to the MOST RECENT months when a project runs long. Taking the
    # first 36 instead cut a 52-month cash flow off at its 36th month: the
    # airport project's own sheet ran to Oct 2026 and its report stopped at
    # Jun 2025, hiding the whole recent end — the part a monthly report is
    # actually about (2026-09-09). The cumulative figures are absolute, so a
    # tail slice keeps them true.
    rows = rows[-_CASHFLOW_MAX_MONTHS:]
    if not rows:
        return None
    height = height or 80 * mm
    d = Drawing(width, height)
    monthly = [r["planned"] for r in rows] + [r["actual"] for r in rows]
    cumulative = [r.get("cum_planned") or 0 for r in rows] + [r.get("cum_actual") or 0 for r in rows]
    plot_y, plot_h = 28, height - 62

    chart = VerticalBarChart()
    # Headroom so the cumulative line doesn't touch the frame. The axis snaps
    # its top to a whole step, and the plot is inset by exactly what the
    # widest tick label needs — full figures, or K/M/B on a narrow chart.
    _, label_w = number_axis(chart.valueAxis, 0, max(monthly + cumulative + [0]) or 1,
                             plot_h, 6, width, headroom=1.08)
    top = chart.valueAxis.valueMax
    plot_x = label_w + 8
    plot_w = width - plot_x - 12
    chart.x, chart.y = plot_x, plot_y
    chart.width, chart.height = plot_w, plot_h
    chart.data = [[r["planned"] for r in rows], [r["actual"] for r in rows]]
    _date_category_axis(chart.categoryAxis, [r["month"] for r in rows], chart.width)
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.boxAnchor = "e"
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    _grid(chart.valueAxis, cfg)
    _bar_geometry(chart, GAP_WIDE)  # "Cash flow - Tentative Records"
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[1].fillColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.bars[0].strokeColor = chart.bars[1].strokeColor = None
    d.add(chart)

    # Cumulative lines over the same plot rect. Its own axes are hidden — the
    # bar chart already drew them — but the value range must match exactly.
    curve = HorizontalLineChart()
    curve.x, curve.y = plot_x, plot_y
    curve.width, curve.height = plot_w, plot_h
    curve.data = [[r.get("cum_planned") or 0 for r in rows], [r.get("cum_actual") or 0 for r in rows]]
    curve.categoryAxis.categoryNames = [""] * len(rows)
    curve.categoryAxis.visible = 0
    curve.valueAxis.valueMin, curve.valueAxis.valueMax = 0, top
    curve.valueAxis.visible = 0
    curve.valueAxis.visibleGrid = 0
    curve.lines[0].strokeColor = hexcolor(cfg["colors"]["chart_planned"])
    curve.lines[1].strokeColor = hexcolor(cfg["colors"]["chart_actual"])
    curve.lines[0].strokeWidth = curve.lines[1].strokeWidth = 1.6
    d.add(curve)

    # Where each cumulative line ends, called out the way the reference's own
    # Cash flow panel does ("2,434,402,771" / "1,889,559,271"). That final
    # total is the number the panel exists to state, and reading it off a
    # thousands-formatted axis is guesswork (2026-09-02).
    if rows:
        step = plot_w / max(1, len(rows) - 1)
        for row, key in ((0, "cum_planned"), (1, "cum_actual")):
            value = rows[-1].get(key) or 0
            colour = cfg["colors"]["chart_planned" if row == 0 else "chart_actual"]
            y = plot_y + plot_h * (min(top, max(0.0, float(value))) / top if top else 0)
            d.add(String(plot_x + (len(rows) - 1) * step - 2, y + 3, f"{value:,.0f}",
                         fontName=_SANS_BOLD, fontSize=6,
                         fillColor=hexcolor(colour), textAnchor="end"))

    _draw_wrapped_legend(d, [
        (cfg["colors"]["chart_planned"], labels.get("cashflow_planned_monthly", labels["planned"])),
        (cfg["colors"]["chart_actual"], labels.get("cashflow_actual_monthly", labels["actual"])),
        (cfg["colors"]["chart_planned"], labels.get("cashflow_cum_planned", "Cumulative planned")),
        (cfg["colors"]["chart_actual"], labels.get("cashflow_cum_actual", "Cumulative actual")),
    ], plot_x, height - 4, plot_w)
    return d


def cashflow_curve(cfg, rows, width, labels, height=None):
    """Cumulative cash S-curve (planned vs actual added up month over month)."""
    if len(rows) < 2:
        return None
    height = height or 78 * mm
    d = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.y = 26
    chart.height = height - 56
    # Same money-axis sizing and headroom as cashflow_chart above, so the
    # final plateau sits under a labelled tick rather than above the scale.
    _, label_w = number_axis(
        chart.valueAxis, 0, max([r["cum_planned"] for r in rows] + [r["cum_actual"] for r in rows] + [0]) or 1,
        chart.height, 6, width, headroom=1.08)
    chart.x = label_w + 8
    chart.width = width - chart.x - 12
    chart.data = [[r["cum_planned"] for r in rows], [r["cum_actual"] for r in rows]]
    _date_category_axis(chart.categoryAxis, [r["month"] for r in rows], chart.width)
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 6
    # Vertical, like every other date axis: the label budget counts one line
    # height per label, which only holds for text running down the page.
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.boxAnchor = "e"
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    _grid(chart.valueAxis, cfg)
    chart.lines[0].strokeColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.lines[1].strokeColor = hexcolor(cfg["colors"]["chart_actual"])
    chart.lines[0].strokeWidth = chart.lines[1].strokeWidth = 2
    d.add(chart)
    _top_legend(d, [(cfg["colors"]["chart_planned"], labels["planned"]),
                    (cfg["colors"]["chart_actual"], labels["actual"])], width, height - 6)
    return d


_SUBMITTED_TOTAL = "_submitted_total"

# The dashboard grid's own status columns, in its order, named with the
# Submittal.Status display labels so enum_label translates them the same way.
_DASHBOARD_STATUSES = (("approved", "Approved"), ("rejected", "Rejected"), ("pending", "Pending"))


def _submittal_grid_from_rows(rows, labels):
    """(disciplines, status_order, grid) counted from one submittal per row."""
    status_order: list[tuple[str, str]] = []
    seen_status = set()
    disciplines: list[str] = []
    for r in rows:
        if r["status_key"] not in seen_status:
            seen_status.add(r["status_key"])
            status_order.append((r["status_key"], r["status"]))
        if r["discipline"] not in disciplines:
            disciplines.append(r["discipline"])
    grid = {disc: {sk: 0 for sk, _ in status_order} for disc in disciplines}
    for r in rows:
        grid[r["discipline"]][r["status_key"]] += 1

    # The reference dashboard leads with a SUBMITTED bar — the total each
    # discipline has put in — and reads the approved/rejected/pending bars
    # against it. Without that denominator the counts carry no sense of scale,
    # which is exactly what the client couldn't read off this chart
    # (2026-09-02). It is a total, not a status, so it is derived here rather
    # than imported as a fifth bucket that would double-count every row.
    for disc in disciplines:
        grid[disc][_SUBMITTED_TOTAL] = sum(grid[disc][sk] for sk, _ in status_order)
    status_order = [(_SUBMITTED_TOTAL, labels.get("submittals_total", "Submitted"))] + status_order
    return disciplines, status_order, grid


def _submittal_grid_from_counts(lines, labels):
    """(disciplines, status_order, grid) from the dashboard's own grid.

    Its SUBMITTED column is the sheet's own total and is used as it stands,
    not re-derived from the other three: the dashboard is the figure the
    client publishes, and a total that disagrees with its parts is theirs to
    see rather than ours to paper over."""
    disciplines = [line["discipline"] for line in lines]
    status_order = [(_SUBMITTED_TOTAL, labels.get("submittals_total", "Submitted")),
                    *_DASHBOARD_STATUSES]
    grid = {line["discipline"]: {_SUBMITTED_TOTAL: line.get("submitted", 0),
                                 **{key: line.get(key, 0) for key, _ in _DASHBOARD_STATUSES}}
            for line in lines}
    return disciplines, status_order, grid


def submittals_breakdown_chart(cfg, rows, width, labels, height=None, counts=None):
    """Horizontal stacked bar: one row per approval status, each bar split by
    discipline — matches the reference dashboard's MATERIAL SUBMITTALS / SHOP
    DRAWING panels exactly (status-by-discipline counts, not a single total).

    `counts` is the dashboard workbook's own grid for this submittal type,
    when it was imported, and wins outright: the planners asked for these
    charts FROM the dashboard (register F4), and it states counts where the
    app only holds whichever documents someone entered by hand. `rows` is the
    fallback — already filtered to one type by the caller, see resolve_chart's
    "submittals_material"/"submittals_shop_drawing" branches."""
    # Local import: pdf_tables is imported by pdf_canvas, which imports
    # this module — importing it at module level would be circular.
    from .pdf_tables import enum_label

    if counts:
        disciplines, status_order, grid = _submittal_grid_from_counts(counts, labels)
    elif rows:
        disciplines, status_order, grid = _submittal_grid_from_rows(rows, labels)
    else:
        return None
    TOTAL_KEY = _SUBMITTED_TOTAL

    height = height or 60 * mm
    d = Drawing(width, height)
    chart = HorizontalBarChart()
    label_font_size = 7
    # Localize the enum display labels — the same values render Arabic in
    # the submittals TABLE, so leaving the chart English put both in one
    # document (2026-08-30).
    status_names = [shape(label if key == TOTAL_KEY else enum_label(cfg, label))
                    for key, label in status_order]
    # YCategoryAxis labels grow leftward from the axis — reserve real width
    # for the longest one instead of a fixed guess, so "Approved with
    # comments" doesn't clip the way a small fixed margin did.
    label_w = max(pdfmetrics.stringWidth(n, FONT_NAME, label_font_size) for n in status_names) + 6
    legend_w = 32 * mm
    # At a narrow box (e.g. a Summary dashboard panel, ~52mm) `label_w` alone
    # can eat most of the width, leaving no room for a side legend without it
    # overlapping the category labels — found placing this chart in a 52mm
    # Summary panel (2026-08-26): the legend's fixed x position sat directly
    # on top of "Rejected"/"Under Review" instead of beside the bars. Below
    # `min_side_legend_w` there's provably not enough width left for a side
    # legend to read cleanly, so it drops to a wrapped horizontal legend
    # under the chart instead — same data/colors, just repositioned and
    # actually measured (not reportlab's Legend flowable, whose fixed
    # `deltax` column spacing was found to overflow the panel width outright
    # for a 4-discipline legend at 52mm — same investigation).
    min_side_legend_w = 25 * mm
    side_legend = width - label_w - legend_w - 8 >= min_side_legend_w
    palette = cfg["colors"].get("chart_palette") or [cfg["colors"]["chart_planned"], cfg["colors"]["chart_actual"]]
    swatches = [(palette[i % len(palette)], enum_label(cfg, disciplines[i])) for i in range(len(disciplines))]
    legend_rows = 0
    if not side_legend:
        legend_rows = _wrapped_legend_rows(swatches, width, font_size=6)
    legend_h = (legend_rows * 8) if not side_legend else 0
    chart.x, chart.y = label_w, 6 + legend_h
    chart_legend_w = legend_w if side_legend else 0
    chart.width = max(10, width - label_w - chart_legend_w - 8)
    chart.height = height - 12 - legend_h
    chart.data = [[grid[disc][sk] for sk, _ in status_order] for disc in disciplines]
    chart.categoryAxis.categoryNames = status_names
    chart.categoryAxis.style = "stacked"
    _bar_geometry(chart, GAP_STACKED, 100)  # "MATERIAL SUBMITTALS" / "SHOP DRAWING"
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 6
    _grid(chart.valueAxis, cfg)
    for i in range(len(disciplines)):
        chart.bars[i].fillColor = hexcolor(palette[i % len(palette)])
        chart.bars[i].strokeColor = None
    # Blank instead of "0" on an empty segment. A stacked bar draws a label
    # per series whether or not that series has anything in it, so every
    # status with no submittals stacked its zeros on top of each other at the
    # axis origin — two or three "0" glyphs overprinting on the axis spine of
    # the executive summary (2026-08-30).
    #
    # Segments too narrow to hold their own text are left unlabelled too: on a
    # real project the pending bar is a handful against thousands submitted, so
    # its four counts printed on top of each other in a few millimetres and
    # made the whole chart unreadable (2026-09-02). The threshold is a fraction
    # of the widest bar, which is what sets the axis, so it tracks the actual
    # drawn width without needing the geometry.
    widest = max((sum(grid[disc][sk] for disc in disciplines) for sk, _ in status_order),
                 default=0)
    # Count ticks across the bars, spaced by their own label widths so a
    # narrow panel steps in hundreds where a wide one steps in fifties.
    horizontal_number_axis(chart.valueAxis, widest, chart.width, 6)
    min_label = widest * 0.04
    chart.barLabelFormat = lambda v: "%d" % v if v and v >= min_label else ""
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 6
    # In the middle of its own segment. At the default end position each
    # count sat on the join with the next colour, and the last hung past the
    # bar's end.
    chart.barLabels.boxTarget = "mid"
    d.add(chart)
    if side_legend:
        d.add(_legend(swatches, width - legend_w, height - 8, vertical=True))
    else:
        _draw_wrapped_legend(d, swatches, 2, height - 6, width, font_size=6)
    return d


def _wrapped_legend_rows(swatches, max_width, font_size=6, swatch_size=6, gap=3, item_gap=8):
    """How many rows `_draw_wrapped_legend` will need for this width — called
    first to reserve the right amount of chart height before anything is
    drawn (drawing top-down would otherwise need a second pass to fix up
    `chart.height` after the fact)."""
    rows, x = 1, 0.0
    for _, label in swatches:
        w = swatch_size + gap + pdfmetrics.stringWidth(shape(label), FONT_NAME, font_size) + item_gap
        if x + w - item_gap > max_width and x > 0:
            rows += 1
            x = 0
        x += w
    return rows


def _draw_wrapped_legend(d, swatches, x0, y_top, max_width, font_size=6, swatch_size=6, gap=3, item_gap=8, row_h=8):
    """Swatch+label legend that wraps to a new row instead of overflowing
    the panel — reportlab's own `Legend` flowable only supports a fixed
    column pitch (`deltax`), which overflows a narrow chart panel's width
    when there are more than 2-3 items (found 2026-08-26, see
    submittals_breakdown_chart)."""
    x, y = x0, y_top
    for color, label in swatches:
        text = shape(label)
        w = swatch_size + gap + pdfmetrics.stringWidth(text, FONT_NAME, font_size) + item_gap
        if x + w - item_gap > max_width and x > x0:
            x, y = x0, y - row_h
        d.add(Rect(x, y - swatch_size, swatch_size, swatch_size, fillColor=hexcolor(color), strokeColor=None))
        d.add(String(x + swatch_size + gap, y - swatch_size + 1, text, fontName=FONT_NAME, fontSize=font_size))
        x += w


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
    # Too many rows to fit: drop to ZONE level (level 0) rather than taking the
    # first 25 and stopping. Slicing showed one zone plus its buildings and
    # nothing else — 22 of 251 rows, all from Z(A) — presented as if it were
    # the project's schedule, with no marker saying otherwise (2026-08-30).
    # Every zone at level 0 covers the whole project in ~15 readable bars,
    # which is what a schedule summary on one page should be. Only if the
    # zones alone still overflow does it slice, and that is a genuine
    # last resort rather than the normal path.
    MAX_ROWS = 25
    if len(rows) > MAX_ROWS:
        zone_rows = [r for r in rows if r.get("level", 0) == 0]
        rows = zone_rows if zone_rows else rows
    rows = rows[:MAX_ROWS]
    if not rows:
        return None

    # The names take at most a third of the width. A fixed 52mm left a 60mm
    # chart 4mm of timeline (2026-09-14).
    label_w = min(52 * mm, width / 3)
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

    # Gridlines at the finest calendar step — days, weeks, months, quarters,
    # years — whose labels fit side by side across the bar area.
    for tick, text in calendar_ticks(min_d, max_d, chart_w, 6):
        gx = x(tick)
        # The opening label names the period the schedule starts in; a
        # gridline there would pass it off as that period's boundary.
        if tick > min_d:
            d.add(Line(gx, bottom_pad - 4, gx, chart_top,
                       strokeColor=hexcolor(c["table_border"]), strokeWidth=0.3))
        d.add(String(gx + 2, chart_top + 3, text, fontName=FONT_NAME, fontSize=6,
                     fillColor=hexcolor(c["muted"])))

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
        raw_name = (r["name"] if r["level"] == 0 else "    " + r["name"])[:42]
        # Cut to the label column, which narrows with the chart.
        while len(raw_name) > 1 and _text_width(shape(raw_name), 7) > label_w - 4:
            raw_name = raw_name[:-1]
        d.add(String(2, row_top - row_h / 2 - 2, shape(raw_name),
                     fontName=BOLD if r["level"] == 0 else FONT_NAME, fontSize=7,
                     fillColor=hexcolor(c["text"])))

    legend_x = width - 150
    d.add(_legend([(c["chart_planned"], labels["planned"]), (c["chart_actual"], labels["actual"])],
                  legend_x, height - 6, font_size=7))
    if has_slip:
        # To the legend's left on the same row, not stacked below it — a
        # fixed vertical offset collided with the legend's own swatch/text
        # height (varies with font metrics), overlapping "Planned".
        # shape() the dash and the label together, not the label alone with
        # a raw "— " prefixed after — same reasoning as the SPI gauge fix
        # above: bidi needs the whole logical string to place the dash.
        note = shape("— " + labels.get("gantt_revised", "Revised finish"))
        note_w = pdfmetrics.stringWidth(note, FONT_NAME, 7)
        d.add(String(legend_x - note_w - 10, height - 6, note,
                     fontName=FONT_NAME, fontSize=7, fillColor=delay_color))
    return d
