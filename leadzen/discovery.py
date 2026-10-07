"""Exact, employee-approved discovery choices, without model interpretation."""
import uuid
import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from leadzen.accounts.service import access, error, payload
from leadzen.chat import views as chat
from leadzen.chat.engine import MAX_ACTION_COUNT, normalize, prepare, snapshot
from leadzen.config.models import ChatMessage, ChatRun, ChatThread, DiscoverySession, SiteConfig
from leadzen.configuration import effective
from leadzen.lead_finder import key as finder_key, label as finder_label, budget
from leadzen.discovery_progress import candidate_payload, counts, credits, selected_identity


def context(actor_id):
    values, config = effective(), SiteConfig.load()
    blockers = []
    if not (values.ai_enabled and values.llm_api_key and values.model):
        blockers.append("Connect an AI provider and enable AI in Settings.")
    if not finder_key(values):
        blockers.append(f"Add your {finder_label(values)} API key in Settings.")
    if values.lead_finder_provider == "ai_ark":
        from leadzen.config.models import OnboardingState
        from leadzen.ai_ark import search_filters
        from leadzen.home import current_target
        state = OnboardingState.objects.filter(pk=1).first()
        try:
            search_filters(current_target(config, state)["audience"])
        except ValueError as exc:
            blockers.append(str(exc))
    if not (config.product_docs.strip() and config.campaign_target.strip()):
        blockers.append("Complete your product and target audience in Purpose & setup.")
    if not (config.operator_email and config.operator_country_code and config.accepted_legal_notice):
        blockers.append("Complete your identity and legal acknowledgment in Purpose & setup.")
    active = ChatRun.objects.filter(actor_id=actor_id, thread__actor_id=actor_id, status__in=chat.ACTIVE).select_related("thread").first()
    return {"max_count": MAX_ACTION_COUNT, "max_email_count": 12 if values.lead_finder_provider == "ai_ark" else MAX_ACTION_COUNT,
            "provider": values.lead_finder_provider, "provider_name": finder_label(values),
            "profile_budget_per_lead": 1 if values.lead_finder_provider == "ai_ark" else 0, "target": config.campaign_target,
            "ready": not blockers, "blockers": blockers,
            "revision": snapshot("find_leads", {}),
            "active_run": {"thread_id": str(active.thread_id), "status": active.status,
                           "discovery_id": str(active.pk) if DiscoverySession.objects.filter(run=active).exists() else None} if active else None}


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def discovery(request):
    if request.method == "GET":
        # Only saved configuration. No model/provider request or job preparation.
        return JsonResponse(context(request.actor.pk))
    body = payload(request)
    args = normalize("find_leads", {"count": body.get("count"), "emails": body.get("emails")})
    credits = budget(args["count"], args["emails"])
    if credits > 25:
        return error("Use at most 12 leads with email lookup for AI Ark's 25-credit per-run limit")
    if type(body.get("estimated_credits")) is not int or body["estimated_credits"] != credits:
        return error("The displayed provider-credit estimate does not match your choices. Review and retry.")
    try:
        request_id = uuid.UUID(str(body.get("request_id", "")))
    except ValueError:
        return error("A unique request ID is required")
    selection = {"discovery": args, "estimated_credits": credits, "revision": body.get("revision")}
    existing = ChatRun.objects.filter(request_id=request_id).select_related("thread").first()
    if existing:
        if existing.actor_id != request.actor.pk or existing.thread.actor_id != request.actor.pk:
            return error("Request ID already used", 409)
        original = existing.thread.messages.filter(role="user").order_by("created_at", "pk").first()
        if not original or original.data != selection:
            return error("Request ID already used for different choices", 409)
        return JsonResponse({"thread_id": str(existing.thread_id), "run": chat.run_payload(existing)}, status=202)
    chat.recover_stale(request.actor.pk)
    current = context(request.actor.pk)
    if body.get("revision") != current["revision"]:
        return error("Your setup or target changed. Refresh this screen and review before starting.", 409)
    if not current["ready"]:
        return error(" ".join(current["blockers"]), 409)
    if current["active_run"]:
        return error("Finish or stop your active task before finding more leads.", 409)
    if ChatRun.objects.filter(actor_id=request.actor.pk, created_at__gt=timezone.now() - timedelta(minutes=10)).count() >= 15:
        return error("Discovery and chat limit reached. Try again in a few minutes.", 429)
    if ChatThread.objects.filter(actor_id=request.actor.pk, archived=False, deleted_at__isnull=True).count() >= 100:
        return error("Archive a conversation before creating another discovery run.", 409)
    try:
        with transaction.atomic(using=ChatRun.objects.all().db):
            # Repeat the revision check inside the transaction before approving.
            if body.get("revision") != snapshot("find_leads", args):
                return error("Your setup changed. Refresh and review before starting.", 409)
            thread = ChatThread.objects.create(actor_id=request.actor.pk, title=f"Find {args['count']} leads" + (" with verified emails" if args["emails"] else " without email lookup"))
            row = ChatRun.objects.create(thread=thread, actor_id=request.actor.pk, request_id=request_id)
            prepare(row, "find_leads", args)
            row.refresh_from_db()
            # Start Finding is explicit approval of this exact displayed budget.
            row.pending = {**row.pending, "approved": True, "single_action": True}
            row.status = "queued"
            row.save(update_fields=["pending", "status", "updated_at"])
            DiscoverySession.objects.create(run=row, action=row.pending, goal=args["count"],
                                            unit="emails" if args["emails"] else "leads", target=current["target"])
            ChatMessage.objects.create(thread=thread, role="user", content=f"Find {args['count']} qualified leads. Provider budget: up to {credits} {finder_label()} credits." + (" Include verified email lookup." if args["emails"] else " Do not buy email addresses.") + " Do not send emails.", data=selection)
            ChatMessage.objects.create(thread=thread, role="approval", content="You approved: " + row.pending["summary"], data={"approval": {key: row.pending[key] for key in ("id", "tool", "credits", "emails", "preview")}})
    except IntegrityError:
        return error("Another task was started. Refresh and review your active task.", 409)
    chat.launch(request, row)
    row.refresh_from_db()
    return JsonResponse({"thread_id": str(row.thread_id), "run": chat.run_payload(row)}, status=202)


def owned(request, run_id):
    # Ownership is resolved before configuration, credentials or any worker launch.
    return DiscoverySession.objects.select_related("run", "run__thread").filter(
        run_id=run_id, run__actor_id=request.actor.pk, run__thread__actor_id=request.actor.pk,
        run__thread__archived=False).first()


def progress_payload(session):
    statistics = counts(session)
    events = list(session.events.order_by("-pk")[:100])
    activity = {"kind": events[0].kind, "data": events[0].data, "created_at": events[0].created_at.isoformat()} if events else None
    candidates = list(session.candidates.order_by("-pk")[:100])
    return {"id": str(session.pk), "thread_id": str(session.run.thread_id), "status": session.run.status,
            "phase": session.phase, "current_activity": activity,
            "pause_requested": session.pause_requested, "stop_requested": session.run.cancel_requested,
            "goal": {"count": session.goal, "unit": session.unit}, "counts": statistics, "credits": credits(session),
            "target": session.target, "synthetic": session.synthetic,
            "goal_reached": statistics["produced"] >= session.goal,
            "approval_expires_at": session.run.approval_expires_at.isoformat() if session.run.approval_expires_at else None,
            "events": [{"id": e.pk, "kind": e.kind, "data": e.data, "created_at": e.created_at.isoformat()} for e in reversed(events)],
            "candidates": [candidate_payload(c) for c in reversed(candidates)],
            "leads": [candidate_payload(c) for c in session.candidates.filter(outcome="qualified").order_by("pk")[:50]]}


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def progress(request, run_id, action=None):
    session = owned(request, run_id)
    if not session:
        return error("Discovery not found", 404)
    chat.recover_stale(request.actor.pk)
    session.refresh_from_db()
    row = session.run
    row.refresh_from_db()
    if request.method == "GET" and action is None:
        return JsonResponse(progress_payload(session))
    if request.method != "POST" or action not in {"pause", "resume", "stop"}:
        return error("Route not found", 404)
    if action == "stop":
        ChatRun.objects.filter(pk=row.pk, status__in=chat.ACTIVE).update(cancel_requested=True, updated_at=timezone.now())
        ChatRun.objects.filter(pk=row.pk, status__in=["queued", "paused"]).update(status="cancelled", pending={}, finished_at=timezone.now())
        row.refresh_from_db()
        return JsonResponse(progress_payload(session))
    if action == "pause":
        with transaction.atomic(using=ChatRun.objects.all().db):
            row.refresh_from_db()
            if row.status not in {"queued", "running"} or row.cancel_requested:
                return error("This run cannot be paused", 409)
            DiscoverySession.objects.filter(pk=session.pk).update(pause_requested=True, updated_at=timezone.now())
        session.refresh_from_db()
        return JsonResponse(progress_payload(session))
    with transaction.atomic(using=ChatRun.objects.all().db):
        row.refresh_from_db()
        if row.status != "paused" or row.cancel_requested:
            return error("This run is not paused", 409)
        original = session.action
        if not row.approval_expires_at or row.approval_expires_at <= timezone.now() or snapshot("find_leads", original["arguments"]) != original["snapshot"]:
            return error("The approval expired or setup changed. Stop this run and review a new search.", 409)
        if session.source_ids and selected_identity(session.source_ids) != original.get("source_identity"):
            return error("A selected lead changed or was deleted. Stop and review again.", 409)
        remaining = session.goal - counts(session)["produced"]
        if remaining <= 0:
            return error("The requested goal is already reached", 409)
        pending = {**original, "arguments": {**original["arguments"], "count": remaining}}
        if ChatRun.objects.filter(pk=row.pk, status="paused", cancel_requested=False).update(status="queued", pending=pending, deadline_at=None, updated_at=timezone.now()) != 1:
            return error("The run changed. Refresh before resuming.", 409)
        DiscoverySession.objects.filter(pk=session.pk).update(phase="queued", pause_requested=False, updated_at=timezone.now())
        ChatMessage.objects.create(thread=row.thread, role="user", content=f"Resume the remaining {remaining} results within the original approved budget. Do not send emails.")
    row.refresh_from_db()
    chat.launch(request, row)
    session.refresh_from_db()
    row.refresh_from_db()
    return JsonResponse(progress_payload(session), status=202)


def email_review(session):
    from openoutfind.crm.models import Deal, DealState
    from leadzen.config.models import ContactPreferences, DiscoveryLookup
    candidates = list(session.candidates.filter(outcome="qualified", produced=True).order_by("pk")[:25])
    ids = [c.source_id for c in candidates]
    eligible = set(Deal.objects.filter(Q(lead__email="") | Q(lead__email__isnull=True),
        lead_id__in=ids, lead__synthetic=False, lead__disqualified=False,
        state__in=[DealState.QUALIFIED, DealState.READY_TO_FIND_EMAIL]).values_list("lead_id", flat=True))
    eligible.difference_update(int(i) for i in ContactPreferences.objects.filter(lead__lead_id__in=[str(i) for i in ids], deleted_at__isnull=False).values_list("lead__lead_id", flat=True))
    # A missing/uncertain handle is never automatically resubmitted in a new run.
    eligible.difference_update(DiscoveryLookup.objects.filter(source_id__in=ids).values_list("source_id", flat=True))
    items = [candidate_payload(c) for c in candidates if c.source_id in eligible]
    identity = selected_identity([c["source_id"] for c in items])
    revision = hashlib.sha256(json.dumps({"setup": snapshot("find_leads", {}), "identity": identity, "items": items}, sort_keys=True).encode()).hexdigest()
    return {"items": items, "revision": revision, "max_count": MAX_ACTION_COUNT, "provider_name": finder_label(),
            "note": "Only selected qualified leads from this run. No discovery or email sending. AI-provider charges may apply separately."}


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def emails(request, run_id):
    session = owned(request, run_id)
    if not session:
        return error("Discovery not found", 404)
    if session.run.status in chat.ACTIVE or session.unit != "leads":
        return error("Finish or stop profile discovery before reviewing email lookup", 409)
    if request.method == "GET":
        return JsonResponse(email_review(session))
    body = payload(request)
    ids = body.get("candidate_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_ACTION_COUNT or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
        return error("Select 1–25 different qualified leads")
    ids = sorted(ids)
    if type(body.get("estimated_credits")) is not int or body["estimated_credits"] != len(ids):
        return error("Review the exact selected email-credit limit")
    try:
        request_id = uuid.UUID(str(body.get("request_id", "")))
    except ValueError:
        return error("A unique request ID is required")
    selection = {"parent": str(session.pk), "candidate_ids": ids, "revision": body.get("revision"), "estimated_credits": len(ids)}
    existing = ChatRun.objects.filter(request_id=request_id).select_related("thread").first()
    if existing:
        message = existing.thread.messages.filter(role="user").order_by("created_at", "pk").first()
        if existing.actor_id != request.actor.pk or existing.thread.actor_id != request.actor.pk or not message or message.data != selection:
            return error("Request ID already used", 409)
        return JsonResponse({"run": chat.run_payload(existing)}, status=202)
    chat.recover_stale(request.actor.pk)
    setup = context(request.actor.pk)
    if not setup["ready"] or setup["active_run"]:
        return error("Complete setup and finish or stop your active task first", 409)
    if ChatRun.objects.filter(actor_id=request.actor.pk, created_at__gt=timezone.now() - timedelta(minutes=10)).count() >= 15 or ChatThread.objects.filter(actor_id=request.actor.pk, archived=False, deleted_at__isnull=True).count() >= 100:
        return error("Task limit reached. Try later or archive a conversation", 429)
    try:
        with transaction.atomic(using=ChatRun.objects.all().db):
            review = email_review(session)
            items = {c["id"]: c for c in review["items"]}
            if review["revision"] != body.get("revision") or any(i not in items for i in ids):
                return error("The selected leads or setup changed. Refresh this review.", 409)
            source_ids = [items[i]["source_id"] for i in ids]
            args = normalize("find_leads", {"count": len(ids), "emails": True})
            thread = ChatThread.objects.create(actor_id=request.actor.pk, title=f"Find emails for {len(ids)} selected leads")
            row = ChatRun.objects.create(thread=thread, actor_id=request.actor.pk, request_id=request_id)
            prepare(row, "find_leads", args, selected=True)
            row.refresh_from_db()
            row.pending = {**row.pending, "approved": True, "single_action": True, "source_identity": selected_identity(source_ids)}
            row.status = "queued"
            row.save()
            DiscoverySession.objects.create(run=row, action=row.pending, goal=len(ids), unit="emails", target=session.target, source_ids=source_ids)
            ChatMessage.objects.create(thread=thread, role="user", content=f"Find verified emails for these {len(ids)} selected leads only. Up to {len(ids)} credits. Do not discover new profiles or send emails.", data=selection)
    except IntegrityError:
        return error("Another task started. Refresh and review your active task.", 409)
    chat.launch(request, row)
    row.refresh_from_db()
    return JsonResponse({"run": chat.run_payload(row)}, status=202)
