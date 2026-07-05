# Data fix: the locked "Company Admin" role is seeded via get_or_create(...,
# defaults=...), so it only ever received the current permission list AT
# CREATION TIME. Every permission key added since (view_schedule, finances,
# areas_of_concern, submittals, ...) never made it onto existing companies'
# Company Admin role — so a real (non-platform) company admin was silently
# missing those permissions. This resyncs every locked Company Admin role to
# the full set, current as of this migration. The list is hardcoded (not
# imported from apps.accounts.constants) so this migration keeps working even
# if that module changes shape later.
from django.db import migrations

COMPANY_ADMIN_PERMISSIONS = [
    "manage_company", "manage_users", "manage_roles", "manage_departments",
    "manage_projects", "view_projects", "view_schedule", "submit_progress",
    "review_progress", "approve_progress", "delete_progress_images", "export_reports",
    "view_finances", "manage_finances",
    "view_areas_of_concern", "manage_areas_of_concern",
    "view_submittals", "manage_submittals",
]


def resync(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(is_locked=True, name="Company Admin").update(permissions=COMPANY_ADMIN_PERMISSIONS)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_backfill_default_roles"),
    ]

    operations = [
        migrations.RunPython(resync, migrations.RunPython.noop),
    ]
