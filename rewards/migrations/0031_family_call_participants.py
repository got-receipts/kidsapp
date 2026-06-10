import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0030_profile_photos_and_free_calls_anytime")]

    operations = [
        migrations.CreateModel(
            name="FamilyCallParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("invited", "Invited"), ("joined", "Joined"), ("declined", "Declined")], default="invited", max_length=10)),
                ("invited_at", models.DateTimeField(auto_now_add=True)),
                ("joined_at", models.DateTimeField(blank=True, null=True)),
                ("declined_at", models.DateTimeField(blank=True, null=True)),
                ("call", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="rewards.familycall")),
                ("invited_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="call_invites_sent", to="rewards.profile")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="call_participations", to="rewards.profile")),
            ],
            options={"ordering": ["invited_at"]},
        ),
        migrations.AddConstraint(
            model_name="familycallparticipant",
            constraint=models.UniqueConstraint(fields=("call", "profile"), name="one_family_call_participant"),
        ),
    ]
