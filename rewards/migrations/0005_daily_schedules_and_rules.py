import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0004_savings_goals")]

    operations = [
        migrations.CreateModel(
            name="HouseRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100)),
                ("details", models.CharField(blank=True, max_length=240)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="house_rules_created",
                        to="rewards.profile",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="DailyScheduleEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField()),
                ("start_time", models.TimeField(blank=True, null=True)),
                ("title", models.CharField(max_length=100)),
                ("details", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "child",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="schedule_events", to="rewards.profile"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="events_created",
                        to="rewards.profile",
                    ),
                ),
            ],
            options={"ordering": ["day", "start_time", "created_at"]},
        ),
        migrations.CreateModel(
            name="ChildRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100)),
                ("details", models.CharField(blank=True, max_length=240)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "child",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="specific_rules", to="rewards.profile"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="child_rules_created",
                        to="rewards.profile",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
