import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0007_optional_morning_chore")]

    operations = [
        migrations.AddField(
            model_name="ledgerrequest",
            name="counterparty",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transfers_with",
                to="rewards.profile",
            ),
        ),
        migrations.AlterField(
            model_name="ledgerrequest",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chore", "Chore reward"),
                    ("goal", "Growth goal reward"),
                    ("store", "Store purchase"),
                    ("convert", "Cash to tokens"),
                    ("cash_out", "Cash out"),
                    ("award", "Guardian award"),
                    ("star", "Good behavior star"),
                    ("transfer", "Move to spending"),
                    ("balance", "Balance correction"),
                    ("penalty", "Quest not verified"),
                    ("gift", "Family transfer"),
                ],
                max_length=12,
            ),
        ),
    ]
