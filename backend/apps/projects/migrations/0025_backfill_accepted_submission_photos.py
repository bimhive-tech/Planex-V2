# One-off backfill: carry photos from submissions that were ALREADY accepted
# (before the carry-over feature shipped) into the progress-entry gallery, so
# old evidence photos aren't stranded on the submission card only. New
# acceptances handle this live (see submission_views._record_accepted_entry).
from django.core.files.base import ContentFile
from django.db import migrations


def backfill(apps, schema_editor):
    ProgressSubmission = apps.get_model("projects", "ProgressSubmission")
    ProgressEntry = apps.get_model("projects", "ProgressEntry")
    ProgressImage = apps.get_model("projects", "ProgressImage")

    accepted = (
        ProgressSubmission.objects.filter(status="accepted")
        .prefetch_related("images")
    )
    for sub in accepted:
        imgs = list(sub.images.all())
        if not imgs:
            continue

        # Idempotency guard: skip if this activity already has an entry at the
        # accepted value carrying at least as many photos — that's either the
        # live carry-over (new acceptances) or a prior run of this migration.
        already = (
            ProgressEntry.objects.filter(
                activity_id=sub.activity_id, progress_percent=sub.submitted_progress
            )
            .filter(images__isnull=False)
            .distinct()
        )
        if any(e.images.count() >= len(imgs) for e in already):
            continue

        # Date the entry when the submission was actually accepted, not "today",
        # so it lands correctly in the activity's history.
        when = (sub.decided_at or sub.created_at)
        entry = ProgressEntry.objects.create(
            company_id=sub.company_id, project_id=sub.project_id,
            activity_id=sub.activity_id, date=when.date(),
            progress_percent=sub.submitted_progress, note=sub.note,
            recorded_by_id=sub.submitted_by_id,
        )
        for simg in imgs:
            try:
                data = simg.image.read()
            except Exception:  # noqa: BLE001 — a missing/orphaned file must not break deploy
                continue
            pimg = ProgressImage(
                company_id=sub.company_id, entry=entry,
                caption=simg.caption, uploaded_by_id=simg.uploaded_by_id,
            )
            name = simg.image.name.rsplit("/", 1)[-1]
            pimg.image.save(name, ContentFile(data), save=True)


def noop(apps, schema_editor):
    # Not reversible — we can't know which gallery photos originated here.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0024_submissionimage"),
    ]
    operations = [
        migrations.RunPython(backfill, noop),
    ]
