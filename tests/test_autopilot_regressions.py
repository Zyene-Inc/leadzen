"""Queue progress and scheduling regressions found by the final Autopilot review."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from cold_outreach.emails.models import Mailbox, Message, Direction, Thread
from cold_outreach.leads.models import Deal, DealState, Suppression
from leadzen.config.models import AutopilotRun, CampaignRecipient, ContactPreferences
from leadzen import autopilot
from leadzen.autopilot_worker import deliver_due
from test_autopilot import NOW, policy, setup_run, enable_service
from test_campaigns import connected, add


@pytest.mark.parametrize("reason", ["reply", "suppressed", "completed", "deleted"])
def test_stopped_recipient_does_not_block_other_outreach(connected, reason):
    p, run, campaign, first = setup_run(connected)
    second = CampaignRecipient.objects.create(campaign=campaign, deal_id=add(connected, "second@example.com"),
        personal_steps=first.personal_steps, status="pending")
    second.authorization_hash = autopilot.recipient_hash(campaign, second)
    second.save()
    if reason == "reply":
        thread = Thread.objects.create(mailbox=Mailbox.objects.get())
        Deal.objects.filter(pk=first.deal_id).update(thread=thread)
        Message.objects.create(mailbox=Mailbox.objects.get(), thread=thread, direction=Direction.INBOUND,
            message_id="already-replied", from_address=first.deal.lead.email, to_address=campaign.from_address,
            subject="Reply", body_text="Thanks")
    elif reason == "suppressed":
        Suppression.objects.create(email=first.deal.lead.email)
    elif reason == "completed":
        Deal.objects.filter(pk=first.deal_id).update(state=DealState.COMPLETED)
    else:
        ContactPreferences.objects.filter(lead=first.deal.lead).update(deleted_at=NOW)
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        assert send.call_count == 1
        assert str(send.call_args.args[1]["To"]) == "second@example.com"
    first.refresh_from_db(); second.refresh_from_db()
    assert first.status == "stopped" and first.next_step == 0
    assert second.next_step == 1
    p.refresh_from_db()
    assert not p.issue  # A reply/opt-out is expected, not a service outage alert.


def test_learned_capacity_changes_keep_policy_but_still_limit_sending(connected):
    p, run, campaign, recipient = setup_run(connected)
    Mailbox.objects.update(daily_limit=0)
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        autopilot.check_policy(p)
        deliver_due(p)
        send.assert_not_called()
    assert autopilot.setup_hash() == p.setup_hash
    Mailbox.objects.update(signature="Changed identity")
    assert autopilot.setup_hash() != p.setup_hash


def test_next_start_matches_available_same_day_catchup(connected):
    p = policy()
    morning = NOW + timedelta(minutes=30)
    with patch("django.utils.timezone.now", return_value=morning):
        assert autopilot.next_start(p) == autopilot.local_now(p, morning)
        AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=morning.date())
        assert str(autopilot.next_start(p).date()) == "2026-10-06"
    AutopilotRun.objects.all().delete()
    with patch("django.utils.timezone.now", return_value=NOW + timedelta(hours=2)):
        assert str(autopilot.next_start(p).date()) == "2026-10-06"


def test_recovered_inbox_failure_clears_only_transient_policy_warning(connected):
    p, run, campaign, recipient = setup_run(connected)
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict", side_effect=OSError("synthetic inbox offline")), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_not_called()
    p.refresh_from_db(); recipient.refresh_from_db()
    assert p.issue and recipient.status == "pending"
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_called_once()
    p.refresh_from_db(); recipient.refresh_from_db()
    assert not p.issue and recipient.next_step == 1


def test_recovery_does_not_hide_an_uncertain_send(connected):
    p, run, campaign, first = setup_run(connected)
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver", side_effect=OSError("synthetic unknown acceptance")):
        deliver_due(p)
    first.refresh_from_db(); p.refresh_from_db()
    assert first.status == "review" and p.issue
    second = CampaignRecipient.objects.create(campaign=campaign, deal_id=add(connected, "recovered@example.com"),
        personal_steps=first.personal_steps, status="pending")
    second.authorization_hash = autopilot.recipient_hash(campaign, second)
    second.save()
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_called_once()
    p.refresh_from_db(); first.refresh_from_db()
    assert p.issue and first.status == "review"
