import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
from django.db.models import Q


def remove_legacy_chore_cash_rewards(apps, schema_editor):
    Chore = apps.get_model("rewards", "Chore")
    LedgerRequest = apps.get_model("rewards", "LedgerRequest")
    Chore.objects.exclude(cash_reward_cents=0).update(cash_reward_cents=0)
    LedgerRequest.objects.filter(kind="chore", status="pending").exclude(cash_delta_cents=0).update(cash_delta_cents=0)


class Migration(migrations.Migration):
    dependencies = [
        ("rewards", "0016_recover_existing_family_logins"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="birth_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="childrule",
            name="consequence",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="childrule",
            name="expires_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="childrule",
            name="scheduled_remove_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="childrule",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="houserule",
            name="consequence",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="houserule",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="storeitem",
            name="token_cost",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="storeitem",
            name="cash_cost_cents",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="storeitem",
            name="hidden",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="storeitem",
            name="inventory_quantity",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="storeitem",
            name="minimum_age",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="storeitem",
            name="requires_approval",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="storeitem",
            name="token_unlock_threshold",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(remove_legacy_chore_cash_rewards, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="chore",
            constraint=models.CheckConstraint(condition=Q(cash_reward_cents=0), name="chore_rewards_tokens_only"),
        ),
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
                ],
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="FamilySettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tokens_per_dollar", models.PositiveIntegerField(default=10)),
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
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("chore", "New chore"),
                            ("reward", "Token reward"),
                            ("rule", "Rule update"),
                            ("grounded", "Grounded mode"),
                            ("wallet", "Wallet update"),
                            ("store", "Store purchase"),
                        ],
                        max_length=12,
                    ),
                ),
                ("title", models.CharField(max_length=80)),
                ("message", models.CharField(max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "recipient",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="rewards.profile"),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Purchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_cost", models.PositiveIntegerField(default=0)),
                ("cash_cost_cents", models.PositiveIntegerField(default=0)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("fulfilled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "child",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="purchases", to="rewards.profile"),
                ),
                (
                    "item",
                    models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchases", to="rewards.storeitem"),
                ),
                (
                    "ledger",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="purchase", to="rewards.ledgerrequest"),
                ),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.CreateModel(
            name="RuleAcknowledgement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("acknowledged_at", models.DateTimeField(auto_now_add=True)),
                (
                    "child",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rule_acknowledgements", to="rewards.profile"),
                ),
                (
                    "child_rule",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acknowledgements",
                        to="rewards.childrule",
                    ),
                ),
                (
                    "house_rule",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acknowledgements",
                        to="rewards.houserule",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="ruleacknowledgement",
            constraint=models.CheckConstraint(
                condition=Q(house_rule__isnull=False, child_rule__isnull=True) | Q(house_rule__isnull=True, child_rule__isnull=False),
                name="acknowledges_one_rule_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="ruleacknowledgement",
            constraint=models.UniqueConstraint(
                condition=Q(house_rule__isnull=False),
                fields=("child", "house_rule"),
                name="one_house_rule_ack_per_child",
            ),
        ),
        migrations.AddConstraint(
            model_name="ruleacknowledgement",
            constraint=models.UniqueConstraint(
                condition=Q(child_rule__isnull=False),
                fields=("child", "child_rule"),
                name="one_child_rule_ack_per_child",
            ),
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=40)),
                ("description", models.CharField(max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_actions", to="rewards.profile"),
                ),
                (
                    "child",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to="rewards.profile"),
                ),
                (
                    "child_rule",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to="rewards.childrule"),
                ),
                (
                    "house_rule",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to="rewards.houserule"),
                ),
                (
                    "ledger",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to="rewards.ledgerrequest"),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
