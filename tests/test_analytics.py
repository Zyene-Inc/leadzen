"""Results: campaign attribution, reply/bounce/opt-out definitions and history backfill."""
import importlib
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from cold_outreach.emails.models import DeliveryEvent, Direction, Mailbox, Message
from cold_outreach.leads.models import Deal, Suppression
from leadzen.analytics import results
from leadzen.campaigns import run_campaign
from leadzen.config.models import CampaignRecipient, CampaignSend
from tests.test_campaigns import add, connected, make  # noqa: F401  (fixture)


def send(identifier):
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), \
            patch("cold_outreach.emails.sender._deliver"), patch("leadzen.transports.sync_replies_strict"):
        sent = run_campaign(identifier, 5)
    Mailbox.objects.update(next_send_at=None)
    CampaignRecipient.objects.update(next_send_at=timezone.now() - timedelta(minutes=1))
    return sent


def accept_all():
    for message in Message.objects.filter(direction=Direction.OUTBOUND).exclude(delivery_events__status="accepted"):
        DeliveryEvent.objects.create(message=message, status="accepted")


def inbound(deal, kind="human_reply"):
    deal.refresh_from_db()
    first = Message.objects.filter(thread_id=deal.thread_id, direction=Direction.OUTBOUND).first()
    return Message.objects.create(mailbox=first.mailbox, thread_id=deal.thread_id, direction=Direction.INBOUND, kind=kind,
                                  message_id=f"<{kind}-{deal.pk}-{timezone.now().timestamp()}@example.com>", from_address=deal.lead.email,
                                  subject="Re: hello", body_text="Thanks")


def started(client):
    person = add(client)
    identifier = make(client, person)
    client.put(f"/api/campaigns/{identifier}", data='{"status":"active"}', content_type="application/json")
    return identifier, Deal.objects.get(pk=person)


def test_each_campaign_send_is_attributed_and_a_reply_is_credited_to_its_step(connected):
    identifier, deal = started(connected)
    assert send(identifier) == 1
    row = CampaignSend.objects.get()
    assert (row.step, row.inferred, str(row.campaign_id)) == (0, False, identifier)
    assert row.message_pk == Message.objects.get(direction=Direction.OUTBOUND).pk
    accept_all()
    assert send(identifier) == 1  # follow-up 1
    accept_all()
    inbound(deal)
    data = results(30)
    campaign = data["campaigns"][0]
    assert (campaign["contacted"], campaign["sent"], campaign["replied"], campaign["reply_rate"]) == (1, 2, 1, 1.0)
    assert [(s["sent"], s["replies"]) for s in campaign["steps"]] == [(1, 0), (1, 1)]
    assert data["overview"]["replied"] == 1 and data["overview"]["contacted"] == 1 and data["overview"]["sent"] == 2
    assert data["best_campaign"] is None  # one person is too few to rank


def test_unaccepted_bounced_and_opted_out_sends_are_reported_honestly(connected):
    identifier, deal = started(connected)
    send(identifier)
    data = results(30)
    assert data["overview"]["sent"] == 0 and data["campaigns"] == []  # nothing accepted yet
    message = Message.objects.get(direction=Direction.OUTBOUND)
    DeliveryEvent.objects.create(message=message, status="accepted")
    DeliveryEvent.objects.create(message=message, status="bounced")
    Suppression.objects.create(email="manual@example.com", reason="Manually suppressed by employee")
    data = results(30)
    assert data["overview"]["bounced"] == 1 and data["overview"]["bounce_rate"] == 1.0 and data["overview"]["opted_out"] == 0
    Suppression.objects.create(email=deal.lead.email, reason="Employee recorded opt-out")
    data = results(30)
    assert data["overview"]["opted_out"] == 1 and data["campaigns"][0]["opted_out"] == 1
    assert data["overview"]["replied"] == 0


def test_a_reply_before_our_first_email_is_not_counted(connected):
    identifier, deal = started(connected)
    send(identifier)
    accept_all()
    reply = inbound(deal)
    Message.objects.filter(pk=reply.pk).update(recorded_at=timezone.now() - timedelta(days=2))
    assert results(30)["overview"]["replied"] == 0


def test_period_trend_and_endpoint_validation(connected):
    identifier, deal = started(connected)
    send(identifier)
    accept_all()
    Message.objects.filter(direction=Direction.OUTBOUND).update(recorded_at=timezone.now() - timedelta(days=40))
    CampaignSend.objects.update(sent_at=timezone.now() - timedelta(days=40))
    assert results(30)["overview"]["sent"] == 0 and results(None)["overview"]["sent"] == 1
    assert len(results(7)["trend"]) == 7 and len(results(None)["trend"]) == 90
    assert connected.get("/api/results?period=bad").status_code == 400
    body = connected.get("/api/results?period=all").json()
    assert body["period"] == "all" and body["overview"]["sent"] == 1 and body["min_sample"] == 10


def test_window_closed_attempt_leaves_no_attribution(connected):
    identifier, _ = started(connected)
    from leadzen.transports import SendingWindowClosed
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), \
            patch("cold_outreach.emails.sender._deliver", side_effect=SendingWindowClosed("closed")):
        assert run_campaign(identifier, 1) == 0
    assert not CampaignSend.objects.exists() and not Message.objects.filter(direction=Direction.OUTBOUND).exists()


def test_history_backfill_attributes_earlier_sends_in_order(connected):
    from django.apps import apps
    from django.db import connection
    identifier, deal = started(connected)
    send(identifier)
    send(identifier)
    CampaignSend.objects.all().delete()
    migration = importlib.import_module("leadzen.config.migrations.0025_campaignsend")
    migration.backfill(apps, type("Editor", (), {"connection": connection})())
    rows = list(CampaignSend.objects.order_by("step").values_list("step", "inferred"))
    assert rows == [(0, True), (1, True)]
    migration.backfill(apps, type("Editor", (), {"connection": connection})())
    assert CampaignSend.objects.count() == 2  # rerunning never duplicates


def test_best_campaign_and_message_rank_only_above_the_sample_size(connected, monkeypatch):
    identifier, deal = started(connected)
    send(identifier)
    accept_all()
    inbound(deal)
    monkeypatch.setattr("leadzen.analytics.MIN_SAMPLE", 1)
    data = results(30)
    assert data["best_campaign"]["id"] == identifier and data["best_campaign"]["reply_rate"] == 1.0
    assert data["best_message"]["step"] == 0 and data["best_message"]["campaign_id"] == identifier


def test_hard_bounce_suppression_is_not_an_opt_out(connected):
    identifier, deal = started(connected)
    send(identifier)
    message = Message.objects.get(direction=Direction.OUTBOUND)
    DeliveryEvent.objects.create(message=message, status="accepted")
    DeliveryEvent.objects.create(message=message, status="bounced", enhanced_status="5.1.1")
    Suppression.objects.create(email=deal.lead.email, reason="undeliverable (5.1.1)")
    overview = results(30)["overview"]
    assert overview["bounced"] == 1 and overview["opted_out"] == 0


def test_summary_and_campaign_rows_count_the_same_people_for_a_period(connected):
    identifier, deal = started(connected)
    send(identifier)
    accept_all()
    # First email 20 days ago; the follow-up and the reply arrive this week.
    old = timezone.now() - timedelta(days=20)
    Message.objects.filter(direction=Direction.OUTBOUND).update(recorded_at=old)
    CampaignSend.objects.update(sent_at=old)
    send(identifier)
    accept_all()
    inbound(deal)
    week = results(7)
    assert week["overview"]["contacted"] == 0 and week["campaigns"] == []
    month = results(30)
    assert (month["overview"]["contacted"], month["overview"]["replied"]) == (1, 1)
    assert (month["campaigns"][0]["contacted"], month["campaigns"][0]["replied"]) == (1, 1)
