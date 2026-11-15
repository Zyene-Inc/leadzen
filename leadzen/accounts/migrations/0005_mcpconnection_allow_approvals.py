from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_accounts", "0004_accountprofile_tour_state")]

    operations = [
        migrations.AddField(
            model_name="mcpconnection",
            name="allow_approvals",
            field=models.BooleanField(default=False),
        ),
    ]
