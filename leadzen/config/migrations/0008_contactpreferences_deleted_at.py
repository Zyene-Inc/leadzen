from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0007_chatrun_deadline_at_chatrun_model_requests")]

    operations = [
        migrations.AddField(
            model_name="contactpreferences",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
