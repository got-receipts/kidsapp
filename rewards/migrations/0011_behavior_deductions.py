from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0010_mom_family_viewer")]

    operations = [
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
                    ("behavior", "Behavior deduction"),
                    ("gift", "Family transfer"),
                ],
                max_length=12,
            ),
        ),
    ]
