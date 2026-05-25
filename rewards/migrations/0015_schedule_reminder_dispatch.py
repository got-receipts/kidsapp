from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rewards", "0014_native_schedule_calendar"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduleReminderDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField(unique=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("recipient_count", models.PositiveIntegerField(default=0)),
            ],
        ),
    ]
