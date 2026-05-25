from django.contrib.auth.hashers import make_password
from django.db import migrations


RECOVERY_PASSWORD = "password123"


def recover_existing_family_logins(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("rewards", "Profile")
    Wallet = apps.get_model("rewards", "Wallet")
    accounts = [
        ("kj", "KJ", "child"),
        ("astoria", "Astoria", "child"),
        ("saphira", "Saphira", "child"),
        ("dad", "Dad", "guardian"),
        ("mom", "Mom", "viewer"),
        ("gg", "GG", "guardian"),
    ]

    # Only repair databases that already contain seeded family accounts.
    # A new database is left to seed_family so deployment environment passwords apply.
    if not User.objects.filter(username__in=[username for username, _, _ in accounts]).exists():
        return

    for username, display_name, role in accounts:
        user, _ = User.objects.get_or_create(username=username)
        user.password = make_password(RECOVERY_PASSWORD)
        user.save(update_fields=["password"])
        profile, _ = Profile.objects.update_or_create(
            user=user,
            defaults={"display_name": display_name, "role": role},
        )
        if role == "child":
            Wallet.objects.get_or_create(child=profile)


class Migration(migrations.Migration):
    dependencies = [
        ("rewards", "0015_schedule_reminder_dispatch"),
    ]

    operations = [
        migrations.RunPython(recover_existing_family_logins, migrations.RunPython.noop),
    ]
