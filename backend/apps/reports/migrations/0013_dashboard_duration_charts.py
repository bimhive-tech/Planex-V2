"""Put the dashboard's Time Performance and Project Duration charts on the
project-progress page of every template and report already saved (register
F3).

The two chart sources arrived with the rest of section F, but a source only
shows in a report once a page carries an element for it — and the planners
could not find them (2026-09-14). They go beside the zone-progress bars, in
the space that page leaves free to their right: the progress page is the SPI
gauge and the duration pie over a half-width zone chart, with the other half
empty. A page that has no such space — one someone rearranged, or set
landscape with the zone chart already full width — is left alone rather than
having charts stacked over its content.
"""
import uuid

from django.db import migrations

_ANCHORS = {"spi", "duration", "zone_progress"}
_NEW = ("time_performance", "project_duration")
_PAGE_W = {"portrait": 210, "landscape": 297}   # A4, mm
_MARGIN = 16
_GAP = 4


def _source(el):
    return (el.get("props") or {}).get("source")


def _place(page, default_orientation) -> bool:
    elements = page.get("elements") or []
    sources = {_source(el) for el in elements}
    if not _ANCHORS <= sources or sources & set(_NEW):
        return False
    zone = next(el for el in elements if _source(el) == "zone_progress")
    x = zone["x"] + zone["w"] + _GAP
    page_w = _PAGE_W.get(page.get("orientation") or default_orientation or "portrait", 210)
    if x + zone["w"] > page_w - _MARGIN + 0.5:
        return False
    h = (zone["h"] - _GAP) / 2
    zone_props = zone.get("props") or {}
    for i, source in enumerate(_NEW):
        elements.append({
            "id": str(uuid.uuid4()), "type": "chart", "z": zone.get("z", 0),
            "x": x, "y": zone["y"] + i * (h + _GAP), "w": zone["w"], "h": h,
            "props": {"source": source, "chart_type": "column",
                      "show_title": zone_props.get("show_title", True),
                      "show_caption": zone_props.get("show_caption", False)},
        })
    page["elements"] = elements
    return True


def _rearrange(layout, default_orientation) -> bool:
    pages = (layout or {}).get("pages")
    if not isinstance(pages, list):
        return False
    return any([_place(page, default_orientation) for page in pages])


def forwards(apps, schema_editor):
    ReportTemplate = apps.get_model("reports", "ReportTemplate")
    Report = apps.get_model("reports", "Report")

    orientation_of = {}
    for template in ReportTemplate.objects.all():
        config = template.config or {}
        orientation = ((config.get("page_design") or {}).get("orientation")
                       or (config.get("page") or {}).get("orientation"))
        orientation_of[template.id] = orientation
        if _rearrange(config.get("layout"), orientation):
            template.config = config
            template.save(update_fields=["config"])

    for report in Report.objects.exclude(layout_override=None):
        override = report.layout_override or {}
        orientation = ((override.get("page_design") or {}).get("orientation")
                       or orientation_of.get(report.template_id))
        if _rearrange(override.get("layout"), orientation):
            report.layout_override = override
            report.save(update_fields=["layout_override"])


class Migration(migrations.Migration):
    dependencies = [("reports", "0012_summary_over_two_pages")]

    # Irreversible on purpose: the charts are ordinary elements once placed,
    # and removing them again would also remove ones a user placed by hand.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
