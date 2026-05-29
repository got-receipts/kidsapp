from django.db import migrations, models

import rewards.models


class Migration(migrations.Migration):

    dependencies = [
        ("rewards", "0028_hidden_message_contacts"),
    ]

    operations = [
        migrations.AddField(
            model_name="familymessage",
            name="attachment",
            field=models.FileField(blank=True, upload_to=rewards.models.family_message_attachment_upload_to),
        ),
        migrations.AddField(
            model_name="familymessage",
            name="attachment_kind",
            field=models.CharField(blank=True, choices=[("photo", "Photo"), ("gif", "GIF"), ("video", "Video"), ("audio", "Audio")], max_length=10),
        ),
        migrations.AddField(
            model_name="familymessage",
            name="gif_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="familymessage",
            name="attachment_mime",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="familymessage",
            name="attachment_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="familymessage",
            name="body",
            field=models.TextField(blank=True, max_length=1000),
        ),
    ]