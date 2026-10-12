from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0020_lead_finder_provider")]
    operations = [
        migrations.CreateModel(name="SearchPlan", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("fingerprint", models.CharField(max_length=64, unique=True)),
            ("target", models.TextField(default="")),
            ("spec", models.JSONField(default=dict)),
            ("state", models.JSONField(default=dict)),
            ("active", models.BooleanField(default=False)),
            ("activated_at", models.DateTimeField(blank=True, null=True)),
            ("archived_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
        ]),
    ]
