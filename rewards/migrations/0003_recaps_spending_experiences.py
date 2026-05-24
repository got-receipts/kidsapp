from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0002_daily_chores_stars_push")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="last_recap_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="last_recap_day",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="wallet",
            name="spending_cents",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="storeitem",
            name="category",
            field=models.CharField(
                choices=[("treat", "Treat"), ("experience", "Adventure"), ("grand", "Grand prize")],
                default="treat",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="ledgerrequest",
            name="spending_delta_cents",
            field=models.IntegerField(default=0),
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
                ],
                max_length=12,
            ),
        ),
    ]
