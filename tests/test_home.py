"""Home reports persisted facts, never sample analytics or provider side effects."""
import json
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.test import Client
from django.utils import timezone


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())


def test_discovery_counts_real_profiles_and_explicit_verdicts(account_client):
    from openoutfind.crm.models import Lead, Deal, DealState
    from cold_outreach.leads.models import Lead as Contact, Deal as Conversation
    from leadzen.config.models import ContactPreferences
    good = Lead.objects.create(full_name="Bruce Lish", email="bruce@example.com")
    Deal.objects.create(lead=good, reason="Practice owner")
    no_email = Lead.objects.create(full_name="Sarah Smith")
    Deal.objects.create(lead=no_email, state=DealState.NO_EMAIL_FOUND, reason="Marketing manager")
    rejected = Lead.objects.create(full_name="Emily Waters")
    Deal.objects.create(lead=rejected, state=DealState.FAILED, outcome="wrong_fit", reason="Not a decision-maker")
    Lead.objects.create(full_name="Not assessed yet")
    Lead.objects.create(full_name="Internal training anchor", synthetic=True)
    deleted = Lead.objects.create(full_name="Deleted Person")
    Deal.objects.create(lead=deleted)
    contact = Contact.objects.create(lead_id=str(deleted.pk))
    ContactPreferences.objects.create(lead=contact, deleted_at=timezone.now())
    Conversation.objects.create(lead=contact)
    Conversation.objects.create(lead=Contact.objects.create(lead_id="manual-person", email="manual@example.com"))
    home = account_client.get("/api/overview").json()["home"]
    assert home["metrics"] == {"found": 4, "qualified": 2, "with_email": 1, "contacted": 0, "replies": 0}
    assert {row["name"]: row["status"] for row in home["recent_activity"]} == {"Bruce Lish": "qualified", "Sarah Smith": "qualified", "Emily Waters": "rejected"}


def test_contacted_and_replies_count_people_not_attempts_or_automations(account_client):
    from cold_outreach.emails.models import Mailbox, Message, Direction, DeliveryEvent, Thread
    box = Mailbox.objects.create(host="smtp.example.com", from_address="sender@example.com", username="sender@example.com")
    thread = Thread.objects.create(mailbox=box)
    for i, address in enumerate(["Person@example.com", "person@example.com", "failed@example.com"]):
        message = Message.objects.create(mailbox=box, thread=thread, direction=Direction.OUTBOUND, message_id=f"out-{i}", to_address=address, sent_at=timezone.now() - timedelta(days=2))
        if i < 2:
            DeliveryEvent.objects.create(message=message, status="accepted")
            DeliveryEvent.objects.create(message=message, status="accepted")
    for i, (kind, address) in enumerate([("human_reply", "person@example.com"), ("human_reply", "PERSON@example.com"), ("auto_reply", "bot@example.com"), ("bounce", "daemon@example.com"), ("unrelated", "other@example.com"), ("opt_out", "stop@example.com")]):
        Message.objects.create(mailbox=box, thread=thread, direction=Direction.INBOUND, kind=kind, message_id=f"in-{i}", from_address=address)
    Message.objects.create(mailbox=box, direction=Direction.INBOUND, kind="human_reply", message_id="unlinked", from_address="unlinked@example.com")
    metrics = account_client.get("/api/overview").json()["home"]["metrics"]
    assert metrics["contacted"] == 1
    assert metrics["replies"] == 1


def test_credit_snapshot_is_unknown_until_checked_and_invalidated_by_key_change(account_client, monkeypatch):
    from leadzen.configuration import save_dashboard_settings
    from leadzen.config.models import OnboardingState
    from leadzen.setup_wizard import fingerprint
    monkeypatch.setattr("leadzen.setup_wizard.probe_discovery", lambda *_: pytest.fail("Home must not call a provider"))
    assert account_client.get("/api/overview").json()["home"]["credits"]["balance"] is None
    values = save_dashboard_settings({}, bettercontact_api_key="synthetic-first-key")
    checked_at = timezone.now() - timedelta(days=2)
    state = OnboardingState.objects.create(checks={"discovery": {"credits": 0, "tested_at": checked_at.isoformat(), "expires_at": checked_at.isoformat(), "fingerprint": fingerprint(values, "discovery")}})
    credits = account_client.get("/api/overview").json()["home"]["credits"]
    assert credits["balance"] == 0 and credits["checked_at"] == checked_at.isoformat()
    assert "fingerprint" not in json.dumps(credits) and "synthetic-first-key" not in json.dumps(credits)
    save_dashboard_settings({}, bettercontact_api_key="synthetic-second-key")
    assert account_client.get("/api/overview").json()["home"]["credits"]["balance"] is None


def audience():
    return {"industry": "Dental practices", "country": "US", "company_size": "2-50", "roles": ["Owner", "Practice Manager"], "seniority": ["owner", "manager"], "instructions": "Exclude trainees."}


def test_target_updates_saved_engine_instructions_without_retesting_connections(account_client):
    from leadzen.config.models import SiteConfig, OnboardingState
    config = SiteConfig.load()
    config.operator_name, config.product_docs = "Ashish Dikonda", "Keep product intact"
    config.save()
    state = OnboardingState.objects.create(draft={"product_name": "Existing product"}, completed_steps=[1, 2, 3, 4, 5, 6])
    result = account_client.put("/api/target", data=json.dumps({"audience": audience(), "confirmed": True, "accepted_legal_notice": True}), content_type="application/json")
    assert result.status_code == 200, result.content
    config.refresh_from_db()
    state.refresh_from_db()
    assert "Dental practices" in config.campaign_target and "United States" in config.campaign_target
    assert config.product_docs == "Keep product intact" and state.draft["product_name"] == "Existing product"
    home = account_client.get("/api/overview").json()["home"]
    assert home["operator_name"] == "Ashish Dikonda"
    assert home["target"]["audience"] == audience()
    # An unfinished wizard draft is not the currently active target.
    state.draft["audience"]["industry"] = "Restaurants"
    state.save()
    home = account_client.get("/api/overview").json()["home"]
    assert home["target"]["audience"] is None
    assert "Dental practices" in home["target"]["summary"]


def test_invalid_or_unauthorized_target_changes_do_not_write(account_client):
    from leadzen.config.models import SiteConfig
    config = SiteConfig.load()
    config.campaign_target = "Existing target"
    config.save()
    result = account_client.put("/api/target", data=json.dumps({"audience": audience(), "confirmed": False}), content_type="application/json")
    assert result.status_code == 400
    assert Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token").get("/api/target").status_code == 401
    config.refresh_from_db()
    assert config.campaign_target == "Existing target"
