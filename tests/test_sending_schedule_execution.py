"""Employee weekly schedules reach preparation, due dates and real adapter gates."""
import json
import uuid
from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from cold_outreach.emails.models import Mailbox, Message
from leadzen import autopilot
from leadzen.autopilot_worker import checkpoint, deliver_due, workspace_tick
from leadzen.campaigns import next_send_time, run_campaign
from leadzen.config.models import AutopilotRun, CampaignRecipient, EmailCampaign, EmailReview, ReviewedEmail, SiteConfig
from leadzen.configuration import save_dashboard_settings
from leadzen.transports import SendingWindowClosed, delivery_guard, delivery_guard_scope
from test_autopilot import policy, setup_run, enable_service
from test_campaigns import connected, add, make
from test_email_transports import FakeSocket, installed_transports

ZONE = ZoneInfo("America/New_York")
TUESDAY = datetime(2026, 10, 6, 8, 45, tzinfo=ZONE)
SCHEDULE = {"timezone": "America/New_York", "days": [1, 5], "start": "08:45", "end": "09:15"}


def schedule(value=None):
    value = value or SCHEDULE
    SiteConfig.objects.update(sending_schedule=value)
    return value


def api_sender():
    save_dashboard_settings({"ai_enabled": True, "mailbox_address": "sender@example.com", "mail_transport": "compatible", "mail_api_url": "https://api.resend.com/email", "imap_host": "imap.example.com", "imap_port": 993}, llm_api_key="synthetic-ai", mail_api_key="synthetic-api", mailbox_password="synthetic")


def socket():
    body = b'{"id":"synthetic-accepted"}'
    return FakeSocket(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)


def test_outreach_and_campaign_previews_show_exact_employee_days_minutes(connected):
    schedule()
    identifier = make(connected, add(connected))
    item = connected.get("/api/campaigns").json()["items"][0]
    assert item["sending_schedule"] == SCHEDULE
    assert item["delay_timezone"] == SCHEDULE["timezone"]
    for window in (connected.get("/api/outreach").json()["window"],
                   connected.get(f"/api/campaigns/{identifier}/preview").json()["automatic_window"]):
        assert window["days"] == [1, 5] and window["start_time"] == "08:45" and window["end_time"] == "09:15"
        assert window["start"] == 8.75 and window["end"] == 9.25 and not window["weekdays_only"]


def test_legacy_automatic_preview_does_not_broaden_to_initial_mail_hours(connected):
    from leadzen.followups import authorize
    identifier = make(connected, add(connected))
    data = connected.get(f"/api/campaigns/{identifier}/preview").json()
    assert data["window"]["start_time"] == "08:00" and data["window"]["end_time"] == "20:00"
    assert data["automatic_window"]["start_time"] == "09:00" and data["automatic_window"]["end_time"] == "17:00"
    campaign = EmailCampaign.objects.get(pk=identifier)
    authorize(campaign, [campaign.recipients.get().pk], 1)
    assert connected.get("/api/campaigns").json()["items"][0]["sending_schedule"]["start"] == "09:00"


@pytest.mark.parametrize("when,allowed", [
    (TUESDAY - timedelta(minutes=1), False), (TUESDAY, True),
    (TUESDAY + timedelta(minutes=29), True), (TUESDAY + timedelta(minutes=30), False),
    (TUESDAY + timedelta(days=4), True), (TUESDAY + timedelta(days=1), False),
])
def test_manual_campaign_selected_day_and_minute_gate(connected, when, allowed):
    schedule()
    identifier = make(connected, add(connected))
    EmailCampaign.objects.update(status="active")
    with patch("django.utils.timezone.now", return_value=when), patch("cold_outreach.core.sending_window.within_sending_window", return_value=False), patch("cold_outreach.emails.sender._deliver") as send:
        assert run_campaign(identifier, 1) == int(allowed)
        assert send.call_count == int(allowed)


@pytest.mark.parametrize("when,allowed", [
    (TUESDAY - timedelta(minutes=1), False), (TUESDAY, True),
    (TUESDAY + timedelta(minutes=29), True), (TUESDAY + timedelta(minutes=30), False),
    (TUESDAY + timedelta(days=4), True), (TUESDAY + timedelta(days=1), False),
])
def test_autopilot_discovery_uses_selected_days_start_and_clipped_catchup(connected, when, allowed):
    schedule()
    p = policy(sending_schedule=SCHEDULE)
    def prepared(run):
        checkpoint(run, "completed")
    with patch("django.utils.timezone.now", return_value=when), patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.autopilot_worker.prepare", side_effect=prepared) as prepare:
        workspace_tick()
        workspace_tick()
        assert prepare.call_count == int(allowed)
        assert AutopilotRun.objects.count() == int(allowed)
    p.refresh_from_db()
    assert not p.issue


def test_preparation_deadline_cannot_extend_beyond_short_selected_window(connected):
    schedule()
    policy(sending_schedule=SCHEDULE)
    when = TUESDAY + timedelta(minutes=25)
    def prepared(run):
        assert run.deadline_at == TUESDAY + timedelta(minutes=30)
        checkpoint(run, "completed")
    with patch("django.utils.timezone.now", return_value=when), patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.autopilot_worker.prepare", side_effect=prepared) as prepare:
        workspace_tick()
        prepare.assert_called_once()


def test_next_start_and_working_day_delays_use_selected_days(connected):
    schedule()
    p = policy(sending_schedule=SCHEDULE)
    with patch("django.utils.timezone.now", return_value=TUESDAY + timedelta(minutes=30)):
        assert autopilot.next_start(p) == TUESDAY + timedelta(days=4)
    identifier = make(connected, add(connected))
    campaign = EmailCampaign.objects.get(pk=identifier)
    campaign.delay_basis = "working_days"
    assert next_send_time(campaign, TUESDAY, 1) == TUESDAY + timedelta(days=4)
    assert next_send_time(campaign, TUESDAY, 2) == TUESDAY + timedelta(days=7)
    campaign.delay_basis = "calendar_days"
    assert next_send_time(campaign, TUESDAY, 1) == TUESDAY + timedelta(days=4)


def test_new_standing_authorization_takes_schedule_from_settings_only(connected):
    schedule()
    save_dashboard_settings({"ai_enabled": True, "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "smtp_port": 587, "imap_host": "imap.example.com", "imap_port": 993}, llm_api_key="synthetic", bettercontact_api_key="synthetic", mailbox_password="synthetic")
    with patch("leadzen.discovery.context", return_value={"blockers": []}):
        setup = connected.get("/api/autopilot").json()["setup"]
        assert setup["sending_schedule"] == SCHEDULE
        result = connected.post("/api/autopilot", json.dumps({"enabled": True, "authorize_automatic_outreach": True,
            "request_id": str(uuid.uuid4()), "revision": setup["revision"], "timezone": "Pacific/Honolulu",
            "sending_schedule": {"days": [0], "start": "00:00", "end": "23:59"}}), content_type="application/json")
    assert result.status_code == 200, result.content
    scope = result.json()["policy"]["scope"]
    assert scope["timezone"] == SCHEDULE["timezone"] and scope["sending_schedule"] == SCHEDULE


def test_custom_autopilot_can_send_saturday_and_stops_at_exact_close(connected):
    schedule()
    p, run, campaign, recipient = setup_run(connected, sending_schedule=SCHEDULE)
    when = TUESDAY + timedelta(days=4)
    AutopilotRun.objects.filter(pk=run.pk).update(workday=when.date())
    with patch("django.utils.timezone.now", return_value=when), patch("cold_outreach.core.sending_window.within_sending_window", return_value=False), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_called_once()
    Mailbox.objects.update(next_send_at=None)
    CampaignRecipient.objects.filter(pk=recipient.pk).update(next_send_at=when)
    with patch("django.utils.timezone.now", return_value=when + timedelta(minutes=30)), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_not_called()
    p.refresh_from_db()
    assert not p.issue


def test_changed_schedule_holds_existing_standing_and_followup_authorization(connected):
    from leadzen.followups import authorize, guard
    schedule()
    p, run, campaign, recipient = setup_run(connected, sending_schedule=SCHEDULE)
    recipient.next_step = 1
    recipient.save()
    authorize(campaign, [recipient.pk], p.actor_id)
    schedule({**SCHEDULE, "end": "10:00"})
    with patch("django.utils.timezone.now", return_value=TUESDAY), pytest.raises(PermissionError):
        autopilot.check_policy(p)
    with patch("django.utils.timezone.now", return_value=TUESDAY), pytest.raises(PermissionError):
        guard(campaign, recipient)


@pytest.mark.parametrize("automatic", [False, True])
def test_http_close_during_tls_is_deferred_without_request_bytes_or_false_issue(connected, monkeypatch, automatic):
    from leadzen.followups import authorize, run_due
    schedule()
    api_sender()
    identifier = make(connected, add(connected))
    campaign = EmailCampaign.objects.get(pk=identifier)
    campaign.status = "active"
    campaign.save()
    recipient = campaign.recipients.get()
    if automatic:
        recipient.next_step = 1
        recipient.next_send_at = TUESDAY
        recipient.save()
        authorize(campaign, [recipient.pk], 1)
    clock = [TUESDAY]
    secured = socket()
    def tls(*args, **kwargs):
        clock[0] += timedelta(minutes=30)
        return secured
    with patch("django.utils.timezone.now", side_effect=lambda: clock[0]), installed_transports(monkeypatch), patch("leadzen.transports.sync_replies_strict"), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", side_effect=tls):
        assert (run_due() if automatic else run_campaign(identifier, 1)) == 0
    recipient.refresh_from_db(); campaign.refresh_from_db()
    assert recipient.status == "pending" and recipient.claimed_at is None
    assert recipient.next_step == int(automatic) and not secured.written
    assert not Message.objects.exists() and not campaign.followup_approval.get("issue")


@pytest.mark.parametrize("failure", ["approval_changed", "unknown_provider"])
def test_only_known_pre_submission_schedule_close_can_unclaim(connected, monkeypatch, failure):
    schedule()
    api_sender()
    identifier = make(connected, add(connected))
    campaign = EmailCampaign.objects.get(pk=identifier)
    campaign.status = "active"
    campaign.save()
    secured = socket()
    def tls(*args, **kwargs):
        if failure == "approval_changed":
            EmailCampaign.objects.filter(pk=campaign.pk).update(name="Changed after review")
        else:
            raise OSError("synthetic unknown connection")
        return secured
    with patch("django.utils.timezone.now", return_value=TUESDAY), installed_transports(monkeypatch), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", side_effect=tls), pytest.raises((PermissionError, ValueError)):
        run_campaign(identifier, 1)
    recipient = campaign.recipients.get()
    assert recipient.status == "review" and Message.objects.count() == 1 and recipient.next_step == 0
    assert not secured.written


def test_reviewed_inbox_reply_keeps_immediate_semantics_outside_selected_hours(connected, monkeypatch):
    from test_reviewed_outreach import conversation, review, queued
    from leadzen.outreach import run_review
    from cold_outreach.leads.models import Deal
    schedule()
    api_sender()
    # The review composer fixture is synthetic; the actual HTTP adapter is used.
    thread, incoming = conversation(Deal.objects.get(pk=add(connected)))
    when = TUESDAY + timedelta(days=1, hours=5)
    from leadzen.accounts.models import LoginSession
    LoginSession.objects.update(expires_at=when + timedelta(days=1))
    secured = socket()
    with patch("django.utils.timezone.now", return_value=when):
        job = queued(connected, review(connected, thread_id=thread.pk))
        with installed_transports(monkeypatch), patch("leadzen.outreach.sync_replies_strict"), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", return_value=secured):
            assert run_review(job) == 1
    assert b"POST /email" in secured.written
    assert ReviewedEmail.objects.get().state == "accepted"


def test_transport_schedule_context_is_removed_after_exception(connected):
    def stopped():
        raise SendingWindowClosed("closed")
    with pytest.raises(SendingWindowClosed), delivery_guard_scope(stopped):
        delivery_guard()
    delivery_guard()  # Does not leak the employee's approval into another action.


def test_mailbox_capacity_and_receiver_pause_use_new_york_day(connected):
    from cold_outreach.emails.models import Direction, Thread, DeliveryEvent
    from cold_outreach.leads.models import Deal
    from cold_outreach.emails.delivery_policy import Response
    # Previously saved foreign zones cannot move the business-day ledger.
    schedule({**SCHEDULE, "timezone": "Asia/Kolkata"})
    box = Mailbox.objects.get()
    box.daily_limit = 10
    box.save()
    messages = []
    # 03:00 UTC is still the prior New York day; 04:00 UTC opens today.
    for index, hour in enumerate([3, 4]):
        thread = Thread.objects.create(mailbox=box)
        Deal.objects.filter(pk=add(connected, f"person{index}@example.com")).update(thread=thread)
        messages.append(Message.objects.create(mailbox=box, thread=thread, direction=Direction.OUTBOUND,
            message_id=f"synthetic-{index}", sent_at=datetime(2026, 10, 6, hour, tzinfo=ZoneInfo("UTC"))))
    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 7, 2, tzinfo=ZoneInfo("UTC"))):
        assert box.sent_today() == 1 and box.headroom_today() == 9
        event = DeliveryEvent.objects.create(message=messages[0], status="rejected", response=Response.QUOTA_EXCEEDED)
        DeliveryEvent.objects.filter(pk=event.pk).update(occurred_at=messages[0].sent_at)
        assert not box.paused_today()
        DeliveryEvent.objects.filter(pk=event.pk).update(occurred_at=messages[1].sent_at)
        assert box.paused_today() and box.headroom_today() == 0


def test_unchanged_mailbox_calendar_uses_new_york_for_non_us_country(connected):
    from cold_outreach.emails.models import mailbox
    SiteConfig.objects.update(operator_country_code="IN")
    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 7, 2, tzinfo=ZoneInfo("UTC"))):
        assert mailbox._local_midnight() == datetime(2026, 10, 6, tzinfo=ZONE)
