from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("rewards", "0027_video_reactions")]

    operations = [
        migrations.CreateModel(
            name="HiddenMessageContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hidden_message_contacts", to="rewards.profile")),
                ("contact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hidden_for_children", to="rewards.profile")),
                ("hidden_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="message_contacts_hidden", to="rewards.profile")),
            ],
            options={"ordering": ["contact__display_name"]},
        ),
        migrations.AddConstraint(
            model_name="hiddenmessagecontact",
            constraint=models.UniqueConstraint(fields=("child", "contact"), name="one_hidden_message_contact_per_child"),
        ),
    ]