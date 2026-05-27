from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0025_family_discover_playlists")]

    operations = [
        migrations.AddField(
            model_name="familysettings",
            name="free_calls_after_6pm_enabled",
            field=models.BooleanField(default=True),
        ),
    ]