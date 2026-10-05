from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0014_workspacecontext_chatthread_context_and_more")]
    operations = [migrations.AddField(model_name="chatthread", name="deleted_at", field=models.DateTimeField(null=True, blank=True))]
