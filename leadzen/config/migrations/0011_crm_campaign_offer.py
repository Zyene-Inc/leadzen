from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0010_discovery_progress")]
    operations = [
        migrations.AddField("outreachjob", "request_id", models.UUIDField(null=True, blank=True, unique=True)),
        migrations.AddField("outreachjob", "campaign_approval", models.JSONField(default=dict)),
        migrations.AddField("emailcampaign", "target", models.CharField(max_length=2000, blank=True, default="")),
        migrations.AddField("emailcampaign", "product", models.CharField(max_length=2000, blank=True, default="")),
        migrations.AddField("emailcampaign", "booking_link", models.URLField(max_length=500, blank=True, default="")),
        migrations.AddField("emailcampaign", "signature", models.TextField(blank=True, default="")),
        migrations.AddField("emailcampaign", "delay_basis", models.CharField(max_length=24, default="calendar_days")),
        migrations.AddField("emailcampaign", "delay_timezone", models.CharField(max_length=64, default="UTC")),
        migrations.AddField("discoverylookup", "email_status", models.CharField(max_length=32, blank=True, default="")),
    ]
