"""Bar charts for the report (reportlab.graphics), styled after the reference's
planned/actual charts. Built only from data we have (actual progress per zone)."""
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm

from .pdf_base import FONT_NAME, hexcolor, shape


def zone_progress_chart(cfg, ctx, width):
    """Vertical bars of actual progress per zone, with value labels."""
    zones = ctx["zones"][:12]  # keep it legible
    if not zones:
        return None
    height = 70 * mm
    d = Drawing(width, height)

    chart = VerticalBarChart()
    chart.x = 22
    chart.y = 26
    chart.width = width - 44
    chart.height = height - 50
    chart.data = [[round(z["progress"], 1) for z in zones]]
    chart.categoryAxis.categoryNames = [shape(z["name"]) for z in zones]
    chart.categoryAxis.labels.fontName = FONT_NAME
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.categoryAxis.labels.dy = -2
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 20
    chart.valueAxis.labels.fontName = FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    chart.barWidth = 8
    chart.groupSpacing = 6
    chart.bars[0].fillColor = hexcolor(cfg["colors"]["chart_planned"])
    chart.bars[0].strokeColor = None

    # Value labels above each bar.
    chart.barLabels.fontName = FONT_NAME
    chart.barLabels.fontSize = 7
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.nudge = 7
    chart.barLabels.fillColor = hexcolor(cfg["colors"]["text"])

    d.add(chart)
    return d
