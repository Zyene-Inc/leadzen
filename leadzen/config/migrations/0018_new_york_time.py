from django.db import migrations, models


def use_new_york(apps, schema_editor):
    alias = schema_editor.connection.alias
    config_model = apps.get_model("leadzen_config", "SiteConfig")
    for config in config_model.objects.using(alias).all():
        if isinstance(config.sending_schedule, dict) and config.sending_schedule:
            config.sending_schedule = {**config.sending_schedule, "timezone": "America/New_York"}
            config.save(using=alias, update_fields=["sending_schedule"])
    state_model = apps.get_model("leadzen_config", "OnboardingState")
    for state in state_model.objects.using(alias).all():
        saved = state.draft.get("sending_schedule") if isinstance(state.draft, dict) else None
        if isinstance(saved, dict):
            state.draft = {**state.draft, "sending_schedule": {**saved, "timezone": "America/New_York"}}
            state.save(using=alias, update_fields=["draft"])
    apps.get_model("leadzen_config", "EmailCampaign").objects.using(alias).update(delay_timezone="America/New_York")
    # Policy scopes are immutable authorization evidence. The fixed business-clock
    # fingerprint and send guards hold old approvals until the employee reapproves.
    # Absolute due/send timestamps are retained; no message is replayed here.


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0017_siteconfig_sending_schedule")]
    operations = [
        migrations.AlterField(model_name="emailcampaign", name="delay_timezone",
            field=models.CharField(max_length=64, default="America/New_York")),
        migrations.RunPython(use_new_york, migrations.RunPython.noop),
    ]
