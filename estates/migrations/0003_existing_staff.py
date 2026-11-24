"""Existing admins and guards work for the first estate."""

from django.db import migrations


def assign(apps, schema_editor):
    User = apps.get_model("authentication", "User")
    Estate = apps.get_model("estates", "Estate")
    first = Estate.objects.order_by("id").first()
    if first:
        User.objects.filter(estate__isnull=True, is_superuser=False).update(estate=first)


class Migration(migrations.Migration):
    dependencies = [("estates", "0002_default_estate"), ("authentication", "0004_user_estate")]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
