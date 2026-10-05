from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0016_daily_autopilot")]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="sending_schedule",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
