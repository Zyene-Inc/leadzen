"""Durable authorization for reviewed campaign follow-ups, never new cold leads."""
import hashlib
import json
import os
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from leadzen.config.models import EmailCampaign, RuntimeSettings, SiteConfig
from leadzen.transports import SendingWindowClosed


def fingerprint(campaign, recipient):
    from leadzen.campaigns import OFFER_FIELDS
    from leadzen.mailboxes import active_mailboxes
    from leadzen.timezone import TIME_ZONE
    data = {
        "business_timezone": TIME_ZONE,
        "campaign": {key: getattr(campaign, key) for key in (
            "name", "category", "steps", "from_address", *OFFER_FIELDS, "delay_timezone")},
        "runtime": list(RuntimeSettings.objects.values()),
        "site": list(SiteConfig.objects.values()),
        "signatures": list(active_mailboxes().order_by("pk").values("from_address", "signature")),
        "personal_steps": recipient.personal_steps,
        "recipient": {key: getattr(recipient.deal.lead, key) for key in (
            "email", "first_name", "last_name", "company")},
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def authorize(campaign, recipient_ids, actor_id):
    """Called inside the final-confirmation transaction, using server-selected IDs."""
    if len(campaign.steps) < 2:
        raise ValueError("This campaign has no follow-ups to approve")
    approval = dict(campaign.followup_approval)
    # A changed setup requires a new scope; prior recipients are never silently reapproved.
    scopes = dict(approval.get("recipients", {})) if approval.get("actor_id") == actor_id else {}
    for recipient in campaign.recipients.filter(pk__in=recipient_ids).select_related("deal__lead"):
        scopes[str(recipient.pk)] = {"fingerprint": fingerprint(campaign, recipient),
                                    "expires_at": (timezone.now() + timedelta(days=365)).isoformat()}
    campaign.followup_approval = {"actor_id": actor_id, "recipients": scopes,
                                 "approved_at": timezone.now().isoformat()}
    campaign.save(update_fields=["followup_approval"])


def guard(campaign, recipient):
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()
    campaign.refresh_from_db()
    recipient.refresh_from_db()
    approval = campaign.followup_approval
    scope = approval.get("recipients", {}).get(str(recipient.pk), {})
    expires = parse_datetime(scope.get("expires_at", ""))
    actor = os.environ.get("LEADZEN_ACTOR_ID")
    if (campaign.status != "active" or recipient.next_step < 1
            or recipient.status not in {"pending", "sending"}
            or not expires or timezone.is_naive(expires) or expires <= timezone.now()
            or (actor and str(approval.get("actor_id")) != actor)
            or scope.get("fingerprint") != fingerprint(campaign, recipient)):
        raise PermissionError("Automatic follow-up approval changed or expired. Review the sequence again.")
    if not within_window(campaign):
        raise SendingWindowClosed("Sending resumes during your selected days and hours")


def within_window(campaign):
    """Custom Settings apply to all sequences; legacy approvals keep 9–5."""
    from leadzen.campaigns import campaign_schedule
    from leadzen.sending_schedule import within_window as selected_window
    return selected_window(schedule=campaign_schedule(campaign, automatic=True))


def run_due():
    """One bounded, locked workspace pass. Pending first emails are never automatic."""
    from leadzen.campaigns import run_campaign
    sent = 0
    for campaign in EmailCampaign.objects.filter(status="active", autopilot_run__isnull=True).exclude(followup_approval={}):
        if not within_window(campaign):
            continue
        ids = list(campaign.recipients.filter(
            status="pending", next_step__gt=0, next_send_at__lte=timezone.now(),
            pk__in=campaign.followup_approval.get("recipients", {}),
        ).order_by("next_send_at", "pk").values_list("pk", flat=True)[:25])
        if not ids:
            continue
        try:
            sent += run_campaign(campaign.pk, 25, recipient_ids=ids, automatic=True)
        except SendingWindowClosed:
            continue
        except Exception:
            # No automatic retry of a claimed send. A later pass can retry an
            # unclaimed inbox sync, but changed approvals stay held for review.
            campaign.refresh_from_db()
            if campaign.followup_approval:
                approval = {**campaign.followup_approval, "issue": "Automatic follow-ups held. Check the reviewed sequence, account, connections and recipient delivery state before resuming."}
                EmailCampaign.objects.filter(pk=campaign.pk).update(followup_approval=approval)
            continue
    return sent
