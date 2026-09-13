"""A project's shared currency is set once at creation and never shown again.

The project form fills `currency` from the company default when the project is
created and offers no input for it afterwards, while every currency a user can
actually see and change is a per-field one (budget, contract value, ...). So the
moment someone prices a project in EGP that was created when the default was
AED, the two disagree permanently — and every amount carrying no currency of its
own (cash flow, invoices, the Part amount, a chart's axis unit) prints the wrong
code. The Cairo airport project reads AED over EGP figures today.

Going forward the figure is derived rather than stored (see
Project.display_currency). This brings the stored column into line so the API,
the project form and the report all say the same thing.

Deliberately one-way: the value being replaced is the stale one, and restoring
it would only recreate the disagreement.
"""
from django.db import migrations

# Same order and reasoning as Project._CURRENCY_SOURCES.
SOURCES = (
    ("budget", "budget_currency"),
    ("contract_value", "contract_value_currency"),
    ("approved_value", "approved_value_currency"),
    ("forecast_cost", "forecast_cost_currency"),
    ("advance_payment", "advance_payment_currency"),
)


# Only a project still on this has never had a currency chosen for it.
DEFAULT_CURRENCY = "AED"


def follow_the_money(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    for project in Project.objects.all().iterator():
        # A chosen currency stands. Two live projects are priced in Egyptian
        # pounds through this field alone, with every per-field picker left at
        # the default -- exactly the reverse of the Cairo case, and overwriting
        # them from the money would swap one wrong label for another.
        if project.currency and project.currency != DEFAULT_CURRENCY:
            continue
        for amount_field, code_field in SOURCES:
            if getattr(project, amount_field) is None:
                continue
            code = getattr(project, code_field)
            if code and code != project.currency:
                project.currency = code
                project.save(update_fields=["currency"])
            break


class Migration(migrations.Migration):

    dependencies = [("projects", "0052_alter_projectscope_scope_type")]

    operations = [migrations.RunPython(follow_the_money, migrations.RunPython.noop)]
