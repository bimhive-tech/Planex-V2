"""Four stakeholder lists become one roster of parties.

Owner / consultant / contractor / sub-contractor were four tables. They are one
roster of firms wearing different hats, so the role moves to where the pairing
already lives — the Project's own `*_name` string. No Project row is touched:
those fields were never FKs, so every project keeps naming exactly who it named.
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


# Merged in a fixed order so a name held by two lists resolves the same way on
# every replay. Owners come first: they are the list that carried no contact
# details, so a consultant/contractor row of the same name gets to supply them.
_SOURCES = ["Client", "Consultant", "Contractor", "SubContractor"]


def merge_into_parties(apps, schema_editor):
    Party = apps.get_model("master_data", "Party")
    rows = {}  # (company_id, name) -> field dict
    for model_name in _SOURCES:
        Model = apps.get_model("master_data", model_name)
        for old in Model.objects.all().order_by("sort_order", "name"):
            key = (old.company_id, old.name)
            row = rows.get(key)
            if row is None:
                rows[key] = {
                    "company_id": old.company_id, "name": old.name,
                    "phone": getattr(old, "phone", "") or "",
                    "email": getattr(old, "email", "") or "",
                }
                continue
            # Same firm already taken from an earlier list — keep the first
            # contact details we have rather than blanking them, so merging an
            # owner with no phone into a contractor that has one keeps the phone.
            row["phone"] = row["phone"] or (getattr(old, "phone", "") or "")
            row["email"] = row["email"] or (getattr(old, "email", "") or "")

    per_company = {}
    to_create = []
    for (company_id, _), row in rows.items():
        order = per_company.get(company_id, 0)
        per_company[company_id] = order + 1
        to_create.append(Party(id=uuid.uuid4(), sort_order=order, **row))
    Party.objects.bulk_create(to_create, batch_size=500)


def split_back(apps, schema_editor):
    """Reverse into Client only.

    Which of the four lists a party came from is exactly the distinction this
    migration removes, so it cannot be recovered — putting every party back as
    an owner keeps the roster's names rather than inventing a role for each.
    """
    Party = apps.get_model("master_data", "Party")
    Client = apps.get_model("master_data", "Client")
    Client.objects.bulk_create([
        Client(id=uuid.uuid4(), company_id=p.company_id, name=p.name, sort_order=p.sort_order)
        for p in Party.objects.all()
    ], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("master_data", "0005_subcontractor"),
    ]

    operations = [
        migrations.CreateModel(
            name="Party",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=180)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name="parties", to="accounts.company")),
            ],
            options={"ordering": ["sort_order", "name"], "verbose_name_plural": "parties"},
        ),
        migrations.AddConstraint(
            model_name="party",
            constraint=models.UniqueConstraint(fields=("company", "name"),
                                               name="uniq_party_per_company"),
        ),
        migrations.RunPython(merge_into_parties, split_back),
        migrations.DeleteModel(name="Client"),
        migrations.DeleteModel(name="Consultant"),
        migrations.DeleteModel(name="Contractor"),
        migrations.DeleteModel(name="SubContractor"),
    ]
