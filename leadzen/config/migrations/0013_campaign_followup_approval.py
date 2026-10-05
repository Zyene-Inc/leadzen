from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0012_email_review")]
    operations = [migrations.AddField(
        model_name="emailcampaign", name="followup_approval",
        field=models.JSONField(default=dict),
    )]
