"""Employee-scoped contacts and manually authored email sequences."""
import re
import uuid
import copy
from datetime import timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from leadzen.timezone import NEW_YORK, TIME_ZONE
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from cold_outreach.leads.models import Deal, DealState, Lead, Outcome, Suppression
from cold_outreach.emails.models import Direction, Message
from leadzen.accounts.service import access, email_address, error, payload
from leadzen.config.models import CampaignRecipient, ContactPreferences, EmailCampaign
from leadzen.configuration import SettingsError, effective
from leadzen.sending_schedule import within_sending_window
from leadzen.transports import SendingWindowClosed

FIELDS = {"first_name": 100, "last_name": 100, "company": 200, "title": 200, "website": 500, "profile_text": 10000}
TAGS = {"first_name", "last_name", "company", "sender_name", "booking_link"}
OFFER_FIELDS = ("target", "product", "booking_link", "signature", "delay_basis")


def offer_values(body, existing=None):
    values = {}
    for key in OFFER_FIELDS:
        value = body.get(key, getattr(existing, key, "calendar_days" if key == "delay_basis" else ""))
        maximum = 500 if key == "booking_link" else 2000
        if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and (key != "signature" or c not in "\n\t") for c in value):
            raise ValueError(f"Enter valid {key.replace('_', ' ')} of up to {maximum} characters")
        values[key] = value.strip()
    if values["delay_basis"] not in {"calendar_days", "working_days"}:
        raise ValueError("Choose working days or calendar days")
    if values["booking_link"]:
        url = urlsplit(values["booking_link"])
        if url.scheme != "https" or not url.hostname or url.username or url.password or any(c.isspace() for c in values["booking_link"]):
            raise ValueError("Enter an HTTPS booking link without credentials or whitespace")
    return values


def contact_values(body, *, allow_empty_email=False):
    values = {"email": "" if allow_empty_email and body.get("email") == "" else email_address(body.get("email"))}
    for key, maximum in FIELDS.items():
        value = body.get(key, "")
        if not isinstance(value, str) or len(value) > maximum or (key != "profile_text" and any(ord(c) < 32 for c in value)):
            raise ValueError(f"{key} is invalid or too long")
        values[key] = value.strip()
    opted_in = body.get("opted_in", False)
    note = body.get("consent_note", "")
    if not isinstance(opted_in, bool) or not isinstance(note, str) or len(note) > 500:
        raise ValueError("Enter valid consent details")
    if opted_in and not note.strip():
        raise ValueError("Describe when and how this contact opted in")
    return values, {"opted_in": opted_in, "consent_note": note.strip()}


@csrf_exempt
@require_http_methods(["POST"])
@access(workspace=True)
def add_contacts(request):
    body = payload(request)
    rows = body.get("contacts", [body])
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100 or any(not isinstance(row, dict) for row in rows):
        return error("Add between 1 and 100 contacts per import")
    validated = [contact_values(row) for row in rows]
    if len({values["email"] for values, _ in validated}) != len(validated):
        return error("The import contains duplicate email addresses")
    alias = Lead.objects.all().db
    with transaction.atomic(using=alias):
        if Lead.objects.filter(email__in=[v["email"] for v, _ in validated]).exists():
            return error("A contact with one of these email addresses already exists. Edit that contact instead.", 409)
        ids = []
        for values, preferences in validated:
            lead = Lead.objects.create(lead_id=f"manual-{uuid.uuid4().hex}", **values)
            deal = Deal.objects.create(lead=lead, reason="Added by employee")
            ContactPreferences.objects.create(lead=lead, **preferences)
            if Suppression.objects.filter(email__iexact=lead.email).exists():
                deal.state, deal.outcome = DealState.COMPLETED, Outcome.UNSUBSCRIBED
                deal.save()
            ids.append(deal.pk)
    return JsonResponse({"ids": ids, "created": len(ids)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@access(workspace=True)
def contact(request, deal_id):
    deal = Deal.objects.select_related("lead").filter(pk=deal_id).first()
    if deal is None:
        return error("Contact not found", 404)
    if request.method == "GET":
        if ContactPreferences.objects.filter(lead=deal.lead, deleted_at__isnull=False).exists():
            return error("Contact not found", 404)
        from leadzen.crm import contact_payload
        return JsonResponse(contact_payload(deal, detail=True))
    alias = Deal.objects.all().db
    with transaction.atomic(using=alias):
        removed = ContactPreferences.objects.filter(lead=deal.lead, deleted_at__isnull=False).exists()
        if request.method == "DELETE":
            if deal.state != DealState.COMPLETED:
                deal.state, deal.outcome = DealState.COMPLETED, Outcome.NOT_INTERESTED
                deal.save()
            if not removed:
                ContactPreferences.objects.update_or_create(lead=deal.lead, defaults={"deleted_at": timezone.now()})
            CampaignRecipient.objects.filter(deal=deal).exclude(status="completed").update(status="stopped")
            return JsonResponse({"ok": True})
        if removed:
            return error("Contact not found", 404)
        body = payload(request)
        if body.get("stop") is True:
            if deal.state != DealState.COMPLETED:
                deal.state, deal.outcome = DealState.COMPLETED, Outcome.NOT_INTERESTED
                deal.save()
            CampaignRecipient.objects.filter(deal=deal).exclude(status="completed").update(status="stopped")
            return JsonResponse({"ok": True})
        if body.get("suppress") is True:
            if not deal.lead.email:
                return error("No email address is saved. Stop this lead instead.")
            from leadzen.suppression import block_address
            block_address(deal.lead.email, "Employee recorded opt-out")
            return JsonResponse({"ok": True})
        values, preferences = contact_values(body, allow_empty_email=not deal.lead.email)
        if values["email"] != deal.lead.email:
            return error("Email identity cannot be changed. Add a separate contact to preserve conversation history.")
        for key, value in values.items():
            setattr(deal.lead, key, value)
        deal.lead.save()
        ContactPreferences.objects.update_or_create(lead=deal.lead, defaults=preferences)
    return JsonResponse({"ok": True})


def campaign_payload(campaign):
    recipients = campaign.recipients.select_related("deal__lead")
    return {"id": str(campaign.pk), "name": campaign.name, "status": campaign.status,
            "automatic_followups": bool(campaign.followup_approval.get("recipients")),
            "autopilot": bool(campaign.autopilot_run_id),
            "followup_issue": campaign.followup_approval.get("issue", ""),
            **{key: getattr(campaign, key) for key in OFFER_FIELDS}, "delay_timezone": TIME_ZONE,
            "sending_schedule": campaign_schedule(campaign, automatic=bool(campaign.followup_approval.get("recipients"))),
            "category": campaign.category, "steps": campaign.steps, "from_address": campaign.from_address,
            "recipients": [{"id": r.deal_id, "email": r.deal.lead.email, "status": r.status,
                            "personal_steps": r.personal_steps, "next_step": r.next_step, "next_send_at": r.next_send_at.isoformat() if r.next_send_at else None} for r in recipients[:100]],
            "total": recipients.count(), "sent": recipients.filter(next_step__gt=0).count()}


def validated_steps(body):
    steps = body.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
        raise ValueError("A sequence has an initial email and up to two follow-ups")
    normalized = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError("Invalid sequence step")
        subject, text, days = step.get("subject", ""), step.get("body", ""), step.get("delay_days", 0)
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 200 or any(ord(c) < 32 for c in subject):
            raise ValueError("Each step needs a subject of up to 200 characters")
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError("Each step needs a body of up to 10000 characters")
        if isinstance(days, bool) or not isinstance(days, int) or (index > 0 and not 1 <= days <= 90) or (index == 0 and days != 0):
            raise ValueError("The first step has no delay. Follow-ups must wait 1–90 days.")
        if any(tag.strip() not in TAGS for tag in re.findall(r"{{(.*?)}}", subject + text)):
            raise ValueError("Supported tags: first_name, last_name, company, sender_name, booking_link")
        normalized.append({"subject": subject.strip(), "body": text.strip(), "delay_days": days})
    return normalized


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def campaigns(request):
    if request.method == "GET":
        return JsonResponse({"items": [campaign_payload(c) for c in EmailCampaign.objects.order_by("-created_at")[:100]]})
    body = payload(request)
    return create_campaign(body)


def create_campaign(body):
    """Shared draft boundary for the workspace UI and the chat tool."""
    name = body.get("name", "")
    if not isinstance(name, str) or not name.strip() or len(name) > 160:
        return error("A campaign name of up to 160 characters is required")
    category = body.get("category", "outreach")
    if category not in {"outreach", "opted_in", "transactional"}:
        return error("Choose a valid campaign category")
    steps = validated_steps(body)
    offer = offer_values(body)
    if category == "transactional" and len(steps) != 1:
        return error("Transactional campaigns have one step")
    ids = body.get("contact_ids", [])
    if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
        return error("Select 1–100 different contacts")
    deals = list(Deal.objects.filter(pk__in=ids, lead__preferences__deleted_at__isnull=True).select_related("lead"))
    if len(deals) != len(ids):
        return error("One or more contacts do not belong to this workspace", 404)
    if any(d.state != DealState.READY or not d.lead.email or Suppression.objects.filter(email__iexact=d.lead.email).exists() for d in deals):
        return error("Choose ready contacts with an email address that have not opted out")
    if category != "outreach" and ContactPreferences.objects.filter(lead_id__in=[d.lead_id for d in deals], opted_in=True).count() != len(deals):
        return error("This campaign requires recorded recipient opt-in")
    values = effective()
    uses_resend = values.mail_transport == "resend" or (values.mail_transport == "smtp" and values.smtp_host == "smtp.resend.com")
    uses_zeptomail = values.mail_transport == "zeptomail" or (values.mail_transport == "smtp" and "zeptomail" in values.smtp_host)
    if uses_resend and category == "outreach":
        return error("Resend does not support cold outreach. Choose opted-in contacts.")
    if uses_zeptomail and (category != "transactional" or len(steps) > 1):
        return error("ZeptoMail supports single transactional emails, not outreach sequences")
    alias = EmailCampaign.objects.all().db
    with transaction.atomic(using=alias):
        if CampaignRecipient.objects.filter(deal_id__in=ids, campaign__status__in=["draft", "active", "paused"], status__in=["pending", "sending", "review"]).exists():
            return error("A selected contact is already enrolled in another campaign", 409)
        from leadzen.sending_schedule import get_schedule
        campaign = EmailCampaign.objects.create(name=name.strip(), category=category, steps=steps, from_address=values.mailbox_address,
                                               delay_timezone=get_schedule()["timezone"], **offer)
        CampaignRecipient.objects.bulk_create([CampaignRecipient(campaign=campaign, deal=d) for d in deals])
    return JsonResponse(campaign_payload(campaign), status=201)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
@access(workspace=True)
def campaign(request, campaign_id):
    row = EmailCampaign.objects.filter(pk=campaign_id).first()
    if row is None:
        return error("Campaign not found", 404)
    body = payload(request) if request.method == "PUT" else {}
    if any(key in body for key in ("steps", "name", *OFFER_FIELDS)):
        if row.autopilot_run_id:
            return error("Autopilot messages retain their saved authorization. Stop this sequence before preparing manual outreach.", 409)
        if row.status != "draft":
            return error("Only a draft sequence can be edited", 409)
        steps = validated_steps(body) if "steps" in body else row.steps
        offer = offer_values(body, row)
        name = body.get("name", row.name)
        if not isinstance(name, str) or not name.strip() or len(name) > 160:
            return error("Enter a campaign name of up to 160 characters")
        if row.category == "transactional" and len(steps) > 1:
            return error("Transactional campaigns have one step")
        row.steps, row.name = steps, name.strip()
        for key, value in offer.items():
            setattr(row, key, value)
        row.save(update_fields=["steps", "name", *OFFER_FIELDS])
        return JsonResponse(campaign_payload(row))
    status = "archived" if request.method == "DELETE" else body.get("status")
    if status not in {"active", "paused", "archived"} or row.status == "archived":
        return error("Choose active, paused or archived status")
    row.status = status
    row.save(update_fields=["status"])
    if status == "archived":
        row.recipients.update(status="stopped")
        row.followup_approval = {}
        row.save(update_fields=["followup_approval"])
    return JsonResponse(campaign_payload(row))


def render_template(value, lead, sender_name, booking_link=""):
    tags = {key: getattr(lead, key, "") for key in TAGS - {"sender_name", "booking_link"}}
    tags["sender_name"] = sender_name
    tags["booking_link"] = booking_link
    return re.sub(r"{{\s*(\w+)\s*}}", lambda match: tags.get(match[1], ""), value)


def rendered_step(campaign, step, lead, sender_name, mailbox_signature=""):
    """The same subject/body/signature for review and actual delivery."""
    return {"subject": render_template(step["subject"], lead, sender_name, campaign.booking_link),
            "body": render_template(step["body"], lead, sender_name, campaign.booking_link),
            "signature": campaign.signature or mailbox_signature}


def campaign_schedule(campaign, *, automatic=False):
    from leadzen.sending_schedule import get_schedule, is_custom
    if campaign.autopilot_run_id:
        from leadzen.autopilot import sending_schedule
        return sending_schedule(campaign.autopilot_run.policy)
    if automatic and not is_custom():
        return {"timezone": TIME_ZONE, "days": [0, 1, 2, 3, 4],
                "start": "09:00", "end": "17:00"}
    return get_schedule()


def next_send_time(campaign, sent_at, days):
    from leadzen.sending_schedule import is_custom, next_wall_open
    scoped = bool(campaign.autopilot_run_id and "sending_schedule" in campaign.autopilot_run.policy.scope)
    if is_custom() or scoped:
        schedule = campaign_schedule(campaign)
        local = timezone.localtime(sent_at, ZoneInfo(schedule["timezone"]))
        if campaign.delay_basis == "calendar_days":
            local += timedelta(days=days)
        else:
            for _ in range(days):
                local += timedelta(days=1)
                while local.weekday() not in schedule["days"]:
                    local += timedelta(days=1)
        return next_wall_open(local.replace(tzinfo=None), schedule)
    if campaign.delay_basis == "calendar_days":
        return sent_at + timedelta(days=days)
    from cold_outreach.core.business_time import is_business_day
    local = timezone.localtime(sent_at, NEW_YORK)
    for _ in range(days):
        local += timedelta(days=1)
        while not is_business_day(local.date()):
            local += timedelta(days=1)
    return local


def recipient_steps(campaign, recipient):
    return recipient.personal_steps if campaign.autopilot_run_id else campaign.steps


def initial_attempted(campaign, recipient, own_message=None):
    """Cold outreach must not reopen a previously attempted address under a new ID."""
    return (campaign.category == "outreach" and not campaign.autopilot_run_id and recipient.next_step == 0
            and Message.objects.filter(direction=Direction.OUTBOUND,
                to_address__iexact=recipient.deal.lead.email).exclude(pk=own_message).exists())


def sending_preview(campaign, count):
    from cold_outreach.emails import sender
    from leadzen.chat.engine import snapshot
    from leadzen.config.models import SiteConfig
    from leadzen.mailboxes import active_mailboxes
    box = active_mailboxes().first()
    recipients, ids = [], []
    for r in campaign.recipients.filter(status="pending").select_related("deal__lead").order_by("pk")[:100]:
        d = r.deal
        if d.state == DealState.COMPLETED or not d.lead.email or ContactPreferences.objects.filter(lead=d.lead, deleted_at__isnull=False).exists() or Suppression.objects.filter(email__iexact=d.lead.email).exists():
            continue
        if initial_attempted(campaign, r):
            continue
        if d.thread_id and Message.objects.filter(thread_id=d.thread_id, direction=Direction.INBOUND).exists():
            continue
        if campaign.category != "outreach" and not ContactPreferences.objects.filter(lead=d.lead, opted_in=True).exists():
            continue
        if r.next_send_at and r.next_send_at > timezone.now():
            continue
        steps = recipient_steps(campaign, r)
        if r.next_step >= len(steps):
            continue
        rendered = rendered_step(campaign, steps[r.next_step], d.lead, SiteConfig.load().operator_name, box.signature if box else "")
        remaining = []
        for index in range(r.next_step + 1, len(steps)):
            future = rendered_step(campaign, steps[index], d.lead, SiteConfig.load().operator_name, box.signature if box else "")
            remaining.append({"step": index + 1, "delay_days": steps[index]["delay_days"],
                              "subject": future["subject"], "body": sender._opt_out(sender._sign(future["body"], future["signature"]))})
        recipients.append({"id": r.pk, "email": d.lead.email, "step": r.next_step + 1, "subject": rendered["subject"], "body": sender._opt_out(sender._sign(rendered["body"], rendered["signature"])), "followups": remaining})
        ids.append(r.pk)
        if len(ids) >= count:
            break
    args = {"campaign_id": str(campaign.pk), "recipient_ids": ids}
    from leadzen.sending_schedule import window_payload
    return {"from_address": campaign.from_address, "count": count, "recipients": recipients,
            "window": window_payload(campaign_schedule(campaign)),
            "automatic_window": window_payload(campaign_schedule(campaign, automatic=True)),
            "revision": snapshot("send_campaign", args), "recipient_ids": ids,
            "automatic_available": __import__("os").environ.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") == "1",
            "delay_basis": campaign.delay_basis, "timezone": TIME_ZONE,
            "note": "The worker checks replies, permission, the sending schedule and pacing again. Automatic follow-ups require approving the remaining sequence below and the enabled scheduler. They use the displayed automatic sending hours and stop on any reply or opt-out. Automatic inbox checks do not call AI; classify saved replies separately in Inbox. Provider acceptance does not guarantee inbox placement."}


@require_http_methods(["GET"])
@access(workspace=True)
def preview(request, campaign_id):
    row = EmailCampaign.objects.filter(pk=campaign_id).first()
    if not row:
        return error("Campaign not found", 404)
    try:
        count = int(request.GET.get("count", "1"))
    except ValueError:
        return error("Enter a count from 1 to 25")
    if not 1 <= count <= 25:
        return error("Enter a count from 1 to 25")
    return JsonResponse(sending_preview(row, count))


def approved_job_guard(job):
    from leadzen.chat.engine import snapshot
    from leadzen.workspaces import assert_worker_access
    from django.utils.dateparse import parse_datetime
    approval = job.campaign_approval
    if not isinstance(approval, dict) or not isinstance(approval.get("expires_at"), str):
        raise PermissionError("Review and approve this campaign again")
    expires = parse_datetime(approval["expires_at"])
    if not expires or timezone.is_naive(expires) or expires <= timezone.now():
        raise PermissionError("The campaign send approval expired")
    assert_worker_access()
    job.refresh_from_db()
    if job.status != "running" or snapshot("send_campaign", {"campaign_id": str(job.campaign_id), "recipient_ids": approval.get("recipient_ids", [])}, execution=True) != approval.get("snapshot"):
        raise PermissionError("The reviewed campaign, identity or recipient permission changed")


def run_campaign(campaign_id, count, *, recipient_ids=None, before_send=None, automatic=False):
    """One bounded due-send pass; queued work is rechecked at each transport call."""
    from cold_outreach.emails import sender
    from leadzen.config.models import SiteConfig
    from leadzen.mailboxes import active_mailboxes
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()
    campaign = EmailCampaign.objects.get(pk=campaign_id)
    if campaign.autopilot_run_id and not automatic:
        raise PermissionError("Autopilot sequences must use their standing authorization")
    if campaign.status != "active":
        raise SettingsError("Activate the campaign before running it")
    values = effective()
    frozen_content = {key: copy.deepcopy(getattr(campaign, key)) for key in ("name", "category", "steps", "from_address", *OFFER_FIELDS, "delay_timezone")}
    if values.mailbox_address != campaign.from_address:
        raise SettingsError("The campaign's sending identity changed. Restore its mailbox first.")
    box = active_mailboxes().first()
    if not box:
        raise SettingsError("Connect an email sender first")
    sent = 0
    candidates = campaign.recipients.filter(status="pending")
    if recipient_ids is not None:
        candidates = candidates.filter(pk__in=recipient_ids)
    for recipient_id in list(candidates.order_by("pk").values_list("pk", flat=True)):
        if sent >= count or (not campaign.autopilot_run_id and not within_sending_window()):
            break
        assert_worker_access()
        campaign.refresh_from_db()
        box.refresh_from_db()
        from cold_outreach.emails.models.mailbox import _local_midnight
        attempts_today = Message.objects.filter(mailbox=box, direction=Direction.OUTBOUND, recorded_at__gte=_local_midnight()).count()
        if campaign.status != "active" or not box.free_now() or not box.headroom_today() or attempts_today >= box.daily_limit:
            break
        recipient = CampaignRecipient.objects.select_related("deal__lead").get(pk=recipient_id)
        steps = recipient_steps(campaign, recipient)
        if recipient.status != "pending" or recipient.next_step >= len(steps):
            continue
        if automatic:
            from leadzen.followups import guard, within_window
            if campaign.autopilot_run_id:
                from leadzen.autopilot import send_guard as guard
            if not within_window(campaign):
                break
            guard(campaign, recipient)
        if recipient.next_send_at and recipient.next_send_at > timezone.now():
            continue
        deal = recipient.deal
        if deal.state == DealState.COMPLETED or ContactPreferences.objects.filter(lead=deal.lead, deleted_at__isnull=False).exists() or Suppression.objects.filter(email__iexact=deal.lead.email).exists() or initial_attempted(campaign, recipient) or (deal.thread_id and Message.objects.filter(thread_id=deal.thread_id, direction=Direction.INBOUND).exists()):
            recipient.status = "stopped"
            recipient.save(update_fields=["status"])
            continue
        if campaign.autopilot_run_id:
            from leadzen.autopilot import send_guard
            send_guard(campaign, recipient)
        if recipient.next_step > 0 or campaign.autopilot_run_id:
            from leadzen.transports import sync_replies_strict
            sync_replies_strict(box, classify=False) if automatic else sync_replies_strict(box)
            deal.refresh_from_db()
            if Message.objects.filter(thread_id=deal.thread_id, direction=Direction.INBOUND).exists() or Suppression.objects.filter(email__iexact=deal.lead.email).exists():
                recipient.status = "stopped"
                recipient.save(update_fields=["status"])
                continue
        if campaign.category != "outreach" and not ContactPreferences.objects.filter(lead=deal.lead, opted_in=True).exists():
            recipient.status = "stopped"
            recipient.save(update_fields=["status"])
            continue
        # Claim before the external effect. An interrupted/ambiguous send is left
        # for review; the worker never silently retries and duplicates it.
        if CampaignRecipient.objects.filter(pk=recipient.pk, status="pending").update(status="sending", claimed_at=timezone.now()) != 1:
            continue
        step = steps[recipient.next_step]
        sender_name = SiteConfig.load().operator_name
        rendered = rendered_step(campaign, step, deal.lead, sender_name, box.signature)
        rendered_body = rendered["body"]
        # Override this message only, never the employee's shared mailbox sign-off.
        message_box = copy.copy(box)
        message_box.signature = rendered["signature"]
        message = sender._build_message(message_box, deal.lead.email, rendered["subject"], rendered_body, None, recipient.message_id or None, recipient.message_id or None)
        row = sender._record_send(box, message, rendered_body, deal.thread, None)
        row._leadzen_transactional = campaign.category == "transactional"
        try:
            # Revalidate live campaign and contact state immediately at the sink.
            assert_worker_access()
            campaign.refresh_from_db()
            deal.refresh_from_db()
            if any(getattr(campaign, key) != value for key, value in frozen_content.items()):
                raise PermissionError("Campaign content changed after review")
            if campaign.status != "active" or deal.state == DealState.COMPLETED or ContactPreferences.objects.filter(lead=deal.lead, deleted_at__isnull=False).exists() or Suppression.objects.filter(email__iexact=deal.lead.email).exists():
                raise PermissionError("Campaign access or recipient permission changed")
            if campaign.category != "outreach" and not ContactPreferences.objects.filter(lead=deal.lead, opted_in=True).exists():
                raise PermissionError("Recipient opt-in was withdrawn")
            if deal.thread_id and Message.objects.filter(thread_id=deal.thread_id, direction=Direction.INBOUND).exists():
                raise PermissionError("A reply arrived before sending")
            if automatic:
                guard(campaign, recipient, row.pk) if campaign.autopilot_run_id else guard(campaign, recipient)
                if not within_window(campaign):
                    raise SendingWindowClosed("Automatic sending hours ended")
            if campaign.autopilot_run_id:
                from leadzen.autopilot import send_guard
                send_guard(campaign, recipient, row.pk)
            if before_send:
                before_send()
            def transport_guard():
                assert_worker_access()
                campaign.refresh_from_db()
                deal.refresh_from_db()
                deal.lead.refresh_from_db()
                if (campaign.status != "active" or any(getattr(campaign, key) != value for key, value in frozen_content.items())
                        or deal.state == DealState.COMPLETED or ContactPreferences.objects.filter(lead=deal.lead, deleted_at__isnull=False).exists()
                        or Suppression.objects.filter(email__iexact=deal.lead.email).exists()
                        or (deal.thread_id and Message.objects.filter(thread_id=deal.thread_id, direction=Direction.INBOUND).exists())):
                    raise PermissionError("Campaign or recipient permission changed before sending")
                if campaign.category != "outreach" and not ContactPreferences.objects.filter(lead=deal.lead, opted_in=True).exists():
                    raise PermissionError("Recipient opt-in was withdrawn")
                if initial_attempted(campaign, recipient, row.pk):
                    CampaignRecipient.objects.filter(pk=recipient.pk, status="sending").update(status="stopped")
                    raise PermissionError("A competing or previous outreach attempt already exists for this address")
                if automatic:
                    guard(campaign, recipient, row.pk) if campaign.autopilot_run_id else guard(campaign, recipient)
                elif not within_sending_window():
                    raise SendingWindowClosed("Sending resumes during your selected days and hours")
                if before_send:
                    before_send()
            from leadzen.autopilot import delivery_scope
            from leadzen.transports import delivery_guard_scope
            with delivery_scope(campaign, recipient, row.pk), delivery_guard_scope(transport_guard):
                sender._deliver(box, message, row)
        except SendingWindowClosed:
            # This exception is raised only before submission. Remove only our
            # never-submitted record; unknown provider failures stay held below.
            row.delete()
            CampaignRecipient.objects.filter(pk=recipient.pk, status="sending").update(status="pending", claimed_at=None)
            break
        except Exception:
            CampaignRecipient.objects.filter(pk=recipient.pk).exclude(status="stopped").update(status="review")
            raise
        # A delete/stop may win while the provider accepts this email. Retain
        # the send log, but never let our stale in-memory completion resurrect
        # the contact or its follow-up queue. Serialize these local writes.
        with transaction.atomic(using=Deal.objects.all().db):
            updated = Deal.objects.filter(pk=deal.pk, lead__preferences__deleted_at__isnull=True).exclude(state=DealState.COMPLETED).update(
                state=DealState.EMAILED, mailbox=box, thread=row.thread,
                email_subject=str(message["Subject"]), email_sent_at=timezone.now(), updated_at=timezone.now(),
            )
            recipient.refresh_from_db(fields=["status"])
            recipient.next_step += 1
            recipient.message_id = str(message["Message-ID"])
            recipient.status = "stopped" if not updated or recipient.status == "stopped" else "completed" if recipient.next_step >= len(steps) else "pending"
            recipient.next_send_at = None if recipient.status != "pending" else next_send_time(campaign, timezone.now(), steps[recipient.next_step]["delay_days"])
            recipient.save()
        box.next_send_at = timezone.now() + timedelta(minutes=5)
        box.save(update_fields=["next_send_at"])
        sent += 1
    return sent
