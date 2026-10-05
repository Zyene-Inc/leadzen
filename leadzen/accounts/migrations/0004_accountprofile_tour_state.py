from django.db import migrations, models


def preserve_completed_tours(apps, schema_editor):
    profile = apps.get_model("leadzen_accounts", "AccountProfile")
    profile.objects.using(schema_editor.connection.alias).filter(tour_completed_at__isnull=False).update(
        tour_started_at=models.F("tour_completed_at"),
    )


class Migration(migrations.Migration):
    dependencies = [("leadzen_accounts", "0003_mcp_oauth")]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="tour_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="tour_current_step",
            field=models.CharField(default="welcome", max_length=64),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="tour_skipped_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(preserve_completed_tours, migrations.RunPython.noop),
    ]
