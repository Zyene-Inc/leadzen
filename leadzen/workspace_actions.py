"""Small Workspace entry points over the canonical jobs, inbox and Chat approvals."""
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from leadzen.accounts.service import access, error, payload
from leadzen.chat import views as chat
from leadzen.chat.engine import prepare
from leadzen.config.models import ChatMessage, ChatRun, ChatThread, EmailCampaign, EmailReview, OutreachJob


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def check_replies(request):
    """Prepare a single inbox-check approval; no external access on preparation."""
    if request.method == "GET":
        chat.recover_stale(request.actor.pk)
        run = ChatRun.objects.filter(actor_id=request.actor.pk, thread__actor_id=request.actor.pk, thread__deleted_at__isnull=True, status__in=chat.ACTIVE, thread__messages__role="user", thread__messages__data={"workspace_action": "check_replies"}).select_related("thread").first()
        return JsonResponse({"check": {"thread_id": str(run.thread_id), "run": chat.run_payload(run)} if run else None})
    try:
        request_id = uuid.UUID(str(payload(request).get("request_id", "")))
    except ValueError:
        return error("A unique request ID is required")
    existing = ChatRun.objects.filter(request_id=request_id).select_related("thread").first()
    if existing:
        message = existing.thread.messages.filter(role="user").first()
        if existing.actor_id != request.actor.pk or existing.thread.actor_id != request.actor.pk or not message or message.data != {"workspace_action": "check_replies"}:
            return error("Request ID already used", 409)
        return JsonResponse({"thread_id": str(existing.thread_id), "run": chat.run_payload(existing)})
    chat.recover_stale(request.actor.pk)
    if ChatRun.objects.filter(actor_id=request.actor.pk, status__in=chat.ACTIVE).exists():
        return error("Finish or stop your active task before checking replies.", 409)
    if ChatRun.objects.filter(actor_id=request.actor.pk, created_at__gt=timezone.now() - timedelta(minutes=10)).count() >= 15:
        return error("Task limit reached. Try again in a few minutes.", 429)
    if ChatThread.objects.filter(actor_id=request.actor.pk, archived=False, deleted_at__isnull=True).count() >= 100:
        return error("Archive an old chat before checking replies again.", 409)
    from leadzen.configuration import effective
    values = effective()
    if not values.mailbox_address or not values.imap_host or not (values.imap_password or values.mailbox_password):
        return error("Connect your reply inbox in Settings first.", 409)
    if not values.ai_enabled or not values.llm_api_key:
        return error("Connect AI in Settings to classify replies.", 409)
    try:
        with transaction.atomic(using=ChatRun.objects.all().db):
            thread = ChatThread.objects.create(actor_id=request.actor.pk, title="Check for replies", context={"workspacePath": "/inbox"})
            run = ChatRun.objects.create(actor_id=request.actor.pk, thread=thread, request_id=request_id)
            ChatMessage.objects.create(thread=thread, role="user", content="Check my connected inbox for replies and classify them. Do not send emails or take any other action.", data={"workspace_action": "check_replies"})
            prepare(run, "sync_mailbox", {})
            run.refresh_from_db()
            run.pending = {**run.pending, "single_action": True}
            run.save(update_fields=["pending"])
    except IntegrityError:
        return error("Another task is active. Refresh before continuing.", 409)
    return JsonResponse({"thread_id": str(thread.pk), "run": chat.run_payload(run)}, status=201)


@require_http_methods(["GET"])
@access(workspace=True)
def attention(request):
    """Actionable saved records, not invented unread counters or live provider calls."""
    from cold_outreach.emails.models import Message, Thread
    items = []
    for row in EmailReview.objects.filter(actor_id=request.actor.pk, status__in=["draft", "failed"]).order_by("-created_at")[:4]:
        items.append({"id": f"review-{row.pk}", "label": "Review reply" if row.kind == "reply" else f"Review {row.requested_count} messages", "detail": "Draft ready" if row.status == "draft" else "Preparation or sending needs attention", "href": f"/outreach?review={row.pk}"})
    from leadzen.config.models import AutopilotRun, AutopilotPolicy
    for run in AutopilotRun.objects.filter(actor_id=request.actor.pk, phase="needs_attention").order_by("-workday")[:3]:
        items.append({"id": f"autopilot-{run.pk}", "label": f"Autopilot · {run.workday}", "detail": run.issue or "Some messages need attention", "href": "/outreach"})
    for policy in AutopilotPolicy.objects.filter(actor_id=request.actor.pk, enabled=True).exclude(issue="")[:1]:
        items.append({"id": f"autopilot-policy-{policy.pk}", "label": "Autopilot needs attention", "detail": policy.issue, "href": "/outreach"})
    for row in EmailCampaign.objects.filter(status="draft", autopilot_run__isnull=True).order_by("-created_at")[:4]:
        items.append({"id": f"campaign-{row.pk}", "label": row.name, "detail": "Outreach draft · needs review", "href": f"/outreach?campaign={row.pk}"})
    # A saved human reply is awaiting a response only if the latest message is
    # inbound. Do not call it unread: this application has no read receipt model.
    from django.db.models import OuterRef, Subquery, Q
    latest = Message.objects.filter(thread_id=OuterRef("pk")).filter(Q(direction="in") | Q(direction="out", delivery_events__status="accepted")).order_by("-recorded_at", "-pk")
    threads = Thread.objects.annotate(latest_kind=Subquery(latest.values("kind")[:1]), latest_direction=Subquery(latest.values("direction")[:1]), latest_at=Subquery(latest.values("recorded_at")[:1])).filter(latest_direction="in", latest_kind="human_reply").order_by("-latest_at")[:4]
    for thread in threads:
        message = thread.messages.filter(direction="in", kind="human_reply").order_by("-recorded_at", "-pk").first()
        items.append({"id": f"reply-{thread.pk}", "label": message.from_address, "detail": "Human reply · awaiting response", "href": f"/inbox?thread={thread.pk}"})
    for row in EmailCampaign.objects.exclude(status="archived").exclude(followup_approval__issue__isnull=True).order_by("-created_at")[:4]:
        if row.followup_approval.get("issue"):
            items.append({"id": f"blocked-{row.pk}", "label": row.name, "detail": row.followup_approval["issue"], "href": f"/outreach?campaign={row.pk}"})
    for row in OutreachJob.objects.filter(status="failed").order_by("-created_at")[:3]:
        items.append({"id": f"job-{row.pk}", "label": "Sending needs attention", "detail": "Check the saved result before retrying", "href": "/outreach"})
    return JsonResponse({"items": items})
