"""Backfill: mark seeded roles as system/locked and ensure every tenant company
has the 'Company Admin' (locked) and 'User' (editable) default roles."""
from django.db import migrations

PLATFORM_ADMIN = "Platform Admin"
COMPANY_ADMIN = "Company Admin"
USER = "User"


def forwards(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    Role = apps.get_model("accounts", "Role")

    # Platform Admin role → system + locked.
    Role.objects.filter(name=PLATFORM_ADMIN, is_platform_role=True).update(
        is_system=True, is_locked=True
    )

    for company in Company.objects.all():
        if company.is_platform_admin:
            continue
        # Existing Company Admin → system + locked.
        Role.objects.filter(company=company, name=COMPANY_ADMIN).update(
            is_system=True, is_locked=True
        )
        # Ensure a default 'User' role exists (editable, not deletable).
        Role.objects.get_or_create(
            company=company,
            name=USER,
            defaults={"permissions": ["view_projects"], "is_system": True, "is_locked": False},
        )


def backwards(apps, schema_editor):
    # No-op: flags simply revert with the schema migration if needed.
    pass


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_role_is_locked_role_is_system")]
    operations = [migrations.RunPython(forwards, backwards)]
