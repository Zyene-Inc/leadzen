"""Authenticated, bounded chat commands; the browser never supplies ownership."""
import json
import time
import subprocess
import sys
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from leadzen.accounts.service import access, error, payload
from leadzen.config.models import ChatMessage, ChatRun, ChatThread
from leadzen.configuration import effective
from leadzen.workspaces import worker_environment

ACTIVE = ["queued", "running", "awaiting_approval", "paused"]


def recover_stale(actor_id):
    """Abandoned processes never replay consumed approvals or uncertain sends."""
    from django.db.models import Q
    cutoff = timezone.now()
    rows = ChatRun.objects.filter(actor_id=actor_id).filter(Q(status="running", deadline_at__lt=cutoff - timedelta(minutes=1)) | Q(status="queued", updated_at__lt=cutoff - timedelta(minutes=3)) | Q(status="paused", approval_expires_at__lt=cutoff))
    for row in rows:
        if ChatRun.objects.filter(pk=row.pk, status=row.status, updated_at=row.updated_at).update(status="failed", pending={}, finished_at=cutoff):
            from leadzen.config.models import DiscoverySession
            DiscoverySession.objects.filter(run_id=row.pk).update(phase="failed", pause_requested=False)
            for message in row.thread.messages.filter(role="tool", data__result__status="running"):
                message.data = {"tool": message.data.get("tool"), "result": {"status": "interrupted", "note": "Review contacts and campaign history before retrying."}}
                message.save(update_fields=["data"])
            for message in row.thread.messages.filter(role="assistant", data__run_id=str(row.pk), data__streaming=True):
                message.data = {**message.data, "streaming": False, "interrupted": True}
                message.save(update_fields=["data"])
            ChatMessage.objects.create(thread=row.thread, role="assistant", content="This worker stopped or exceeded its time limit. Some actions may have completed. Review contacts and campaign status; no action was automatically retried.")


def thread_payload(row):
    return {"id": str(row.pk), "title": row.title, "updated_at": row.updated_at.isoformat()}


def run_payload(row):
    if not row:
        return None
    pending = row.pending
    from leadzen.config.models import DiscoverySession
    return {"id": str(row.pk), "status": row.status, "steps": row.steps, "cancel_requested": row.cancel_requested,
            "created_at": row.created_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "discovery_id": str(row.pk) if DiscoverySession.objects.filter(run=row).exists() else None,
            "approval": {key: pending[key] for key in ("id", "tool", "summary", "credits", "emails", "preview") if key in pending} if row.status == "awaiting_approval" else None,
            "approval_expires_at": row.approval_expires_at.isoformat() if row.approval_expires_at else None}


def detail(row):
    from leadzen.chat.context import structured
    from leadzen.config.models import DiscoverySession
    sessions = {str(s.pk): s for s in DiscoverySession.objects.filter(run__thread=row).select_related("run")}
    messages = []
    for m in row.messages.order_by("created_at", "pk")[:200]:
        data = m.data
        # A saved tool observation may have been written just before the run
        # finished. Read its canonical current status without duplicating records.
        discovery = data.get("result", {}).get("discovery") if isinstance(data.get("result"), dict) else None
        if discovery and discovery.get("id") in sessions:
            session = sessions[discovery["id"]]
            data = {**data, "result": {**data["result"], "discovery": {**discovery, "status": session.run.status}}}
        messages.append({"id": str(m.pk), "role": m.role, "content": m.content, "data": data, "created_at": m.created_at.isoformat()})
    return {**thread_payload(row), "context": structured(row.actor_id), "messages": messages,
            "run": run_payload(row.runs.order_by("-created_at").first())}


def launch(request, row):
    try:
        module = "leadzen.mcp.worker" if row.thread.context.get("mcpConnectionId") else "leadzen.chat_worker"
        subprocess.Popen([sys.executable, "-m", module, str(row.pk)], env=worker_environment(request.actor.leadzen_profile), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        ChatRun.objects.filter(pk=row.pk, status="queued").update(status="failed", finished_at=timezone.now())
        ChatMessage.objects.create(thread=row.thread, role="assistant", content="The worker could not start. Please retry or contact support@zyene.com.")


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def threads(request):
    recover_stale(request.actor.pk)
    rows = ChatThread.objects.filter(actor_id=request.actor.pk, archived=False, deleted_at__isnull=True)
    if request.method == "GET":
        return JsonResponse({"items": [thread_payload(t) for t in rows.order_by("-updated_at")[:100]]})
    if rows.count() >= 100:
        return error("Archive a conversation before creating another", 409)
    from leadzen.chat.context import structured, FIELDS
    context = structured(request.actor.pk)
    row = ChatThread.objects.create(actor_id=request.actor.pk, context={k: v for k, v in context.items() if k in FIELDS})
    return JsonResponse(thread_payload(row), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@access(workspace=True)
def thread(request, thread_id):
    row = ChatThread.objects.filter(pk=thread_id, actor_id=request.actor.pk, archived=False, deleted_at__isnull=True).first()
    if not row:
        return error("Conversation not found", 404)
    recover_stale(request.actor.pk)
    if request.method == "DELETE":
        # Retain run/progress audit records and all canonical Workspace objects.
        # Never cascade-delete a conversation's leads, drafts or discoveries.
        with transaction.atomic(using=ChatThread.objects.all().db):
            row = ChatThread.objects.select_for_update().filter(pk=thread_id, actor_id=request.actor.pk, deleted_at__isnull=True).first()
            if not row:
                return error("Conversation not found", 404)
            if row.runs.filter(status__in=ACTIVE).exists():
                return error("Finish or stop the current task before deleting this chat", 409)
            row.deleted_at = timezone.now()
            row.save(update_fields=["deleted_at", "updated_at"])
            from leadzen.chat.context import save
            from leadzen.config.models import WorkspaceContext
            context = WorkspaceContext.objects.filter(actor_id=request.actor.pk).first()
            if context and context.references.get("lastChatId") == str(row.pk):
                save(request.actor.pk, {"lastChatId": None})
        return JsonResponse({"deleted": True, "id": str(row.pk)})
    if request.method == "PUT":
        body = payload(request)
        if row.runs.filter(status__in=ACTIVE).exists():
            return error("Finish or stop the current task first", 409)
        title = body.get("title", row.title)
        if not isinstance(title, str) or not title.strip() or len(title) > 100:
            return error("Enter a title of up to 100 characters")
        row.title, row.archived = title.strip(), body.get("archived") is True
        row.save(update_fields=["title", "archived", "updated_at"])
    if not row.archived:
        from leadzen.chat.context import save, structured, FIELDS
        latest = structured(request.actor.pk)
        if latest.get("lastChatId") and latest["lastChatId"] != str(row.pk):
            restored = structured(request.actor.pk, row.context)
            restore = {k: v for k, v in restored.items() if k in FIELDS and k not in {"workspacePath", "lastChatId"}}
            save(request.actor.pk, restore)
        save(request.actor.pk, {"lastChatId": str(row.pk)})
    return JsonResponse(detail(row))


@csrf_exempt
@require_http_methods(["POST"])
@access(workspace=True)
def message(request, thread_id):
    row = ChatThread.objects.filter(pk=thread_id, actor_id=request.actor.pk, archived=False, deleted_at__isnull=True).first()
    if not row:
        return error("Conversation not found", 404)
    if row.context.get("mcpConnectionId"):
        return error("This is a single MCP action. Continue in your connected app or start a new LeadZen chat.", 409)
    recover_stale(request.actor.pk)
    body = payload(request)
    text = body.get("content", "")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Write a message of 1–4000 characters")
    try:
        request_id = uuid.UUID(str(body.get("request_id", "")))
    except ValueError:
        return error("A unique request ID is required")
    existing = ChatRun.objects.filter(request_id=request_id).first()
    if existing:
        if existing.actor_id != request.actor.pk or existing.thread_id != row.pk:
            return error("Request ID already used", 409)
        return JsonResponse({"run": run_payload(existing)}, status=202)
    values = effective()
    if not values.ai_enabled or not values.llm_api_key or not values.model:
        return error("Connect an AI provider and enable AI in Connections first", 409)
    if ChatRun.objects.filter(actor_id=request.actor.pk, status__in=ACTIVE).exists():
        return error("Finish or stop your active chat task first", 409)
    if ChatRun.objects.filter(actor_id=request.actor.pk, created_at__gt=timezone.now() - timedelta(minutes=10)).count() >= 15:
        return error("Chat limit reached. Try again in a few minutes.", 429)
    if row.messages.count() >= 160:
        return error("This conversation is full. Start a new one.", 409)
    from leadzen.chat.engine import redact
    text = redact(text.strip())
    try:
        with transaction.atomic(using=ChatRun.objects.all().db):
            row = ChatThread.objects.select_for_update().filter(pk=thread_id, actor_id=request.actor.pk, archived=False, deleted_at__isnull=True).first()
            if not row:
                return error("Conversation not found", 404)
            from leadzen.chat.context import structured, save, FIELDS
            if "context" in body:
                save(request.actor.pk, body["context"])
            latest = structured(request.actor.pk)
            row.context = {k: v for k, v in latest.items() if k in FIELDS}
            run = ChatRun.objects.create(thread=row, actor_id=request.actor.pk, request_id=request_id)
            ChatMessage.objects.create(thread=row, role="user", content=text, data={"context": row.context})
            if row.title == "New conversation":
                row.title = text[:80]
            row.save()
    except IntegrityError:
        return error("Another chat task is active. Refresh the conversation.", 409)
    launch(request, run)
    return JsonResponse({"run": run_payload(run)}, status=202)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def run(request, run_id, action=None):
    row = ChatRun.objects.filter(pk=run_id, actor_id=request.actor.pk, thread__actor_id=request.actor.pk).first()
    if not row:
        return error("Task not found", 404)
    if request.method == "GET" and action is None:
        return JsonResponse(run_payload(row))
    if request.method != "POST" or action not in {"approval", "cancel"}:
        return error("Route not found", 404)
    if action == "cancel":
        # Running sinks finish safely; cancellation never implies an email was unsent.
        ChatRun.objects.filter(pk=row.pk, status__in=ACTIVE).update(cancel_requested=True)
        ChatRun.objects.filter(pk=row.pk, status__in=["queued", "awaiting_approval", "paused"]).update(status="cancelled", finished_at=timezone.now())
        row.refresh_from_db()
        return JsonResponse(run_payload(row))
    if row.thread.context.get("mcpConnectionId"):
        from leadzen.mcp.auth import connection_live
        try:
            connection_live(row.thread.context["mcpConnectionId"], request.actor.pk)
        except PermissionError:
            return error("This app was disconnected. Request a new action after reconnecting.", 403)
    body = payload(request)
    if type(body.get("approved")) is not bool:
        return error("Approval must be true or false")
    from leadzen.chat.engine import snapshot
    with transaction.atomic(using=ChatRun.objects.all().db):
        row.refresh_from_db()
        if row.status != "awaiting_approval" or body.get("action_id") != row.pending.get("id"):
            return error("This approval is no longer available", 409)
        if not body["approved"]:
            ChatRun.objects.filter(pk=row.pk, status="awaiting_approval").update(status="cancelled", finished_at=timezone.now())
            ChatMessage.objects.create(thread=row.thread, role="assistant", content="Action declined. No new lead lookup or email send was started.")
            row.refresh_from_db()
            return JsonResponse(run_payload(row))
        try:
            unchanged = snapshot(row.pending["tool"], row.pending["arguments"], row=row) == row.pending["snapshot"]
        except ValueError:
            unchanged = False
        if not row.approval_expires_at or row.approval_expires_at <= timezone.now() or not unchanged:
            return error("Approval expired or the connections, campaign or contacts changed. Decline and request a fresh action.", 409)
        row.pending = {**row.pending, "approved": True}
        row.status = "queued"
        row.save()
        ChatMessage.objects.create(thread=row.thread, role="approval", content="You approved: " + row.pending["summary"], data={"approval": {key: row.pending[key] for key in ("id", "tool", "credits", "emails", "preview")}})
    launch(request, row)
    return JsonResponse(run_payload(row), status=202)


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@access(workspace=True)
def workspace_context(request):
    from leadzen.chat.context import save, structured
    if request.method == "PUT":
        body = payload(request)
        if "references" in body:
            if type(body.get("expected_actor_id")) is not int or body["expected_actor_id"] != request.actor.pk:
                return error("The signed-in Workspace changed. Refresh before switching modes.", 409)
            body = body["references"]
        save(request.actor.pk, body)
    return JsonResponse(structured(request.actor.pk))


@require_http_methods(["GET"])
@access(workspace=True)
def stream(request, thread_id):
    # Streaming iteration runs AFTER the access decorator exits its DB scope.
    # Re-enter it explicitly, and recheck session/access on every snapshot.
    owner = request.actor
    if not ChatThread.objects.filter(pk=thread_id, actor_id=owner.pk, archived=False, deleted_at__isnull=True).exists():
        return error("Conversation not found", 404)
    from django.db.models import Q
    from leadzen.config.models import WorkspaceContext
    lease = uuid.uuid4()
    with transaction.atomic(using=WorkspaceContext.objects.all().db):
        WorkspaceContext.objects.get_or_create(actor_id=owner.pk)
        if WorkspaceContext.objects.filter(actor_id=owner.pk).filter(Q(stream_expires_at__isnull=True) | Q(stream_expires_at__lte=timezone.now())).update(stream_token=lease, stream_expires_at=timezone.now() + timedelta(seconds=25)) != 1:
            return error("Another tab is streaming this Workspace. Reading saved progress instead.", 429)
    def snapshots():
        from leadzen.workspaces import workspace_scope
        from leadzen.accounts.service import session_user
        previous = None
        until = time.monotonic() + 20
        while time.monotonic() < until:
            actor = session_user(request)
            if not actor or actor.pk != owner.pk or actor.leadzen_profile.must_change_password or not actor.leadzen_profile.onboarding_completed_at:
                yield 'event: expired\ndata: {}\n\n'
                return
            with workspace_scope(actor.leadzen_profile):
                row = ChatThread.objects.filter(pk=thread_id, actor_id=actor.pk, archived=False, deleted_at__isnull=True).first()
                if not row:
                    return
                value = detail(row)
                from leadzen.config.models import DiscoverySession
                session = DiscoverySession.objects.filter(run_id=(value.get("run") or {}).get("id")).select_related("run").first()
                if session:
                    from leadzen.discovery import progress_payload
                    value["discovery"] = progress_payload(session)
                encoded = json.dumps(value, ensure_ascii=False)
            if encoded != previous:
                yield "data: " + encoded + "\n\n"
                previous = encoded
            else:
                yield ": heartbeat\n\n"
            if not value.get("run") or value["run"]["status"] not in {"queued", "running"}:
                return
            time.sleep(0.25)
    def leased_snapshots():
        from leadzen.workspaces import workspace_scope
        try:
            yield from snapshots()
        finally:
            with workspace_scope(owner.leadzen_profile):
                WorkspaceContext.objects.filter(actor_id=owner.pk, stream_token=lease).update(stream_token=None, stream_expires_at=None)
    response = StreamingHttpResponse(leased_snapshots(), content_type="text/event-stream")
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"
    return response
