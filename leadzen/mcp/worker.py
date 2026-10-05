"""Execute one employee-reviewed MCP action; never run a model planner loop."""
import os
import sys
from datetime import timedelta


def _matches_action(row, action):
    from leadzen.mcp.tools import normalized, _canonical_tool, ENTRIES
    from leadzen.chat.tools import engine_find_args
    from leadzen.config.models import DiscoverySession
    from leadzen.discovery_progress import counts, selected_identity
    direct = row.thread.context["mcpAction"]
    source_args = normalized(direct["name"], {**direct["arguments"], "requestId": str(row.request_id)})
    source_args.pop("requestId")
    expected_tool, expected_args = _canonical_tool(direct["name"], source_args)
    if not (ENTRIES[direct["name"]][3] or (direct["name"] == "update_draft" and source_args.get("instructions"))):
        return False
    extra = {"recipient_ids"} if expected_tool == "send_campaign" else set()
    if (action["tool"] == expected_tool and set(action["arguments"]) - set(expected_args) == extra
            and all(action["arguments"].get(key) == value for key, value in expected_args.items())):
        return True
    # The existing portal Resume control creates a single-action engine payload
    # for the remainder of a saved discovery session. It cannot widen the goal,
    # select another audience, buy additional emails, or refresh the consent.
    if direct["name"] not in {"find_leads", "find_work_emails"} or action["tool"] != "find_leads" or action.get("single_action") is not True:
        return False
    session = DiscoverySession.objects.filter(run=row).first()
    if not session:
        return False
    original = session.action
    expected = engine_find_args(source_args) if direct["name"] == "find_leads" else {"count": len(source_args["leadIds"]), "emails": True, "audience": ""}
    remaining = session.goal - counts(session)["produced"]
    return (session.goal == expected["count"] and original["arguments"] == expected
            and session.unit == ("emails" if expected["emails"] else "leads") and remaining > 0
            and original["id"] == action["id"] and original["snapshot"] == action["snapshot"]
            and action["arguments"] == {**expected, "count": remaining}
            and (not session.source_ids or selected_identity(session.source_ids) == original.get("source_identity")))


def drive(run_id):
    from django.utils import timezone
    from leadzen.chat import engine
    from leadzen.chat.tools import approved, SEND_TOOLS
    from leadzen.config.models import ChatRun
    from leadzen.mcp.guard import connection_execution
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()  # Registers the control alias before grant validation.
    row = ChatRun.objects.select_related("thread").filter(pk=run_id, status="queued", cancel_requested=False).first()
    if not row or not row.thread.context.get("mcpConnectionId") or not row.thread.context.get("mcpAction"):
        return
    connection_id = row.thread.context["mcpConnectionId"]
    owner = os.environ.get("LEADZEN_ACTOR_ID")
    if owner and owner != str(row.actor_id):
        engine.finish(row, "failed", "Worker ownership changed. Review this operation in LeadZen.")
        return
    previous = os.environ.get("LEADZEN_CHAT_RUN_ID")
    try:
        with connection_execution(connection_id, row.actor_id):
            expires = row.approval_expires_at
            deadline = min(timezone.now() + timedelta(minutes=10), expires) if expires else timezone.now() + timedelta(minutes=10)
            if ChatRun.objects.filter(pk=run_id, status="queued", cancel_requested=False).update(
                    status="running", steps=1, updated_at=timezone.now(), deadline_at=deadline) != 1:
                return
            row.refresh_from_db()
            os.environ["LEADZEN_CHAT_RUN_ID"] = str(row.pk)
            action = row.pending
            if not action or not action.get("approved") or not row.approval_expires_at or row.approval_expires_at <= timezone.now():
                engine.finish(row, "failed", "The portal approval expired or is unavailable. No new action was started.")
                return
            if not _matches_action(row, action):
                engine.finish(row, "failed", "This direct operation no longer matches its approved capability.")
                return
            if engine.snapshot(action["tool"], action["arguments"], row=row) != action.get("snapshot"):
                engine.finish(row, "failed", "The approved setup or messages changed. Review a fresh operation in LeadZen.")
                return
            engine.assert_action_access()
            # Consume before the external effect. A crash or uncertainty cannot
            # turn polling, duplicate dispatch, or approval replay into a retry.
            ChatRun.objects.filter(pk=row.pk, status="running").update(pending={})
            token = approved.set({**action, "actor_id": row.actor_id, "run_id": str(row.pk), "used": False})
            try:
                args = {**action["arguments"], "approvalToken": action["id"]} if action["tool"] in SEND_TOOLS else action["arguments"]
                result = engine.perform(row, action["tool"], args, action["summary"])
            finally:
                approved.reset(token)
            observation = row.thread.messages.filter(role="tool").order_by("-created_at", "-pk").first()
            if observation:
                observation.data = {**observation.data, "mcpOperationId": str(row.pk)}
                observation.save(update_fields=["data"])
            if engine.discovery_checkpoint(row, result):
                return
            row.refresh_from_db()
            if row.cancel_requested:
                engine.finish(row, "cancelled", "Operation stopped. Review recorded results; an in-flight action may already have completed.")
            else:
                engine.finish(row, "succeeded", "Operation completed. Review the recorded result for accepted, deferred or uncertain work.")
    except Exception:
        row.refresh_from_db()
        if row.status in {"queued", "running"}:
            engine.finish(row, "failed", "Operation stopped or could not finish. Review saved results before requesting another action; no automatic retry was scheduled.")
    finally:
        if previous is None:
            os.environ.pop("LEADZEN_CHAT_RUN_ID", None)
        else:
            os.environ["LEADZEN_CHAT_RUN_ID"] = previous


def main(run_id):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadzen.settings")
    import django
    django.setup()
    from django.conf import settings
    from leadzen.web_worker import _database_lock
    try:
        with _database_lock(settings.DATABASE_PATH):
            drive(run_id)
    except Exception:
        from django.utils import timezone
        from leadzen.config.models import ChatRun
        from leadzen.chat.engine import finish
        row = ChatRun.objects.filter(pk=run_id, status="queued").first()
        if row:
            finish(row, "failed", "Another outreach worker is busy. Review your current tasks before requesting another operation.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
