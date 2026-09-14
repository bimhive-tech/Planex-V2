"""One duration chart on the project-progress page, drawn as the dashboard's
own "DURATION (Working Days)" pie (register A6, 2026-09-14).

The page carried two charts from the same three dashboard cells: a two-wedge
completed/remaining pie ("duration") and a duration-and-delay bar chart
("project_duration"). The planners asked for the first to go and the second
to become the dashboard's pie. The pie goes in the space the removed chart
held — it was drawn for a pie — and keeps its own settings.

Only a page holding both is changed; a page with just one of them is
somebody's own layout and is left alone.
"""
from django.db import migrations


def _source(el):
    return (el.get("props") or {}).get("source")


def _merge(page) -> bool:
    elements = page.get("elements") or []
    old = next((el for el in elements if el.get("type") == "chart" and _source(el) == "duration"), None)
    new = next((el for el in elements if el.get("type") == "chart" and _source(el) == "project_duration"), None)
    if old is None or new is None:
        return False
    for key in ("x", "y", "w", "h", "z", "rotation"):
        if key in old:
            new[key] = old[key]
    new["props"] = {**(new.get("props") or {}), "chart_type": "pie"}
    page["elements"] = [el for el in elements if el is not old]
    return True


def _rearrange(layout) -> bool:
    pages = (layout or {}).get("pages")
    if not isinstance(pages, list):
        return False
    return any([_merge(page) for page in pages])


def forwards(apps, schema_editor):
    ReportTemplate = apps.get_model("reports", "ReportTemplate")
    Report = apps.get_model("reports", "Report")

    for template in ReportTemplate.objects.all():
        config = template.config or {}
        if _rearrange(config.get("layout")):
            template.config = config
            template.save(update_fields=["config"])

    for report in Report.objects.exclude(layout_override=None):
        override = report.layout_override or {}
        if _rearrange(override.get("layout")):
            report.layout_override = override
            report.save(update_fields=["layout_override"])


class Migration(migrations.Migration):
    dependencies = [("reports", "0013_dashboard_duration_charts")]

    # Irreversible on purpose: the removed chart's settings aren't kept, and
    # the pie may have been restyled since.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
