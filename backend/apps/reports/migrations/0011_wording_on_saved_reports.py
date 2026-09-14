"""Apply the planners' wording (register A1-A4) to reports' own saved layouts.

0009 made these changes to templates and meant to make them to every report
with a customised layout too, but looked for that layout's pages at the top of
`layout_override`. A report keeps them one level down, under "layout" (see
constants.merge_layout_override), so 0009 found nothing and every customised
report still opened on الملخص التنفيذي, الموقف التنفيذي and the retired
ورقة متابعة الإنجاز page (found 2026-09-14 rendering the airport report).

The rewrite itself is 0009's, imported rather than copied, so the two can't
drift apart.
"""
import importlib

from django.db import migrations

_wording = importlib.import_module("apps.reports.migrations.0009_owner_wording_and_summary_pages")


def forwards(apps, schema_editor):
    Report = apps.get_model("reports", "Report")
    for report in Report.objects.exclude(layout_override=None):
        override = report.layout_override or {}
        if _wording._rewrite(override.get("layout")):
            report.layout_override = override
            report.save(update_fields=["layout_override"])


class Migration(migrations.Migration):
    dependencies = [("reports", "0010_report_pins_a_schedule_import")]

    # Irreversible for 0009's reason: a heading may have been edited since.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
