import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [("rewards", "0017_reward_workflow_rules_wallet_store_notifications")]

    operations = [
        migrations.CreateModel(
            name="FamilyMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(max_length=1000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "recipient",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="received_family_messages", to="rewards.profile"),
                ),
                (
                    "sender",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sent_family_messages", to="rewards.profile"),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["recipient", "read_at"], name="message_unread_idx"),
                    models.Index(fields=["sender", "recipient", "created_at"], name="message_thread_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="familymessage",
            constraint=models.CheckConstraint(
                condition=~Q(sender=F("recipient")),
                name="family_message_recipient_differs_from_sender",
            ),
        ),
    ]
