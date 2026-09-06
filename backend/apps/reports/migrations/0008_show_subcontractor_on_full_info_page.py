"""Switch the sub-contractor row on for the full-page Project Info tables that
already exist.

The row is opt-in per element (see resolve_table): the same "project_info"
source is drawn full-page, as a panel on the Summary page, and as a 56mm strip
on a stage dashboard, and only the full-page one has room for a 27th row on a
project that fills every optional field. New templates get the flag from
layout_seed; these are the ones already saved.

Width is the discriminator because it separates the three cleanly and by a
wide margin — measured across every template and report in this database, the
full-page tables are 178mm and the panels 88-95mm (2026-09-06). Height does
not: the Summary panel is 154mm tall, taller than the threshold any height
rule would need.
"""
from django.db import migrations

# Comfortably between the 95mm panels and the 178mm full-page tables.
FULL_PAGE_MIN_W_MM = 150


def _apply(config) -> bool:
    """Set the flag on every wide project_info table. Returns whether anything
    changed, so an untouched row isn't rewritten."""
    changed = False
    for page in ((config or {}).get("layout") or {}).get("pages") or []:
        for el in page.get("elements") or []:
            props = el.get("props") or {}
            if (el.get("type") == "table" and props.get("source") == "project_info"
                    and float(el.get("w") or 0) >= FULL_PAGE_MIN_W_MM
                    and not props.get("show_subcontractor")):
                props["show_subcontractor"] = True
                el["props"] = props
                changed = True
    return changed


def enable(apps, schema_editor):
    ReportTemplate = apps.get_model("reports", "ReportTemplate")
    Report = apps.get_model("reports", "Report")

    for template in ReportTemplate.objects.all():
        if _apply(template.config):
            template.save(update_fields=["config"])
    for report in Report.objects.all():
        if _apply(report.layout_override):
            report.save(update_fields=["layout_override"])


def disable(apps, schema_editor):
    ReportTemplate = apps.get_model("reports", "ReportTemplate")
    Report = apps.get_model("reports", "Report")

    def _strip(config) -> bool:
        changed = False
        for page in ((config or {}).get("layout") or {}).get("pages") or []:
            for el in page.get("elements") or []:
                if (el.get("props") or {}).pop("show_subcontractor", None) is not None:
                    changed = True
        return changed

    for template in ReportTemplate.objects.all():
        if _strip(template.config):
            template.save(update_fields=["config"])
    for report in Report.objects.all():
        if _strip(report.layout_override):
            report.save(update_fields=["layout_override"])


class Migration(migrations.Migration):
    dependencies = [("reports", "0007_alter_reportimage_kind")]
    operations = [migrations.RunPython(enable, disable)]
