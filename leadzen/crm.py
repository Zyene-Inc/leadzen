"""Saved CRM facts and explicit, one-profile work-email approval."""
import hashlib
import json
import uuid
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import CharField, Count, Exists, F, OuterRef, Q, Subquery, Window
from django.db.models.functions import Cast, RowNumber
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from cold_outreach.emails.models import Direction, Message
from cold_outreach.leads.models import Deal, DealState, Suppression
from openoutfind.crm.models import Deal as Decision, Lead as Profile
from leadzen.accounts.service import access, error, payload
from leadzen.config.models import ChatMessage, ChatRun, ChatThread, DiscoveryLookup, DiscoverySession, SiteConfig
from leadzen.discovery import context
from leadzen.discovery_progress import safe_profile, selected_identity
from leadzen.home import QUALIFIED

STAGES = {"all", "qualified", "email_found", "contacted", "replied", "suppressed"}


def website_link(value):
    # Finder exports may contain a bare company domain rather than a full URL.
    if isinstance(value, str) and re.fullmatch(r"(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,63}", value):
        value = "https://" + value
    return safe_profile(value)


def source_profile(deal):
    # Imported finder identities are exact, not guessed from an email or name.
    key = deal.lead.lead_id
    if not key.isdecimal() or len(key) > 18:
        return None
    return Profile.objects.select_related("company").filter(pk=int(key), synthetic=False).first()


def contact_name(deal):
    name = " ".join(filter(None, [deal.lead.first_name, deal.lead.last_name]))
    if name:
        return name
    source = source_profile(deal)
    return (source.full_name if source else "") or deal.lead.email or "Unnamed contact"


def contacts_query():
    decisions = Decision.objects.annotate(source_key=Cast("lead_id", CharField())).filter(
        source_key=OuterRef("lead__lead_id"), lead__synthetic=False, lead__disqualified=False,
        state__in=QUALIFIED).exclude(outcome="wrong_fit")
    profiles = Profile.objects.annotate(source_key=Cast("pk", CharField())).filter(source_key=OuterRef("lead__lead_id"), synthetic=False)
    latest_message = Message.objects.filter(thread_id=OuterRef("thread_id")).order_by("-recorded_at", "-pk")
    return Deal.objects.filter(lead__preferences__deleted_at__isnull=True).select_related("lead", "lead__preferences").annotate(
        crm_qualified=Exists(decisions), crm_name=Subquery(profiles.values("full_name")[:1]),
        crm_suppressed=Exists(Suppression.objects.filter(email__iexact=OuterRef("lead__email"))),
        crm_replied=Exists(Message.objects.filter(thread_id=OuterRef("thread_id"), direction=Direction.INBOUND, kind="human_reply")),
        crm_latest_message_id=Subquery(latest_message.values("pk")[:1]),
    ).order_by("-updated_at", "-pk")


def contact_payload(deal, *, detail=False, facts=None):
    from leadzen.lead_finder import LABELS
    source = facts["source"] if facts is not None else source_profile(deal)
    decision = facts["decision"] if facts is not None else Decision.objects.filter(lead=source).first() if source else None
    qualified = bool(decision and decision.state in QUALIFIED and decision.outcome != "wrong_fit" and not source.disqualified)
    suppressed = bool(deal.crm_suppressed) if facts is not None else bool(deal.lead.email and Suppression.objects.filter(email__iexact=deal.lead.email).exists())
    replies = facts["replies"] if facts is not None else Message.objects.filter(thread_id=deal.thread_id, direction=Direction.INBOUND, kind="human_reply").count() if deal.thread_id else 0
    contacted = bool(deal.email_sent_at)
    stage = "suppressed" if suppressed else "replied" if replies else "contacted" if contacted else "email_found" if deal.lead.email else "qualified" if qualified else "contact"
    receipt = facts["receipt"] if facts is not None else DiscoveryLookup.objects.filter(source_id=source.pk).select_related("session__run__thread").order_by("-session__run__created_at").first() if source else None
    latest_session = facts["session"] if facts is not None else DiscoverySession.objects.filter(source_ids=[source.pk], unit="emails").select_related("run", "run__thread").order_by("-run__created_at").first() if source else None
    lookup_session = receipt.session if receipt else latest_session
    lookup = None
    if lookup_session:
        lookup = {"run_id": str(lookup_session.pk) if not lookup_session.run.thread.archived else None,
                  "provider_name": LABELS.get(lookup_session.action.get("provider"), "BetterContact"),
                  "status": lookup_session.run.status, "receipt_state": receipt.state if receipt else "not_submitted",
                  "credits_used": float(receipt.credits) if receipt and receipt.credits is not None else None,
                  "email_verdict": receipt.email_status if receipt else "",
                  "synthetic": lookup_session.synthetic}
    email_status = "available" if deal.lead.email else "not_requested"
    if deal.lead.email and source and source.email == deal.lead.email and receipt and receipt.state == "terminated":
        email_status = "verified" if receipt.email_status in {"valid", "deliverable"} else "catch_all_safe" if receipt.email_status == "catch_all_safe" else "available"
    elif not deal.lead.email and lookup:
        email_status = "pending" if lookup["status"] in {"queued", "running", "paused"} else "not_found" if receipt and receipt.state == "terminated" else "review"
    preferences = getattr(deal.lead, "preferences", None)
    result = {"id": deal.pk, "lead_id": deal.lead.lead_id,
              "name": " ".join(filter(None, [deal.lead.first_name, deal.lead.last_name])) or (source.full_name if source else "") or deal.lead.email or "Unnamed contact",
              "first_name": deal.lead.first_name, "last_name": deal.lead.last_name,
              "email": deal.lead.email, "email_status": email_status, "lookup": lookup,
              "company": deal.lead.company or ((source.company.name or source.company.domain) if source and source.company else ""),
              "title": deal.lead.title or (source.job_title if source else ""),
              "website": website_link(deal.lead.website or (source.company.domain if source and source.company else "")), "linkedin_url": safe_profile(deal.lead.linkedin_url or (source.profile_url if source else "")),
              "qualified": qualified, "crm_status": stage, "state": deal.state, "outcome": deal.outcome,
              "reason": (decision.reason if decision else deal.reason) or "No qualification explanation is recorded for this contact.",
              "email_subject": deal.email_subject, "email_sent_at": deal.email_sent_at.isoformat() if deal.email_sent_at else None,
              "reply_count": replies, "opted_in": bool(preferences and preferences.opted_in),
              "consent_note": preferences.consent_note if preferences else "", "profile_text": deal.lead.profile_text}
    from leadzen.web import _message_payload
    latest = facts["message"] if facts is not None else Message.objects.filter(thread_id=deal.thread_id).order_by("-recorded_at").first() if deal.thread_id else None
    result["latest_message"] = _message_payload(latest) if latest else None
    if detail:
        from leadzen.timeline import outreach_timeline
        result["timeline"] = outreach_timeline(deal)
    return result


def contact_payloads(deals):
    """Batch saved facts for one bounded page without per-contact query growth."""
    keys = [int(d.lead.lead_id) for d in deals if d.lead.lead_id.isdecimal() and len(d.lead.lead_id) <= 18]
    latest_receipt = DiscoveryLookup.objects.filter(source_id=OuterRef("pk")).order_by("-session__run__created_at", "-pk")
    sources = {str(p.pk): p for p in Profile.objects.filter(pk__in=keys, synthetic=False).select_related("company")
        .annotate(crm_receipt_id=Subquery(latest_receipt.values("pk")[:1]))}
    decisions = {d.lead_id: d for d in Decision.objects.filter(lead_id__in=[p.pk for p in sources.values()])}
    receipts = {r.source_id: r for r in DiscoveryLookup.objects.filter(pk__in=[p.crm_receipt_id for p in sources.values() if p.crm_receipt_id])
        .select_related("session__run__thread")}
    sessions = {}
    unsubmitted = [[p.pk] for p in sources.values() if p.pk not in receipts]
    if unsubmitted:
        latest = DiscoverySession.objects.filter(unit="emails", source_ids__in=unsubmitted).select_related("run__thread").annotate(
            crm_rank=Window(expression=RowNumber(), partition_by=[F("source_ids")], order_by=[F("run__created_at").desc(), F("run_id").desc()])
        ).filter(crm_rank=1)
        sessions = {s.source_ids[0]: s for s in latest}
    thread_ids = {d.thread_id for d in deals if d.thread_id}
    replies = {r["thread_id"]: r["total"] for r in Message.objects.filter(thread_id__in=thread_ids, direction=Direction.INBOUND, kind="human_reply")
        .values("thread_id").annotate(total=Count("pk"))}
    from cold_outreach.emails.models import DeliveryEvent
    accepted = DeliveryEvent.objects.filter(message_id=OuterRef("pk"), status="accepted")
    messages = {m.pk: m for m in Message.objects.filter(pk__in=[d.crm_latest_message_id for d in deals if d.crm_latest_message_id])
        .annotate(crm_accepted=Exists(accepted))}
    result = []
    for deal in deals:
        source_key = deal.lead.lead_id
        source = sources.get(str(int(source_key))) if source_key.isdecimal() and len(source_key) <= 18 else None
        key = source.pk if source else None
        result.append(contact_payload(deal, facts={"source": source, "decision": decisions.get(key), "receipt": receipts.get(key),
            "session": sessions.get(key), "replies": replies.get(deal.thread_id, 0), "message": messages.get(deal.crm_latest_message_id)}))
    return result


def list_contacts(request):
    query, stage, state = request.GET.get("q", "").strip(), request.GET.get("stage", "all"), request.GET.get("state", "all")
    try:
        limit, offset = int(request.GET.get("limit", 50)), int(request.GET.get("offset", 0))
    except ValueError:
        return error("Enter valid pagination")
    if stage not in STAGES or len(query) > 200 or not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
        return error("Choose a valid lead filter, search up to 200 characters and page size 1–100")
    rows = contacts_query()
    if state in {choice.value for choice in DealState}:
        rows = rows.filter(state=state)
    if stage == "qualified":
        rows = rows.filter(crm_qualified=True)
    elif stage == "email_found":
        rows = rows.exclude(lead__email="").exclude(lead__email__isnull=True)
    elif stage == "contacted":
        rows = rows.filter(email_sent_at__isnull=False)
    elif stage == "replied":
        rows = rows.filter(crm_replied=True, thread_id__isnull=False)
    elif stage == "suppressed":
        rows = rows.filter(crm_suppressed=True).exclude(lead__email="")
    if query:
        rows = rows.filter(Q(crm_name__icontains=query) | Q(lead__email__icontains=query) | Q(lead__first_name__icontains=query) | Q(lead__last_name__icontains=query) | Q(lead__company__icontains=query) | Q(lead__title__icontains=query))
    return JsonResponse({"items": contact_payloads(list(rows[offset:offset + limit])), "total": rows.count(), "limit": limit, "offset": offset})


def owned_contact(deal_id):
    return Deal.objects.filter(pk=deal_id, lead__preferences__deleted_at__isnull=True).select_related("lead").first()


def email_review(deal, actor_id):
    from leadzen.chat.engine import snapshot
    source = source_profile(deal)
    setup = context(actor_id)
    decision = Decision.objects.filter(lead=source).first() if source else None
    reason = ""
    if not source or not safe_profile(source.profile_url):
        reason = "Only a saved discovery profile can be enriched. LeadZen will not guess a profile from a name or email."
    elif source.disqualified or not decision or decision.state not in {"Qualified", "Ready to Find Email"} or decision.outcome == "wrong_fit":
        reason = "This lead is not currently eligible for a qualified work-email lookup."
    elif deal.lead.email or source.email:
        reason = "An email address is already saved. No new purchase is needed."
    elif deal.state != DealState.READY:
        reason = "This contact's outreach has been stopped or already started."
    elif DiscoveryLookup.objects.filter(source_id=source.pk).exists():
        reason = "A lookup has already been submitted. Review its saved result; an uncertain purchase is never repeated automatically."
    elif not setup["ready"]:
        reason = " ".join(setup["blockers"])
    elif setup["active_run"]:
        reason = "Finish or stop your active task before requesting an email."
    identity = selected_identity([source.pk]) if source else {}
    revision = hashlib.sha256(json.dumps({"setup": snapshot("find_leads", {}), "identity": identity,
        "id": deal.pk, "state": deal.state, "email": deal.lead.email, "source_email": source.email if source else "",
        "decision": [decision.state, decision.outcome] if decision else None, "eligible": not reason}, sort_keys=True).encode()).hexdigest()
    from leadzen.lead_finder import label
    return {"eligible": not reason, "reason": reason, "revision": revision, "estimated_credits": 1, "provider_name": label(),
            "name": contact_payload(deal)["name"], "source_id": source.pk if source else None}


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def work_email(request, deal_id):
    from leadzen.chat import views as chat
    from leadzen.chat.engine import normalize, prepare
    deal = owned_contact(deal_id)
    if not deal:
        return error("Contact not found", 404)
    if request.method == "GET":
        return JsonResponse(email_review(deal, request.actor.pk))
    body = payload(request)
    if type(body.get("estimated_credits")) is not int or body["estimated_credits"] != 1:
        return error("Confirm the one-credit work-email budget before starting")
    try:
        request_id = uuid.UUID(str(body.get("request_id", "")))
    except ValueError:
        return error("A unique request ID is required")
    selection = {"contact_id": deal.pk, "revision": body.get("revision"), "estimated_credits": 1}
    existing = ChatRun.objects.filter(request_id=request_id).select_related("thread").first()
    if existing:
        message = existing.thread.messages.filter(role="user").order_by("created_at", "pk").first()
        if existing.actor_id != request.actor.pk or existing.thread.actor_id != request.actor.pk or not message or message.data != selection:
            return error("Request ID already used", 409)
        return JsonResponse({"run": chat.run_payload(existing)}, status=202)
    chat.recover_stale(request.actor.pk)
    if ChatRun.objects.filter(actor_id=request.actor.pk, created_at__gt=timezone.now() - timedelta(minutes=10)).count() >= 15 or ChatThread.objects.filter(actor_id=request.actor.pk, archived=False, deleted_at__isnull=True).count() >= 100:
        return error("Task limit reached. Try later or archive a conversation", 429)
    try:
        with transaction.atomic(using=ChatRun.objects.all().db):
            deal = owned_contact(deal_id)
            if not deal:
                return error("Contact not found", 404)
            review = email_review(deal, request.actor.pk)
            if not review["eligible"] or review["revision"] != body.get("revision"):
                return error(review["reason"] or "The lead or setup changed. Review this lookup again.", 409)
            source_ids = [review["source_id"]]
            thread = ChatThread.objects.create(actor_id=request.actor.pk, title=f"Work email for {review['name']}"[:100])
            row = ChatRun.objects.create(thread=thread, actor_id=request.actor.pk, request_id=request_id)
            prepare(row, "find_leads", normalize("find_leads", {"count": 1, "emails": True}), selected=True)
            row.refresh_from_db()
            row.pending = {**row.pending, "approved": True, "single_action": True, "source_identity": selected_identity(source_ids),
                           "summary": f"Find a work email for {review['name']} only. Up to 1 {review['provider_name']} credit. No email sending."}
            row.status = "queued"
            row.save()
            DiscoverySession.objects.create(run=row, action=row.pending, goal=1, unit="emails", source_ids=source_ids, target=SiteConfig.load().campaign_target)
            ChatMessage.objects.create(thread=thread, role="user", content=row.pending["summary"], data=selection)
    except IntegrityError:
        return error("Another task started. Refresh and review your active task.", 409)
    chat.launch(request, row)
    row.refresh_from_db()
    return JsonResponse({"run": chat.run_payload(row)}, status=202)
