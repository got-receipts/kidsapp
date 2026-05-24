import django.db.models.deletion
from django.db import migrations, models


def reset_replaced_calendar_configuration(apps, schema_editor):
    FamilySettings = apps.get_model("rewards", "FamilySettings")
    FamilySettings.objects.update(teamup_calendar_url="", teamup_calendar_enabled=False)


class Migration(migrations.Migration):
    dependencies = [
        ("rewards", "0012_ledgerrequest_spend_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="grounded_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RenameField(
            model_name="familysettings",
            old_name="google_calendar_id",
            new_name="teamup_calendar_url",
        ),
        migrations.RenameField(
            model_name="familysettings",
            old_name="google_calendar_enabled",
            new_name="teamup_calendar_enabled",
        ),
        migrations.AlterField(
            model_name="familysettings",
            name="teamup_calendar_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.RunPython(reset_replaced_calendar_configuration, migrations.RunPython.noop),
        migrations.CreateModel(
            name="BehaviorNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=80)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("negative", models.BooleanField(default=True)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                ("scheduled_lift_at", models.DateTimeField(blank=True, null=True)),
                (
                    "child",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="behavior_notes", to="rewards.profile"),
                ),
                (
                    "issued_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="behavior_notes_issued", to="rewards.profile"),
                ),
            ],
            options={"ordering": ["-issued_at"]},
        ),
    ]
