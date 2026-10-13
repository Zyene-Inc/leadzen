"""Mark Workspace job threads created before they carried an origin marker.

Each Workspace job wrote a recognizable first message; Chat conversations never do.
Only the context marker is added. Nothing is deleted, archived or rewritten.
"""
from django.db import migrations

JOB_KEYS = ("discovery", "candidate_ids", "contact_id", "workspace_action")


def mark(apps, schema_editor):
    Thread = apps.get_model("leadzen_config", "ChatThread")
    Message = apps.get_model("leadzen_config", "ChatMessage")
    alias = schema_editor.connection.alias
    for thread in Thread.objects.using(alias).all().iterator():
        context = thread.context if isinstance(thread.context, dict) else {}
        if context.get("origin"):
            continue
        first = Message.objects.using(alias).filter(thread_id=thread.pk, role="user").order_by("created_at", "pk").first()
        data = first.data if first is not None and isinstance(first.data, dict) else {}
        if thread.title.startswith("Autopilot · ") or any(key in data for key in JOB_KEYS):
            Thread.objects.using(alias).filter(pk=thread.pk).update(context={**context, "origin": "workspace"})


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0021_search_plan")]
    operations = [migrations.RunPython(mark, migrations.RunPython.noop)]
