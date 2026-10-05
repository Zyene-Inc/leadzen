from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0008_contactpreferences_deleted_at")]
    operations = [migrations.CreateModel(
        name="OnboardingState",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("draft", models.JSONField(default=dict)),
            ("completed_steps", models.JSONField(default=list)),
            ("checks", models.JSONField(default=dict)),
            ("testing_until", models.DateTimeField(blank=True, null=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ],
    )]
