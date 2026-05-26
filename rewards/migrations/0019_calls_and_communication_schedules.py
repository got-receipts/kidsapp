import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q
import rewards.models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0018_family_messages")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chore", "New chore"),
                    ("reward", "Token reward"),
                    ("rule", "Rule update"),
                    ("grounded", "Grounded mode"),
                    ("wallet", "Wallet update"),
                    ("store", "Store purchase"),
                    ("message", "Message"),
                    ("call", "Call"),
                ],
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="CommunicationSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("feature", models.CharField(choices=[("messaging", "Messages only"), ("calling", "Calls only"), ("both", "Messages and calls")], default="both", max_length=12)),
                ("days_of_week", models.CharField(default="0,1,2,3,4,5,6", max_length=20)),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="communication_schedules", to="rewards.profile")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="communication_schedules_created", to="rewards.profile")),
            ],
            options={"ordering": ["child__display_name", "start_time"]},
        ),
        migrations.CreateModel(
            name="FamilyCall",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("call_type", models.CharField(choices=[("audio", "Audio"), ("video", "Video")], max_length=8)),
                ("status", models.CharField(choices=[("ringing", "Ringing"), ("active", "Active"), ("declined", "Declined"), ("ended", "Ended")], default="ringing", max_length=10)),
                ("room_name", models.CharField(default=rewards.models.new_call_room_name, editable=False, max_length=80, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("answered_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("caller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="calls_started", to="rewards.profile")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="calls_received", to="rewards.profile")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="familycall",
            constraint=models.CheckConstraint(
                condition=~Q(caller=F("recipient")),
                name="family_call_recipient_differs_from_caller",
            ),
        ),
    ]
