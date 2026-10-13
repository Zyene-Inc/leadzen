from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0023_chatrun_lane")]
    operations = [migrations.AddField(model_name="outreachjob", name="resolved_at", field=models.DateTimeField(blank=True, null=True))]
