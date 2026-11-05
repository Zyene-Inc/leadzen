"""Bounces, spam complaints and sending-domain health (ported from Warmbly)."""
# Copyright 2026 Mindroot Ltd; modifications copyright 2026 Zyene. Test cases
# adapted from Warmbly (https://github.com/warmbly/warmbly), commit
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1, Apache License 2.0. See
# THIRD_PARTY_NOTICES.md.
import uuid
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from cold_outreach.emails.models import Mailbox, Message, Thread
from cold_outreach.leads.models import Deal, Lead, Suppression
from leadzen import arf, dsn
from leadzen.config.models import MailSignal, SiteConfig
from leadzen.configuration import save_dashboard_settings
from leadzen.domain_health import check
from leadzen.mail_signals import COMPLAINT, HARD_BOUNCE, NONE, SOFT_BOUNCE, apply_mail_signals, keep_reports


@pytest.fixture
def connected(account_client, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    save_dashboard_settings({"provider": "openai", "model": "synthetic-model", "base_url": "https://api.example.com/v1", "mailbox_address": "sender@zyene-synthetic.com", "smtp_host": "smtp.example.com", "smtp_port": 465, "imap_host": "imap.example.com", "imap_port": 993, "signature": "Synthetic Sender"}, llm_api_key="synthetic-ai-key", mailbox_password="synthetic-mail-password")
    config = SiteConfig.load()
    config.operator_name, config.operator_country_code = "Synthetic Sender", "US"
    config.save()
    return account_client


def dsn_report(status, diagnostic, recipient="bruce@example.com", original="synthetic-out@zyene-synthetic.com", action="failed"):
    return (
        "From: Mail Delivery System <MAILER-DAEMON@mx.example.com>\r\n"
        "To: sender@zyene-synthetic.com\r\nSubject: Undelivered Mail Returned to Sender\r\n"
        "Message-ID: <ndr-%s@mx.example.com>\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/report; report-type=delivery-status; boundary="B"\r\n\r\n'
        "--B\r\nContent-Type: text/plain\r\n\r\nThis is the mail system. Delivery failed.\r\n"
        "--B\r\nContent-Type: message/delivery-status\r\n\r\nReporting-MTA: dns; mx.example.com\r\n\r\n"
        "Final-Recipient: rfc822; %s\r\nAction: %s\r\nStatus: %s\r\nDiagnostic-Code: smtp; %s\r\n\r\n"
        "--B\r\nContent-Type: message/rfc822\r\n\r\nFrom: sender@zyene-synthetic.com\r\nTo: %s\r\n"
        "Subject: Patient reviews\r\nMessage-ID: <%s>\r\n\r\nHi Bruce\r\n--B--\r\n"
    ) % (uuid.uuid4().hex, recipient, action, status, diagnostic, recipient, original)


def arf_report(feedback_type="abuse", original="synthetic-out@zyene-synthetic.com"):
    return (
        "From: staff@hotmail.com\r\nTo: sender@zyene-synthetic.com\r\nSubject: complaint about message\r\n"
        "Message-ID: <fbl-%s@hotmail.com>\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/report; report-type=feedback-report; boundary="F"\r\n\r\n'
        "--F\r\nContent-Type: text/plain\r\n\r\nThis is an email abuse report.\r\n"
        "--F\r\nContent-Type: message/feedback-report\r\n\r\nFeedback-Type: %s\r\nUser-Agent: Hotmail FBL\r\n"
        "Version: 1\r\nOriginal-Mail-From: <sender@zyene-synthetic.com>\r\nOriginal-Rcpt-To: <bruce@example.com>\r\n\r\n"
        "--F\r\nContent-Type: message/rfc822-headers\r\n\r\nFrom: sender@zyene-synthetic.com\r\nTo: bruce@example.com\r\n"
        "Message-ID: <%s>\r\n\r\n--F--\r\n"
    ) % (uuid.uuid4().hex, feedback_type, original)


def outreach():
    box = Mailbox.objects.first()
    lead = Lead.objects.create(lead_id=uuid.uuid4().hex, email="bruce@example.com", first_name="Bruce")
    thread = Thread.objects.create(mailbox=box)
    Message.objects.create(mailbox=box, thread=thread, direction="out", kind="outbound", message_id="synthetic-out@zyene-synthetic.com",
                           from_address=box.from_address, to_address=lead.email, subject="Patient reviews", sent_at=timezone.now())
    deal = Deal.objects.create(lead=lead, reason="Synthetic", state="Emailed", thread=thread, mailbox=box)
    return box, deal


def inbound(box, raw, kind="bounce", sender="mailer-daemon@mx.example.com"):
    return Message.objects.create(mailbox=box, direction="in", kind=kind, message_id=uuid.uuid4().hex, from_address=sender,
                                  to_address=box.from_address, subject="Report", raw=raw.encode(), received_at=timezone.now())


# ── Parsers (Warmbly's cases) ───────────────────────────────────────


def test_dsn_permanent_and_transient():
    permanent = dsn.parse("Final-Recipient: rfc822; a@b.com\nAction: failed\nStatus: 5.1.1\nDiagnostic-Code: smtp; 550 5.1.1 User unknown\n")
    assert permanent.permanent and permanent.failed_recipient == "a@b.com" and permanent.status == "5.1.1"
    assert permanent.reason() == "550 5.1.1 User unknown"
    delayed = dsn.parse("Action: delayed\nStatus: 4.4.1\n")
    assert delayed.is_bounce and not delayed.permanent
    # "failed" next to a 4.x.x status is retry-then-fail: transient.
    assert not dsn.parse("Action: failed\nStatus: 4.2.0\n").permanent
    gmail = dsn.Report().with_failed_recipients("x@group.example", "Delivery Status Notification (Failure)", "The group does not accept posts")
    assert gmail.permanent and gmail.failed_recipient == "x@group.example"
    assert not dsn.Report().with_failed_recipients("x@y.com", "Delayed", "will retry").permanent


@pytest.mark.parametrize("text,cause", [
    ("550 5.1.1 User unknown", dsn.CAUSE_RECIPIENT_INVALID),
    ("552 5.2.2 Mailbox full", dsn.CAUSE_MAILBOX_FULL),
    ("Recipient address rejected: Mailbox full", dsn.CAUSE_MAILBOX_FULL),
    ("554 5.7.1 Service unavailable; client host blocked using spamhaus", dsn.CAUSE_REPUTATION_BLOCK),
    ("Sender address rejected: User unknown in local recipient table", dsn.CAUSE_REPUTATION_BLOCK),
    ("451 4.7.1 greylisted, try again", dsn.CAUSE_TRANSIENT),
    ("550 5.4.1 Recipient address rejected: Access denied", dsn.CAUSE_RECIPIENT_INVALID),
    ("550 5.0.0 rejected", dsn.CAUSE_UNKNOWN),
    ("connecting from 192.168.1.10 5.1.1", dsn.CAUSE_RECIPIENT_INVALID),
])
def test_dsn_blame(text, cause):
    assert dsn.blame(text) == cause


def test_arf_reads_only_abuse_and_never_the_sender():
    report = arf.parse_mime(arf_report().encode())
    assert report.is_complaint and report.original_message_id == "synthetic-out@zyene-synthetic.com"
    assert report.complained_recipient == "bruce@example.com" and report.user_agent == "Hotmail FBL"
    for kind in ("not-spam", "fraud", "opt-out"):
        assert not arf.parse(f"Feedback-Type: {kind}\nMessage-ID: <x@y.com>\n").is_complaint
    assert arf.parse("Feedback-Type: abuse\nOriginal-Mail-From: <s@ours.com>\n").complained_recipient == ""
    assert not arf.detect("ada@acme.com", "Re: your note", "text/plain")
    assert not arf.detect("mailer-daemon@acme.com", "Undeliverable", "multipart/report; report-type=delivery-status")


def test_sync_keeps_complaint_reports_from_strangers():
    import email
    rule = keep_reports(lambda mailbox, msg: False)
    assert keep_reports(rule) is rule
    assert rule(None, email.message_from_string(arf_report()))
    assert not rule(None, email.message_from_string("From: stranger@acme.com\nSubject: hello\n\nhi"))


# ── Mailbox projection ──────────────────────────────────────────────


def test_hard_bounce_blocks_with_reason_and_date(connected):
    box, deal = outreach()
    report = inbound(box, dsn_report("5.1.1", "550 5.1.1 <bruce@example.com>: Recipient address rejected: User unknown"))
    assert apply_mail_signals(box) == 1
    record = Suppression.objects.get(email="bruce@example.com")
    assert record.reason.startswith("Hard bounce: ") and "User unknown" in record.reason and record.suppressed_at
    signal = MailSignal.objects.get(message_pk=report.pk)
    assert (signal.kind, signal.cause, signal.suppressed) == (HARD_BOUNCE, dsn.CAUSE_RECIPIENT_INVALID, True)
    deal.refresh_from_db()
    assert deal.state == "Completed"
    # Each report is read once.
    assert apply_mail_signals(box) == 0 and MailSignal.objects.count() == 1


@pytest.mark.parametrize("status,diagnostic,action,cause", [
    ("4.2.2", "452 4.2.2 Mailbox full, try again later", "delayed", dsn.CAUSE_TRANSIENT),
    ("5.2.2", "552 5.2.2 Mailbox full", "failed", dsn.CAUSE_MAILBOX_FULL),
    ("5.7.1", "554 5.7.1 Message rejected due to spam policy", "failed", dsn.CAUSE_REPUTATION_BLOCK),
])
def test_soft_bounce_is_recorded_not_blocked(connected, status, diagnostic, action, cause):
    box, _ = outreach()
    report = inbound(box, dsn_report(status, diagnostic, action=action))
    assert apply_mail_signals(box) == 0
    assert not Suppression.objects.exists()
    signal = MailSignal.objects.get(message_pk=report.pk)
    assert (signal.kind, signal.cause, signal.suppressed) == (SOFT_BOUNCE, cause, False)


def test_bounce_for_unknown_send_or_other_recipient_blocks_nobody(connected):
    box, _ = outreach()
    inbound(box, dsn_report("5.1.1", "550 User unknown", original="not-ours@elsewhere.com"))
    inbound(box, dsn_report("5.1.1", "550 User unknown", recipient="someone-else@example.com"))
    assert apply_mail_signals(box) == 0
    assert not Suppression.objects.exists()
    assert set(MailSignal.objects.values_list("kind", flat=True)) == {NONE}


def test_spam_complaint_blocks_the_address_we_sent_to(connected):
    box, _ = outreach()
    report = inbound(box, arf_report(), kind="unrelated", sender="staff@hotmail.com")
    assert apply_mail_signals(box) == 1
    record = Suppression.objects.get(email="bruce@example.com")
    assert record.reason == "Spam complaint reported by Hotmail FBL"
    assert MailSignal.objects.get(message_pk=report.pk).kind == COMPLAINT
    # The sending address named as Original-Mail-From is never blocked.
    assert not Suppression.objects.filter(email="sender@zyene-synthetic.com").exists()


def test_not_spam_feedback_and_human_replies_are_ignored(connected):
    box, _ = outreach()
    inbound(box, arf_report("not-spam"), kind="unrelated", sender="staff@hotmail.com")
    human = inbound(box, dsn_report("5.1.1", "550 User unknown"), kind="human_reply", sender="bruce@example.com")
    assert apply_mail_signals(box) == 0
    assert not Suppression.objects.exists()
    assert not MailSignal.objects.filter(message_pk=human.pk).exists()


def test_strict_sync_reads_reports_after_the_inbox(connected):
    box, _ = outreach()
    inbound(box, dsn_report("5.1.1", "550 5.1.1 User unknown"))
    from leadzen.transports import sync_replies_strict
    from cold_outreach.emails.models import FolderCoverage

    def mirrored(mailbox, folder="INBOX"):
        FolderCoverage.objects.update_or_create(mailbox=mailbox, folder=folder, defaults={"synced_at": timezone.now(), "uidvalidity": 1})
        return 0
    with patch("cold_outreach.emails.sync.mirror", side_effect=mirrored):
        sync_replies_strict(box)
    assert Suppression.objects.filter(email="bruce@example.com").exists()


# ── Domain health ───────────────────────────────────────────────────


class FakeDNS:
    def __init__(self, txt=None, mx=None, broken=()):
        self.records, self.mx_hosts, self.broken = txt or {}, mx or [], set(broken)
        self.asked = []

    def txt(self, name):
        self.asked.append(name)
        return ([], True) if name in self.broken else (self.records.get(name, []), False)

    def mx(self, name):
        return ([], True) if "mx" in self.broken else (self.mx_hosts, False)


def test_domain_health_passing_with_provider_dkim_hint():
    lookups = FakeDNS({"acme.com": ["v=spf1 include:zoho.com ~all"], "_dmarc.acme.com": ["v=DMARC1; p=quarantine"],
                       "zoho._domainkey.acme.com": ["v=DKIM1; k=rsa; p=MIGfMA0"]}, ["mx.zoho.com"])
    result = check("Acme.com.", lookups)
    assert result["state"] == "passing" and "DKIM is set up" in result["summary"]
    rows = {c["key"]: c for c in result["checks"]}
    assert [rows[k]["status"] for k in ("spf", "dkim", "dmarc", "mx")] == ["pass"] * 4
    assert "sends to spam" in rows["dmarc"]["message"]
    # The provider's selector is tried in the first batch.
    assert lookups.asked.index("zoho._domainkey.acme.com") < 10


def test_domain_health_missing_records_explain_the_fix():
    result = check("acme.com", FakeDNS(mx=["mx.zoho.eu"]))
    assert result["state"] == "failing" and result["summary"] == "Needs attention: SPF and DMARC."
    rows = {c["key"]: c for c in result["checks"]}
    assert rows["spf"]["fix"] == {"type": "TXT", "host": "acme.com", "value": "v=spf1 include:zoho.eu ~all"}
    assert rows["dmarc"]["fix"]["host"] == "_dmarc.acme.com" and "p=none" in rows["dmarc"]["fix"]["value"]
    # An undiscovered DKIM key is "not verified", never "missing".
    assert rows["dkim"]["status"] == "unknown" and rows["dkim"]["fix"]["host"] == "zoho._domainkey.acme.com"


def test_domain_health_edge_cases():
    # A subdomain inherits its parent's DMARC (sp= applies).
    inherited = check("mail.acme.com", FakeDNS({"mail.acme.com": ["v=spf1 -all"], "_dmarc.acme.com": ["v=DMARC1; p=reject; sp=none"]}, ["mx.acme.com"]))
    dmarc = next(c for c in inherited["checks"] if c["key"] == "dmarc")
    assert dmarc["status"] == "pass" and "policy: none" in dmarc["message"] and "acme.com" in dmarc["message"]
    # Two SPF records fail; a revoked DKIM key (empty p=) does not count.
    doubled = check("acme.com", FakeDNS({"acme.com": ["v=spf1 a ~all", "v=spf1 mx ~all"], "_dmarc.acme.com": ["v=DMARC1; p=none"],
                                         "google._domainkey.acme.com": ["v=DKIM1; p="]}, ["aspmx.l.google.com"]))
    rows = {c["key"]: c["status"] for c in doubled["checks"]}
    assert rows["spf"] == "fail" and rows["dkim"] == "unknown"
    # A resolver failure is unknown, never a misconfiguration.
    timeout = check("acme.com", FakeDNS(broken={"acme.com"}))
    assert timeout["state"] == "unknown" and next(c for c in timeout["checks"] if c["key"] == "spf")["status"] == "unknown"
    # Special-use domains are not looked up.
    reserved = FakeDNS()
    assert check("sender.example", reserved)["state"] == "unknown" and reserved.asked == []


def test_domain_health_endpoint_uses_the_saved_mailbox(connected):
    with patch("leadzen.domain_health.Lookups", return_value=FakeDNS()) as lookups:
        result = connected.post("/api/settings/domain-health", {"domain": "attacker.example"}, content_type="application/json",
                                HTTP_AUTHORIZATION="Bearer test-dashboard-token")
    assert result.status_code == 200, result.content
    assert result.json()["domain"] == "zyene-synthetic.com"
    lookups.assert_called_once()
