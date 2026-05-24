import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0008_family_transfers")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="grounded",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="grounded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="grounded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="grounded_children",
                to="rewards.profile",
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="grounded_reason",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.CreateModel(
            name="FamilySettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("google_calendar_id", models.CharField(blank=True, max_length=255)),
                ("google_calendar_enabled", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="family_settings_updates",
                        to="rewards.profile",
                    ),
                ),
            ],
            options={"verbose_name_plural": "family settings"},
        ),
    ]
