from django.db import migrations


PLAYLISTS = [
    ("Family Discover Mix 1", "PLcpk5TCg3vzfFoNIsmxY92jQjTZN7Vlw3"),
    ("Family Discover Mix 2", "PLasCX3wfxLR12dNqE3QqYSY4AXyV8qRD8"),
    ("Family Discover Mix 3", "PLEPQby6_o7m34KVQslk3BJV-nWgBhD-mk"),
]


def add_family_playlists(apps, schema_editor):
    VideoPlaylist = apps.get_model("rewards", "VideoPlaylist")
    for title, youtube_playlist_id in PLAYLISTS:
        VideoPlaylist.objects.get_or_create(
            youtube_playlist_id=youtube_playlist_id,
            defaults={
                "title": title,
                "description": "Parent-approved YouTube playlist.",
                "active": True,
            },
        )


def remove_family_playlists(apps, schema_editor):
    VideoPlaylist = apps.get_model("rewards", "VideoPlaylist")
    VideoPlaylist.objects.filter(youtube_playlist_id__in=[item[1] for item in PLAYLISTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("rewards", "0024_video_playlist_source")]

    operations = [
        migrations.DeleteModel(name="VideoPlaylistAssignment"),
        migrations.RunPython(add_family_playlists, remove_family_playlists),
    ]
