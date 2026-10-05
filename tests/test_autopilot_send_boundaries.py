"""Synthetic regressions for address dedup and the last pre-request guard."""
import uuid
from unittest.mock import patch

import pytest
from cold_outreach.emails.models import Direction, Mailbox, Message
from cold_outreach.leads.models import Deal, Lead
from cold_outreach.emails.delivery_policy import record_acceptance

from leadzen import autopilot
from leadzen.autopilot_worker import deliver_due
from leadzen.config.models import EmailReview, ReviewedEmail
from test_autopilot import NOW, enable_service, setup_run
from test_campaigns import connected
from test_email_transports import FakeSocket, installed_transports


@pytest.fixture(autouse=True)
def synthetic_email_host(monkeypatch):
    monkeypatch.setenv("LEADZEN_EMAIL_HOSTS", "api.example.com")


def http_socket(body=b'{"id":"synthetic-accepted"}'):
    return FakeSocket(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)


@pytest.mark.parametrize("draft_state", ["pending", "sending", "accepted", "review"])
def test_same_address_review_on_another_contact_stops_automatic_opener(connected, draft_state):
    p, run, campaign, recipient = setup_run(connected)
    # Finder and manual records can use different IDs for the same address.
    old_lead = Lead.objects.create(lead_id="manual-reviewed-contact", email=recipient.deal.lead.email.upper())
    old_deal = Deal.objects.create(lead=old_lead)
    review = EmailReview.objects.create(actor_id=p.actor_id, request_id=uuid.uuid4(), status="draft",
        kind="initial", requested_count=1, from_address=campaign.from_address)
    ReviewedEmail.objects.create(review=review, deal=old_deal, state=draft_state,
        subject="Human prepared", body="Human prepared")
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_not_called()
    recipient.refresh_from_db()
    assert recipient.status == "stopped" and recipient.next_step == 0


def test_outbound_started_after_preparation_stops_automatic_opener(connected):
    p, run, campaign, recipient = setup_run(connected)
    Message.objects.create(mailbox=Mailbox.objects.get(), direction=Direction.OUTBOUND,
        message_id="competing-outbound", from_address=campaign.from_address,
        to_address=recipient.deal.lead.email.upper(), subject="Already attempted", body_text="Already attempted")
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_not_called()
    recipient.refresh_from_db()
    assert recipient.status == "stopped" and recipient.next_step == 0


def test_mail_policy_revoked_during_tls_writes_no_http_bytes(connected):
    from leadzen.email_api import post_email
    p, run, campaign, recipient = setup_run(connected)
    secured = http_socket()
    def finish_tls(*args, **kwargs):
        autopilot.disable(p)
        return secured
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.delivery_scope(campaign, recipient), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", side_effect=finish_tls):
        autopilot.external_guard()
        with pytest.raises(PermissionError):
            post_email("https://api.example.com/email", "synthetic", {}, provider="compatible")
    assert secured.written == b""


def test_paid_policy_revoked_during_tls_keeps_one_reservation_and_writes_no_bytes(connected):
    from leadzen.ai import pinned_open
    p, run, campaign, recipient = setup_run(connected)
    run.phase = "drafting"
    run.save(update_fields=["phase"])
    secured = http_socket(b"{}")
    def finish_tls(*args, **kwargs):
        autopilot.disable(p)
        return secured
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.execution(run), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", side_effect=finish_tls):
        with pytest.raises(PermissionError):
            pinned_open("POST", "https://api.example.com/v1/chat/completions", {}, b"{}", "api.example.com")
    run.refresh_from_db()
    assert run.model_requests == 1 and secured.written == b""


def test_successful_paid_post_does_not_reserve_twice_after_tls(connected):
    from leadzen.ai import pinned_request
    p, run, campaign, recipient = setup_run(connected)
    run.phase = "drafting"
    run.save(update_fields=["phase"])
    secured = http_socket(b"{}")
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.execution(run), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", return_value=secured):
        status, headers, body = pinned_request("POST", "https://api.example.com/v1/chat/completions", {}, b"{}", "api.example.com")
    run.refresh_from_db()
    assert status == 200 and body == b"{}"
    assert run.model_requests == 1 and b"POST /v1/chat/completions" in secured.written


@pytest.mark.parametrize("transport", ["http", "smtp"])
def test_normal_initial_transport_excludes_its_own_log_only(connected, monkeypatch, transport):
    from leadzen.email_api import post_email
    p, run, campaign, recipient = setup_run(connected)
    secured = http_socket() if transport == "http" else FakeSocket(
        b"220 ready\r\n250-server\r\n250 AUTH PLAIN\r\n235 logged in\r\n250 sender\r\n250 recipient\r\n354 data\r\n250 synthetic-queue-id\r\n221 bye\r\n")
    with installed_transports(monkeypatch) as sender:
        def deliver(mailbox, message, row):
            # Campaigns have already recorded this own row before transport.
            assert Message.objects.filter(pk=row.pk, to_address=recipient.deal.lead.email).exists()
            if transport == "http":
                identifier = post_email("https://api.example.com/email", "synthetic", {"to": str(message["To"])}, provider="compatible")
                record_acceptance(row, 250, identifier.encode())
            else:
                with sender._SMTP("smtp.example.com", 465, timeout=10) as smtp:
                    smtp.starttls()
                    smtp.login("sender@example.com", "synthetic")
                    smtp.send_message(message)
                    record_acceptance(row, *smtp.accepted_response)
        with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", return_value=secured), patch.object(sender, "_deliver", side_effect=deliver):
            deliver_due(p)
    recipient.refresh_from_db()
    assert recipient.next_step == 1 and recipient.status == "pending"
    assert Message.objects.filter(direction=Direction.OUTBOUND).count() == 1
    assert Message.objects.get(direction=Direction.OUTBOUND).delivery_events.filter(status="accepted").count() == 1
    assert (b"POST /email" if transport == "http" else b"data\r\n") in secured.written


def test_competing_outbound_during_tls_blocks_before_http_bytes(connected):
    from leadzen.email_api import post_email
    p, run, campaign, recipient = setup_run(connected)
    secured = http_socket()
    def finish_tls(*args, **kwargs):
        Message.objects.create(mailbox=Mailbox.objects.get(), direction=Direction.OUTBOUND,
            message_id="late-competing-outbound", from_address=campaign.from_address,
            to_address=recipient.deal.lead.email, subject="Another attempt", body_text="Another attempt")
        return secured
    def deliver(mailbox, message, row):
        post_email("https://api.example.com/email", "synthetic", {"to": str(message["To"])}, provider="compatible")
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver", side_effect=deliver), patch("leadzen.transports.public_socket", return_value=secured), patch("ssl.SSLContext.wrap_socket", side_effect=finish_tls):
        deliver_due(p)
    recipient.refresh_from_db()
    assert recipient.status == "stopped" and recipient.next_step == 0
    assert secured.written == b""
    assert not Message.objects.filter(delivery_events__status="accepted").exists()
    p.refresh_from_db()
    assert not p.issue  # A normal duplicate stop must not become a provider alert.
