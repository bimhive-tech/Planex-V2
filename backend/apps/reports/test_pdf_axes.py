"""Chart axes that follow the size a chart is drawn at (register F1).

The Customize canvas and the PDF draw the same reportlab Drawing at the
element's size, so these choices are what BOTH show."""
import datetime

from django.test import SimpleTestCase
from reportlab.graphics.charts.axes import YValueAxis
from reportlab.lib.units import mm

from .constants import default_config
from .pdf_base import ensure_fonts
from .pdf_axes import (calendar_ticks, date_unit_labels, number_axis, number_format,
                       percent_axis, value_step)
from .pdf_canvas import resolve_chart


def _months(n, start=(2022, 3)):
    year, month = start
    return [datetime.date(year + (month - 1 + i) // 12, (month - 1 + i) % 12 + 1, 1) for i in range(n)]


def _ticks(axis, lo, hi):
    step = axis.valueStep
    first = -(-lo // step) * step
    out, v = [], first
    while v <= hi + 1e-9:
        out.append(v)
        v += step
    return out


class ValueStepTests(SimpleTestCase):
    def test_steps_are_nice_numbers(self):
        for length in (40, 90, 150, 300, 700):
            step = value_step(1_000_000, length, 10)
            mantissa = step / 10 ** len(str(int(step))[1:])
            self.assertIn(round(mantissa, 6), (1, 2, 2.5, 5))

    def test_a_shorter_axis_never_gets_a_finer_step(self):
        steps = [value_step(100, length, 11) for length in (40, 80, 120, 200, 400)]
        self.assertEqual(steps, sorted(steps, reverse=True))

    def test_never_finer_than_asked(self):
        self.assertEqual(value_step(100, 10_000, 1, finest=5), 5)


class PercentAxisTests(SimpleTestCase):
    def test_the_default_chart_height_keeps_the_reference_ten_percent_steps(self):
        axis = YValueAxis()
        # The S-curve's plot at its default 72mm.
        self.assertEqual(percent_axis(axis, 72 * mm - 56, 6), 10)
        self.assertEqual((axis.valueMin, axis.valueMax), (0, 100))

    def test_shrinking_coarsens_and_growing_refines(self):
        self.assertGreater(percent_axis(YValueAxis(), 60, 6), 10)
        self.assertEqual(percent_axis(YValueAxis(), 400, 6), 5)

    def test_ticks_stand_clear_of_each_other(self):
        for length in (50, 90, 140, 260):
            axis = YValueAxis()
            step = percent_axis(axis, length, 7)
            self.assertGreaterEqual(length * step / 100, 7 * 1.8 - 1e-9)


class NumberFormatTests(SimpleTestCase):
    def test_money_is_written_in_full_while_it_fits(self):
        fmt = number_format(700_000_000, 100_000_000, 131 * mm, 6)
        self.assertEqual(fmt(700_000_000), "700,000,000")

    def test_a_narrow_chart_still_writes_amounts_in_full(self):
        """Register A2: amounts in full everywhere, even where a K/M/B tick
        would have been shorter."""
        fmt = number_format(2_750_000_000, 250_000_000, 50 * mm, 6)
        self.assertEqual(fmt(2_750_000_000), "2,750,000,000")
        self.assertEqual(fmt(250_000_000), "250,000,000")

    def test_the_axis_leaves_the_data_range_alone(self):
        """Snapping out to whole steps spent a quarter of a small chart on
        empty axis: a -47 day delay drew its axis down to -500."""
        axis = YValueAxis()
        number_axis(axis, -224, 1553, 100, 7, 60 * mm)
        self.assertEqual((axis.valueMin, axis.valueMax), (-224, 1553))
        self.assertTrue(all(v % axis.valueStep == 0 for v in _ticks(axis, -224, 1553)))


class DateLabelTests(SimpleTestCase):
    def test_granularity_follows_the_width(self):
        months = _months(57)
        self.assertEqual(date_unit_labels(months, 700, 6)[0], "month")
        self.assertEqual(date_unit_labels(months, 250, 6)[0], "quarter")
        self.assertEqual(date_unit_labels(months, 90, 6)[0], "year")

    def test_a_monthly_series_is_never_labelled_in_days(self):
        self.assertEqual(date_unit_labels(_months(6), 5000, 6)[0], "month")

    def test_a_daily_series_is_labelled_in_days_when_there_is_room(self):
        days = [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(10)]
        unit, labels = date_unit_labels(days, 500, 6)
        self.assertEqual((unit, labels[0]), ("day", "01 Jan"))

    def test_a_short_first_period_does_not_crowd_the_next(self):
        """March start: Q1 is one month long, and its label printed on top of
        Q2's."""
        unit, labels = date_unit_labels(_months(57), 250, 6)
        self.assertEqual(unit, "quarter")
        shown = [i for i, text in enumerate(labels) if text]
        self.assertEqual(labels[shown[0]], "Q2 22")
        self.assertTrue(all(b - a >= 3 for a, b in zip(shown, shown[1:])))

    def test_every_label_that_is_shown_fits(self):
        months = _months(72)
        for length in (60, 120, 240, 480):
            _, labels = date_unit_labels(months, length, 6)
            shown = [i for i, text in enumerate(labels) if text]
            pitch = length / len(months)
            self.assertTrue(all((b - a) * pitch >= 6 * 1.6 - 1e-9 for a, b in zip(shown, shown[1:])))


class CalendarTickTests(SimpleTestCase):
    def test_a_wide_schedule_header_steps_finer_than_a_narrow_one(self):
        start, end = datetime.date(2023, 7, 10), datetime.date(2026, 12, 1)
        wide = calendar_ticks(start, end, 700, 6)
        narrow = calendar_ticks(start, end, 200, 6)
        self.assertGreater(len(wide), len(narrow))
        self.assertEqual([label for _, label in narrow], ["2024", "2025", "2026"])

    def test_no_tick_is_labelled_before_the_span_starts(self):
        start = datetime.date(2023, 7, 10)
        ticks = calendar_ticks(start, datetime.date(2030, 1, 1), 60, 6)
        self.assertTrue(all(tick >= start for tick, _ in ticks))


class ChartsFollowTheirSizeTests(SimpleTestCase):
    """End to end through resolve_chart, the path both canvas and PDF take."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_fonts()          # label widths are measured in the report font

    def _ctx(self):
        months = _months(40)
        cum = 0
        rows = []
        for i, month in enumerate(months):
            cum += 10_000_000
            rows.append({"month": month, "planned": 10_000_000, "actual": 8_000_000,
                         "cum_planned": cum, "cum_actual": cum * 0.8})
        return {"cashflow": rows, "project": {"currency": "EGP"}}

    def _bars(self, drawing):
        from reportlab.graphics.charts.barcharts import VerticalBarChart

        return next(el for el in drawing.contents if isinstance(el, VerticalBarChart))

    def test_the_cash_flow_axes_change_as_the_chart_is_resized(self):
        cfg = default_config()
        small = self._bars(resolve_chart("cashflow_monthly", "column", cfg, self._ctx(), {}, 60 * mm, 45 * mm))
        large = self._bars(resolve_chart("cashflow_monthly", "column", cfg, self._ctx(), {}, 267 * mm, 150 * mm))
        self.assertGreater(small.valueAxis.valueStep, large.valueAxis.valueStep)
        self.assertEqual(small.valueAxis.labelTextFormat(small.valueAxis.valueStep),
                         f"{small.valueAxis.valueStep:,.0f}")
        self.assertEqual(large.valueAxis.labelTextFormat(large.valueAxis.valueStep),
                         f"{large.valueAxis.valueStep:,.0f}")
        self.assertIn("Mar 22", large.categoryAxis.categoryNames)
        self.assertNotIn("Mar 22", small.categoryAxis.categoryNames)
