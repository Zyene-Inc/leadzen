# Portions copyright 2026 Mindroot Ltd, licensed under the Apache License,
# Version 2.0 (http://www.apache.org/licenses/LICENSE-2.0). Modifications
# copyright 2026 Zyene.
#
# The actions follow Warmbly (https://github.com/warmbly/warmbly), commit
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1: internal/app/advanced/
# reply_optout_recheck.go and replyclassify.IsOptOut (suppress on an opt-out
# reply, never on bulk mail's own footer), internal/app/inboxtag/followup.go
# and replyclassify/returndate.go (hold an out-of-office lead until the next
# business day after the return date, else a fixed hold) and
# replyclassify.IsAutomated (an away message is not a human reply). Translated
# from Go to Python and adapted by Zyene to LeadZen's campaigns, Do not contact
# list and Inbox. See THIRD_PARTY_NOTICES.md.
"""Label each saved reply and act on the two labels that need it.

- unsubscribe → Do not contact, with the reason and date.
- out of office → that lead's approved follow-ups wait until the next business
  day after the return date (or ``FALLBACK_HOLD_DAYS`` when none is written).

Nothing here sends mail or drafts a reply. Replies still need the employee's
approval exactly as before.
"""
from __future__ import annotations

import email
import logging
from datetime import datetime, time, timedelta
from email import policy

from django.db.models import Q
from django.utils import timezone

from cold_outreach.emails.models import Direction, Message
from leadzen import reply_classify as rc

logger = logging.getLogger(__name__)

INTERESTED, NOT_INTERESTED, OUT_OF_OFFICE = "interested", "not_interested", "out_of_office"
UNSUBSCRIBE, AUTO_REPLY, NEEDS_REVIEW = "unsubscribe", "auto_reply", "needs_review"
LABELS = (INTERESTED, NOT_INTERESTED, OUT_OF_OFFICE, UNSUBSCRIBE, AUTO_REPLY, NEEDS_REVIEW)
_FROM_CLASS = {rc.POSITIVE: INTERESTED, rc.NEGATIVE: NOT_INTERESTED, rc.OUT_OF_OFFICE: OUT_OF_OFFICE,
               rc.UNSUBSCRIBE: UNSUBSCRIBE, rc.AUTO_REPLY: AUTO_REPLY}
# Warmbly's configured fallback when an away message names no return date.
FALLBACK_HOLD_DAYS = 7
# An old away message is history, not a reason to hold a sequence now.
HOLD_RECENT_DAYS = 14
# Messages the sender library has read as replies or opt-outs.
SORTED_KINDS = ("human_reply", "auto_reply", "opt_out")


def _without_own_footer(body: str) -> str:
    """Drop the opt-out line every send carries, should a reply quote it unmarked."""
    from cold_outreach.emails.sender import OPT_OUT_LINE
    lines = [line for line in (body or "").split("\n") if OPT_OUT_LINE.lower() not in line.lower().lstrip("> ")]
    return "\n".join(lines)


def label_message(message):
    """``(label, source, return_date)`` for one inbound message."""
    if message.kind == "opt_out":
        return UNSUBSCRIBE, rc.SOURCE_HEADER, None  # Sent to the +unsub alias.
    raw = bytes(message.raw or b"")
    headers = email.message_from_bytes(raw, policy=policy.compat32) if raw else None
    body = _without_own_footer(message.body_text)
    result = rc.classify(headers, message.subject, body)
    if result.label == rc.UNSUBSCRIBE and headers is not None and rc.is_bulk_mail(headers):
        result = rc.Result(rc.UNKNOWN)  # A newsletter's own footer is not a request to us.
    if result.label == rc.UNKNOWN and message.kind == "auto_reply":
        result = rc.Result(rc.AUTO_REPLY, 0.9, rc.SOURCE_HEADER)
    label = _FROM_CLASS.get(result.label, NEEDS_REVIEW)
    back = None
    if label == OUT_OF_OFFICE:
        received = timezone.localtime(message.received_at or message.recorded_at or timezone.now()).date()
        back = rc.find_return_date(message.subject, body, received)
    return label, result.source, back


def _hold_followups(message, back):
    """Pause this sender's pending follow-ups; they resume on their own."""
    from leadzen.config.models import CampaignRecipient
    received = message.received_at or message.recorded_at or timezone.now()
    if received < timezone.now() - timedelta(days=HOLD_RECENT_DAYS):
        return False
    zone = timezone.get_current_timezone()
    if back:
        resume = timezone.make_aware(datetime.combine(rc.next_business_day(back), time()), zone)
    else:
        resume = received + timedelta(days=FALLBACK_HOLD_DAYS)
    recipients = CampaignRecipient.objects.filter(
        deal__lead__email__iexact=message.from_address, status="pending", next_step__gt=0,
        campaign__status__in=["active", "paused"]).filter(Q(next_send_at__isnull=True) | Q(next_send_at__lt=resume))
    return recipients.update(next_send_at=resume) > 0


def sort_replies(mailbox) -> int:
    """Label every unlabelled reply in this mailbox once. Returns replies labelled."""
    from leadzen.config.models import ReplyLabel
    from leadzen.suppression import block_address
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()
    seen = ReplyLabel.objects.values("message_pk")
    pending = (Message.objects.filter(mailbox=mailbox, direction=Direction.INBOUND, kind__in=SORTED_KINDS)
               .exclude(pk__in=seen).order_by("pk"))
    count = 0
    for message in pending.iterator(chunk_size=100):
        try:
            label, source, back = label_message(message)
        except Exception:
            logger.exception("reply sorting: could not read message %s", message.pk)
            continue
        action = ""
        if label == UNSUBSCRIBE and message.from_address and message.from_address.lower() != mailbox.from_address.lower():
            try:
                block_address(message.from_address, "Asked to unsubscribe in a reply")
                action = "blocked"
            except ValueError:
                logger.warning("reply sorting: %s could not be blocked", message.from_address)
        elif label == OUT_OF_OFFICE and _hold_followups(message, back):
            action = "held"
        ReplyLabel.objects.get_or_create(message_pk=message.pk, defaults={
            "label": label, "source": source, "return_date": back, "action": action})
        count += 1
    return count


def away_messages():
    """Inbound messages labelled out of office: they never count as a human reply."""
    from leadzen.config.models import ReplyLabel
    return ReplyLabel.objects.filter(label=OUT_OF_OFFICE).values("message_pk")


def labels_for(message_pks):
    from leadzen.config.models import ReplyLabel
    return {row.message_pk: row for row in ReplyLabel.objects.filter(message_pk__in=list(message_pks))}


def label_payload(row):
    if row is None:
        return None
    return {"label": row.label, "return_date": row.return_date.isoformat() if row.return_date else None, "action": row.action}


def replies(**filters):
    """Inbound messages that stop a sequence: everything but labelled away messages.

    An unlabelled message still counts, so a reply that could not be read stops
    follow-ups exactly as before.
    """
    return Message.objects.filter(direction=Direction.INBOUND, **filters).exclude(pk__in=away_messages())
