"""Reply sorting in Inbox (ported from Warmbly's rule-based reply classifier)."""
# Copyright 2026 Mindroot Ltd; modifications copyright 2026 Zyene. Test cases
# adapted from Warmbly (https://github.com/warmbly/warmbly), commit
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1, files internal/app/replyclassify/
# *_test.go, Apache License 2.0. See THIRD_PARTY_NOTICES.md.
import email
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from cold_outreach.emails.models import Mailbox, Message, Thread
from cold_outreach.leads.models import Deal, Lead, Suppression
from leadzen import reply_classify as rc
from leadzen.config.models import CampaignRecipient, EmailCampaign, ReplyLabel, SiteConfig
from leadzen.configuration import save_dashboard_settings
from leadzen.reply_sorting import replies, sort_replies

RETURN_DATE_CASES = [
    ('english return on with ordinal', 'Automatic reply: your email', 'Thanks for your message. I will reply to your email on my return on the 8th September.', None, '2026-09-08'),
    ('english back on iso', 'Out of office', 'I am away and back on 2026-09-21.', None, '2026-09-21'),
    ('english until month day', 'Out of Office', "I'm out of the office until September 15, back to normal after.", None, '2026-09-15'),
    ('german wieder erreichbar am', 'Automatische Antwort: Angebot', 'Ich bin nicht im Büro und wieder erreichbar am 09.09.2026.', None, '2026-09-09'),
    ('german ab dem short dotted', 'Abwesenheitsnotiz', 'Ich bin ab dem 10.9. wieder im Büro.', None, '2026-09-10'),
    ('german bis einschliesslich is the last day away', 'Abwesend', 'Ich bin bis einschließlich 30. September abwesend.', None, '2026-10-01'),
    ('english through is the last day away', 'Out of office', 'Away through 18 September.', None, '2026-09-19'),
    ('english until names the return itself', 'Out of office', 'Out of the office until 18 September.', None, '2026-09-18'),
    ('the earliest date in the window wins', 'Out of office', 'I am away until 10 September; ref 2026-10-01 for the contract.', None, '2026-09-10'),
    ('french jusqu au', 'Réponse automatique', "Je suis absent jusqu'au 12 septembre.", None, '2026-09-12'),
    ('dutch terug op', 'Automatisch antwoord', 'Ik ben terug op 7 oktober.', None, '2026-10-07'),
    ('year rolls forward', 'Out of office', "I'll be back on 5 January.", (2026, 12, 20), '2027-01-05'),
    ('no date at all', 'Automatische Antwort: Ihre Nachricht', 'Ich bin zur Zeit nicht im Büro.', None, ''),
    ('date with no cue', 'Automatic reply', 'Our next release is 2026-10-01.', None, ''),
    ('date already past', 'Out of office', 'I was back on 2026-08-01.', None, ''),
    ('date beyond the window', 'Out of office', 'I am back on 2027-06-01.', None, ''),
    ('ambiguous slash date is refused', 'Out of office', "I'm back on 9/8/2026.", None, ''),
    ('a time is not a date', 'Out of office', 'Back on 9.9.2026 (I leave at 17.30.)', None, '2026-09-09'),
    ('a bare month and year is not a date', 'Out of office', "I'm out of the office until October 2026.", None, ''),
    ('a bare month and year, back on', 'Out of office', "I'll be back on November 2026.", None, ''),
    ('german ab montag den', 'Abwesenheitsnotiz', 'Ab Montag den 14.09. bin ich wieder im Büro.', None, '2026-09-14'),
    ('german ab montag comma den', 'Abwesenheitsnotiz', 'Ab Montag, den 14.09., bin ich wieder im Büro.', None, '2026-09-14'),
    ('german ab montag comma', 'Abwesenheitsnotiz', 'Ab Montag, 14.9., bin ich wieder im Büro.', None, '2026-09-14'),
    ('german ab dienstag comma', 'Abwesenheitsnotiz', 'Ab Dienstag, 15. September, bin ich wieder erreichbar.', None, '2026-09-15'),
    ('german ab kw', 'Abwesenheitsnotiz', 'Ich bin ab KW 38 wieder erreichbar.', None, '2026-09-14'),
    ('german ab kw without a space', 'Abwesenheitsnotiz', 'Ab KW38 wieder im Büro.', None, '2026-09-14'),
    ('german ab der kalenderwoche', 'Abwesenheitsnotiz', 'Ab der Kalenderwoche 38 bin ich wieder im Büro.', None, '2026-09-14'),
    ('german bis kw is the last week away', 'Abwesenheitsnotiz', 'Ich bin bis KW37 im Urlaub.', None, '2026-09-14'),
    ('german bis einschliesslich kw', 'Abwesenheitsnotiz', 'Ich bin bis einschließlich KW 37 nicht im Büro.', None, '2026-09-14'),
    ('a week under way means back now', 'Abwesenheitsnotiz', 'Ab KW 36 bin ich wieder da.', None, '2026-09-04'),
    ('german bis kw range is away through the last week', 'Abwesenheitsnotiz', 'Ich bin bis KW 37/38 im Urlaub.', None, '2026-09-21'),
    ('german kw range with an en dash', 'Abwesenheitsnotiz', 'Ich bin bis KW 37–38 im Urlaub.', None, '2026-09-21'),
    ('german ab kw range starts with its first week', 'Abwesenheitsnotiz', 'Ab KW 38/39 bin ich wieder erreichbar.', None, '2026-09-14'),
    ('german ab weekday bis is a range', 'Abwesenheitsnotiz', 'Ich bin ab Freitag, 4.9., bis 18.9. im Urlaub.', None, '2026-09-18'),
    ('german ab dem bis zum is a range', 'Abwesenheitsnotiz', 'Ich bin ab dem 4.9. bis zum 18.9. nicht im Büro.', None, '2026-09-18'),
    ('a negated return word keeps the range', 'Abwesenheitsnotiz', 'Ab dem 7.9. bin ich nicht erreichbar, bis einschließlich 18.9. vertritt mich Frau Klein.', None, '2026-09-19'),
    ('a month abbreviation keeps the range', 'Abwesenheitsnotiz', 'Ich bin ab dem 4. Sept. bis zum 18. Sept. im Urlaub.', None, '2026-09-18'),
    ('a return word ends the range', 'Abwesenheitsnotiz', 'Ab dem 14.9. bin ich wieder erreichbar, bis zum 30.9. jedoch nur eingeschränkt.', None, '2026-09-14'),
    ('a sentence ends the range', 'Abwesenheitsnotiz', 'Ab Montag, 14.9., bin ich im Haus. Bis 30.9. gilt unser Aktionspreis.', None, '2026-09-14'),
    ('a sentence opening on bis after a date ends the range', 'Abwesenheitsnotiz', 'Ich bin ab dem 4.9. Bis zum 18.9. vertritt mich Frau Klein, danach Herr Braun.', None, '2026-09-04'),
    ('a bis before the return date is not its end', 'Abwesenheitsnotiz', 'Ab dem 14.9. wieder da. Bis zum 11.9. vertritt mich Frau Klein.', None, '2026-09-14'),
    ('a week already over is not a return date', 'Abwesenheitsnotiz', 'Ich bin bis KW 30 im Urlaub.', None, ''),
    ('a week that does not exist', 'Abwesenheitsnotiz', 'Ich bin ab KW 60 wieder da.', None, ''),
    ('week rolls into next year', 'Abwesenheitsnotiz', 'Ab KW 2 bin ich wieder im Büro.', (2026, 12, 21), '2027-01-11'),
    ('french typographic apostrophe', 'Réponse automatique', 'Je suis absent jusqu’au 12 septembre.', None, '2026-09-12'),
]


@pytest.mark.parametrize("name,subject,body,now,want", RETURN_DATE_CASES, ids=[c[0] for c in RETURN_DATE_CASES])
def test_return_date_matches_warmbly(name, subject, body, now, want):
    got = rc.find_return_date(subject, body, date(*now) if now else date(2026, 9, 4))
    assert (got.isoformat() if got else "") == want


@pytest.mark.parametrize("subject,body,want", [
    ("", "Please unsubscribe me from this list.", True),
    ("Re: hi", "remove me from your list", True),
    ("", "Stop emailing me.", True),
    ("", "I'd like to opt-out.", True),
    ("", "Stop by our booth next week!", False),
    ("", "We have an unsubscribed model in beta", False),
    ("", "Sounds interesting, let's talk.\n\nOn Tue, Sep 1, 2026 Jane <jane@x.com> wrote:\n> If this isn't relevant, just reply and I'll stop.\n> Unsubscribe: https://example.com/u/abc", False),
    ("", "Yes please\n> unsubscribe here", False),
    ("", "Please remove me\n\nOn Mon Jane wrote:\n> hello", True),
    ("", "not interested\r\nFrom: Jane\r\nSent: Monday\r\nunsubscribe", False),
    ("", "Please don’t email me again.", True),
    ("", "", False),
    ("", "STOP!!", True),
    ("", "Hi Sam,\n\nRemove me please.\n\nThanks,\nJane Doe\nSent from my iPhone", True),
    ("", "Stop\nI'd love a demo though", False),
    ("", "Bitte tragen Sie mich aus Ihrem Verteiler aus.", True),
    ("", "Hiermit widerspreche ich gem. Art. 21 DSGVO der weiteren Verarbeitung meiner Daten.", True),
    ("", "Por favor, dejen de enviarme correos.", True),
    ("", "取消订阅", True),
])
def test_opt_out_matches_warmbly(subject, body, want):
    assert rc.is_opt_out(subject, body) is want


def headers(**values):
    message = email.message.Message()
    for key, value in values.items():
        message[key.replace("_", "-")] = value
    return message


@pytest.mark.parametrize("hdrs,subject,body,label", [
    ({}, "Re: Patient reviews", "Sounds great, let's talk Tuesday.", rc.POSITIVE),
    ({}, "Re: Patient reviews", "How much does it cost?", rc.POSITIVE),
    ({}, "Re: Patient reviews", "Thanks, but we're not interested.", rc.NEGATIVE),
    ({}, "Re: Patient reviews", "No thanks, we already have a vendor.", rc.NEGATIVE),
    ({}, "Re: Ihre Nachricht", "Danke, im Moment kein Bedarf.", rc.NEGATIVE),
    ({}, "Re: Patient reviews", "Please remove me from your list.", rc.UNSUBSCRIBE),
    ({}, "Re: Patient reviews", "Can you call me Thursday at 3?", rc.UNKNOWN),
    # A human mentioning a holiday in the body is not an away message.
    ({}, "Re: Quick question", "I'm on holiday next week, ping me after.", rc.UNKNOWN),
    ({}, "Automatic reply: Patient reviews", "I am out until 18 September.", rc.OUT_OF_OFFICE),
    ({}, "Automatische Antwort: Ihre Nachricht", "Ich bin nicht im Büro.", rc.OUT_OF_OFFICE),
    ({"Auto_Submitted": "auto-replied"}, "Re: Patient reviews", "Thanks for your email.", rc.OUT_OF_OFFICE),
    ({"Auto_Submitted": "auto-generated"}, "Your ticket #123", "We received your request.", rc.AUTO_REPLY),
    ({"From": "noreply@vendor.com"}, "Receipt", "Thanks", rc.AUTO_REPLY),
    ({"X_Failed_Recipients": "a@b.com", "Auto_Submitted": "auto-replied"}, "Delivery Status Notification (Failure)", "", rc.AUTO_REPLY),
    ({}, "Report Domain: example.test Submitter: google.com Report-ID: abc", "", rc.AUTO_REPLY),
])
def test_classify_layers(hdrs, subject, body, label):
    assert rc.classify(headers(**hdrs), subject, body).label == label


# ── Inbox actions ───────────────────────────────────────────────────


@pytest.fixture
def connected(account_client, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    save_dashboard_settings({"provider": "openai", "model": "synthetic-model", "base_url": "https://api.example.com/v1", "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "smtp_port": 465, "imap_host": "imap.example.com", "imap_port": 993, "signature": "Synthetic Sender"}, llm_api_key="synthetic-ai-key", mailbox_password="synthetic-mail-password")
    config = SiteConfig.load()
    config.operator_name, config.operator_country_code = "Synthetic Sender", "US"
    config.save()
    return account_client


def sequence(email_address="bruce@example.com"):
    box = Mailbox.objects.first()
    lead = Lead.objects.create(lead_id=uuid.uuid4().hex, email=email_address, first_name="Bruce")
    thread = Thread.objects.create(mailbox=box)
    Message.objects.create(mailbox=box, thread=thread, direction="out", kind="outbound", message_id=f"out-{uuid.uuid4().hex}",
                           from_address=box.from_address, to_address=lead.email, subject="Patient reviews", sent_at=timezone.now())
    deal = Deal.objects.create(lead=lead, reason="Synthetic", state="Emailed", thread=thread, mailbox=box)
    campaign = EmailCampaign.objects.create(name="Synthetic", from_address=box.from_address, status="active",
                                            steps=[{"subject": "a", "body": "b", "delay_days": 0}, {"subject": "c", "body": "d", "delay_days": 3}])
    recipient = CampaignRecipient.objects.create(campaign=campaign, deal=deal, next_step=1, status="pending")
    return box, deal, recipient


def reply(box, deal, subject, body, kind="human_reply", raw=b"", sender=None):
    raw = raw or f"From: {sender or deal.lead.email}\r\nTo: {box.from_address}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}".encode()
    return Message.objects.create(mailbox=box, thread=deal.thread, direction="in", kind=kind, message_id=uuid.uuid4().hex,
                                  from_address=sender or deal.lead.email, to_address=box.from_address, subject=subject,
                                  body_text=body, raw=raw or None, received_at=timezone.now())


def test_unsubscribe_reply_goes_on_do_not_contact(connected):
    box, deal, recipient = sequence()
    message = reply(box, deal, "Re: Patient reviews", "Please take me off your list.")
    assert sort_replies(box) == 1
    label = ReplyLabel.objects.get(message_pk=message.pk)
    assert (label.label, label.action) == ("unsubscribe", "blocked")
    assert Suppression.objects.get(email="bruce@example.com").reason == "Asked to unsubscribe in a reply"
    # Read once.
    assert sort_replies(box) == 0


def test_own_footer_quoted_without_markers_is_not_a_request(connected):
    from cold_outreach.emails.sender import OPT_OUT_LINE
    box, deal, _ = sequence()
    message = reply(box, deal, "Re: Patient reviews", f"Sure, send pricing.\n\n{OPT_OUT_LINE}")
    sort_replies(box)
    assert ReplyLabel.objects.get(message_pk=message.pk).label == "interested"
    assert not Suppression.objects.exists()


def test_newsletter_footer_is_not_an_unsubscribe(connected):
    box, deal, _ = sequence()
    raw = b"From: news@vendor.com\r\nList-Unsubscribe: <mailto:u@vendor.com>\r\nSubject: Weekly\r\n\r\nunsubscribe here"
    message = reply(box, deal, "Weekly", "To unsubscribe from these emails, click here.", raw=raw, sender="news@vendor.com")
    sort_replies(box)
    assert ReplyLabel.objects.get(message_pk=message.pk).label == "needs_review"
    assert not Suppression.objects.exists()


def test_out_of_office_holds_followups_until_after_the_return_date(connected):
    box, deal, recipient = sequence()
    back = (timezone.localdate() + timedelta(days=10))
    message = reply(box, deal, "Automatic reply: Patient reviews", f"I am out of the office until {back.isoformat()}.", kind="auto_reply")
    sort_replies(box)
    label = ReplyLabel.objects.get(message_pk=message.pk)
    assert (label.label, label.return_date, label.action) == ("out_of_office", back, "held")
    recipient.refresh_from_db()
    assert recipient.status == "pending"
    assert timezone.localtime(recipient.next_send_at).date() == rc.next_business_day(back)
    # An away message does not count as a reply; a human one still does.
    assert not replies(thread_id=deal.thread_id).exists()
    reply(box, deal, "Re: Patient reviews", "Back now, not interested.")
    assert replies(thread_id=deal.thread_id).exists()


def test_out_of_office_without_a_date_uses_the_fallback_hold(connected):
    box, deal, recipient = sequence()
    reply(box, deal, "Out of Office", "I am travelling with limited access to email.", kind="auto_reply")
    sort_replies(box)
    recipient.refresh_from_db()
    assert recipient.next_send_at > timezone.now() + timedelta(days=6)
    assert ReplyLabel.objects.get().return_date is None


def test_campaign_stops_on_a_human_reply_but_not_on_an_away_message(connected):
    from leadzen.campaigns import replied_after_outreach
    box, deal, recipient = sequence()
    reply(box, deal, "Automatic reply: Patient reviews", "Back on 2026-12-01", kind="auto_reply")
    # Unlabelled mail still stops follow-ups, exactly as before.
    assert replied_after_outreach(deal)
    sort_replies(box)
    assert not replied_after_outreach(deal)


def test_strict_sync_sorts_replies(connected):
    box, deal, _ = sequence()
    reply(box, deal, "Re: Patient reviews", "Sounds great, let's talk.")
    from leadzen.transports import sync_replies_strict
    from cold_outreach.emails.models import FolderCoverage

    def mirrored(mailbox, folder="INBOX"):
        FolderCoverage.objects.update_or_create(mailbox=mailbox, folder=folder, defaults={"synced_at": timezone.now(), "uidvalidity": 1})
        return 0
    with patch("cold_outreach.emails.sync.mirror", side_effect=mirrored), patch("cold_outreach.emails.sender._deliver") as send:
        sync_replies_strict(box)
        send.assert_not_called()
    assert ReplyLabel.objects.get().label == "interested"


def test_inbox_shows_labels_and_filters(connected):
    box, deal, _ = sequence()
    first = reply(box, deal, "Re: Patient reviews", "Sounds great, let's talk.")
    _, other, _ = sequence("ann@example.com")
    reply(box, other, "Re: Patient reviews", "No thanks.")
    sort_replies(box)
    listed = connected.get("/api/inbox/conversations").json()
    assert {item["reply_label"]["label"] for item in listed["items"]} == {"interested", "not_interested"}
    interested = connected.get("/api/inbox/conversations?label=interested").json()
    assert interested["total"] == 1 and interested["items"][0]["address"] == "bruce@example.com"
    assert connected.get("/api/inbox/conversations?label=bogus").status_code == 400
    detail = connected.get(f"/api/inbox/conversations/{deal.thread_id}").json()
    labels = {m["id"]: m["reply_label"] for m in detail["messages"]}
    assert labels[first.pk]["label"] == "interested"
    # Suggesting a reply is unchanged: still a reviewed draft, nothing sent.
    assert detail["can_reply"] is True
