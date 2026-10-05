"""Stored timeline and terminal suppression, with synthetic mail events only."""
import json
from io import StringIO
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from cold_outreach.emails.models import DeliveryEvent, Mailbox, Message, Thread
from cold_outreach.leads.models import Deal, Lead, Suppression
from leadzen.config.models import CampaignRecipient, EmailCampaign


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")


def sequence():
    box = Mailbox.objects.create(host="smtp.example.com", from_address="sender@example.com")
    thread = Thread.objects.create(mailbox=box)
    lead = Lead.objects.create(lead_id="timeline-bruce", first_name="Bruce", email="bruce@example.com")
    deal = Deal.objects.create(lead=lead, thread=thread, state="Emailed")
    campaign = EmailCampaign.objects.create(name="Dental outreach", status="active", from_address=box.from_address,
        delay_basis="working_days", delay_timezone="America/New_York", steps=[
            {"subject": "Initial", "body": "Hello", "delay_days": 0},
            {"subject": "Follow-up", "body": "Checking in", "delay_days": 3},
            {"subject": "Final", "body": "Last note", "delay_days": 5}])
    due = datetime(2026, 10, 7, 14, tzinfo=dt_timezone.utc)
    recipient = CampaignRecipient.objects.create(campaign=campaign, deal=deal, next_step=1, next_send_at=due)
    message = Message.objects.create(mailbox=box, thread=thread, direction="out", message_id="initial", subject="Initial")
    event = DeliveryEvent.objects.create(message=message, status="accepted")
    return deal, recipient, event


def test_timeline_uses_acceptance_and_saved_working_day_due_dates(account_client):
    deal, recipient, event = sequence()
    with patch("leadzen.web.effective") as credentials, patch("leadzen.campaigns.run_campaign") as send:
        row = account_client.get(f"/api/contacts/{deal.pk}").json()["timeline"]
        assert row["events"][0]["label"] == "Initial email"
        assert row["events"][0]["at"] == event.occurred_at.isoformat()
        steps = row["sequences"][0]["steps"]
        assert steps[0]["at"] == recipient.next_send_at.isoformat()
        assert steps[0]["status"] == "due"
        assert steps[1]["at"].startswith("2026-10-14T10:00:00")
        assert steps[1]["status"] == "estimated"
        assert row["can_stop"] is True
        credentials.assert_not_called()
        send.assert_not_called()


def test_timeline_preserves_hours_but_reports_new_york_for_old_zone_without_sending(account_client):
    from leadzen.config.models import SiteConfig
    deal, _, _ = sequence()
    schedule = {"timezone": "Asia/Kolkata", "days": [1, 5], "start": "12:15", "end": "16:45"}
    config = SiteConfig.load()
    config.sending_schedule = schedule
    config.save()
    with patch("leadzen.campaigns.run_campaign") as send, patch("leadzen.transports.sync_replies_strict") as inbox:
        response = account_client.get(f"/api/contacts/{deal.pk}")
        assert response.status_code == 200
        sequence_data = response.json()["timeline"]["sequences"][0]
        assert sequence_data["sending_schedule"] == {**schedule, "timezone": "America/New_York"}
        assert sequence_data["timezone"] == "America/New_York"
        send.assert_not_called()
        inbox.assert_not_called()


@pytest.mark.parametrize("kind,reason", [("human_reply", "reply"), ("auto_reply", "inbound"), ("opt_out", "inbound")])
def test_saved_inbound_blocks_future_steps_without_a_read_mutation(account_client, kind, reason):
    deal, recipient, _ = sequence()
    Message.objects.create(mailbox=deal.thread.mailbox, thread=deal.thread, direction="in", kind=kind,
                           message_id="reply", received_at=timezone.now())
    row = account_client.get(f"/api/contacts/{deal.pk}").json()["timeline"]
    assert row["blocked_reason"] == reason
    assert row["sequences"][0]["steps"] == []
    assert row["sequences"][0]["status"] == "stopped"
    assert (any(event["label"] == "Reply received" for event in row["events"])) == (kind == "human_reply")
    recipient.refresh_from_db()
    assert recipient.status == "pending"  # Opening a lead never runs the sender.


def test_stop_sequence_retains_history_and_cannot_be_resurrected_by_import(account_client):
    from cold_outreach.leads.ingest import ingest
    deal, recipient, _ = sequence()
    assert account_client.put(f"/api/contacts/{deal.pk}", data='{"stop":true}', content_type="application/json").status_code == 200
    recipient.refresh_from_db()
    assert recipient.status == "stopped"
    row = account_client.get(f"/api/contacts/{deal.pk}").json()["timeline"]
    assert row["blocked_reason"] == "completed" and not row["can_stop"]
    assert len(row["events"]) == 1 and not row["sequences"][0]["steps"]
    ingest(StringIO(json.dumps({"lead_id": deal.lead.lead_id, "email": deal.lead.email}) + "\n"))
    deal.refresh_from_db()
    assert deal.state == "Completed"
    assert not Suppression.objects.exists()


def test_unaccepted_attempt_is_never_displayed_as_sent(account_client):
    deal, _, _ = sequence()
    Message.objects.create(mailbox=deal.thread.mailbox, thread=deal.thread, direction="out", message_id="uncertain")
    row = account_client.get(f"/api/contacts/{deal.pk}").json()["timeline"]
    assert [e["status"] for e in row["events"]] == ["accepted", "unconfirmed"]


def test_manual_suppression_is_normalized_idempotent_and_stops_matching_deals(account_client):
    deal, recipient, _ = sequence()
    other = Lead.objects.create(lead_id="same-address", email="BRUCE@example.com")
    other_deal = Deal.objects.create(lead=other)
    body = {"email": " Bruce@Example.com ", "reason": "Manually suppressed"}
    with patch("leadzen.web.effective") as credentials, patch("leadzen.email_api.post_email") as send:
        response = account_client.post("/api/suppression", data=json.dumps(body), content_type="application/json")
        assert response.status_code == 201, response.content
        first = response.json()["record"]
        body["reason"] = "Changed reason"
        duplicate = account_client.post("/api/suppression", data=json.dumps(body), content_type="application/json")
        assert duplicate.status_code == 200 and duplicate.json()["record"] == first
        credentials.assert_not_called()
        send.assert_not_called()
    deal.refresh_from_db(); other_deal.refresh_from_db(); recipient.refresh_from_db()
    assert deal.state == other_deal.state == "Completed" and recipient.status == "stopped"
    row = account_client.get(f"/api/contacts/{deal.pk}").json()["timeline"]
    assert row["blocked_reason"] == "suppressed" and row["suppression"]["reason"] == "Manually suppressed"
    assert account_client.get("/api/suppression?q=BRUCE").json()["total"] == 1
    assert Suppression.objects.count() == 1 and Message.objects.count() == 1


def test_suppression_before_import_survives_delete_and_preserves_original_reason(account_client):
    from cold_outreach.leads.ingest import ingest
    body = {"email": "new@example.com", "reason": "Opted out"}
    assert account_client.post("/api/suppression", data=json.dumps(body), content_type="application/json").status_code == 201
    response = account_client.post("/api/contacts", data=json.dumps({"email": "NEW@example.com"}), content_type="application/json")
    deal = Deal.objects.get(pk=response.json()["ids"][0])
    assert deal.state == "Completed"
    assert account_client.delete(f"/api/contacts/{deal.pk}").status_code == 200
    ingest(StringIO(json.dumps({"lead_id": "imported-after-optout", "email": "NEW@example.com"}) + "\n"))
    assert Deal.objects.get(lead__lead_id="imported-after-optout").state == "Completed"
    assert Suppression.objects.get().reason == "Opted out"


def test_legacy_mixed_case_suppression_still_blocks_the_upstream_import_gate(account_client):
    from cold_outreach.leads.ingest import ingest
    original = Suppression.objects.create(email="UPPER@example.com", reason="Original opt-out")
    response = account_client.post("/api/suppression", data='{"email":"upper@example.com","reason":"Manually suppressed"}', content_type="application/json")
    assert response.status_code == 200
    record = response.json()["record"]
    assert record["id"] == original.pk and record["suppressed_at"] == original.suppressed_at.isoformat()
    assert record["reason"] == "Original opt-out" and record["email"] == "upper@example.com"
    ingest(StringIO(json.dumps({"lead_id": "legacy-case", "email": "upper@example.com"}) + "\n"))
    assert Deal.objects.get(lead__lead_id="legacy-case").state == "Completed"
    assert Suppression.objects.count() == 1


@pytest.mark.parametrize("body", [{"email": "bad"}, {"email": "a@example.com", "reason": "x" * 201},
                                   {"email": "a@example.com", "reason": "bad\nreason"}, {"email": "a@example.com", "reason": 2}])
def test_invalid_suppression_does_not_write(account_client, body):
    assert account_client.post("/api/suppression", data=json.dumps(body), content_type="application/json").status_code == 400
    assert not Suppression.objects.exists()


def test_bearer_only_and_revoked_sessions_cannot_suppress(account_client):
    from django.contrib.auth import get_user_model
    body = '{"email":"a@example.com"}'
    assert Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token").post("/api/suppression", data=body, content_type="application/json").status_code == 401
    get_user_model().objects.update(is_active=False)
    assert account_client.post("/api/suppression", data=body, content_type="application/json").status_code == 401
    assert not Suppression.objects.exists()


def test_real_private_timeline_and_suppression_databases(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OUTSEND_", "OPENOUTFIND_", "LEADZEN_"))}
    env.update(LEADZEN_DB=str(tmp_path / "control.sqlite3"), LEADZEN_WORKSPACE_ROOT=str(tmp_path / "workspaces"), PYTHONPATH=str(root), DJANGO_SETTINGS_MODULE="leadzen.settings", LEADZEN_ALLOWED_HOSTS="testserver,localhost,127.0.0.1")
    result = subprocess.run([sys.executable, str(root / "tests/scenarios/lead_timeline.py")], cwd=root, env=env, text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr[-6000:]
    assert "Timeline and suppression isolation verified" in result.stdout
