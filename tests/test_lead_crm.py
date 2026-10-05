"""The CRM reads saved facts; a single work-email purchase is separately approved."""
import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone

from tests.test_discovery import discovery_client
from tests.test_chat import chat_client, post
from cold_outreach.leads.models import Deal, Lead, Suppression
from leadzen.config.models import ContactPreferences, DiscoveryLookup, DiscoverySession


def prospect():
    from openoutfind.crm.models import Lead as Profile, Deal as Decision
    profile = Profile.objects.create(full_name="Bruce Synthetic", job_title="Director of Dentistry", profile_url="https://example.com/profile/bruce")
    Decision.objects.create(lead=profile, state="Qualified", reason="Director-level dental decision-maker")
    lead = Lead.objects.create(lead_id=str(profile.pk), title=profile.job_title, linkedin_url=profile.profile_url, website="https://example.com", company="Synthetic Practice")
    return Deal.objects.create(lead=lead), profile


def lookup_body(client, deal):
    review = client.get(f"/api/contacts/{deal.pk}/email").json()
    return {"revision": review["revision"], "estimated_credits": 1, "request_id": str(uuid.uuid4())}


def test_crm_detail_full_name_reason_links_and_unrequested_email(discovery_client):
    deal, _ = prospect()
    with patch("leadzen.chat.views.launch") as launch, patch("leadzen.chat.engine.find_leads") as finder:
        response = discovery_client.get(f"/api/contacts/{deal.pk}")
        assert response.status_code == 200
        row = response.json()
        assert row["name"] == "Bruce Synthetic"
        assert row["qualified"] and row["crm_status"] == "qualified"
        assert row["reason"] == "Director-level dental decision-maker"
        assert row["email_status"] == "not_requested"
        assert row["linkedin_url"] == "https://example.com/profile/bruce"
        assert discovery_client.get("/api/leads?q=Bruce&stage=qualified").json()["total"] == 1
        launch.assert_not_called()
        finder.assert_not_called()


@pytest.mark.parametrize("stage,expected", [("all", 1), ("qualified", 1), ("email_found", 0), ("contacted", 0), ("replied", 0), ("suppressed", 0)])
def test_crm_stage_filters(discovery_client, stage, expected):
    prospect()
    assert discovery_client.get(f"/api/leads?stage={stage}").json()["total"] == expected


def test_suppressed_and_deleted_contacts_are_not_email_purchase_candidates(discovery_client):
    deal, _ = prospect()
    Suppression.objects.create(email="stop@example.com")
    deal.lead.email = "stop@example.com"
    deal.lead.save()
    assert discovery_client.get("/api/leads?stage=suppressed").json()["total"] == 1
    with patch("leadzen.chat.views.launch") as launch:
        assert not discovery_client.get(f"/api/contacts/{deal.pk}/email").json()["eligible"]
        ContactPreferences.objects.create(lead=deal.lead, deleted_at=timezone.now())
        assert discovery_client.get(f"/api/contacts/{deal.pk}").status_code == 404
        assert post(discovery_client, f"/api/contacts/{deal.pk}/email", {}).status_code == 404
        launch.assert_not_called()


def test_manual_contact_never_guesses_a_profile_for_paid_lookup(discovery_client):
    lead = Lead.objects.create(lead_id="manual-synthetic", email="person@example.com")
    deal = Deal.objects.create(lead=lead)
    review = discovery_client.get(f"/api/contacts/{deal.pk}/email").json()
    assert not review["eligible"]
    assert not discovery_client.get(f"/api/contacts/{deal.pk}").json()["qualified"]


def test_one_credit_approval_scopes_exact_source_and_is_idempotent(discovery_client):
    deal, profile = prospect()
    body = lookup_body(discovery_client, deal)
    with patch("leadzen.chat.views.launch") as launch:
        response = post(discovery_client, f"/api/contacts/{deal.pk}/email", body)
        assert response.status_code == 202, response.content
        assert post(discovery_client, f"/api/contacts/{deal.pk}/email", body).json()["run"]["id"] == response.json()["run"]["id"]
        launch.assert_called_once()
    session = DiscoverySession.objects.get(run_id=response.json()["run"]["id"])
    assert session.source_ids == [profile.pk] and session.goal == 1 and session.unit == "emails"
    assert session.run.credits_reserved == 1 and session.run.emails_reserved == 0
    assert session.action["approved"] and session.action["source_identity"]


@pytest.mark.parametrize("change", ["profile", "deleted", "email", "qualification", "receipt", "budget"])
def test_stale_and_unapproved_email_requests_cannot_launch(discovery_client, change):
    from openoutfind.crm.models import Deal as Decision
    deal, profile = prospect()
    body = lookup_body(discovery_client, deal)
    if change == "profile":
        profile.profile_url = "https://example.com/changed"
        profile.save()
    elif change == "deleted":
        ContactPreferences.objects.create(lead=deal.lead, deleted_at=timezone.now())
    elif change == "email":
        profile.email = "already@example.com"
        profile.save()
    elif change == "qualification":
        Decision.objects.filter(lead=profile).update(state="Failed", outcome="wrong_fit")
    elif change == "receipt":
        from tests.test_discovery_live import start
        run = start(discovery_client)
        DiscoveryLookup.objects.create(session_id=run, source_id=profile.pk, state="uncertain")
    else:
        body["estimated_credits"] = 0
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, f"/api/contacts/{deal.pk}/email", body).status_code in (400, 404, 409)
        launch.assert_not_called()


def test_foreign_detail_denied_before_credentials_and_invalid_filters(discovery_client):
    with patch("leadzen.discovery.effective") as credentials, patch("leadzen.chat.views.launch") as launch:
        assert discovery_client.get("/api/contacts/999999").status_code == 404
        assert discovery_client.get("/api/contacts/999999/email").status_code == 404
        assert post(discovery_client, "/api/contacts/999999/email", {}).status_code == 404
        credentials.assert_not_called()
        launch.assert_not_called()
    assert discovery_client.get("/api/leads?stage=made-up").status_code == 400
    assert discovery_client.get("/api/leads?q=" + "a" * 201).status_code == 400


def test_single_lookup_receipt_is_not_invented_or_retried(discovery_client):
    deal, profile = prospect()
    with patch("leadzen.chat.views.launch"):
        response = post(discovery_client, f"/api/contacts/{deal.pk}/email", lookup_body(discovery_client, deal))
    session = DiscoverySession.objects.get(run_id=response.json()["run"]["id"])
    receipt = DiscoveryLookup.objects.create(session=session, source_id=profile.pk, state="submitted", request_id="synthetic-handle")
    row = discovery_client.get(f"/api/contacts/{deal.pk}").json()
    assert row["lookup"]["credits_used"] is None and row["email_status"] == "pending"
    session.run.status = "failed"
    session.run.save()
    assert not discovery_client.get(f"/api/contacts/{deal.pk}/email").json()["eligible"]
    receipt.state, receipt.credits, receipt.email_status = "terminated", 1, "valid"
    receipt.save()
    profile.email = deal.lead.email = "bruce@example.com"
    profile.save()
    deal.lead.save()
    row = discovery_client.get(f"/api/contacts/{deal.pk}").json()
    assert row["email_status"] == "verified" and row["lookup"]["credits_used"] == 1


def test_catch_all_and_missing_provider_verdicts_are_not_called_verified(discovery_client):
    deal, profile = prospect()
    with patch("leadzen.chat.views.launch"):
        response = post(discovery_client, f"/api/contacts/{deal.pk}/email", lookup_body(discovery_client, deal))
    session = DiscoverySession.objects.get(run_id=response.json()["run"]["id"])
    receipt = DiscoveryLookup.objects.create(session=session, source_id=profile.pk, state="terminated", credits=1)
    profile.email = deal.lead.email = "bruce@example.com"
    profile.save()
    deal.lead.save()
    assert discovery_client.get(f"/api/contacts/{deal.pk}").json()["email_status"] == "available"
    receipt.email_status = "catch_all_safe"
    receipt.save()
    assert discovery_client.get(f"/api/contacts/{deal.pk}").json()["email_status"] == "catch_all_safe"


def test_stopping_selected_lead_revokes_email_worker_before_provider(discovery_client):
    from leadzen.discovery_progress import Monitor
    deal, _ = prospect()
    with patch("leadzen.chat.views.launch"):
        response = post(discovery_client, f"/api/contacts/{deal.pk}/email", lookup_body(discovery_client, deal))
    session = DiscoverySession.objects.get(run_id=response.json()["run"]["id"])
    session.run.status = "running"
    from datetime import timedelta
    session.run.deadline_at = timezone.now() + timedelta(minutes=1)
    session.run.save()
    monitor = Monitor(session)
    monitor.guard()
    discovery_client.put(f"/api/contacts/{deal.pk}", data='{"stop":true}', content_type="application/json")
    with pytest.raises(PermissionError, match="Selected lead"):
        monitor.guard()


def test_contacted_replied_filters_and_addressless_profile_edit(discovery_client):
    from cold_outreach.emails.models import Thread, Mailbox, Message
    deal, _ = prospect()
    updated = discovery_client.put(f"/api/contacts/{deal.pk}", data='{"email":"","first_name":"Bruce","company":"Synthetic","consent_note":"","opted_in":false}', content_type="application/json")
    assert updated.status_code == 200
    deal.lead.refresh_from_db()
    assert deal.lead.first_name == "Bruce" and deal.lead.email == ""
    assert discovery_client.put(f"/api/contacts/{deal.pk}", data='{"suppress":true}', content_type="application/json").status_code == 400
    assert not Suppression.objects.exists()
    box = Mailbox.objects.first()
    deal.thread = Thread.objects.create(mailbox=box)
    deal.email_sent_at = timezone.now()
    deal.save()
    assert discovery_client.get("/api/leads?stage=contacted").json()["total"] == 1
    Message.objects.create(mailbox=box, thread=deal.thread, direction="in", kind="human_reply", message_id="synthetic-crm-reply", body_text="Synthetic reply")
    row = discovery_client.get("/api/leads?stage=replied").json()["items"][0]
    assert row["crm_status"] == "replied" and row["reply_count"] == 1


def test_company_domains_are_links_but_unsafe_urls_are_not(discovery_client):
    deal, _ = prospect()
    deal.lead.website = "example.com"
    deal.lead.save()
    assert discovery_client.get(f"/api/contacts/{deal.pk}").json()["website"] == "https://example.com"
    for unsafe in ["javascript:alert(1)", "https://user:pass@example.com", "//example.com"]:
        deal.lead.website = unsafe
        deal.lead.save()
        assert discovery_client.get(f"/api/contacts/{deal.pk}").json()["website"] == ""
