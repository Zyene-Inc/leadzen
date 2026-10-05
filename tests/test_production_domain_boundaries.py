"""Synthetic production boundary checks; no provider calls or customer databases."""
import os
import subprocess
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cold_outreach.emails import sender
from cold_outreach.emails.models import Direction, Mailbox, Message
from cold_outreach.leads.models import Deal, Lead

from leadzen.campaigns import run_campaign, sending_preview
from leadzen.config.models import CampaignRecipient, SiteConfig
from leadzen.configuration import SettingsError, apply_dashboard_overrides, effective, save_dashboard_settings
from leadzen.email_api import DeliveryError, post_email
from test_campaigns import add, connected, make
from test_email_transports import FakeSocket


def test_dashboard_clears_legacy_plaintext_and_exported_credentials(connected, monkeypatch):
    config = SiteConfig.load()
    config.llm_api_key, config.mailbox_password = "synthetic-legacy-ai", "synthetic-legacy-mail"
    config.bettercontact_api_key = "synthetic-legacy-finder"
    config.save()
    save_dashboard_settings({"provider": "openai", "model": "synthetic", "mailbox_address": "sender@example.com"},
        llm_api_key="synthetic-current-ai", mailbox_password="synthetic-current-mail")
    config.refresh_from_db()
    assert not config.llm_api_key and not config.mailbox_password and not config.bettercontact_api_key
    save_dashboard_settings({"provider": "openai", "model": "synthetic", "mailbox_address": "sender@example.com"},
        clear_llm_api_key=True, clear_mailbox_password=True, clear_bettercontact_api_key=True)
    variables = ("OPENOUTFIND_LLM_API_KEY", "OUTSEND_LLM_API_KEY", "OUTSEND_MAILBOX_PASSWORD",
                 "OPENOUTFIND_LLM_API_BASE", "OUTSEND_SMTP_HOST", "OUTSEND_IMAP_HOST")
    for variable in variables:
        monkeypatch.setenv(variable, "synthetic-stale-export")
    apply_dashboard_overrides()
    assert not any(variable in os.environ for variable in variables)
    assert not effective().llm_api_key and not effective().mailbox_password


def test_mailbox_settings_sync_after_worker_adapter_encrypts_once(connected, monkeypatch):
    from django.db import connection
    from leadzen.configuration import _decode
    from leadzen.mailboxes import prepare_worker_mailbox, sync_dashboard_mailbox
    field = Mailbox._meta.get_field("password")
    # Restore process-wide field changes at teardown even if another test has
    # already installed the worker adapter.
    monkeypatch.setattr(field, "get_prep_value", field.get_prep_value)
    monkeypatch.setattr(field, "from_db_value", getattr(field, "from_db_value", lambda raw, *args: raw), raising=False)
    monkeypatch.setattr(field, "_leadzen_encrypted", False, raising=False)
    prepare_worker_mailbox(require_ai=False)
    sync_dashboard_mailbox()
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT password FROM {connection.ops.quote_name(Mailbox._meta.db_table)}")
        stored = cursor.fetchone()[0]
    assert _decode(stored)["mailbox_password"] == effective().mailbox_password
    assert Mailbox.objects.get().password == effective().mailbox_password


@pytest.mark.parametrize("field", ["llm_api_key", "mailbox_password", "mail_api_key", "imap_password"])
def test_credentials_with_header_or_protocol_controls_are_rejected(connected, field):
    with pytest.raises(SettingsError, match="control characters"):
        save_dashboard_settings({"mailbox_address": "sender@example.com"}, **{field: "synthetic\r\nAuthorization: injected"})


@pytest.mark.parametrize("url", ["https://unapproved.example.com/emails", "http://api.resend.com/emails",
    "https://api.resend.com:8443/emails", "https://api.resend.com/emails?credential=synthetic",
    "https://api.resend.com/emails#fragment"])
def test_email_api_revalidates_destination_before_any_socket(url, monkeypatch):
    monkeypatch.delenv("LEADZEN_EMAIL_HOSTS", raising=False)
    with patch("leadzen.transports.public_socket") as connect, pytest.raises(SettingsError):
        post_email(url, "synthetic-key", {})
    connect.assert_not_called()


def test_oversized_email_request_never_contacts_provider():
    with patch("leadzen.transports.public_socket") as connect, pytest.raises(DeliveryError, match="limit"):
        post_email("https://api.resend.com/emails", "synthetic-key", {"text": "x" * 262145})
    connect.assert_not_called()


def duplicate_campaign(connected):
    original = Deal.objects.get(pk=add(connected))
    duplicate = Deal.objects.create(lead=Lead.objects.create(lead_id="synthetic-finder-duplicate", email=original.lead.email.upper()))
    identifier = make(connected, duplicate.pk)
    from leadzen.config.models import EmailCampaign
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    return identifier, original, CampaignRecipient.objects.get(campaign_id=identifier)


def competing_message(deal):
    return Message.objects.create(mailbox=Mailbox.objects.get(), direction=Direction.OUTBOUND,
        message_id="synthetic-competing-attempt", from_address="sender@example.com",
        to_address=deal.lead.email, subject="Previously attempted", body_text="Synthetic")


def test_manual_cold_campaign_cannot_resend_address_under_another_canonical_id(connected):
    identifier, original, recipient = duplicate_campaign(connected)
    competing_message(original)
    assert sending_preview(recipient.campaign, 1)["recipient_ids"] == []
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch.object(sender, "_deliver") as send:
        assert run_campaign(identifier, 1) == 0
    send.assert_not_called()
    recipient.refresh_from_db()
    assert recipient.status == "stopped" and recipient.next_step == 0
    assert Message.objects.count() == 1


def test_competing_manual_attempt_during_tls_cannot_write_http_message(connected):
    identifier, original, recipient = duplicate_campaign(connected)
    sock = FakeSocket(b'HTTP/1.1 200 OK\r\nContent-Length: 18\r\n\r\n{"id":"synthetic"}')
    def finish_tls(*args, **kwargs):
        competing_message(original)
        return sock
    def deliver(mailbox, message, row):
        post_email("https://api.resend.com/emails", "synthetic-key", {"to": str(message["To"])})
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch.object(sender, "_deliver", side_effect=deliver), \
            patch("leadzen.transports.public_socket", return_value=sock), patch("ssl.SSLContext.wrap_socket", side_effect=finish_tls):
        with pytest.raises(PermissionError, match="previous outreach"):
            run_campaign(identifier, 1)
    recipient.refresh_from_db()
    assert sock.written == b"" and recipient.status == "stopped" and recipient.next_step == 0


def test_nonzero_followup_child_and_timeout_are_visible_without_child_output(db, caplog):
    from leadzen.scheduler import tick
    profile = SimpleNamespace()
    profiles = SimpleNamespace(select_related=lambda *args: [profile])
    results = [SimpleNamespace(returncode=7), subprocess.TimeoutExpired("synthetic", 180, output="synthetic-secret")]
    for result in results:
        with patch("leadzen.accounts.models.AccountProfile.objects.filter", return_value=profiles), \
                patch("leadzen.web_worker._database_lock", return_value=nullcontext()), \
                patch("leadzen.workspaces.database_path", return_value=SimpleNamespace(is_file=lambda: True)), \
                patch("leadzen.workspaces.worker_environment", return_value={}), \
                patch("leadzen.scheduler.subprocess.run", **({"side_effect": result} if isinstance(result, Exception) else {"return_value": result})):
            tick()
    assert "exit code 7" in caplog.text and "execution deadline" in caplog.text
    assert "synthetic-secret" not in caplog.text


def test_failed_autopilot_child_is_visible_without_child_output(db, caplog, monkeypatch):
    from leadzen import autopilot_dispatch as dispatch
    monkeypatch.setattr(dispatch, "_workers", {1: (SimpleNamespace(poll=lambda: 9), 0)})
    empty_profiles = SimpleNamespace(select_related=lambda *args: SimpleNamespace(order_by=lambda *args: []))
    with patch("leadzen.accounts.models.AccountProfile.objects.filter", return_value=empty_profiles), \
            patch("leadzen.web_worker._database_lock", return_value=nullcontext()):
        dispatch.tick()
    assert "exit code 9" in caplog.text and not dispatch._workers


def test_eligibility_is_bounded_and_matches_live_initial_safety_gates(connected):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from cold_outreach.emails.models import Thread
    from cold_outreach.leads.models import Suppression
    from leadzen.config.models import ContactPreferences
    from leadzen.outreach import eligible
    leads = Lead.objects.bulk_create([Lead(lead_id=f"synthetic-eligibility-{i}", email=f"person-{i}@example.com") for i in range(100)])
    deals = Deal.objects.bulk_create([Deal(lead=lead) for lead in leads])
    Suppression.objects.create(email=leads[0].email.upper())
    ContactPreferences.objects.create(lead=leads[1], deleted_at=__import__("django.utils.timezone", fromlist=["now"]).now())
    competing_message(deals[2])
    thread = Thread.objects.create(mailbox=Mailbox.objects.get())
    Deal.objects.filter(pk=deals[3].pk).update(thread=thread)
    Message.objects.create(mailbox=Mailbox.objects.get(), thread=thread, direction=Direction.INBOUND,
        message_id="synthetic-prior-inbound", from_address=leads[3].email)
    identifier = make(connected, deals[4].pk)
    with CaptureQueriesContext(connection) as captured:
        assert eligible().count() == 95
        selected = list(eligible()[:25])
    assert len(captured) == 2 and len(selected) == 25
    assert not {d.pk for d in deals[:5]} & {d.pk for d in selected}


def test_exact_stop_after_500_conversations_remains_terminal_for_duplicate_ids(connected):
    from cold_outreach.emails.models import Thread
    from cold_outreach.leads.models import DealState, Suppression
    from leadzen.outreach import honor_saved_optouts
    box = Mailbox.objects.get()
    leads = Lead.objects.bulk_create([Lead(lead_id=f"synthetic-stop-{i}", email=f"stop-{i}@example.com") for i in range(501)])
    Deal.objects.bulk_create([Deal(lead=lead, state=DealState.EMAILED, mailbox=box) for lead in leads])
    last = Deal.objects.get(lead=leads[-1])
    thread = Thread.objects.create(mailbox=box)
    Deal.objects.filter(pk=last.pk).update(thread=thread)
    duplicate = Deal.objects.create(lead=Lead.objects.create(lead_id="synthetic-stop-duplicate", email=leads[-1].email.upper()))
    Message.objects.create(mailbox=box, thread=thread, direction=Direction.INBOUND,
        message_id="synthetic-late-stop", from_address=last.lead.email.upper(), body_text="STOP", kind="")
    honor_saved_optouts(box)
    assert Suppression.objects.filter(email=last.lead.email).exists()
    last.refresh_from_db()
    duplicate.refresh_from_db()
    assert last.state == duplicate.state == DealState.COMPLETED
    assert last.outcome == duplicate.outcome == "unsubscribed"


def test_crm_page_batches_saved_facts_and_preserves_payloads(connected):
    import uuid
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from cold_outreach.emails.models import DeliveryEvent, Thread
    from openoutfind.crm.models import Deal as Decision, Lead as Profile
    from leadzen.config.models import ChatRun, ChatThread, ContactPreferences, DiscoveryLookup, DiscoverySession
    from leadzen.crm import contact_payload, contact_payloads, contacts_query
    profiles = Profile.objects.bulk_create([Profile(full_name=f"Synthetic {i}", profile_url=f"https://example.com/profile/{i}") for i in range(100)])
    Decision.objects.bulk_create([Decision(lead=p, state="Qualified", reason="Saved synthetic decision") for p in profiles])
    leads = Lead.objects.bulk_create([Lead(lead_id=str(p.pk), email=f"profile-{p.pk}@example.com") for p in profiles])
    deals = Deal.objects.bulk_create([Deal(lead=lead) for lead in leads])
    ContactPreferences.objects.create(lead=leads[0], opted_in=True, consent_note="Synthetic signup")
    box = Mailbox.objects.get()
    thread = Thread.objects.create(mailbox=box)
    Deal.objects.filter(pk=deals[0].pk).update(thread=thread)
    Message.objects.create(mailbox=box, thread=thread, direction=Direction.INBOUND, kind="human_reply",
        message_id="synthetic-crm-in", from_address=leads[0].email, body_text="Hello")
    last = Message.objects.create(mailbox=box, thread=thread, direction=Direction.OUTBOUND,
        message_id="synthetic-crm-out", from_address=box.from_address, to_address=leads[0].email)
    DeliveryEvent.objects.create(message=last, status="accepted")
    from django.contrib.auth import get_user_model
    actor_id = get_user_model().objects.get(email="unit@example.com").pk
    chat_thread = ChatThread.objects.create(actor_id=actor_id)
    run = ChatRun.objects.create(thread=chat_thread, actor_id=actor_id, request_id=uuid.uuid4(), status="succeeded")
    receipt_session = DiscoverySession.objects.create(run=run, unit="emails", source_ids=[profiles[0].pk], goal=1)
    DiscoveryLookup.objects.create(session=receipt_session, source_id=profiles[0].pk, state="terminated", credits="1.00", email_status="valid")
    second_run = ChatRun.objects.create(thread=chat_thread, actor_id=actor_id, request_id=uuid.uuid4(), status="failed")
    DiscoverySession.objects.create(run=second_run, unit="emails", source_ids=[profiles[1].pk], goal=1)
    rows = list(contacts_query())
    expected = [contact_payload(deal) for deal in rows]
    with CaptureQueriesContext(connection) as captured:
        actual = contact_payloads(list(contacts_query()))
    assert actual == expected
    assert len(captured) <= 8
    assert any(row["latest_message"] and row["latest_message"]["accepted"] for row in actual)
    assert any(row["lookup"] and row["lookup"]["receipt_state"] == "not_submitted" for row in actual)


@pytest.mark.parametrize("name", ["cold_outreach.emails.sync", "openoutfind.enrichment.bettercontact", "openai._client", "httpx2", "pydantic_ai.models"])
def test_production_provider_logs_never_persist_customer_or_credential_text(monkeypatch, caplog, name):
    import logging
    from leadzen.production_logging import configure_production_logging
    monkeypatch.setenv("LEADZEN_ENV", "production")
    configure_production_logging()
    # Quiet finder runs can leave the root above CRITICAL, suppressing inherited
    # logger levels. Set and restore this logger's level to exercise a real record.
    target_logger = logging.getLogger(name)
    target_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=name):
            try:
                raise ValueError("synthetic-provider-token and private.person@example.com")
            except ValueError:
                target_logger.error("Provider failed for %s with %s", "private.person@example.com", "synthetic-provider-token", exc_info=True, stack_info=True)
    finally:
        target_logger.removeHandler(caplog.handler)
    assert "synthetic-provider-token" not in caplog.text and "private.person@example.com" not in caplog.text
    assert "Provider/dependency event" in caplog.text
    assert caplog.records[-1].name == name and caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].exc_info is None and caplog.records[-1].stack_info is None


def test_safe_application_job_summary_remains_visible_in_production(monkeypatch, caplog):
    import logging
    monkeypatch.setenv("LEADZEN_ENV", "production")
    logging.getLogger("leadzen.scheduler").error("Workspace worker failed (exit code %s).", 7)
    assert "exit code 7" in caplog.text


def test_trickling_provider_body_stops_at_total_deadline(monkeypatch):
    from leadzen.provider_io import ProviderResponseError, read_response
    clock = SimpleNamespace(now=0.0, reads=0)
    def trickle(size):
        clock.now += 0.4
        clock.reads += 1
        return b"x"
    monkeypatch.setattr("leadzen.provider_io.time.monotonic", lambda: clock.now)
    with pytest.raises(ProviderResponseError, match="deadline"):
        read_response(SimpleNamespace(sock=None), SimpleNamespace(read1=trickle), limit=1000, deadline=1.0)
    assert clock.reads == 3


def test_provider_response_byte_limit_is_enforced_before_unbounded_read():
    import io
    import time
    from leadzen.provider_io import ProviderResponseError, read_response
    with pytest.raises(ProviderResponseError, match="limit"):
        read_response(SimpleNamespace(sock=None), io.BytesIO(b"x" * 101), limit=100, deadline=time.monotonic() + 2)


@pytest.mark.parametrize("detached", [False, True])
def test_provider_deadline_interrupts_blocked_and_detached_response_socket(detached):
    import socket
    import time
    from leadzen.provider_io import ProviderResponseError, read_response
    reader, writer = socket.socketpair()
    connection = SimpleNamespace(sock=None if detached else reader)
    response = SimpleNamespace(read1=lambda size: reader.recv(size), fp=SimpleNamespace(raw=SimpleNamespace(_sock=reader)))
    started = time.monotonic()
    try:
        with pytest.raises((ProviderResponseError, TimeoutError)):
            read_response(connection, response, limit=100, deadline=started + 0.05)
        assert time.monotonic() - started < 1
    finally:
        reader.close()
        writer.close()
