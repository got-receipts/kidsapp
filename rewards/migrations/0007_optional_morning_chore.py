from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0006_quest_verification_penalties")]

    operations = [
        migrations.AddField(
            model_name="chore",
            name="optional",
            field=models.BooleanField(default=False),
        ),
    ]
