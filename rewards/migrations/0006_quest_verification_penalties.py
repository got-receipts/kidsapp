from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0005_daily_schedules_and_rules")]

    operations = [
        migrations.AlterField(
            model_name="wallet",
            name="tokens",
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="chore",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "To do"),
                    ("in_progress", "Working on it"),
                    ("submitted", "Waiting approval"),
                    ("completed", "Completed"),
                    ("late", "Completed after deadline"),
                    ("not_verified", "Not verified - points lost"),
                ],
                default="open",
                max_length=12,
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
                ],
                max_length=12,
            ),
        ),
    ]
