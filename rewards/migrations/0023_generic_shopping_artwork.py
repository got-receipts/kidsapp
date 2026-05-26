from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("rewards", "0022_discover_video_library")]

    operations = [
        migrations.RemoveField(model_name="shoppingproduct", name="image_url"),
        migrations.RemoveField(model_name="shoppingorderitem", name="image_url"),
    ]
