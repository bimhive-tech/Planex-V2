"""Backfill: every project that already has ProjectScope/Activity rows gets
one ScheduleImport batch (its scopes/activities predate this feature, so
there's only ever been one generation of data for them — same invariant the
app already relied on before this migration). Without this, those rows would
sit at schedule_import=NULL forever, which the app's "current batch" queries
(added alongside this feature) treat as "no import happened yet", hiding
real, already-imported data."""
from django.db import migrations


def backfill(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    ProjectScope = apps.get_model("projects", "ProjectScope")
    Activity = apps.get_model("projects", "Activity")
    ScheduleImport = apps.get_model("projects", "ScheduleImport")
    ProgressSnapshot = apps.get_model("projects", "ProgressSnapshot")

    project_ids = ProjectScope.objects.values_list("project_id", flat=True).distinct()
    for project in Project.objects.filter(id__in=project_ids):
        latest_snapshot = ProgressSnapshot.objects.filter(project=project).order_by("-date").first()
        date = latest_snapshot.date if latest_snapshot else project.updated_at.date()
        batch = ScheduleImport.objects.create(
            company=project.company, project=project, date=date, source="",
            activity_count=Activity.objects.filter(project=project).count(),
        )
        ProjectScope.objects.filter(project=project).update(schedule_import=batch)
        Activity.objects.filter(project=project).update(schedule_import=batch)


def noop_reverse(apps, schema_editor):
    pass  # Nothing to undo — reversing would just orphan the batches, not restore the prior (already-lossy) state.


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0044_scheduleimport_activity_schedule_import_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
