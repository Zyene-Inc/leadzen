"""Bounded standing authorization for scheduled outreach, separate from human review."""
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from leadzen.accounts.service import access, error, payload
from leadzen.config.models import AutopilotPolicy, AutopilotRun, CampaignRecipient, SiteConfig
from leadzen.timezone import NEW_YORK, TIME_ZONE

_current = ContextVar("autopilot_run", default=None)
_delivery = ContextVar("autopilot_delivery", default=None)
LIMITS = {"daily_contacts": (1, 25, 10), "monthly_contacts": (1, 500, 200),
          "daily_credits": (1, 25, 10), "monthly_credits": (1, 500, 200),
          "daily_ai_requests": (1, 200, 60), "monthly_ai_requests": (1, 4000, 1200),
          "authorization_days": (1, 90, 30)}


class ContactStopped(PermissionError):
    """A recipient stopped normally; this is not an Autopilot service failure."""


def enabled():
    return os.environ.get("LEADZEN_AUTOPILOT_ENABLED") == "1"


def setup_hash():
    from leadzen.chat.engine import snapshot
    from leadzen.mailboxes import active_mailboxes
    return hashlib.sha256(json.dumps({"setup": snapshot("find_leads", {}),
        "mailboxes": list(active_mailboxes().order_by("pk").values("from_address", "signature"))}, sort_keys=True).encode()).hexdigest()


def setup(actor_id):
    from leadzen.discovery import context
    from leadzen.configuration import effective
    from leadzen.outreach import provider_policy
    from leadzen.sending_schedule import get_schedule
    values, config = effective(), SiteConfig.load()
    blockers = list(context(actor_id)["blockers"])
    if not values.mailbox_address or not (values.mailbox_password if values.mail_transport == "smtp" else values.mail_api_key):
        blockers.append("Connect a sending mailbox in Settings.")
    if not values.imap_host or not (values.imap_password or values.mailbox_password):
        blockers.append("Connect Inbox so replies can stop follow-ups.")
    try:
        provider_policy("initial")
    except ValueError as exc:
        blockers.append(str(exc))
    return {"revision": setup_hash(), "blockers": blockers, "target": config.campaign_target,
            "product": config.product_docs, "sender": values.mailbox_address, "signature": values.signature,
            "booking_link": config.booking_link, "service_enabled": enabled(),
            "sending_schedule": get_schedule(config)}


def local_now(policy, now=None):
    return timezone.localtime(now or timezone.now(), NEW_YORK)


def sending_schedule(policy, *, initial=False):
    """New approvals use Settings; historical approvals keep their saved window."""
    if "sending_schedule" in policy.scope:
        from leadzen.sending_schedule import normalize_schedule
        saved = policy.scope["sending_schedule"]
        return normalize_schedule({**saved, "timezone": TIME_ZONE})
    return {"timezone": TIME_ZONE, "days": [0, 1, 2, 3, 4],
            "start": "10:00" if initial else "09:00", "end": "17:00"}


def start_schedule(policy):
    schedule = sending_schedule(policy, initial=True)
    hour, minute = map(int, schedule["start"].split(":"))
    finish = min(hour * 60 + minute + 120, int(schedule["end"][:2]) * 60 + int(schedule["end"][3:]))
    return {**schedule, "end": f"{finish // 60:02}:{finish % 60:02}"}


def within_start_window(policy, now=None):
    from leadzen.sending_schedule import within_window
    return within_window(now, start_schedule(policy))


def within_delivery_window(policy, now=None, *, initial=False):
    from leadzen.sending_schedule import within_window
    return within_window(now, sending_schedule(policy, initial=initial))


def next_start(policy):
    from leadzen.sending_schedule import next_open
    now = local_now(policy)
    has_run = AutopilotRun.objects.filter(actor_id=policy.actor_id, workday=now.date()).exists()
    if has_run:
        now = datetime.combine(now.date() + timedelta(days=1), time(), NEW_YORK)
    return next_open(now, start_schedule(policy))


def policy_payload(row):
    changed = row.setup_hash != setup_hash() or not policy_clock_matches(row)
    scope = {**row.scope, "timezone": TIME_ZONE}
    if "sending_schedule" in scope:
        scope["sending_schedule"] = sending_schedule(row)
    return {"id": str(row.pk), "enabled": row.enabled, "scope": scope,
            "expires_at": row.expires_at.isoformat(), "expires_on": str(timezone.localtime(row.expires_at, NEW_YORK).date()),
            "expired": row.expires_at <= timezone.now(),
            "heartbeat_stale": not row.heartbeat_at or timezone.now() - row.heartbeat_at > timedelta(minutes=20),
            "authorized_at": row.authorized_at.isoformat(),
            "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
            "issue": row.issue, "setup_changed": changed,
            "next_start": next_start(row).isoformat() if not changed and row.enabled and row.expires_at > timezone.now() else None}


def policy_clock_matches(policy):
    return policy.scope.get("timezone") == TIME_ZONE and ("sending_schedule" not in policy.scope
        or isinstance(policy.scope["sending_schedule"], dict) and policy.scope["sending_schedule"].get("timezone") == TIME_ZONE)


def state(actor_id):
    row = AutopilotPolicy.objects.filter(actor_id=actor_id).order_by("-authorized_at").first()
    runs = AutopilotRun.objects.filter(actor_id=actor_id).order_by("-workday")[:10]
    return {"setup": setup(actor_id), "policy": policy_payload(row) if row else None,
            "runs": [{"id": str(r.pk), "workday": str(r.workday), "phase": r.phase, "issue": r.issue,
                      "ai_requests": r.model_requests, "reserved_credits": r.email_credits,
                      "contacts": r.checkpoint.get("contacts", 0),
                      "discovery_ids": [r.checkpoint[k] for k in ("discovery_id", "enrichment_id") if r.checkpoint.get(k)],
                      "accepted": sum(c.recipients.aggregate(n=Sum("next_step"))["n"] or 0 for c in r.campaigns.all()),
                      "campaign_ids": [str(c.pk) for c in r.campaigns.all()]} for r in runs]}


def disable(row):
    row.enabled, row.disabled_at = False, timezone.now()
    row.save(update_fields=["enabled", "disabled_at"])
    CampaignRecipient.objects.filter(campaign__autopilot_run__policy=row, status="pending").update(status="stopped")
    from leadzen.config.models import ChatRun
    run_ids = [r.checkpoint.get(key) for r in row.runs.all() for key in ("discovery_id", "enrichment_id") if r.checkpoint.get(key)]
    ChatRun.objects.filter(pk__in=run_ids, status__in=["queued", "running", "paused"]).update(cancel_requested=True, status="cancelled", finished_at=timezone.now())
    AutopilotRun.objects.filter(policy=row).exclude(phase__in=["completed", "needs_attention", "stopped"]).update(phase="stopped", updated_at=timezone.now())


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def settings(request):
    if request.method == "GET":
        return JsonResponse(state(request.actor.pk))
    body = payload(request)
    request_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    with transaction.atomic(using=AutopilotPolicy.objects.all().db):
        if body.get("enabled") is False:
            for row in AutopilotPolicy.objects.filter(actor_id=request.actor.pk, enabled=True):
                disable(row)
        else:
            if body.get("enabled") is not True or body.get("authorize_automatic_outreach") is not True:
                return error("Explicit authorization for recurring paid lookups, AI, inbox checks and sending is required")
            try:
                identifier = uuid.UUID(str(body.get("request_id", "")))
            except ValueError:
                return error("A unique authorization request ID is required")
            existing = AutopilotPolicy.objects.filter(pk=identifier).first()
            if existing:
                if existing.actor_id != request.actor.pk or existing.scope.get("request_hash") != request_hash:
                    return error("Authorization request already used", 409)
                return JsonResponse(state(request.actor.pk))
            current_setup = setup(request.actor.pk)
            if body.get("revision") != current_setup["revision"]:
                return error("Your setup changed. Review the current target, offer and mailbox again.", 409)
            if current_setup["blockers"]:
                return error(" ".join(current_setup["blockers"]), 409)
            scope = {}
            for key, (low, high, default) in LIMITS.items():
                value = body.get(key, default)
                if type(value) is not int or not low <= value <= high:
                    return error(f"{key.replace('_', ' ').capitalize()} must be {low}–{high}")
                scope[key] = value
            for daily, monthly in [("daily_contacts", "monthly_contacts"), ("daily_credits", "monthly_credits"), ("daily_ai_requests", "monthly_ai_requests")]:
                if scope[daily] > scope[monthly]:
                    return error("Monthly limits must cover at least one daily limit")
            # Schedule and timezone are read from the employee's Settings, never
            # minted by a browser or model in a standing-authorization request.
            schedule = current_setup["sending_schedule"]
            zone = schedule["timezone"]
            delays = body.get("followup_days", [3, 5])
            tone = body.get("tone", "Brief, professional and helpful")
            if not isinstance(delays, list) or len(delays) > 2 or any(type(d) is not int or not 1 <= d <= 30 for d in delays):
                return error("Choose up to two follow-ups, each 1–30 working days after the previous email")
            if not isinstance(tone, str) or not tone.strip() or len(tone) > 500:
                return error("Enter writing guidance of up to 500 characters")
            scope.update(timezone=zone, sending_schedule=schedule, followup_days=delays, tone=tone.strip(), request_hash=request_hash,
                         **{k: current_setup[k] for k in ("target", "product", "sender", "signature", "booking_link")})
            for row in AutopilotPolicy.objects.filter(actor_id=request.actor.pk, enabled=True):
                disable(row)
            AutopilotPolicy.objects.create(id=identifier, actor_id=request.actor.pk, scope=scope,
                setup_hash=current_setup["revision"], expires_at=timezone.now() + timedelta(days=scope["authorization_days"]))
    return JsonResponse(state(request.actor.pk))


def check_policy(policy):
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()
    policy.refresh_from_db()
    actor = os.environ.get("LEADZEN_ACTOR_ID")
    if (not enabled() or not policy.enabled or policy.expires_at <= timezone.now()
            or (actor and actor != str(policy.actor_id)) or policy.setup_hash != setup_hash()
            or not policy_clock_matches(policy)):
        raise PermissionError("Autopilot is off, expired, or its setup changed. Review and enable it again.")


@contextmanager
def execution(run):
    token = _current.set(run.pk)
    try:
        yield
    finally:
        _current.reset(token)


def external_guard(*, reserve_model=False, reserve_credit=False):
    """Called by actual AI/provider sinks; persistent conservative reservations."""
    delivery = _delivery.get()
    if delivery:
        send_guard(*delivery)
    identifier = _current.get()
    if not identifier:
        return
    with transaction.atomic(using=AutopilotRun.objects.all().db):
        run = AutopilotRun.objects.select_related("policy").get(pk=identifier)
        check_policy(run.policy)
        local = local_now(run.policy)
        if (run.phase in {"stopped", "needs_attention"} or not run.deadline_at or run.deadline_at <= timezone.now()
                or local.date() != run.workday or not within_delivery_window(run.policy, local, initial=True)):
            raise PermissionError("Today's Autopilot work stopped or its execution window ended")
        scope = run.policy.scope
        for reserve, field, daily, monthly in [(reserve_model, "model_requests", "daily_ai_requests", "monthly_ai_requests"),
                                               (reserve_credit, "email_credits", "daily_credits", "monthly_credits")]:
            if not reserve:
                continue
            total = AutopilotRun.objects.filter(actor_id=run.actor_id, workday__year=run.workday.year, workday__month=run.workday.month).aggregate(n=Sum(field))["n"] or 0
            if getattr(run, field) >= scope[daily] or total >= scope[monthly]:
                raise PermissionError("Autopilot's approved provider budget is exhausted")
            setattr(run, field, getattr(run, field) + 1)
            run.save(update_fields=[field, "updated_at"])


def recipient_hash(campaign, recipient):
    from leadzen.followups import fingerprint
    return hashlib.sha256(json.dumps({"base": fingerprint(campaign, recipient), "steps": recipient.personal_steps,
        "run": str(campaign.autopilot_run_id)}, sort_keys=True).encode()).hexdigest()


def send_guard(campaign, recipient, own_message=None):
    campaign.refresh_from_db()
    recipient.refresh_from_db()
    run = campaign.autopilot_run
    check_policy(run.policy)
    now = local_now(run.policy)
    from cold_outreach.leads.models import Suppression, DealState
    from cold_outreach.emails.models import Message, Direction
    from leadzen.config.models import ContactPreferences, ReviewedEmail
    deal = recipient.deal
    # Recheck address-level dedup after preparation too. A different canonical
    # contact may acquire a manual draft/send while this recipient waits in queue.
    duplicate_initial = recipient.next_step == 0 and (
        deal.state != DealState.READY
        or Message.objects.filter(direction=Direction.OUTBOUND, to_address__iexact=deal.lead.email).exclude(pk=own_message).exists()
        or ReviewedEmail.objects.filter(deal__lead__email__iexact=deal.lead.email, state__in=["pending", "sending", "accepted", "sent", "review"]).exists()
        or CampaignRecipient.objects.filter(deal__lead__email__iexact=deal.lead.email).exclude(pk=recipient.pk).exists())
    if (deal.state == DealState.COMPLETED or Suppression.objects.filter(email__iexact=deal.lead.email).exists()
            or ContactPreferences.objects.filter(lead=deal.lead, deleted_at__isnull=False).exists()
            or duplicate_initial
            or (deal.thread_id and Message.objects.filter(thread_id=deal.thread_id, direction=Direction.INBOUND).exists())):
        # This is a terminal recipient decision, not a mailbox/policy failure.
        # Persist it even at the transport boundary so the due queue can advance.
        CampaignRecipient.objects.filter(pk=recipient.pk, status__in=["pending", "sending"]).update(status="stopped")
        recipient.status = "stopped"
        raise ContactStopped("This contact stopped or replied")
    if (not run.checkpoint.get("delivery_authorized") or campaign.status != "active" or recipient.status not in {"pending", "sending"}
            or not recipient.personal_steps or recipient.authorization_hash != recipient_hash(campaign, recipient)
            or (recipient.next_step == 0 and now.date() != run.workday)):
        raise PermissionError("This message is outside its Autopilot authorization")
    if not within_delivery_window(run.policy, now, initial=recipient.next_step == 0):
        from leadzen.transports import SendingWindowClosed
        raise SendingWindowClosed("Sending resumes during your selected days and hours")


@contextmanager
def delivery_scope(campaign, recipient, own_message=None):
    token = _delivery.set((campaign, recipient, own_message) if campaign.autopilot_run_id else None)
    try:
        yield
    finally:
        _delivery.reset(token)
