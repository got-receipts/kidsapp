import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rewards", "0021_shopping_catalog_and_fulfillment")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chore", "New chore"),
                    ("reward", "Token reward"),
                    ("rule", "Rule update"),
                    ("grounded", "Grounded mode"),
                    ("wallet", "Wallet update"),
                    ("store", "Store purchase"),
                    ("message", "Message"),
                    ("call", "Call"),
                    ("shopping", "Shopping order"),
                    ("discover", "Discover"),
                ],
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="VideoPlaylist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100)),
                ("description", models.CharField(blank=True, max_length=240)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="video_playlists_created",
                        to="rewards.profile",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DiscoverSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("days_of_week", models.CharField(default="0,1,2,3,4,5,6", max_length=20)),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="discover_schedules",
                        to="rewards.profile",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="discover_schedules_created",
                        to="rewards.profile",
                    ),
                ),
            ],
            options={"ordering": ["child__display_name", "start_time"]},
        ),
        migrations.CreateModel(
            name="VideoClip",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("youtube_id", models.CharField(max_length=11)),
                ("title", models.CharField(max_length=120)),
                ("subject_tag", models.CharField(blank=True, max_length=40)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "added_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="video_clips_added",
                        to="rewards.profile",
                    ),
                ),
                (
                    "playlist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clips",
                        to="rewards.videoplaylist",
                    ),
                ),
            ],
            options={"ordering": ["position", "created_at"]},
        ),
        migrations.CreateModel(
            name="VideoPlaylistAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True)),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assigned_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="video_playlist_assignments_created",
                        to="rewards.profile",
                    ),
                ),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="video_playlist_assignments",
                        to="rewards.profile",
                    ),
                ),
                (
                    "playlist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="rewards.videoplaylist",
                    ),
                ),
            ],
            options={"ordering": ["playlist__title"]},
        ),
        migrations.CreateModel(
            name="VideoFavorite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="video_favorites",
                        to="rewards.profile",
                    ),
                ),
                (
                    "clip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorites",
                        to="rewards.videoclip",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="VideoWatchEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_watched_at", models.DateTimeField(auto_now_add=True)),
                ("last_watched_at", models.DateTimeField(auto_now=True)),
                ("view_count", models.PositiveIntegerField(default=1)),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="video_watch_events",
                        to="rewards.profile",
                    ),
                ),
                (
                    "clip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watch_events",
                        to="rewards.videoclip",
                    ),
                ),
            ],
            options={"ordering": ["-last_watched_at"]},
        ),
        migrations.AddConstraint(
            model_name="videoclip",
            constraint=models.UniqueConstraint(fields=("playlist", "youtube_id"), name="one_youtube_video_per_playlist"),
        ),
        migrations.AddConstraint(
            model_name="videoplaylistassignment",
            constraint=models.UniqueConstraint(fields=("playlist", "child"), name="one_video_playlist_assignment_per_child"),
        ),
        migrations.AddConstraint(
            model_name="videofavorite",
            constraint=models.UniqueConstraint(fields=("child", "clip"), name="one_video_favorite_per_child"),
        ),
        migrations.AddConstraint(
            model_name="videowatchevent",
            constraint=models.UniqueConstraint(fields=("child", "clip"), name="one_video_watch_summary_per_child"),
        ),
    ]
