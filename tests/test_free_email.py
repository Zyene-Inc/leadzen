"""Free LinkedIn work-email lookup before the paid BetterContact purchase. Synthetic only: no network."""
import json
from unittest.mock import patch

import pytest

from tests.test_discovery import discovery_client  # noqa: F401
from tests.test_chat import chat_client, post  # noqa: F401
from cold_outreach.leads.models import Deal, Lead
from leadzen import free_email
from leadzen.config.models import FreeEmailLookup

FOUND = {"found": True, "email": "Bruce@SyntheticPractice.example", "company": "Synthetic Practice", "validation": "valid"}


@pytest.fixture(autouse=True)
def free_lookup_on(monkeypatch):
    monkeypatch.setenv("LEADZEN_FREE_EMAIL_LOOKUP", "on")


def prospect(slug="bruce", *, synthetic=False, company="Synthetic Practice", domain="syntheticpractice.example"):
    from openoutfind.crm.models import Company, Deal as Decision, Lead as Profile
    firm = Company.objects.create(key=f"synthetic-{slug}", name=company, domain=domain)
    profile = Profile.objects.create(full_name=f"{slug.title()} Synthetic", job_title="Director", company=firm, synthetic=synthetic,
                                     profile_url=f"https://www.linkedin.com/in/{slug}-synthetic/")
    decision = Decision.objects.create(lead=profile, state="Qualified", reason="Synthetic fit")
    lead = Lead.objects.create(lead_id=str(profile.pk), title=profile.job_title, linkedin_url=profile.profile_url, company=company)
    return Deal.objects.create(lead=lead), profile, decision


@pytest.mark.parametrize("value,expected", [
    ("https://www.linkedin.com/in/ada-l/", "https://www.linkedin.com/in/ada-l"),
    ("linkedin.com/in/ada-l", "https://www.linkedin.com/in/ada-l"),
    ("https://m.linkedin.com/in/ada.l", "https://www.linkedin.com/in/ada.l"),
    ("https://www.linkedin.com/company/acme", None),
    ("https://evil.example/in/ada", None),
    ("https://user:pw@www.linkedin.com/in/ada", None),
    ("https://www.linkedin.com:8443/in/ada", None),
])
def test_only_public_profile_urls_are_sent(value, expected):
    assert free_email.normalize_profile(value) == expected


@pytest.mark.parametrize("answer,status", [
    (FOUND, "found"),
    ({**FOUND, "company": "Other Corp", "email": "b@syntheticpractice.example"}, "found"),  # company domain still proves it
    ({**FOUND, "validation": "unknown"}, "unverified"),
    ({**FOUND, "company": "Other Corp", "email": "b@other.example"}, "unverified"),
    ({"found": False}, "not_found"),
    ({"found": True, "email": "not-an-email"}, "error"),
    ([], "error"),
])
def test_only_valid_company_addresses_count_as_found(answer, status):
    assert free_email.parse(answer, company="Synthetic Practice", domain="syntheticpractice.example")[0] == status


def test_found_email_is_saved_verified_and_paid_lookup_is_not_offered(discovery_client):
    from openoutfind.crm.models import DealState
    deal, profile, decision = prospect()
    with patch("leadzen.free_email.request", return_value=FOUND) as call, patch("leadzen.chat.views.launch") as launch:
        response = post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {})
        assert response.status_code == 200, response.content
        call.assert_called_once_with("https://www.linkedin.com/in/bruce-synthetic")
        launch.assert_not_called()
    contact = discovery_client.get(f"/api/contacts/{deal.pk}").json()
    assert contact["email"] == "bruce@syntheticpractice.example"
    assert contact["email_status"] == "verified" and contact["crm_status"] == "email_found"
    assert contact["free_lookup"]["status"] == "found" and "email" not in contact["free_lookup"]
    profile.refresh_from_db(); decision.refresh_from_db()
    assert profile.email == "bruce@syntheticpractice.example" and decision.state == DealState.RESOLVED
    assert not discovery_client.get(f"/api/contacts/{deal.pk}/email").json()["eligible"]


def test_miss_offers_paid_lookup_and_is_never_repeated(discovery_client):
    deal, profile, _ = prospect()
    with patch("leadzen.free_email.request", return_value={"found": False}) as call:
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).json()["status"] == "not_found"
        # A miss is a final answer about this person: offer the purchase, don't ask again.
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).status_code == 200
        assert call.call_count == 1
        assert free_email.after_discovery(5) == {"checked": 0, "found": 0, "not_found": 0, "errors": 0, "stopped": ""}
    contact = discovery_client.get(f"/api/contacts/{deal.pk}").json()
    assert contact["email"] == "" and contact["free_lookup"] == {"status": "not_found", "checked_at": contact["free_lookup"]["checked_at"], "label": "Free lookup", "retry": False}
    review = discovery_client.get(f"/api/contacts/{deal.pk}/email").json()
    assert review["eligible"] and review["estimated_credits"] == 1


def test_unverified_address_is_never_saved(discovery_client):
    deal, profile, _ = prospect()
    with patch("leadzen.free_email.request", return_value={**FOUND, "validation": "catch_all"}):
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).json()["status"] == "unverified"
    profile.refresh_from_db(); deal.lead.refresh_from_db()
    assert not profile.email and not deal.lead.email
    assert FreeEmailLookup.objects.get(source_id=profile.pk).email == ""


def test_provider_failure_can_be_retried_and_rate_limit_is_reported(discovery_client):
    deal, profile, _ = prospect()
    with patch("leadzen.free_email.request", side_effect=ValueError("HTTP 500")):
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).json()["status"] == "error"
    assert discovery_client.get(f"/api/contacts/{deal.pk}").json()["free_lookup"]["retry"] is True
    with patch("leadzen.free_email.request", side_effect=free_email.RateLimited()):
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).status_code == 429
    with patch("leadzen.free_email.request", return_value=FOUND):
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).json()["status"] == "found"
    assert FreeEmailLookup.objects.get(source_id=profile.pk).attempts == 3


def test_ineligible_and_disabled_lookups_never_call_the_provider(discovery_client, monkeypatch):
    deal, profile, decision = prospect()
    manual = Deal.objects.create(lead=Lead.objects.create(lead_id="manual-synthetic"))
    with patch("leadzen.free_email.request") as call:
        assert post(discovery_client, f"/api/contacts/{manual.pk}/free-email", {}).status_code == 409
        decision.state, decision.outcome = "Failed", "wrong_fit"
        decision.save()
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).status_code == 409
        decision.state, decision.outcome = "Qualified", ""
        decision.save()
        monkeypatch.setenv("LEADZEN_FREE_EMAIL_LOOKUP", "off")
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).status_code == 409
        assert free_email.after_discovery(5)["checked"] == 0
        monkeypatch.setenv("LEADZEN_FREE_EMAIL_LOOKUP", "on")
        profile.profile_url = "https://example.com/profile/bruce"
        profile.save()
        assert post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {}).status_code == 409
        call.assert_not_called()


def test_after_discovery_checks_new_qualified_profiles_within_the_hourly_limit(discovery_client, monkeypatch):
    prospect("ada")
    prospect("grace")
    prospect("synthetic", synthetic=True)
    monkeypatch.setenv("LEADZEN_FREE_EMAIL_HOURLY_LIMIT", "1")
    with patch("leadzen.free_email.request", return_value={"found": False}) as call:
        summary = free_email.after_discovery(5)
    assert call.call_count == 1 and summary["checked"] == 1 and summary["stopped"] == "hourly_limit"
    monkeypatch.setenv("LEADZEN_FREE_EMAIL_HOURLY_LIMIT", "60")
    with patch("leadzen.free_email.request", return_value={"found": False}) as call:
        assert free_email.after_discovery(5)["checked"] == 1
    assert call.call_count == 1 and FreeEmailLookup.objects.count() == 2


def test_discovery_runs_free_lookup_only_after_profile_search(chat_client, monkeypatch):
    from leadzen.chat.engine import find_leads
    monkeypatch.delenv("LEADZEN_CHAT_RUN_ID", raising=False)
    prospect("ada")

    def command(*args, **kwargs):
        kwargs["stdout"].write(json.dumps({"lead_id": "synthetic-new", "first_name": "New"}) + "\n")

    with patch("django.core.management.call_command", side_effect=command), patch("leadzen.ai.install_engine_adapters"), \
            patch("leadzen.wizard.apply_to_environment"), patch("leadzen.free_email.request", return_value=FOUND | {"company": "Synthetic Practice"}) as call:
        result = find_leads({"count": 2, "emails": False, "audience": "Synthetic audience"})
        assert result["free_emails"]["found"] == 1 and "Free email lookup: 1 of 1 found." in result["note"]
        assert call.call_count == 1
        paid = find_leads({"count": 2, "emails": True, "audience": "Synthetic audience"})
        assert "free_emails" not in paid and call.call_count == 1


def test_only_the_approved_host_is_allowed():
    from leadzen.ai import pinned_open
    from leadzen.configuration import SettingsError
    with pytest.raises(SettingsError):
        pinned_open("POST", "https://evil.example/public/findEmailByLinkedIn", {}, b"{}", "evil.example", kind="APPLYBOLT")


def test_lead_list_reports_free_result_without_exposing_it_twice(discovery_client):
    deal, _, _ = prospect()
    with patch("leadzen.free_email.request", return_value=FOUND):
        post(discovery_client, f"/api/contacts/{deal.pk}/free-email", {})
    row = discovery_client.get("/api/leads").json()["items"][0]
    assert row["email_status"] == "verified" and row["free_lookup"]["status"] == "found" and "email" not in row["free_lookup"]


def monitor_for(unit="leads", goal=5):
    import uuid
    from leadzen.config.models import ChatRun, ChatThread, DiscoverySession
    from leadzen.discovery_progress import Monitor
    thread = ChatThread.objects.create(actor_id=1)
    run = ChatRun.objects.create(thread=thread, actor_id=1, request_id=uuid.uuid4(), status="running")
    return Monitor(DiscoverySession.objects.create(run=run, action={"arguments": {}}, goal=goal, unit=unit))


def test_each_lead_is_looked_up_in_the_background_as_it_qualifies(discovery_client):
    import threading
    monitor = monitor_for()
    _, ada, _ = prospect("ada")
    _, grace, _ = prospect("grace")
    both_running = threading.Barrier(2, timeout=10)

    def answer(url, **kwargs):
        assert kwargs == {"preauthorized": True}
        both_running.wait()  # only passes when the two lookups run at the same time
        return FOUND | {"email": f"{url.rsplit('/', 1)[-1]}@syntheticpractice.example"}

    with patch("leadzen.free_email.request", side_effect=answer):
        monitor.verdict(ada)
        monitor.verdict(grace)
        summary = monitor.finish_free_emails()
    assert summary == {"checked": 2, "found": 2, "not_found": 0, "errors": 0, "stopped": ""}
    rows = {c.source_id: c for c in monitor.session.candidates.all()}
    assert rows[ada.pk].data["email"] == "ada-synthetic@syntheticpractice.example"
    assert Lead.objects.get(lead_id=str(grace.pk)).email == "grace-synthetic@syntheticpractice.example"
    events = list(monitor.session.events.filter(kind="email_lookup").values_list("data", flat=True))
    assert len(events) == 2 and all(e["source"] == "free" and e["email_status"] == "valid" for e in events)
    assert monitor.finish_free_emails() is None


def test_rejected_leads_and_stopped_runs_never_reach_the_provider(discovery_client):
    monitor = monitor_for()
    _, ada, decision = prospect("ada")
    decision.state, decision.outcome = "Failed", "wrong_fit"
    decision.save()
    _, grace, _ = prospect("grace")
    with patch("leadzen.free_email.request") as call:
        monitor.verdict(ada)
        with patch("leadzen.chat.engine.assert_action_access", side_effect=PermissionError("stopped")):
            monitor.verdict(grace)
        summary = monitor.finish_free_emails()
    call.assert_not_called()
    assert summary["stopped"] == "stopped" and not FreeEmailLookup.objects.exists()


def test_a_search_that_buys_emails_waits_for_the_free_lookup_first(discovery_client):
    monitor = monitor_for(unit="emails")
    _, ada, decision = prospect("ada")
    with patch("leadzen.free_email.request", return_value=FOUND) as call:
        monitor.verdict(ada)
    call.assert_called_once()
    # The caller's own profile object already carries the address, so nothing is bought.
    assert ada.email == "bruce@syntheticpractice.example"
    decision.refresh_from_db()
    assert decision.state == "Resolved"
    assert monitor.finish_free_emails()["found"] == 1


def test_chat_summary_reports_free_results_and_offers_paid_for_misses(discovery_client):
    from leadzen.chat.engine import email_next_step
    from leadzen.config.models import DiscoveryCandidate
    monitor = monitor_for()
    for index, email in enumerate(["a@example.com", "", ""]):
        DiscoveryCandidate.objects.create(session=monitor.session, source_id=900 + index, outcome="qualified", data={"email": email})
    text = email_next_step(monitor.session, {"checked": 3, "found": 1, "not_found": 1, "errors": 1, "stopped": ""})
    assert "1 of 3 qualified leads" in text and "draft outreach for them now" in text
    assert "For the 2 without one, I can buy emails with BetterContact credits" in text and "couldn't check 1 lead" in text
    assert "approval" in email_next_step(monitor.session, None)
