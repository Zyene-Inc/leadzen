"""Synthetic contracts only: no provider credentials, paid calls or live models."""
import json
import uuid
from dataclasses import asdict
from datetime import timedelta
from unittest.mock import patch

import numpy as np
import pytest
from django.utils import timezone

from tests.test_chat import chat_client, post, turn
from tests.test_discovery import discovery_client
from leadzen.configuration import effective, save_dashboard_settings

AUDIENCE = {"roles": ["Dentist"], "industry": "Dental practices", "country": "US", "company_size": "1-10", "seniority": ["owner"], "instructions": ""}


@pytest.fixture
def ark_client(discovery_client):
    from leadzen.config.models import OnboardingState
    from leadzen.setup_wizard import target_preview
    from leadzen.config.models import SiteConfig
    config = SiteConfig.load()
    config.campaign_target = target_preview(AUDIENCE)
    config.save()
    OnboardingState.objects.update_or_create(pk=1, defaults={"draft": {"audience": AUDIENCE}})
    save_dashboard_settings(asdict(effective()), lead_finder_provider="ai_ark", ai_ark_api_key="synthetic-ark-key")
    return discovery_client


def put(client, provider, **extra):
    return client.put("/api/settings", json.dumps({"lead_finder": {"provider": provider, **extra}}), content_type="application/json")


def start(client, count=1, emails=False):
    context = client.get("/api/discovery").json()
    with patch("leadzen.chat.views.launch"):
        response = post(client, "/api/discovery", {"count": count, "emails": emails, "estimated_credits": count * (2 if emails else 1), "revision": context["revision"], "request_id": str(uuid.uuid4())})
    assert response.status_code == 202, response.content
    from leadzen.config.models import ChatRun
    row = ChatRun.objects.get(pk=response.json()["run"]["id"])
    row.status, row.deadline_at = "running", timezone.now() + timedelta(minutes=10)
    row.save()
    return row


def person(slug="test-dentist"):
    return {"id": "synthetic-person-id", "profile": {"full_name": "Test Dentist", "title": "Dentist", "headline": "Dental practice owner"},
            "link": {"linkedin": f"https://www.linkedin.com/in/{slug}"}, "location": {"country": "United States"},
            "company": {"summary": {"name": "Synthetic Dental", "industry": "Dental practices", "staff": {"total": 5}}, "link": {"domain": "example.com"}}}


def test_keys_are_independent_encrypted_and_never_echoed(ark_client):
    from leadzen.config.models import RuntimeSettings
    assert effective().bettercontact_api_key == "synthetic-secret-finder"
    response = put(ark_client, "bettercontact", api_key="")
    assert response.status_code == 200
    assert effective().lead_finder_provider == "bettercontact"
    assert put(ark_client, "ai_ark", api_key="").status_code == 200
    assert effective().ai_ark_api_key == "synthetic-ark-key"
    assert "synthetic-ark-key" not in response.content.decode() + RuntimeSettings.load().encrypted_secrets
    assert put(ark_client, "ai_ark", clear_api_key=True).status_code == 200
    assert not effective().ai_ark_api_key
    assert effective().bettercontact_api_key == "synthetic-secret-finder"
    assert ark_client.get("/api/discovery").json()["ready"] is False


def test_unrelated_settings_keep_provider_and_both_keys(ark_client):
    response = ark_client.put("/api/settings", json.dumps({"llm": {"model": "another-synthetic-model"}}), content_type="application/json")
    assert response.status_code == 200
    assert effective().lead_finder_provider == "ai_ark"
    assert effective().ai_ark_api_key == "synthetic-ark-key"
    assert effective().bettercontact_api_key == "synthetic-secret-finder"


def test_connection_probe_is_free_and_routes_to_selected_host(ark_client):
    from leadzen.setup_wizard import probe_discovery, candidate, fingerprint
    with patch("leadzen.ai.pinned_request", return_value=(200, {}, b'{"total":12.5}')) as network:
        assert probe_discovery(effective()) == {"credits": 12.5}
    args = network.call_args
    assert args.args[0:2] == ("GET", "https://api.ai-ark.com/api/developer-portal/v1/payments/credits")
    assert args.args[2]["X-TOKEN"] == "synthetic-ark-key"
    other = candidate({"lead_finder": {"provider": "bettercontact"}}, "discovery")
    assert other.bettercontact_api_key == "synthetic-secret-finder"
    assert fingerprint(other, "discovery") != fingerprint(effective(), "discovery")


@pytest.mark.parametrize("balance", [None, True, -1, "NaN", "Infinity", "bad"])
def test_invalid_balances_are_not_reported_as_zero(ark_client, balance):
    from leadzen.ai_ark import credit_balance
    with patch("leadzen.ai_ark.request", return_value={"total": balance}), pytest.raises(ValueError):
        credit_balance()


def test_preview_and_approval_include_search_budget(ark_client):
    setup = ark_client.get("/api/discovery").json()
    assert setup["ready"] and setup["provider_name"] == "AI Ark" and setup["max_email_count"] == 12
    row = start(ark_client, count=3, emails=True)
    assert row.pending["credits"] == 6 and row.pending["provider"] == "ai_ark"
    assert "profile searches" in row.pending["preview"]["note"]


def test_free_search_budget_cannot_buy_ai_ark_profiles(ark_client):
    setup = ark_client.get("/api/discovery").json()
    with patch("leadzen.chat.views.launch") as launch:
        response = post(ark_client, "/api/discovery", {"count": 3, "emails": False, "estimated_credits": 0, "revision": setup["revision"], "request_id": str(uuid.uuid4())})
    assert response.status_code == 400
    launch.assert_not_called()


def test_chat_profile_search_requires_approval(ark_client):
    from leadzen.chat.engine import Decision, drive
    from leadzen.config.models import ChatRun
    thread, run = turn(ark_client, "Find three leads without emails")
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="find_leads", arguments={"count": 3, "includeEmails": False})), patch("leadzen.ai_ark.request") as network:
        drive(run)
    network.assert_not_called()
    row = ChatRun.objects.get(pk=run)
    assert row.status == "awaiting_approval" and row.pending["credits"] == 3


def test_search_uses_exact_audience_and_never_bettercontact(ark_client):
    from leadzen.ai_ark import search
    from leadzen.discovery_progress import observe, current, credits
    row = start(ark_client)
    with observe(row), patch("leadzen.ai.pinned_request", return_value=(200, {}, json.dumps({"content": [person()]}).encode())) as network:
        result = search(current())
        assert search(current()) == result  # Resume uses saved response, not another charge.
        assert credits(current().session)["used"] == .5
    network.assert_called_once()
    args = network.call_args.args
    assert args[1].endswith("/v1/people") and args[4] == "api.ai-ark.com"
    body = json.loads(args[3])
    assert body["size"] == 2 and body["page"] == 0
    assert body["account"]["industries"]["any"]["include"]["content"] == ["Dental practices"]
    assert body["account"]["employeeSize"]["range"] == [{"start": 1, "end": 10}]
    assert result[0]["contact_full_name"] == "Test Dentist"
    assert "email" not in result[0]


def test_uncertain_search_is_reserved_and_never_retried(ark_client):
    from leadzen.ai_ark import search
    from leadzen.discovery_progress import observe, current, credits
    row = start(ark_client)
    with observe(row), patch("leadzen.ai.pinned_request", side_effect=TimeoutError) as network:
        with pytest.raises(TimeoutError):
            search(current())
        with pytest.raises(PermissionError):
            search(current())
        assert credits(current().session)["used"] is None
    network.assert_called_once()


def test_switching_provider_invalidates_inflight_approval(ark_client):
    from leadzen.ai_ark import search
    from leadzen.discovery_progress import observe, current
    row = start(ark_client)
    put(ark_client, "bettercontact")
    with observe(row), patch("leadzen.ai.pinned_request") as network, pytest.raises(PermissionError):
        search(current())
    network.assert_not_called()


def test_ai_ark_results_use_shared_contacts_and_verified_email(ark_client):
    from leadzen.ai_ark import run
    from leadzen.discovery_progress import observe, current
    from cold_outreach.leads.models import Lead
    from leadzen.config.models import DiscoveryLookup
    row = start(ark_client, emails=True)
    enriched = {**person(), "email": {"state": "DONE", "output": [{"address": "dentist@example.com", "found": True, "status": "VALID", "domainType": "SMTP", "free": False, "generic": False}]}}
    with observe(row), patch("leadzen.ai.pinned_request", side_effect=[(200, {}, json.dumps({"content": [person()]}).encode()), (200, {}, json.dumps(enriched).encode())]) as network, patch("openoutfind.discovery.embed_profile", return_value=np.zeros(384)), patch("openoutfind.core.ml.qualifier.qualify_with_llm", return_value=(1, "Matches the dental practice target")):
        result = run({"count": 1, "emails": True, "audience": ""}, current())
    assert not result["partial"], result
    assert result["discovery"]["counts"]["produced"] == 1
    assert result["discovery"]["credits"]["used"] == 1.5
    assert Lead.objects.filter(email="dentist@example.com").exists()
    assert DiscoveryLookup.objects.get().email_status == "valid"
    assert network.call_count == 2


@pytest.mark.parametrize("domain_type,free,generic", [("CATCH_ALL", False, False), ("UNKNOWN", False, False), ("SMTP", True, False), ("SMTP", False, True)])
def test_unsafe_email_is_not_saved(ark_client, domain_type, free, generic):
    from leadzen.ai_ark import enrich
    from leadzen.discovery_progress import observe, current
    from openoutfind.crm.models import Lead, Deal, DealState
    row = start(ark_client, emails=True)
    lead = Lead.objects.create(profile_url=person()["link"]["linkedin"])
    Deal.objects.create(lead=lead, state=DealState.QUALIFIED)
    result = {**person(), "email": {"state": "DONE", "output": [{"address": "unsafe@example.com", "found": True, "status": "VALID", "domainType": domain_type, "free": free, "generic": generic}]}}
    with observe(row), patch("leadzen.ai.pinned_request", return_value=(200, {}, json.dumps(result).encode())):
        enrich(current(), lead)
    lead.refresh_from_db()
    assert not lead.email


@pytest.mark.parametrize("change", ["expired", "cancelled", "unapproved", "wrong_provider"])
def test_invalid_approval_cannot_reach_provider(ark_client, change):
    from leadzen.ai_ark import search
    from leadzen.discovery_progress import observe, current
    from leadzen.config.models import DiscoverySession
    row = start(ark_client)
    if change == "expired":
        row.approval_expires_at = timezone.now() - timedelta(seconds=1)
    elif change == "cancelled":
        row.cancel_requested = True
    else:
        session = DiscoverySession.objects.get(run=row)
        session.action.update({"approved": False} if change == "unapproved" else {"provider": "bettercontact"})
        session.save()
    row.save()
    with observe(row), patch("leadzen.ai.pinned_request") as network, pytest.raises(PermissionError):
        search(current())
    network.assert_not_called()


def test_transport_requires_exact_single_use_reservation(ark_client):
    from leadzen.ai_ark import request, search
    from leadzen.discovery_progress import observe, current
    from leadzen.config.models import DiscoverySearch
    row = start(ark_client)
    with observe(row), patch("leadzen.ai.pinned_request", return_value=(404, {}, b"")) as network:
        with pytest.raises(PermissionError, match="reservation"):
            request("POST", "/v1/people", {"size": 100, "page": 0})
        network.assert_not_called()
        search(current())
        payload = json.loads(network.call_args.args[3])
        receipt = DiscoverySearch.objects.get(session_id=row.pk)
        with pytest.raises(PermissionError, match="changed"):
            request("POST", "/v1/people", {**payload, "size": 100}, receipt=receipt)
        with pytest.raises(PermissionError, match="already attempted"):
            request("POST", "/v1/people", payload, receipt=receipt)
        network.assert_called_once()


def test_contact_email_approval_reserves_only_one_credit_and_no_search(ark_client):
    from tests.test_lead_crm import prospect, lookup_body
    from leadzen.chat.engine import drive
    from leadzen.config.models import ChatRun, DiscoverySearch
    deal, lead = prospect()
    lead.profile_url = person()["link"]["linkedin"]
    lead.save()
    review = ark_client.get(f"/api/contacts/{deal.pk}/email").json()
    assert review["provider_name"] == "AI Ark"
    with patch("leadzen.chat.views.launch"):
        response = post(ark_client, f"/api/contacts/{deal.pk}/email", lookup_body(ark_client, deal))
    assert response.status_code == 202, response.content
    row = ChatRun.objects.get(pk=response.json()["run"]["id"])
    assert row.pending["credits"] == 1
    assert "1 AI Ark credit" in row.pending["summary"]
    with patch("leadzen.ai.pinned_request", return_value=(404, {}, b"")) as network, patch("openoutfind.enrichment.bettercontact._request") as other:
        drive(row.pk)
        drive(row.pk)
    network.assert_called_once()
    assert network.call_args.args[1].endswith("/v1/people/export/single")
    other.assert_not_called()
    assert not DiscoverySearch.objects.exists()


def test_chat_approved_search_reaches_ai_ark_once(ark_client):
    from leadzen.chat.engine import Decision, drive
    from leadzen.config.models import ChatRun, DiscoverySession
    thread, run = turn(ark_client, "Find one dentist without emails")
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="find_leads", arguments={"count": 1, "includeEmails": False})):
        drive(run)
    row = ChatRun.objects.get(pk=run)
    with patch("leadzen.chat.views.launch"):
        response = post(ark_client, f"/api/chat/runs/{run}/approval", {"approved": True, "action_id": row.pending["id"]})
    assert response.status_code == 202, response.content
    with patch("leadzen.ai.pinned_request", return_value=(200, {}, json.dumps({"content": [person()]}).encode())) as network, patch("openoutfind.discovery.embed_profile", return_value=np.zeros(384)), patch("openoutfind.core.ml.qualifier.qualify_with_llm", return_value=(1, "Matches saved target")):
        drive(run)
        drive(run)
    row.refresh_from_db()
    assert row.status == "succeeded"
    assert DiscoverySession.objects.get(run=row).candidates.filter(produced=True).count() == 1
    network.assert_called_once()


def test_unsaved_audience_draft_cannot_spend_on_a_different_target(ark_client):
    from leadzen.config.models import OnboardingState
    from leadzen.ai_ark import search
    from leadzen.discovery_progress import observe, current
    row = start(ark_client)
    state = OnboardingState.objects.get(pk=1)
    state.draft["audience"] = {**AUDIENCE, "industry": "Software"}
    state.save()
    with observe(row), patch("leadzen.ai.pinned_request") as network, pytest.raises(ValueError, match="structured audience"):
        search(current())
    network.assert_not_called()
    assert not ark_client.get("/api/discovery").json()["ready"]


def test_pause_after_paid_search_resumes_saved_profiles_without_repurchase(ark_client):
    from leadzen.ai_ark import run
    from leadzen.discovery_progress import observe, current
    from leadzen.config.models import DiscoverySession
    row = start(ark_client)

    def response(*args, **kwargs):
        DiscoverySession.objects.filter(run=row).update(pause_requested=True)
        return 200, {}, json.dumps({"content": [person()]}).encode()

    with observe(row), patch("leadzen.ai.pinned_request", side_effect=response) as network:
        result = run({"count": 1, "emails": False, "audience": ""}, current())
        assert result["paused"]
        assert result["discovery"]["credits"]["used"] == .5
        DiscoverySession.objects.filter(run=row).update(pause_requested=False)
        with patch("openoutfind.discovery.embed_profile", return_value=np.zeros(384)), patch("openoutfind.core.ml.qualifier.qualify_with_llm", return_value=(1, "Matches target")):
            result = run({"count": 1, "emails": False, "audience": ""}, current())
        assert not result["partial"] and not result["paused"]
        assert result["discovery"]["counts"]["produced"] == 1
    network.assert_called_once()


def test_email_timeout_keeps_uncertain_receipt_and_cannot_retry(ark_client):
    from leadzen.ai_ark import enrich
    from leadzen.discovery_progress import observe, current, credits
    from openoutfind.crm.models import Lead, Deal, DealState
    row = start(ark_client, emails=True)
    lead = Lead.objects.create(profile_url=person()["link"]["linkedin"])
    Deal.objects.create(lead=lead, state=DealState.QUALIFIED)
    with observe(row), patch("leadzen.ai.pinned_request", side_effect=TimeoutError) as network:
        with pytest.raises(TimeoutError):
            enrich(current(), lead)
        enrich(current(), lead)
        assert credits(current().session)["used"] is None
    network.assert_called_once()
    lead.refresh_from_db()
    assert not lead.email


@pytest.mark.parametrize("status,raw", [(401, b"synthetic-secret"), (402, b""), (429, b""), (200, b"bad-json"), (200, b"[]"), (200, b'{"content":{}}')])
def test_failed_search_response_does_not_retry_or_claim_zero_cost(ark_client, status, raw):
    from leadzen.ai_ark import search
    from leadzen.discovery_progress import observe, current, credits
    row = start(ark_client)
    with observe(row), patch("leadzen.ai.pinned_request", return_value=(status, {}, raw)) as network:
        with pytest.raises(ValueError):
            search(current())
        with pytest.raises(PermissionError):
            search(current())
        assert credits(current().session)["used"] is None
    network.assert_called_once()


def test_cancellation_during_pacing_blocks_http_request(ark_client):
    from leadzen.ai_ark import search
    from leadzen.discovery_progress import observe, current
    from leadzen.config.models import ChatRun
    row = start(ark_client)
    with observe(row), patch("leadzen.ai_ark.time.sleep", side_effect=lambda _: ChatRun.objects.filter(pk=row.pk).update(cancel_requested=True)), patch("leadzen.ai.pinned_request") as network:
        with pytest.raises(PermissionError):
            search(current())
    network.assert_not_called()


def test_over_budget_request_never_launches(ark_client):
    setup = ark_client.get("/api/discovery").json()
    with patch("leadzen.chat.views.launch") as launch, patch("leadzen.ai.pinned_request") as network:
        response = post(ark_client, "/api/discovery", {"count": 13, "emails": True, "estimated_credits": 26, "revision": setup["revision"], "request_id": str(uuid.uuid4())})
    assert response.status_code == 400
    launch.assert_not_called()
    network.assert_not_called()


def test_usage_keeps_provider_units_separate_after_switch(ark_client):
    from leadzen.chat.tools import execute
    from leadzen.config.models import ChatThread, ChatRun, DiscoverySession, DiscoveryLookup, DiscoverySearch
    row = start(ark_client)
    ark = DiscoverySession.objects.get(run=row)
    DiscoverySearch.objects.create(session=ark, query_hash="synthetic", size=2, credits="0.5", state="terminated")
    DiscoveryLookup.objects.create(session=ark, source_id=1001, credits=1, state="terminated")
    old = ChatRun.objects.create(thread=ChatThread.objects.create(actor_id=row.actor_id), actor_id=row.actor_id, request_id=uuid.uuid4(), status="succeeded")
    legacy = DiscoverySession.objects.create(run=old, goal=2, unit="emails", action={})
    DiscoveryLookup.objects.create(session=legacy, source_id=1002, credits=2, state="terminated")
    report = execute(row, "get_credit_usage", {})
    assert report["provider"] == "ai_ark" and report["reported_usage"] == 1.5
    put(ark_client, "bettercontact")
    report = execute(row, "get_credit_usage", {})
    assert report["provider"] == "bettercontact" and report["reported_usage"] == 2
    assert report["uncertain_searches"] == 0
