"""Let independent Workspace jobs run alongside each other, one per lane."""
from django.db import migrations, models

PROVIDER_KEYS = ("discovery", "candidate_ids", "contact_id")


def assign(apps, schema_editor):
    Run = apps.get_model("leadzen_config", "ChatRun")
    Message = apps.get_model("leadzen_config", "ChatMessage")
    alias = schema_editor.connection.alias
    for run in Run.objects.using(alias).select_related("thread").iterator():
        first = Message.objects.using(alias).filter(thread_id=run.thread_id, role="user").order_by("created_at", "pk").first()
        data = first.data if first is not None and isinstance(first.data, dict) else {}
        if run.thread.title.startswith("Autopilot · ") or any(key in data for key in PROVIDER_KEYS):
            lane = "provider"
        elif data.get("workspace_action") == "check_replies":
            lane = "inbox"
        else:
            continue
        Run.objects.using(alias).filter(pk=run.pk).update(lane=lane)


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0022_mark_workspace_job_threads")]
    operations = [
        migrations.RemoveConstraint(model_name="chatrun", name="one_active_chat_per_actor"),
        migrations.AddField(model_name="chatrun", name="lane", field=models.CharField(default="chat", max_length=16)),
        migrations.RunPython(assign, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="chatrun", constraint=models.UniqueConstraint(
            condition=models.Q(status__in=["queued", "running", "awaiting_approval", "paused"]),
            fields=("actor_id", "lane"), name="one_active_run_per_lane")),
    ]
