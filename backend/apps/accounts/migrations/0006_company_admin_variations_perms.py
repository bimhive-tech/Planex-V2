# Data fix: grant the two new Variations permissions to every existing locked
# "Company Admin" role. Same root cause as 0005 — the role's permission list is
# only set at creation time, so keys added later never reach existing companies.
# Appends (rather than replacing) so any custom locked-role state is preserved.
from django.db import migrations

NEW_PERMISSIONS = ["view_variations", "manage_variations"]


def add_perms(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for role in Role.objects.filter(is_locked=True, name="Company Admin"):
        perms = list(role.permissions or [])
        changed = False
        for p in NEW_PERMISSIONS:
            if p not in perms:
                perms.append(p)
                changed = True
        if changed:
            role.permissions = perms
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_resync_company_admin_permissions"),
    ]

    operations = [
        migrations.RunPython(add_perms, migrations.RunPython.noop),
    ]
