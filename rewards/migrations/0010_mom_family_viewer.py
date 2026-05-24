from django.db import migrations, models


def make_mom_viewer(apps, schema_editor):
    Profile = apps.get_model("rewards", "Profile")
    Profile.objects.filter(user__username__iexact="mom").update(role="viewer")


def restore_mom_guardian(apps, schema_editor):
    Profile = apps.get_model("rewards", "Profile")
    Profile.objects.filter(user__username__iexact="mom").update(role="guardian")


class Migration(migrations.Migration):
    dependencies = [("rewards", "0009_child_lockdown_and_family_settings")]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="role",
            field=models.CharField(
                choices=[("child", "Child"), ("guardian", "Guardian"), ("viewer", "Family viewer")],
                max_length=10,
            ),
        ),
        migrations.RunPython(make_mom_viewer, restore_mom_guardian),
    ]
