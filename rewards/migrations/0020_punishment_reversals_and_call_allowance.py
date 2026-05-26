import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0019_calls_and_communication_schedules")]

    operations = [
        migrations.AlterField(
            model_name="ledgerrequest",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chore", "Chore reward"),
                    ("goal", "Growth goal reward"),
                    ("store", "Store purchase"),
                    ("spend", "Spend money"),
                    ("convert", "Legacy conversion (disabled)"),
                    ("cash_out", "Cash out"),
                    ("award", "Guardian award"),
                    ("star", "Good behavior star"),
                    ("transfer", "Move to spending"),
                    ("balance", "Balance correction"),
                    ("penalty", "Quest not verified"),
                    ("behavior", "Behavior deduction"),
                    ("gift", "Family transfer"),
                    ("call", "Family call"),
                    ("reversal", "Punishment removed"),
                ],
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="ledgerrequest",
            name="reversal_of",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reversal",
                to="rewards.ledgerrequest",
            ),
        ),
        migrations.AddField(
            model_name="familycall",
            name="allowance_day",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="familycall",
            name="token_cost",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="familycall",
            name="access_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
