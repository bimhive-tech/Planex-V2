"""Tie milestones imported before Milestone.schedule_import existed to the
batch that actually created them.

0050 added the FK but only new writes set it, so every milestone already in
the database read as "added by hand" — permanently exempt from the batch
filter the report now applies, and left behind by "Delete import". An airport
project kept listing 264 of another job's handover dates that way.

An import writes its rows inside one short transaction bracketed by the
ScheduleImport's own created_at/updated_at, so a milestone created inside that
window came from that batch. Anything outside every window really was added by
hand and is left null.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    Milestone = apps.get_model("projects", "Milestone")
    ScheduleImport = apps.get_model("projects", "ScheduleImport")

    windows = {}
    for si in ScheduleImport.objects.all().values("id", "project_id", "created_at", "updated_at"):
        windows.setdefault(si["project_id"], []).append(si)

    updated = []
    for ms in Milestone.objects.filter(schedule_import__isnull=True).only(
            "id", "project_id", "created_at"):
        for si in windows.get(ms.project_id, ()):
            if si["created_at"] <= ms.created_at <= si["updated_at"]:
                ms.schedule_import_id = si["id"]
                updated.append(ms)
                break
    if updated:
        Milestone.objects.bulk_update(updated, ["schedule_import"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("projects", "0050_milestone_schedule_import")]

    # Irreversible on purpose: reversing would have to null out FKs that new
    # imports set legitimately, which is worse than leaving them.
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
