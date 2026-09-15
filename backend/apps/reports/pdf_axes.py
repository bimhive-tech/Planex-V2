"""Chart axis scales that follow the size a chart is drawn at (register F1).

A chart on the report canvas can be dragged to any size, and the Customize
preview draws it through the very same reportlab code the PDF uses. So every
choice here is made from the space the axis actually has, and both the canvas
and the PDF land on the same answer:

  value axes  the finest 1-2-2.5-5 tick step whose labels stand clear of each
              other; amounts are always written in full
  date axes   the finest calendar unit — day, month, quarter, year — whose
              labels fit, so a long cash flow reads in years on a small chart
              and month by month on a large one

Fixed steps (a 10% axis everywhere) and fixed "%b %y" labels were right at one
size only: shrink the chart and the ticks overprinted; grow it and a six-year
series still carried only year-sparse month labels.
"""
import contextvars
import datetime
import math

from reportlab.pdfbase import pdfmetrics

from .pdf_base import FONT_NAME

# One chart element's own value-axis range, {"min", "max", "step"} with any of
# them absent, set by pdf_charts.chart_options around the build (register D2).
# Every value-axis helper below ends by applying it, so a builder never needs
# to know the author moved its axis.
AXIS_OVERRIDE = contextvars.ContextVar("axis_override", default=None)

# More ticks than this is a typo (a step of 1 on a 0-1,000,000 axis), not a
# choice; such a step is ignored rather than drawing a solid bar of labels.
_MAX_TICKS = 200


def _overridden(lo, hi, step):
    """(lo, hi, step) with the current element's own axis choices applied —
    each one only where it leaves a usable axis."""
    o = AXIS_OVERRIDE.get() or {}
    new_lo = o["min"] if o.get("min") is not None else lo
    new_hi = o["max"] if o.get("max") is not None else hi
    if new_hi <= new_lo:
        new_lo, new_hi = lo, hi
    new_step = o.get("step") or step
    if new_step <= 0 or (new_hi - new_lo) / new_step > _MAX_TICKS:
        new_step = step
    return new_lo, new_hi, new_step

# Value-axis tick labels are horizontal text stacked along a vertical axis;
# this many font sizes between ticks leaves a clear gap between neighbours.
# At the report's default chart sizes it lands on the reference dashboard's
# own 10% steps, so nothing changes until a chart is actually resized.
VALUE_TICK_PITCH = 1.8

# Rotated date labels sit side by side along the category axis, each as wide
# as one line of text.
DATE_LABEL_PITCH = 1.6

# Gap between horizontal tick labels along a horizontal axis, in font sizes —
# wide enough that neighbouring counts read as separate numbers, not a row.
_LABEL_GAP = 3

_NICE_MULTIPLIERS = (1, 2, 2.5, 5)


def text_width(text, font_size):
    """`stringWidth` in the report font, or an estimate when the font isn't
    registered (chart builders run in tests without `ensure_fonts()`)."""
    try:
        return pdfmetrics.stringWidth(text, FONT_NAME, font_size)
    except KeyError:
        return len(text) * font_size * 0.5


def _nice_steps_from(raw):
    """Nice steps (1, 2, 2.5, 5 x 10^n) at or above `raw`, ascending."""
    magnitude = 10 ** math.floor(math.log10(raw))
    while True:
        for m in _NICE_MULTIPLIERS:
            step = m * magnitude
            if step >= raw * (1 - 1e-9):
                yield step
        magnitude *= 10


def value_step(span, length, extent, finest=None):
    """The finest nice step over `span` whose ticks sit at least `extent`
    points apart along an axis `length` points long, never finer than
    `finest`."""
    if span <= 0 or length <= 0:
        return finest or 1
    ticks = max(1, int(length // max(extent, 1e-6)))
    raw = max(span / ticks, finest or 0)
    return next(_nice_steps_from(raw))


def percent_axis(axis, length, font_size, lo=0, hi=100, finest=5):
    """A 0-100% value axis with a tick step that suits `length`."""
    step = value_step(hi - lo, length, font_size * VALUE_TICK_PITCH, finest)
    lo, hi, step = _overridden(lo, hi, step)
    axis.valueMin, axis.valueMax, axis.valueStep = lo, hi, step
    places = _decimals_for(step)
    axis.labelTextFormat = f"%.{places}f%%" if places else "%d%%"
    return step


def _decimals_for(step):
    """Decimal places that write every multiple of `step` exactly."""
    for places in range(3):
        if abs(step * 10 ** places - round(step * 10 ** places)) < 1e-6:
            return places
    return 3


def number_format(top, step, chart_width, font_size):
    """Tick-label formatter for a count or money axis reaching `top`: every
    tick written in full ("2,750,000,000"), with just enough decimals to write
    every multiple of the step exactly.

    Axes used to shorten to K/M/B once the full figure crowded a small chart.
    The planners want amounts in full everywhere a report prints one
    (register A2, 2026-09-14), so a small chart spends the width instead.
    `top`, `chart_width` and `font_size` stay in the signature for callers
    that size the plot from the result."""
    return lambda v: f"{v:,.{_decimals_for(step)}f}"


def number_axis(axis, lo, hi, length, font_size, chart_width, *, headroom=1.0):
    """A count/money value axis from `lo` up to `hi` (times `headroom`).

    The ends stay where the data puts them rather than snapping out to whole
    steps: at a small size a step is a quarter of the range, and snapping
    spent that on empty axis — a -47 day delay drew its axis down to -500.
    reportlab still ticks only at whole multiples of the step. Returns
    (formatter, widest tick label width) so the caller can inset the plot by
    exactly what its labels need."""
    hi = hi * headroom
    if hi <= lo:
        hi = lo + 1
    step = value_step(hi - lo, length, font_size * VALUE_TICK_PITCH)
    lo, hi, step = _overridden(lo, hi, step)
    first, last = math.ceil(lo / step - 1e-9) * step, math.floor(hi / step + 1e-9) * step
    fmt = number_format(max(abs(first), abs(last)), step, chart_width, font_size)
    axis.valueMin, axis.valueMax, axis.valueStep = lo, hi, step
    axis.labelTextFormat = fmt
    widest = max(text_width(fmt(first), font_size), text_width(fmt(last), font_size))
    return fmt, widest


def horizontal_number_axis(axis, hi, length, font_size, *, lo=0):
    """A count axis running ACROSS the chart, where each tick label needs its
    own text width along the axis rather than a line height."""
    span = max(hi - lo, 1)
    for step in _nice_steps_from(span / max(1, length // font_size)):
        top = math.ceil(hi / step) * step if hi > lo else lo + step
        fmt = lambda v, p=_decimals_for(step): f"{v:,.{p}f}"  # noqa: E731
        pitch = text_width(fmt(top), font_size) + font_size * _LABEL_GAP
        # A single step spanning everything is as coarse as an axis gets; take
        # it even if its one label is wider than the axis.
        if (top - lo) / step * pitch <= length or step >= span:
            lo, top, step = _overridden(lo, top, step)
            axis.valueMin, axis.valueMax, axis.valueStep = lo, top, step
            axis.labelTextFormat = lambda v, p=_decimals_for(step): f"{v:,.{p}f}"
            return step


# Calendar units, finest first: (bucket key, label) for a date.
_DATE_UNITS = (
    ("day", lambda d: d, lambda d: d.strftime("%d %b")),
    ("month", lambda d: (d.year, d.month), lambda d: d.strftime("%b %y")),
    ("quarter", lambda d: (d.year, (d.month - 1) // 3),
     lambda d: f"Q{(d.month - 1) // 3 + 1} {d.strftime('%y')}"),
    ("year", lambda d: d.year, lambda d: d.strftime("%Y")),
)


def _as_date(value):
    return value.date() if isinstance(value, datetime.datetime) else value


def date_unit_labels(dates, length, font_size):
    """(unit, labels) for a category axis with one point per date.

    Starts from the coarsest unit that still tells every point apart — a
    monthly series labels months, never "01 Jan" days — and coarsens until the
    labels fit `length`. A point is labelled where a new day/month/quarter/
    year begins, and labels are kept at least a label's width apart: a series
    starting in March has a one-month first quarter, and its "Q1 22" printed
    on top of the "Q2 22" beside it."""
    dates = [_as_date(d) for d in dates]
    if not dates:
        return None, []
    budget = max(1, int(length // (font_size * DATE_LABEL_PITCH)))
    min_gap = -(-len(dates) // budget)          # points per label that fits

    start = 0
    for i, (_, key, _) in enumerate(_DATE_UNITS):
        if len({key(d) for d in dates}) == len(dates):
            start = i

    for name, key, label in _DATE_UNITS[start:]:
        firsts, seen = [], set()
        for i, d in enumerate(dates):
            bucket = key(d)
            if bucket not in seen:
                seen.add(bucket)
                firsts.append(i)
        # A period cut short at the start of the series gives way to the
        # full one after it, rather than crowding it.
        if len(firsts) > 1 and firsts[1] - firsts[0] < min_gap:
            firsts = firsts[1:]
        fits = all(b - a >= min_gap for a, b in zip(firsts, firsts[1:]))
        if fits or name == "year":
            keep, last = set(), None
            for i in firsts:
                if last is None or i - last >= min_gap:
                    keep.add(i)
                    last = i
            return name, [label(d) if i in keep else "" for i, d in enumerate(dates)]


# Gantt header steps, finest first: (days, months, label) — exactly one of
# days/months is set.
_CALENDAR_STEPS = (
    (1, 0, "%d %b"), (7, 0, "%d %b"), (14, 0, "%d %b"),
    (0, 1, "%b %y"), (0, 2, "%b %y"), (0, 3, "quarter"), (0, 6, "%b %y"),
    (0, 12, "%Y"), (0, 24, "%Y"), (0, 60, "%Y"), (0, 120, "%Y"),
)


def _add_months(d, months):
    y = d.year + (d.month - 1 + months) // 12
    return d.replace(year=y, month=(d.month - 1 + months) % 12 + 1, day=1)


def _calendar_label(d, fmt):
    return f"Q{(d.month - 1) // 3 + 1} {d.strftime('%y')}" if fmt == "quarter" else d.strftime(fmt)


def _calendar_ticks_for(start, end, days, months, fmt):
    if days:
        cur = start
        step = datetime.timedelta(days=days)
    else:
        # Month steps start on a boundary of the step — quarters on Jan/Apr/
        # Jul/Oct, years on January — so the labels read as calendar periods.
        cur = start.replace(day=1)
        cur = _add_months(cur, -((cur.month - 1) % months)) if months < 12 else cur.replace(month=1)
        if months >= 12:
            cur = cur.replace(year=cur.year - cur.year % (months // 12))
    ticks = []
    while cur <= end:
        # A period that began before the span is not labelled at the span's
        # start: "2020" written over a schedule starting in 2023 is wrong.
        if cur >= start:
            ticks.append((cur, _calendar_label(cur, fmt)))
        cur = cur + step if days else _add_months(cur, months)
    return ticks


def calendar_ticks(start, end, length, font_size):
    """[(date, label)] gridlines across a time span drawn `length` points
    wide, at the finest calendar step whose horizontal labels fit side by
    side."""
    start, end = _as_date(start), _as_date(end)
    span_days = max(1, (end - start).days)
    for days, months, fmt in _CALENDAR_STEPS:
        step_days = days or months * 30.44
        count = span_days / step_days + 1
        pitch = text_width(_calendar_label(end, fmt), font_size) + font_size * _LABEL_GAP
        if count * pitch <= length:
            break
    ticks = _calendar_ticks_for(start, end, days, months, fmt)
    # The period the span opens in is named at its start when there is room
    # before the first boundary: a schedule starting in July 2023 on a
    # yearly header otherwise showed no 2023 at all.
    lead = ((ticks[0][0] - start).days if ticks else span_days) / span_days * length
    if lead >= pitch:
        ticks.insert(0, (start, _calendar_label(start, fmt)))
    return ticks
