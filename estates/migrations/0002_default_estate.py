"""Existing data belongs to the first estate (rename it on the Estate settings page)."""

import os

from django.core.management.color import no_style
from django.db import migrations


def create_default(apps, schema_editor):
    Estate = apps.get_model("estates", "Estate")
    if not Estate.objects.exists():
        Estate.objects.create(
            id=1,
            name=os.environ.get("DEFAULT_ESTATE_NAME", "My Estate"),
            slug=os.environ.get("DEFAULT_ESTATE_SLUG", "main"),
        )
        # The id was set by hand; move PostgreSQL's sequence past it.
        connection = schema_editor.connection
        for sql in connection.ops.sequence_reset_sql(no_style(), [Estate]):
            schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("estates", "0001_initial")]
    operations = [migrations.RunPython(create_default, migrations.RunPython.noop)]
