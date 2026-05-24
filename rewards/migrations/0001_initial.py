# Generated for the initial Family Circle database schema.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Profile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("display_name", models.CharField(max_length=40)),
            ("role", models.CharField(choices=[("child", "Child"), ("guardian", "Guardian")], max_length=10)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="StoreItem", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=100)),
            ("description", models.CharField(blank=True, max_length=180)),
            ("token_cost", models.PositiveIntegerField()),
            ("active", models.BooleanField(default=True)),
        ]),
        migrations.CreateModel(name="Wallet", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("tokens", models.PositiveIntegerField(default=0)),
            ("cash_cents", models.PositiveIntegerField(default=0)),
            ("child", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="wallet", to="rewards.profile")),
        ]),
        migrations.CreateModel(name="Chore", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=100)),
            ("instructions", models.CharField(blank=True, max_length=240)),
            ("token_reward", models.PositiveIntegerField(default=0)),
            ("cash_reward_cents", models.PositiveIntegerField(default=0)),
            ("status", models.CharField(choices=[("open", "To do"), ("submitted", "Waiting approval"), ("completed", "Completed")], default="open", max_length=12)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chores", to="rewards.profile")),
        ]),
        migrations.CreateModel(name="Grade", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("subject", models.CharField(max_length=60)),
            ("assignment", models.CharField(max_length=100)),
            ("score", models.DecimalField(decimal_places=2, max_digits=5)),
            ("maximum_score", models.DecimalField(decimal_places=2, default=100, max_digits=5)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grades", to="rewards.profile")),
            ("recorded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="grades_recorded", to="rewards.profile")),
        ]),
        migrations.CreateModel(name="GrowthGoal", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=100)),
            ("encouragement", models.CharField(blank=True, max_length=240)),
            ("token_reward", models.PositiveIntegerField(default=0)),
            ("status", models.CharField(choices=[("active", "Working on it"), ("submitted", "Waiting approval"), ("completed", "Completed")], default="active", max_length=12)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="goals", to="rewards.profile")),
        ]),
        migrations.CreateModel(name="LedgerRequest", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("kind", models.CharField(choices=[("chore", "Chore reward"), ("goal", "Growth goal reward"), ("store", "Store purchase"), ("convert", "Cash to tokens"), ("cash_out", "Cash out"), ("award", "Guardian award")], max_length=12)),
            ("description", models.CharField(max_length=160)),
            ("token_delta", models.IntegerField(default=0)),
            ("cash_delta_cents", models.IntegerField(default=0)),
            ("status", models.CharField(choices=[("pending", "Waiting"), ("approved", "Approved"), ("declined", "Declined")], default="pending", max_length=10)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("reviewed_at", models.DateTimeField(blank=True, null=True)),
            ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ledger_requests", to="rewards.profile")),
            ("chore", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="rewards.chore")),
            ("goal", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="rewards.growthgoal")),
            ("requested_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requests_made", to="rewards.profile")),
            ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requests_reviewed", to="rewards.profile")),
            ("store_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="rewards.storeitem")),
        ], options={"ordering": ["-created_at"]}),
    ]
