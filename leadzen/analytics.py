"""Outreach results computed from the saved mail log. Read-only.

Definitions, shared by the summary and every campaign row:
- Sent: an outbound message the mail provider accepted (counted when sent).
- Contacted ("people emailed"): a person whose FIRST accepted email falls in the
  period. Their replies and opt-outs count for that period, whenever they arrive.
- Replied: a contacted person's first human reply after our first send.
- Bounced: an outbound message in the period with a bounced or rejected event.
- Opted out: a contacted person who asked to stop (opt-out message, STOP reply,
  unsubscribe, or an employee-recorded opt-out). Hard bounces and manual blocks
  are not opt-outs.
A reply is credited to the latest campaign step sent before it arrived.
"""
from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from cold_outreach.emails.models import DeliveryEvent, Direction, Message
from cold_outreach.leads.models import Suppression
from leadzen.accounts.service import access, error
from leadzen.config.models import CampaignSend, EmailCampaign

PERIODS = {"7": 7, "30": 30, "90": 90, "all": None}
# Below this many contacted people, a reply rate is mostly chance; say so instead of ranking.
MIN_SAMPLE = 10
EASTERN = ZoneInfo("America/New_York")
FAILED = ("bounced", "rejected")
# Do Not Contact reasons that mean the person asked to stop (see leadzen/outreach.py,
# campaigns.contact, the library's unsubscribe projection and the Workspace form).
OPT_OUT_REASONS = ("exact stop", "unsubscribe", "employee recorded opt-out", "opt-out", "opted out")


def rate(part, whole):
    return round(part / whole, 4) if whole else None


def results(days):
    since = timezone.now() - timedelta(days=days) if days else None
    outbound = Message.objects.filter(direction=Direction.OUTBOUND)
    accepted = set(DeliveryEvent.objects.filter(message__direction=Direction.OUTBOUND, status="accepted").values_list("message_id", flat=True))
    failed = set(DeliveryEvent.objects.filter(message__direction=Direction.OUTBOUND, status__in=FAILED).values_list("message_id", flat=True))

    # First accepted send per thread (all time), so a reply is never credited to a later touch.
    first_send, sends = {}, []
    for pk, thread_id, to_address, when in outbound.exclude(thread_id=None).order_by("recorded_at", "pk").values_list("pk", "thread_id", "to_address", "recorded_at"):
        if pk in accepted:
            first_send.setdefault(thread_id, (when, to_address.lower()))
        sends.append((pk, thread_id, when))
    # Filter in memory: an IN list of every contacted thread exceeds SQLite's variable limit.
    first_reply, opted_threads = {}, set()
    for thread_id, kind, when in (Message.objects.filter(direction=Direction.INBOUND, kind__in=["human_reply", "opt_out"]).exclude(thread_id=None)
                                  .order_by("recorded_at").values_list("thread_id", "kind", "recorded_at").iterator()):
        if thread_id not in first_send:
            continue
        if kind == "opt_out":
            opted_threads.add(thread_id)
        elif when > first_send[thread_id][0]:
            first_reply.setdefault(thread_id, when)
    blocked = {email.lower(): at for email, reason, at in Suppression.objects.values_list("email", "reason", "suppressed_at").iterator()
               if (reason or "").strip().lower().startswith(OPT_OUT_REASONS)}
    opted = {t for t, (when, address) in first_send.items() if t in opted_threads or (address in blocked and blocked[address] >= when)}

    in_period = lambda when: since is None or when >= since
    contacted = {t for t, (when, _) in first_send.items() if in_period(when)}
    period_sends = [(pk, t, when) for pk, t, when in sends if in_period(when)]
    overview = {"sent": sum(pk in accepted for pk, _, _ in period_sends), "contacted": len(contacted),
                "replied": sum(t in first_reply for t in contacted), "bounced": sum(pk in failed for pk, _, _ in period_sends),
                "opted_out": len(contacted & opted)}
    overview["reply_rate"] = rate(overview["replied"], overview["contacted"])
    # A bounce can follow an initial acceptance, so rate it against every attempt.
    overview["bounce_rate"] = rate(overview["bounced"], sum(pk in accepted or pk in failed for pk, _, _ in period_sends))

    # Trend: daily sent and new replies, New York dates, at most the last 90 days.
    window = days or 90
    start = (timezone.now() - timedelta(days=window - 1)).astimezone(EASTERN).date()
    buckets = {start + timedelta(days=i): {"sent": 0, "replies": 0} for i in range(window)}
    for pk, _, when in sends:
        day = when.astimezone(EASTERN).date()
        if pk in accepted and day in buckets:
            buckets[day]["sent"] += 1
    for when in first_reply.values():
        day = when.astimezone(EASTERN).date()
        if day in buckets:
            buckets[day]["replies"] += 1
    trend = [{"date": day.isoformat(), **counts} for day, counts in sorted(buckets.items())]

    campaigns = []
    rows = CampaignSend.objects.select_related("recipient__deal").order_by("sent_at", "pk")
    by_campaign = defaultdict(list)
    for row in rows:
        by_campaign[row.campaign_id].append(row)
    for campaign in EmailCampaign.objects.filter(pk__in=list(by_campaign)).order_by("-created_at")[:100]:
        steps = [{"step": i, "subject": (step.get("subject") or "")[:200], "sent": 0, "replies": 0} for i, step in enumerate(campaign.steps or [])]
        per_recipient = defaultdict(list)
        bounced = 0
        for row in by_campaign[campaign.pk]:
            if row.message_pk in failed and in_period(row.sent_at):
                bounced += 1
            if row.message_pk in accepted:
                per_recipient[row.recipient_id].append(row)
        # The campaign's people emailed: first accepted send in the period (as in the summary).
        cohort = {rid: rows for rid, rows in per_recipient.items() if in_period(rows[0].sent_at)}
        sent = replied = opted_out = 0
        for recipient_sends in cohort.values():
            for row in recipient_sends:
                sent += 1
                if row.step < len(steps):
                    steps[row.step]["sent"] += 1
            thread_id = recipient_sends[0].recipient.deal.thread_id
            if thread_id in opted:
                opted_out += 1
            reply = first_reply.get(thread_id)
            before = [row for row in recipient_sends if reply and row.sent_at <= reply]
            if before:
                replied += 1
                if before[-1].step < len(steps):
                    steps[before[-1].step]["replies"] += 1
        for step in steps:
            step["reply_rate"] = rate(step["replies"], step["sent"])
        contacted_count = len(cohort)
        if not contacted_count and not bounced:
            continue
        campaigns.append({"id": str(campaign.pk), "name": campaign.name, "status": campaign.status, "created_at": campaign.created_at.isoformat(),
                          "recipients": campaign.recipients.count(), "contacted": contacted_count, "sent": sent, "replied": replied,
                          "reply_rate": rate(replied, contacted_count), "bounced": bounced, "opted_out": opted_out, "steps": steps,
                          "estimated": any(row.inferred for row in by_campaign[campaign.pk])})

    ranked = [c for c in campaigns if c["contacted"] >= MIN_SAMPLE]
    best_campaign = max(ranked, key=lambda c: (c["reply_rate"], c["contacted"]), default=None)
    messages = [{"campaign_id": c["id"], "campaign": c["name"], **s} for c in campaigns for s in c["steps"] if s["sent"] >= MIN_SAMPLE]
    best_message = max(messages, key=lambda m: (m["reply_rate"], m["sent"]), default=None)
    return {"period": "all" if days is None else str(days), "overview": overview, "trend": trend, "campaigns": campaigns,
            "best_campaign": {"id": best_campaign["id"], "name": best_campaign["name"], "reply_rate": best_campaign["reply_rate"], "contacted": best_campaign["contacted"]} if best_campaign else None,
            "best_message": best_message, "min_sample": MIN_SAMPLE}


@require_http_methods(["GET"])
@access(workspace=True)
def view(request):
    period = request.GET.get("period", "30")
    if period not in PERIODS:
        return error("Choose 7, 30, 90 days or all time")
    return JsonResponse(results(PERIODS[period]))
