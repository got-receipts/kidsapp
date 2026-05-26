from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0023_generic_shopping_artwork")]

    operations = [
        migrations.AddField(
            model_name="videoplaylist",
            name="youtube_playlist_id",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
