# The data date a dashboard import is linked to (register E1).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0057_dashboard_panels"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboardimport",
            name="data_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
