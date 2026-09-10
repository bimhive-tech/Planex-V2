"""Apply the planners' wording decisions to templates and reports already saved.

Four changes were asked for (register items A1-A4). The code defaults handle
every template made from here on; these are the ones already in the database,
where the wording lives as stored label overrides, page names and heading text:

  A1  "Client" becomes "Owner". The Arabic templates already read المالك; it is
      the English label that still said "Owner / Client".
  A2  الموقف التنفيذي becomes تقدم المشروع.
  A3  the summary page header reads just الملخص, not الملخص التنفيذي.
  A4  the ورقة متابعة الإنجاز page goes.

Only these exact strings are touched, so a heading someone has since reworded
in their own words is left alone.
"""
from django.db import migrations

# old -> new, applied to label values, page names and heading text alike.
_RENAMES = {
    "الموقف التنفيذي": "تقدم المشروع",
    "الملخص التنفيذي": "الملخص",
    "Executive Summary": "Summary",
    "Executive Dashboard": "Project Progress",
    "Owner / Client": "Owner",
    "Client": "Owner",
}
_DROP_PAGES = {"ورقة متابعة الإنجاز", "Progress Sheet"}
# The label whose English value is the bare word "Client" — renaming every
# label that happens to equal it would be too broad.
_CLIENT_LABEL = "info_client"


def _rewrite(layout) -> bool:
    """Rename headings and drop the retired page. True when anything changed."""
    pages = (layout or {}).get("pages")
    if not isinstance(pages, list):
        return False

    kept, changed = [], False
    for page in pages:
        if (page.get("name") or "").strip() in _DROP_PAGES:
            changed = True
            continue
        new_name = _RENAMES.get((page.get("name") or "").strip())
        if new_name:
            page["name"] = new_name
            changed = True
        for el in page.get("elements") or []:
            props = el.get("props") or {}
            for key in ("text", "title"):
                new = _RENAMES.get((props.get(key) or "").strip())
                if new:
                    props[key] = new
                    changed = True
        kept.append(page)
    layout["pages"] = kept
    return changed


def _rewrite_labels(config) -> bool:
    labels = (config or {}).get("labels")
    if not isinstance(labels, dict):
        return False
    changed = False
    for key, value in list(labels.items()):
        if not isinstance(value, str):
            continue
        if value.strip() == "Client" and key != _CLIENT_LABEL:
            continue
        new = _RENAMES.get(value.strip())
        if new:
            labels[key] = new
            changed = True
    return changed


def forwards(apps, schema_editor):
    ReportTemplate = apps.get_model("reports", "ReportTemplate")
    Report = apps.get_model("reports", "Report")

    for template in ReportTemplate.objects.all():
        config = template.config or {}
        changed = _rewrite_labels(config)
        changed |= _rewrite(config.get("layout"))
        if changed:
            template.config = config
            template.save(update_fields=["config"])

    for report in Report.objects.exclude(layout_override=None):
        override = report.layout_override or {}
        if _rewrite(override):
            report.layout_override = override
            report.save(update_fields=["layout_override"])


class Migration(migrations.Migration):
    dependencies = [("reports", "0008_show_subcontractor_on_full_info_page")]

    # Irreversible on purpose: reversing would rename headings a user may have
    # edited since, and could not bring back a deleted page's own layout.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
