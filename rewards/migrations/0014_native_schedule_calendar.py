import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rewards", "0013_grounding_notes_teamup"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailyscheduleevent",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dailyscheduleevent",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schedules_approved",
                to="rewards.profile",
            ),
        ),
        migrations.DeleteModel(name="FamilySettings"),
    ]
