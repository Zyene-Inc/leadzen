"""Read-only outreach history and due dates from the employee's saved engine state."""
from django.db.models import OuterRef, Subquery

from cold_outreach.emails.models import DeliveryEvent, Direction, Message
from cold_outreach.leads.models import DealState, Suppression
from leadzen.config.models import CampaignRecipient


def step_label(index, total):
    return "Initial email" if index == 0 else "Final follow-up" if total > 2 and index == total - 1 else "Follow-up"


def outreach_timeline(deal):
    # No credential loads, provider calls, sync or state transitions on this read.
    messages = Message.objects.filter(thread_id=deal.thread_id) if deal.thread_id else Message.objects.none()
    inbound = messages.filter(direction=Direction.INBOUND)
    human = inbound.filter(kind="human_reply").order_by("recorded_at", "pk").first()
    suppressed = Suppression.objects.filter(email__iexact=deal.lead.email).order_by("suppressed_at", "pk").first() if deal.lead.email else None
    blocked = "suppressed" if suppressed else "reply" if human else "inbound" if inbound.exists() else "completed" if deal.state == DealState.COMPLETED else ""
    acceptance = DeliveryEvent.objects.filter(message_id=OuterRef("pk"), status="accepted").order_by("occurred_at", "pk")
    messages = messages.annotate(accepted_at=Subquery(acceptance.values("occurred_at")[:1]))
    first = messages.filter(direction=Direction.OUTBOUND, accepted_at__isnull=False).order_by("recorded_at", "pk").values_list("pk", flat=True).first()
    events = []
    for message in reversed(list(messages.order_by("-recorded_at", "-pk")[:100])):
        if message.direction == Direction.OUTBOUND:
            label = "Initial email" if message.pk == first else "Reply sent" if human and message.recorded_at > human.recorded_at else "Follow-up email"
            status = "accepted" if message.accepted_at else "unconfirmed"
            if not message.accepted_at:
                label = "Email attempt"
            at = message.accepted_at or message.recorded_at
        else:
            label = {"human_reply": "Reply received", "opt_out": "Opt-out received", "auto_reply": "Automatic reply received", "bounce": "Bounce received"}.get(message.kind, "Inbound message received")
            status, at = "received", message.received_at or message.sent_at or message.recorded_at
        events.append({"id": f"message-{message.pk}", "label": label, "status": status, "at": at.isoformat(), "subject": message.subject})
    sequences = []
    for recipient in CampaignRecipient.objects.filter(deal=deal).select_related("campaign").order_by("-campaign__created_at", "-pk")[:20]:
        campaign = recipient.campaign
        automatic = bool(campaign.autopilot_run_id) or str(recipient.pk) in campaign.followup_approval.get("recipients", {})
        status = "stopped" if blocked or recipient.status == "stopped" or campaign.status == "archived" else recipient.status
        steps = []
        if status == "pending":
            from leadzen.campaigns import next_send_time, recipient_steps
            copy = recipient_steps(campaign, recipient)
            due = recipient.next_send_at
            for index in range(recipient.next_step, len(copy)):
                later = index > recipient.next_step
                if later and due:
                    due = next_send_time(campaign, due, copy[index]["delay_days"])
                step_status = "estimated" if later else "scheduled" if automatic and index > 0 else "due"
                if campaign.status != "active":
                    step_status = campaign.status
                steps.append({"id": f"sequence-{recipient.pk}-{index}", "label": step_label(index, len(copy)),
                              "at": due.isoformat() if due else None, "status": step_status,
                              "subject": copy[index]["subject"]})
        from leadzen.campaigns import campaign_schedule
        schedule = campaign_schedule(campaign, automatic=automatic)
        sequences.append({"id": str(campaign.pk), "name": campaign.name, "status": status,
                          "automatic": automatic, "campaign_status": campaign.status,
                          "timezone": schedule["timezone"], "sending_schedule": schedule, "steps": steps})
    return {"events": events, "history_truncated": messages.count() > 100, "sequences": sequences,
            "blocked_reason": blocked,
            "can_stop": not blocked and (deal.state == DealState.EMAILED or any(s["status"] in {"pending", "sending", "review"} for s in sequences)),
            "suppression": {"reason": suppressed.reason, "at": suppressed.suppressed_at.isoformat()} if suppressed else None}
