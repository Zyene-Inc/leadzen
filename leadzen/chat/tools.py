"""Typed, bounded capabilities over existing Workspace services. No shell or URLs."""
import inspect
import json
import os
import uuid
from contextvars import ContextVar
from datetime import timedelta
from typing import Literal

from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from leadzen.config.models import ChatRun, DiscoverySession, ReviewedEmail, SiteConfig
from leadzen.crm import contact_payload, owned_contact
from leadzen.chat.context import remember, structured

approved = ContextVar("chat_confirmed_action", default=None)


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Arguments):
    pass


class Lead(Arguments):
    leadId: StrictInt = Field(gt=0)


class Leads(Arguments):
    leadIds: list[StrictInt] = Field(min_length=1, max_length=25)

    @field_validator("leadIds")
    @classmethod
    def distinct(cls, ids):
        if any(i < 1 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Choose distinct canonical lead IDs")
        return ids


class Drafts(Leads):
    instructions: str = Field(default="", max_length=4000)


class Draft(Arguments):
    draftId: str = Field(pattern=r"^[0-9a-f-]{36}$")


class Edit(Draft):
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10000)
    instructions: str = Field(default="", max_length=4000)


class Regenerate(Draft):
    instructions: str = Field(default="", max_length=4000)


class Send(Draft):
    approvalToken: str | None = None  # Injected by the server only after human confirmation.


class SendMany(Arguments):
    draftIds: list[str] = Field(min_length=1, max_length=25)
    approvalToken: str | None = None

    @field_validator("draftIds")
    @classmethod
    def distinct(cls, ids):
        canonical = [str(uuid.UUID(i)) for i in ids]
        if len(set(canonical)) != len(canonical):
            raise ValueError("Choose distinct canonical draft IDs")
        return canonical


class Thread(Arguments):
    threadId: StrictInt = Field(gt=0)


class Reply(Thread):
    instructions: str = Field(default="", max_length=4000)


class Stop(Arguments):
    runId: str = Field(pattern=r"^[0-9a-f-]{36}$")


class Suppress(Lead):
    reason: str = Field(default="", max_length=170)


class Filters(Arguments):
    query: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=200)
    stage: Literal["all", "qualified", "email_found", "contacted", "replied", "suppressed"] = "all"
    since: str | None = None  # ISO date/time, validated below.
    limit: StrictInt = Field(default=25, ge=1, le=25)

    @field_validator("since")
    @classmethod
    def valid_date(cls, value):
        if value:
            from django.utils.dateparse import parse_datetime, parse_date
            if not (parse_datetime(value) or parse_date(value)):
                raise ValueError("Choose an ISO date or timestamp")
        return value


class List(Arguments):
    filters: Filters = Field(default_factory=Filters)


class TargetOverrides(Arguments):
    audience: str = Field(default="", max_length=2000)
    similarLeadId: StrictInt | None = Field(default=None, gt=0)


class Find(Arguments):
    count: StrictInt = Field(ge=1, le=25)
    includeEmails: Literal[False] = False
    targetOverrides: TargetOverrides | None = None


class Target(Arguments):
    industry: str = Field(max_length=300)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    company_size: str
    roles: list[str] = Field(min_length=1, max_length=20)
    seniority: list[str] = Field(min_length=1, max_length=20)
    instructions: str = Field(default="", max_length=5000)


class NewContact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    company: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=500)
    profile_text: str = Field(default="", max_length=10000)
    opted_in: bool = False
    consent_note: str = Field(default="", max_length=500)


class NewContacts(Arguments):
    contacts: list[NewContact] = Field(min_length=1, max_length=5)


SCHEMAS = {
    "get_workspace_status": Empty, "get_workspace_context": Empty, "get_target": Empty, "update_target": Target,
    "stop_discovery": Stop, "get_lead": Lead, "find_work_emails": Leads, "get_credit_usage": Empty,
    "create_drafts": Drafts, "get_draft": Draft, "update_draft": Edit, "regenerate_draft": Regenerate,
    "send_email": Send, "send_emails": SendMany, "sync_mailbox": Empty, "get_thread": Thread,
    "draft_reply": Reply, "send_reply": Send, "suppress_contact": Suppress, "unsuppress_contact": Lead,
    "get_activity": List, "add_contacts": NewContacts,
}
CONFIRMED = {"find_work_emails", "send_email", "send_emails", "send_reply", "unsuppress_contact"}
SEND_TOOLS = {"send_email", "send_emails", "send_reply"}


def normalize(tool, args):
    schema = SCHEMAS.get(tool)
    if tool == "find_leads" and "emails" not in args:
        schema = Find
    if tool in {"list_leads", "list_replies"} and "filters" in args:
        schema = List
    if schema:
        value = schema.model_validate(args).model_dump()
        if value.get("approvalToken") is not None:
            raise ValueError("Only the backend can issue a sending approval token")
        return value
    return None


def invoke(row, view, body=None, method="GET", **parameters):
    """Bounded compatibility adapter to existing validated Workspace operations.

    A worker has no HTTP session. Actor/access are server-owned and checked before
    invoking the same handler implementation; neither view nor route is model-selected.
    """
    from django.contrib.auth import get_user_model
    from django.test.client import RequestFactory
    from leadzen.outreach import actor_live
    actor_live(row.actor_id)
    alias = "control" if os.environ.get("LEADZEN_CONTROL_DB") else "default"
    actor = get_user_model().objects.using(alias).get(pk=row.actor_id)
    request = RequestFactory().generic(method, "/internal-chat-capability", json.dumps(body or {}), content_type="application/json")
    request.actor = actor
    response = inspect.unwrap(view)(request, **parameters)
    result = json.loads(response.content)
    if response.status_code >= 400:
        raise ValueError(result.get("error", "Workspace operation could not complete"))
    return result


def lead_rows(ids):
    rows = [owned_contact(i) for i in ids]
    if any(d is None for d in rows):
        raise ValueError("One or more leads are unavailable in this Workspace")
    return rows


def draft_rows(row, ids):
    rows = [ReviewedEmail.objects.select_related("review", "deal__lead", "reply_to").filter(pk=i, review__actor_id=row.actor_id).first() for i in ids]
    if any(d is None for d in rows):
        raise ValueError("Draft not found in your Workspace")
    return rows


def enrichment(ids):
    from leadzen.crm import source_profile
    from leadzen.discovery_progress import safe_profile
    from leadzen.config.models import DiscoveryLookup
    from openoutfind.crm.models import Deal as Decision
    from cold_outreach.leads.models import DealState
    result = []
    for deal in lead_rows(ids):
        source = source_profile(deal)
        if not source or not safe_profile(source.profile_url) or source.disqualified or not Decision.objects.filter(lead=source, state__in=["Qualified", "Ready to Find Email"]).exclude(outcome="wrong_fit").exists():
            raise ValueError("Choose qualified saved discovery profiles for work-email lookup")
        if deal.state != DealState.READY or deal.lead.email or source.email or DiscoveryLookup.objects.filter(source_id=source.pk).exists():
            raise ValueError("A selected lead was stopped, already has email, or has an existing lookup. Review its saved result.")
        result.append(source.pk)
    return result


def send_preview(row, args, tool):
    from leadzen import outreach
    from leadzen.mailboxes import active_mailboxes
    ids = args.get("draftIds") or [args["draftId"]]
    drafts = draft_rows(row, ids)
    box = active_mailboxes().first()
    if not box:
        raise ValueError("Connect the sending mailbox first")
    recipients = []
    for d in drafts:
        r = d.review
        if r.status != "draft" or d.state != "pending" or not d.subject or not d.body or outreach.context_hash(r) != r.context_hash or r.created_at < timezone.now() - timedelta(hours=1):
            raise ValueError("Draft or context changed. Create a fresh draft before sending")
        if (tool == "send_reply") != (r.kind == "reply"):
            raise ValueError("Use send_reply for a reply and send_email/send_emails for initial outreach")
        reason = outreach.blocked(d.deal, r.kind, d.reply_to)
        if reason:
            raise ValueError(reason)
        outreach.provider_policy(r.kind)
        if box.from_address != r.from_address or (r.kind == "reply" and d.deal.mailbox_id != box.pk):
            raise ValueError("Restore the draft's sending mailbox")
        data = next(i for i in outreach.review_payload(r)["drafts"] if i["id"] == str(d.pk))
        recipients.append({"id": str(d.pk), "leadId": d.deal_id, "name": data["name"], "email": data["to"], "from_address": r.from_address, "subject": data["subject"], "body": data["preview_body"]})
    return {"from_address": box.from_address, "recipients": recipients, "note": "Only these exact messages are approved. Sending hours, pacing, suppression and new replies are checked again before delivery."}


def snapshot_data(row, tool, args):
    from leadzen import outreach
    if tool in SEND_TOOLS:
        drafts = draft_rows(row, args.get("draftIds") or [args["draftId"]])
        return [{"id": str(d.pk), "actor": d.review.actor_id, "state": d.state, "review_status": d.review.status,
                 "hash": outreach.draft_hash(d), "live_context": outreach.context_hash(d.review), "recipient": contact_payload(d.deal),
                 "blocked": outreach.blocked(d.deal, d.review.kind, d.reply_to)} for d in drafts]
    if tool == "find_work_emails":
        from leadzen.discovery_progress import selected_identity
        return {"source": selected_identity(enrichment(args["leadIds"])), "contacts": [contact_payload(d) for d in lead_rows(args["leadIds"])]}
    if tool == "unsuppress_contact":
        from cold_outreach.leads.models import Suppression
        d = lead_rows([args["leadId"]])[0]
        return {"lead": contact_payload(d), "records": list(Suppression.objects.filter(email__iexact=d.lead.email).values())}
    return {}


def setup_session(row, tool, args):
    if tool not in {"find_leads", "find_work_emails"}:
        return
    if DiscoverySession.objects.filter(run=row).exists():
        if tool == "find_leads" and "emails" in args and DiscoverySession.objects.get(run=row).action.get("single_action"):
            return
        raise ValueError("One discovery action per turn. Ask for the next search in a new message")
    if tool == "find_leads" and "emails" in args:
        return
    from leadzen.chat.engine import snapshot
    from leadzen.discovery import context
    from leadzen.discovery_progress import selected_identity
    setup = context(row.actor_id)
    if not setup["ready"]:
        raise ValueError(" ".join(setup["blockers"]))
    sources = enrichment(args["leadIds"]) if tool == "find_work_emails" else []
    engine = engine_find_args(args) if tool == "find_leads" else {"count": len(sources), "emails": True, "audience": ""}
    action = {"id": str(uuid.uuid4()), "tool": "find_leads", "summary": "Continue the remaining discovery goal", "arguments": engine, "snapshot": snapshot("find_leads", engine), "approved": True, "single_action": True}
    if sources:
        action["source_identity"] = selected_identity(sources)
    DiscoverySession.objects.create(run=row, goal=engine["count"], unit="emails" if engine["emails"] else "leads", source_ids=sources, action=action, target=engine["audience"] or SiteConfig.load().campaign_target)
    # A free run needs the same bounded checkpoint lease as Workspace discovery.
    # Paid enrichment retains the human approval's original expiration.
    if not row.approval_expires_at:
        row.approval_expires_at = timezone.now() + timedelta(minutes=15)
        row.save(update_fields=["approval_expires_at"])
    remember(row, currentRunId=str(row.pk))


def engine_find_args(args):
    if "emails" in args:
        return args
    overrides = args.get("targetOverrides") or {}
    audience = overrides.get("audience", "")
    if overrides.get("similarLeadId"):
        d = lead_rows([overrides["similarLeadId"]])[0]
        audience = (audience or SiteConfig.load().campaign_target) + f"\nFind similar roles and companies to this saved contact: {d.lead.title} at {d.lead.company}."
    return {"count": args["count"], "emails": False, "audience": audience[:2000]}


def drafts_result(row, review):
    remember(row, currentDraftId=review["drafts"][0]["id"], selectedLeadIds=[d.deal_id for d in ReviewedEmail.objects.filter(review_id=review["id"]).order_by("deal_id")])
    return {**review, "workspaceUrl": f"/sending?review={review['id']}"}


def send_confirmed(row, tool, args):
    from leadzen import outreach
    from leadzen.config.models import OutreachJob, EmailReview
    from leadzen.mailboxes import prepare_worker_mailbox
    from leadzen.workspaces import guard_worker_sends
    send_preview(row, args, tool)  # Recheck the exact eligibility after approval.
    drafts = draft_rows(row, args.get("draftIds") or [args["draftId"]])
    prepare_worker_mailbox(require_ai=False)
    guard_worker_sends()
    accepted = 0
    jobs = []
    groups = {}
    for d in drafts:
        groups.setdefault(d.review_id, []).append(d)
    for group in groups.values():
        from leadzen.chat.engine import assert_action_access
        assert_action_access()
        r = group[0].review
        with transaction.atomic(using=ReviewedEmail.objects.all().db):
            if OutreachJob.objects.filter(status__in=["queued", "running"]).exists():
                raise ValueError("An outreach job is already running")
            for d in group:
                d.approved_hash = outreach.draft_hash(d)
                d.save(update_fields=["approved_hash"])
            job = OutreachJob.objects.create(kind="reviewed", request_id=uuid.uuid4(), requested_count=len(group), status="running", started_at=timezone.now(),
                campaign_approval={"review_id": str(r.pk), "draft_ids": [str(d.pk) for d in group], "snapshot": outreach.review_hash(r),
                                   "chat_run_id": str(row.pk), "expires_at": (timezone.now() + timedelta(minutes=15)).isoformat()})
            EmailReview.objects.filter(pk=r.pk).update(status="queued")
        try:
            sent = outreach.run_review(job, wait=False)
        except Exception:
            OutreachJob.objects.filter(pk=job.pk).update(status="failed", finished_at=timezone.now())
            EmailReview.objects.filter(pk=r.pk, status__in=["queued", "running"]).update(status="failed")
            raise
        OutreachJob.objects.filter(pk=job.pk).update(status="succeeded", output=json.dumps({"accepted": sent}), finished_at=timezone.now())
        accepted += sent
        jobs.append(str(job.pk))
    return {"accepted": accepted, "requested": len(drafts), "jobs": jobs, "from_address": drafts[0].review.from_address,
            "drafts": [next(i for i in outreach.review_payload(d.review)["drafts"] if i["id"] == str(d.pk)) for d in draft_rows(row, [str(d.pk) for d in drafts])],
            "note": "Only accepted messages were sent. Remaining messages may be deferred; no automatic retry was scheduled.", "workspaceUrl": "/sending"}


def execute(row, tool, args):
    from leadzen import outreach
    if tool in CONFIRMED:
        capability = approved.get()
        if not capability or capability["tool"] != tool or capability["arguments"] != ({**args, "approvalToken": None} if tool in SEND_TOOLS else args) or capability.get("used") or capability["actor_id"] != row.actor_id or capability["run_id"] != str(row.pk):
            raise PermissionError("This action requires a server-issued, one-time human approval")
        if tool in SEND_TOOLS and args.get("approvalToken") != capability["id"]:
            raise PermissionError("Sending approval token is invalid")
        capability["used"] = True
    if tool in SEND_TOOLS:
        return send_confirmed(row, tool, args)
    if tool == "get_workspace_context":
        return structured(row.actor_id, row.thread.context)
    if tool == "get_workspace_status":
        from leadzen.home import summary
        return summary()
    if tool == "get_credit_usage":
        from leadzen.home import summary
        from leadzen.config.models import DiscoveryLookup
        from django.db.models import Sum
        return {"balance": summary()["credits"], "reported_usage": float(DiscoveryLookup.objects.aggregate(total=Sum("credits"))["total"] or 0), "uncertain_lookups": DiscoveryLookup.objects.filter(credits__isnull=True).count()}
    if tool in {"get_target", "update_target"}:
        from leadzen.home import target
        return invoke(row, target, {"audience": args, "confirmed": True, "accepted_legal_notice": SiteConfig.load().accepted_legal_notice}, "PUT") if tool == "update_target" else invoke(row, target)
    if tool == "get_lead":
        deal = lead_rows([args["leadId"]])[0]
        remember(row, currentLeadId=deal.pk)
        return {**contact_payload(deal, detail=True), "workspaceUrl": f"/contacts/{deal.pk}"}
    if tool == "stop_discovery":
        target = ChatRun.objects.filter(pk=args["runId"], actor_id=row.actor_id, discovery__isnull=False).first()
        if not target:
            raise ValueError("Discovery run not found")
        ChatRun.objects.filter(pk=target.pk, status__in=["queued", "running", "paused"]).update(cancel_requested=True)
        ChatRun.objects.filter(pk=target.pk, status__in=["queued", "paused"]).update(status="cancelled", pending={}, finished_at=timezone.now())
        return {"stop_requested": True, "runId": str(target.pk)}
    if tool == "find_work_emails":
        from leadzen.chat.engine import find_leads
        result = find_leads({"count": len(args["leadIds"]), "emails": True, "audience": ""})
        from leadzen.discovery_progress import credits
        from leadzen.discovery import progress_payload
        session = DiscoverySession.objects.get(run=row)
        return {**result, "items": [{**contact_payload(d), "workspaceUrl": f"/contacts/{d.pk}"} for d in lead_rows(args["leadIds"])], "credits": credits(session), "discovery": progress_payload(session), "workspaceUrl": f"/find-leads/{row.pk}"}
    if tool in {"create_drafts", "draft_reply"}:
        body = {"count": len(args["leadIds"]) if tool == "create_drafts" else 1, "request_id": str(uuid.uuid4()), "instructions": args["instructions"]}
        body.update({"lead_ids": args["leadIds"]} if tool == "create_drafts" else {"thread_id": args["threadId"]})
        return drafts_result(row, invoke(row, outreach.reviews, body, "POST"))
    if tool in {"get_draft", "update_draft", "regenerate_draft"}:
        d = draft_rows(row, [args["draftId"]])[0]
        if tool == "get_draft":
            result = outreach.review_payload(d.review)
        else:
            action = "regenerate" if tool == "regenerate_draft" or args.get("instructions") else "edit"
            if action == "edit" and args.get("subject") is None and args.get("body") is None:
                raise ValueError("Provide a subject, body or revision instructions")
            result = invoke(row, outreach.draft, {"action": action, "revision": outreach.draft_hash(d), "subject": args.get("subject") if args.get("subject") is not None else d.subject,
                "body": args.get("body") if args.get("body") is not None else d.body, "instructions": args.get("instructions", "")}, "POST", review_id=d.review_id, draft_id=d.pk)
        remember(row, currentDraftId=str(d.pk))
        return {**result, "drafts": [i for i in result["drafts"] if i["id"] == str(d.pk)], "workspaceUrl": f"/sending?review={d.review_id}"}
    if tool == "get_thread":
        result = invoke(row, outreach.conversation, thread_id=args["threadId"])
        remember(row, currentThreadId=args["threadId"])
        return {**result, "workspaceUrl": f"/inbox?thread={args['threadId']}"}
    if tool in {"suppress_contact", "unsuppress_contact"}:
        from cold_outreach.leads.models import Deal, DealState, Suppression
        from leadzen.config.models import CampaignRecipient
        from leadzen.suppression import block_address
        d = lead_rows([args["leadId"]])[0]
        if tool == "unsuppress_contact":
            records = Suppression.objects.filter(email__iexact=d.lead.email)
            if not records.exists() or records.exclude(reason__startswith="Manually suppressed").exists():
                raise ValueError("Opt-outs and terminal provider suppressions cannot be removed here")
            records.delete()
            return {"id": d.pk, "suppression_removed": True, "note": "The manual address block was removed. Stopped sequences remain stopped; no sending was enabled.", "workspaceUrl": f"/contacts/{d.pk}"}
        if d.lead.email:
            block_address(d.lead.email, "Manually suppressed" + (": " + args["reason"] if args["reason"] else ""))
        else:
            with transaction.atomic(using=Deal.objects.all().db):
                Deal.objects.filter(pk=d.pk).update(state=DealState.COMPLETED, outcome="not_interested")
                CampaignRecipient.objects.filter(deal=d).exclude(status="completed").update(status="stopped")
        d.refresh_from_db()
        return {**contact_payload(d), "note": "Contact stopped. Existing sequences cannot send to this lead.", "workspaceUrl": f"/contacts/{d.pk}"}
    if tool == "get_activity":
        from leadzen.activity import feed
        result = invoke(row, feed)
        f = args["filters"]
        items = result["items"]
        if f["query"]:
            items = [i for i in items if f["query"].lower() in json.dumps(i).lower()]
        if f["since"]:
            items = [i for i in items if i["at"] >= f["since"]]
        return {"items": items[:f["limit"]], "workspaceUrl": "/activity"}
    if tool == "add_contacts":
        from leadzen import campaigns
        result = invoke(row, campaigns.add_contacts, {"contacts": args["contacts"]}, "POST")
        ids = result["ids"]
        remember(row, selectedLeadIds=ids)
        return {**result, "items": [{**contact_payload(d), "workspaceUrl": f"/contacts/{d.pk}"} for d in (owned_contact(i) for i in ids) if d], "workspaceUrl": "/contacts"}
    raise ValueError("Unsupported Workspace capability")
