from django.db import migrations, models

import rewards.models


class Migration(migrations.Migration):

    dependencies = [
        ("rewards", "0029_family_message_attachments"),
    ]

    operations = [
        migrations.AddField(
            model_name="familysettings",
            name="free_child_calls_anytime_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="profile_photo",
            field=models.FileField(blank=True, upload_to=rewards.models.profile_photo_upload_to),
        ),
    ]
