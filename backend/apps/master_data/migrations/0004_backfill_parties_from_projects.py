"""Seed each company's new stakeholder lists from the names its projects
already carry.

Those three fields have always been free text, so every existing project has a
client/consultant/contractor typed straight onto it. Without this the new
dropdowns would open empty and each of those projects would look like it had
lost its stakeholder the first time someone edited it — the value is still
there, but it wouldn't be in the list to re-pick. Reading the distinct values
back out makes the lists arrive already populated with exactly what the company
has been using, and carries the consultant's/contractor's phone and email over
with the name.
"""
from django.db import migrations


def _rows(Project, company_id, name_field, phone_field=None, email_field=None):
    """Distinct non-blank names for one company, each with the contact details
    from the most recently updated project that used it (a name retyped across
    projects can disagree on phone/email — the newest is the best guess)."""
    fields = [f for f in (name_field, phone_field, email_field) if f]
    seen = {}
    qs = (Project.objects.filter(company_id=company_id)
          .exclude(**{f"{name_field}__exact": ""})
          .order_by("updated_at")
          .values(*fields))
    for row in qs:
        name = (row[name_field] or "").strip()
        if name:
            seen[name] = row      # later (newer) rows win
    return seen


def backfill(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    Project = apps.get_model("projects", "Project")
    Client = apps.get_model("master_data", "Client")
    Consultant = apps.get_model("master_data", "Consultant")
    Contractor = apps.get_model("master_data", "Contractor")

    for company_id in Company.objects.values_list("id", flat=True):
        clients = _rows(Project, company_id, "client_name")
        # contractor_consultant names a consultant too, so it seeds the same
        # list — with no contact details of its own to carry over.
        consultants = _rows(Project, company_id, "consultant_name", "consultant_phone", "consultant_email")
        for name in _rows(Project, company_id, "contractor_consultant"):
            consultants.setdefault(name, {})
        contractors = _rows(Project, company_id, "contractor_name", "contractor_phone", "contractor_email")

        Client.objects.bulk_create(
            [Client(company_id=company_id, name=n, sort_order=i) for i, n in enumerate(sorted(clients))],
            ignore_conflicts=True)
        Consultant.objects.bulk_create(
            [Consultant(company_id=company_id, name=n, sort_order=i,
                        phone=(consultants[n].get("consultant_phone") or ""),
                        email=(consultants[n].get("consultant_email") or ""))
             for i, n in enumerate(sorted(consultants))],
            ignore_conflicts=True)
        Contractor.objects.bulk_create(
            [Contractor(company_id=company_id, name=n, sort_order=i,
                        phone=(contractors[n].get("contractor_phone") or ""),
                        email=(contractors[n].get("contractor_email") or ""))
             for i, n in enumerate(sorted(contractors))],
            ignore_conflicts=True)


def unbackfill(apps, schema_editor):
    """Reversible only in the sense that 0003 drops the tables anyway — the
    rows here are derived, never authored, so there's nothing to preserve."""
    for model in ("Client", "Consultant", "Contractor"):
        apps.get_model("master_data", model).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0003_client_consultant_contractor"),
        ("projects", "0047_progresssnapshot_forecast_progress_and_more"),
    ]
    operations = [migrations.RunPython(backfill, unbackfill)]
