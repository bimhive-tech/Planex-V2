# Backfills the currency/project-type/priority lists every EXISTING company
# gets, mirroring apps.master_data.services.seed_default_master_data. Written
# out literally against the historical model (not by importing services.py)
# per Django's data-migration convention: this must keep working unchanged
# even if the real service function's logic changes later.
from django.db import migrations

_PROJECT_TYPES = ["commercial", "residential", "infrastructure", "industrial"]
_PRIORITIES = ["low", "medium", "high"]
_CURRENCIES = [
    ("AED", "UAE Dirham", "", True),
    ("USD", "US Dollar", "$", False),
    ("SAR", "Saudi Riyal", "", False),
    ("EGP", "Egyptian Pound", "", False),
]


def seed_forwards(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    ProjectType = apps.get_model("master_data", "ProjectType")
    ProjectPriority = apps.get_model("master_data", "ProjectPriority")
    Currency = apps.get_model("master_data", "Currency")

    for company in Company.objects.all():
        for i, name in enumerate(_PROJECT_TYPES):
            ProjectType.objects.get_or_create(company=company, name=name, defaults={"sort_order": i})
        for i, name in enumerate(_PRIORITIES):
            ProjectPriority.objects.get_or_create(company=company, name=name, defaults={"sort_order": i})
        for i, (code, name, symbol, is_default) in enumerate(_CURRENCIES):
            Currency.objects.get_or_create(
                company=company, code=code,
                defaults={"name": name, "symbol": symbol, "is_default": is_default, "sort_order": i},
            )


def seed_backwards(apps, schema_editor):
    # No-op: reversing would delete rows a company may have already edited.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("master_data", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_forwards, seed_backwards),
    ]
