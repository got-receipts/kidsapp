from django.db import migrations, models
import django.db.models.deletion


def copy_favorites_to_reactions(apps, schema_editor):
    VideoFavorite = apps.get_model("rewards", "VideoFavorite")
    VideoReaction = apps.get_model("rewards", "VideoReaction")
    for favorite in VideoFavorite.objects.select_related("clip", "clip__playlist", "child"):
        VideoReaction.objects.update_or_create(
            child_id=favorite.child_id,
            youtube_id=favorite.clip.youtube_id,
            defaults={
                "clip_id": favorite.clip_id,
                "playlist_id": favorite.clip.playlist_id,
                "video_title": favorite.clip.title,
                "value": "like",
            },
        )


class Migration(migrations.Migration):
    dependencies = [("rewards", "0026_family_settings_free_call_toggle")]

    operations = [
        migrations.CreateModel(
            name="VideoReaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("youtube_id", models.CharField(max_length=11)),
                ("video_title", models.CharField(max_length=120)),
                ("value", models.CharField(choices=[("like", "Like"), ("dislike", "Dislike")], max_length=8)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="video_reactions", to="rewards.profile")),
                ("clip", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reactions", to="rewards.videoclip")),
                ("playlist", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reactions", to="rewards.videoplaylist")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddConstraint(
            model_name="videoreaction",
            constraint=models.UniqueConstraint(fields=("child", "youtube_id"), name="one_video_reaction_per_child_video"),
        ),
        migrations.RunPython(copy_favorites_to_reactions, migrations.RunPython.noop),
    ]