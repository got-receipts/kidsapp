import datetime

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="chore",
            name="assigned_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="chores_assigned", to="rewards.profile"),
        ),
        migrations.AddField(
            model_name="chore",
            name="credit_deadline",
            field=models.TimeField(default=datetime.time(19, 0)),
        ),
        migrations.AddField(
            model_name="chore",
            name="due_date",
            field=models.DateField(blank=True, null=True),
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
                ],
                default="open",
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="BehaviorStar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField()),
                ("note", models.CharField(blank=True, max_length=180)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("awarded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stars_awarded", to="rewards.profile")),
                ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="behavior_stars", to="rewards.profile")),
            ],
            options={"ordering": ["-day"]},
        ),
        migrations.AddConstraint(
            model_name="behaviorstar",
            constraint=models.UniqueConstraint(fields=("child", "day"), name="one_behavior_star_per_child_day"),
        ),
        migrations.AddConstraint(
            model_name="chore",
            constraint=models.UniqueConstraint(fields=("child", "title", "due_date"), name="one_daily_chore_assignment"),
        ),
        migrations.AddField(
            model_name="ledgerrequest",
            name="behavior_star",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="rewards.behaviorstar"),
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
                ],
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.TextField()),
                ("auth", models.TextField()),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("guardian", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_subscriptions", to="rewards.profile")),
            ],
        ),
        migrations.CreateModel(
            name="ReminderDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField(unique=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("recipient_count", models.PositiveIntegerField(default=0)),
            ],
        ),
    ]
