"""The private dashboard boundary must fail closed and expose useful campaign data."""
import pytest
from django.test import Client


@pytest.fixture(autouse=True)
def dashboard_environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_DASHBOARD_ORIGINS", "http://testserver")


def test_dashboard_api_requires_the_bearer_token(db):
    response = Client().get("/api/health")
    assert response.status_code == 401


def test_dashboard_api_returns_campaign_overview(db, account_client):
    from cold_outreach.emails.models import Mailbox
    from cold_outreach.leads.models import Deal, Lead

    lead = Lead.objects.create(
        lead_id="lead-1",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        company="Analytical Engines",
        title="Founder",
    )
    Deal.objects.create(lead=lead, reason="Runs a multi-location agency.")
    Mailbox.objects.create(
        host="smtp.example.com",
        port=587,
        imap_host="imap.example.com",
        imap_port=993,
        username="sender@example.com",
        password="not-used-in-test",
        from_address="sender@example.com",
    )

    response = account_client.get("/api/overview")

    assert response.status_code == 200
    assert response.json()["leads"]["total"] == 1
    assert response.json()["mailboxes"][0]["remaining_today"] == 5


def test_send_job_rejects_a_second_active_job(db, account_client):
    from cold_outreach.emails.models import Mailbox
    from leadzen.config.models import OutreachJob

    Mailbox.objects.create(
        host="smtp.example.com",
        port=587,
        imap_host="imap.example.com",
        imap_port=993,
        username="sender@example.com",
        password="not-used-in-test",
        from_address="sender@example.com",
    )
    OutreachJob.objects.create(requested_count=1, status=OutreachJob.Status.RUNNING, pid=123)
    response = account_client.post(
        "/api/jobs/send",
        data="{\"count\": 1}",
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer test-dashboard-token",
    )

    assert response.status_code == 409
    assert "already running" in response.json()["error"]


def test_overview_does_not_report_an_unconfirmed_attempt_as_sent(db, account_client):
    from cold_outreach.emails.models import Mailbox, Message, DeliveryEvent, Direction
    from django.utils import timezone
    box = Mailbox.objects.create(host="smtp.example.com", port=587, username="sender@example.com", from_address="sender@example.com", password="synthetic-password")
    row = Message.objects.create(mailbox=box, direction=Direction.OUTBOUND, message_id="<synthetic-attempt@example.com>", from_address="sender@example.com", to_address="person@example.com", sent_at=timezone.now())
    before = account_client.get("/api/overview").json()
    assert before["today"]["sent"] == 0 and not before["activity"][0]["accepted"]
    DeliveryEvent.objects.create(message=row, status="accepted")
    after = account_client.get("/api/overview").json()
    assert after["today"]["sent"] == 1 and after["activity"][0]["accepted"]


def test_saved_legacy_job_output_redacts_configured_credentials(account_client):
    from leadzen.config.models import OutreachJob
    from leadzen.configuration import save_dashboard_settings
    save_dashboard_settings({"provider": "groq", "model": "synthetic-model"}, llm_api_key="synthetic-private-log-key")
    OutreachJob.objects.create(requested_count=1, status="failed", output="Provider rejected synthetic-private-log-key")
    response = account_client.get("/api/jobs")
    assert response.status_code == 200
    assert "synthetic-private-log-key" not in response.content.decode()
    assert "[credential removed]" in response.json()["items"][0]["output"]
