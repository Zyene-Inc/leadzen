"""Real clock changes and delayed SMTP replies cannot escape saved hours."""
import io
import ssl
from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from cold_outreach.emails.models import Message
from leadzen.autopilot_worker import checkpoint, workspace_tick
from leadzen.campaigns import next_send_time, run_campaign
from leadzen.config.models import CampaignRecipient, EmailCampaign, SiteConfig
from leadzen.configuration import save_dashboard_settings
from leadzen.sending_schedule import UTC, next_wall_open, window_close, within_window
from test_autopilot import enable_service, policy
from test_campaigns import add, connected, make
from test_email_transports import FakeSocket, installed_transports

NY = ZoneInfo("America/New_York")


def hours(start, end, zone="America/New_York"):
    return {"timezone": zone, "days": [6], "start": start, "end": end}


@pytest.mark.parametrize("basis", ["calendar_days", "working_days"])
def test_followup_uses_remaining_spring_window_instead_of_skipping_week(connected, basis):
    schedule = hours("02:00", "03:15")
    SiteConfig.objects.update(sending_schedule=schedule)
    campaign = EmailCampaign.objects.get(pk=make(connected, add(connected)))
    campaign.delay_basis = basis
    # One calendar day from Saturday / one selected working day from Sunday.
    sent = datetime(2026, 3, 7 if basis == "calendar_days" else 1, 2, 30, tzinfo=NY)
    due = next_send_time(campaign, sent, 1)
    assert due == datetime(2026, 3, 8, 3, 0, tzinfo=NY)
    assert within_window(due, schedule)


def test_wall_due_preserves_seconds_and_chooses_first_repeated_time():
    schedule = hours("01:00", "03:00")
    due = next_wall_open(datetime(2026, 11, 1, 1, 35, 20), schedule)
    assert due.astimezone(UTC) == datetime(2026, 11, 1, 5, 35, 20, tzinfo=UTC)
    assert due.fold == 0


def test_wall_due_skips_window_that_completely_disappears():
    due = next_wall_open(datetime(2026, 3, 8, 2, 30), hours("02:00", "02:45"))
    assert due == datetime(2026, 3, 15, 2, 0, tzinfo=NY)


@pytest.mark.parametrize("now,schedule,expected", [
    (datetime(2026, 3, 8, 1, 55, tzinfo=NY), hours("01:55", "02:05"),
     datetime(2026, 3, 8, 7, 0, tzinfo=UTC)),
    # The fall-back jump closes this window before nominal 02:15.
    (datetime(2026, 11, 1, 1, 55, tzinfo=NY), hours("01:45", "02:15"),
     datetime(2026, 11, 1, 6, 0, tzinfo=UTC)),
    # If the repeated hour stays inside the window, it remains open through it.
    (datetime(2026, 11, 1, 1, 55, tzinfo=NY), hours("01:00", "02:15"),
     datetime(2026, 11, 1, 7, 15, tzinfo=UTC)),
    (datetime(2026, 11, 1, 1, 35, tzinfo=NY, fold=1), hours("01:15", "01:45"),
     datetime(2026, 11, 1, 6, 45, tzinfo=UTC)),
])
def test_window_close_uses_first_real_disallowed_instant(now, schedule, expected):
    close = window_close(now, schedule)
    assert close == expected
    assert within_window(close - timedelta(microseconds=1), schedule)
    assert not within_window(close, schedule)


@pytest.mark.parametrize("now,schedule,expected", [
    (datetime(2026, 3, 8, 1, 55, tzinfo=NY), hours("01:55", "02:05"),
     datetime(2026, 3, 8, 7, 0, tzinfo=UTC)),
    (datetime(2026, 11, 1, 1, 55, tzinfo=NY), hours("01:45", "02:15"),
     datetime(2026, 11, 1, 6, 0, tzinfo=UTC)),
])
def test_preparation_deadline_stops_at_gap_or_fold_closure(connected, now, schedule, expected):
    SiteConfig.objects.update(sending_schedule=schedule)
    policy(sending_schedule=schedule)
    def prepared(run):
        assert run.deadline_at == expected
        checkpoint(run, "completed")
    with patch("django.utils.timezone.now", return_value=now), patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.autopilot_worker.prepare", side_effect=prepared) as prepare:
        workspace_tick()
        prepare.assert_called_once()


class ClockReplySocket(FakeSocket):
    """A local SMTP server changes state while replying to a command."""
    def __init__(self, response, trigger, change):
        super().__init__(response)
        self.trigger, self.change, self.closed = trigger, change, False

    def makefile(self, *args, **kwargs):
        parent = self
        class Replies(io.BytesIO):
            def readline(self, *args, **kwargs):
                line = super().readline(*args, **kwargs)
                if line.startswith(parent.trigger):
                    parent.change()
                return line
        return Replies(self.response)

    def close(self):
        self.closed = True


def smtp_campaign(connected):
    schedule = {"timezone": "America/New_York", "days": [1], "start": "08:45", "end": "09:15"}
    SiteConfig.objects.update(sending_schedule=schedule)
    save_dashboard_settings({"ai_enabled": False, "mailbox_address": "sender@example.com",
        "smtp_host": "smtp.example.com", "smtp_port": 465, "imap_host": "imap.example.com", "imap_port": 993})
    from leadzen.mailboxes import sync_dashboard_mailbox
    sync_dashboard_mailbox()
    identifier = make(connected, add(connected))
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    return identifier


SMTP_REPLIES = (b"220 ready\r\n250-server\r\n250 AUTH PLAIN\r\n235 logged in\r\n"
                b"250 sender\r\n250 recipient\r\n354 data\r\n250 synthetic-queue-id\r\n221 bye\r\n")


@pytest.mark.parametrize("change", ["hours", "permission"])
def test_smtp_rechecks_after_354_before_body_and_keeps_denial_state(connected, monkeypatch, change):
    identifier = smtp_campaign(connected)
    clock = [datetime(2026, 10, 6, 8, 45, tzinfo=NY)]
    def changed():
        if change == "hours":
            clock[0] += timedelta(minutes=30)
        else:
            EmailCampaign.objects.filter(pk=identifier).update(status="paused")
    secured = ClockReplySocket(SMTP_REPLIES, b"354", changed)
    with installed_transports(monkeypatch), patch("django.utils.timezone.now", side_effect=lambda: clock[0]), patch("leadzen.transports.public_socket", return_value=FakeSocket(b"")), patch.object(ssl.SSLContext, "wrap_socket", return_value=secured):
        if change == "hours":
            assert run_campaign(identifier, 1) == 0
        else:
            with pytest.raises(PermissionError):
                run_campaign(identifier, 1)
    assert b"data\r\n" in secured.written and b"Subject:" not in secured.written
    assert b"QUIT" not in secured.written and secured.closed
    recipient = CampaignRecipient.objects.get()
    assert recipient.next_step == 0
    if change == "hours":
        assert recipient.status == "pending" and recipient.claimed_at is None
        assert not Message.objects.exists()
    else:
        assert recipient.status == "review" and Message.objects.count() == 1


def test_smtp_close_after_acceptance_does_not_unclaim_or_guard_quit(connected, monkeypatch):
    identifier = smtp_campaign(connected)
    clock = [datetime(2026, 10, 6, 8, 45, tzinfo=NY)]
    def closed_after_acceptance():
        clock[0] += timedelta(minutes=30)
    secured = ClockReplySocket(SMTP_REPLIES, b"250 synthetic-queue-id", closed_after_acceptance)
    with installed_transports(monkeypatch), patch("django.utils.timezone.now", side_effect=lambda: clock[0]), patch("leadzen.transports.public_socket", return_value=FakeSocket(b"")), patch.object(ssl.SSLContext, "wrap_socket", return_value=secured):
        assert run_campaign(identifier, 1) == 1
    assert b"Subject:" in secured.written and b"QUIT\r\n" in secured.written
    assert Message.objects.get().delivery_events.filter(status="accepted").exists()
    assert CampaignRecipient.objects.get().next_step == 1
