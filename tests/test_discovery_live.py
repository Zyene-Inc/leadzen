"""Durable, factual discovery activity, safe controls and separate email approval."""
import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from tests.test_discovery import discovery_client, request_body
from tests.test_chat import chat_client, post


def start(client, emails=False):
    with patch("leadzen.chat.views.launch"):
        response = post(client, "/api/discovery", request_body(client, emails=emails))
    assert response.status_code == 202
    return response.json()["run"]["id"]


def profile(slug="one"):
    from openoutfind.crm.models import Lead
    return Lead.objects.create(profile_url=f"https://www.linkedin.com/in/synthetic-{slug}", full_name=f"Synthetic {slug}", job_title="Practice manager", profile_text="Synthetic practice manager in the US")


def test_progress_starts_at_zero_and_reads_do_not_run_providers(discovery_client):
    run = start(discovery_client)
    with patch("leadzen.chat.views.launch") as launch, patch("leadzen.chat.engine.find_leads") as finder:
        response = discovery_client.get(f"/api/discovery/{run}")
        assert response.status_code == 200
        data = response.json()
        assert data["goal"] == {"count": 3, "unit": "leads"}
        assert data["counts"] == {"discovered": 0, "evaluated": 0, "awaiting_evaluation": 0, "qualified": 0, "rejected": 0, "with_email": 0, "produced": 0}
        assert data["credits"]["used"] == 0 and not data["events"]
        assert "synthetic-secret" not in response.content.decode()
        launch.assert_not_called()
        finder.assert_not_called()


def test_real_verdicts_and_complete_records_are_persisted_immediately(discovery_client):
    from openoutfind.crm.models import Deal
    from leadzen.discovery_progress import Monitor, ProgressOutput
    from leadzen.config.models import DiscoverySession
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    accepted, rejected = profile(), profile("two")
    monitor.discovered([accepted, rejected])
    monitor.discovered([accepted])
    Deal.objects.create(lead=accepted, state="Qualified", reason="Synthetic director-level decision-maker.")
    Deal.objects.create(lead=rejected, state="Failed", outcome="wrong_fit", reason="Synthetic trainee, not a decision-maker.")
    monitor.verdict(accepted)
    monitor.verdict(rejected)
    monitor.verdict(accepted)
    writer = ProgressOutput(monitor)
    record = {"lead_id": accepted.pk, "email": None, "linkedin_url": accepted.profile_url, "reason": "Synthetic director-level decision-maker."}
    writer.write(json.dumps(record)[:12])
    assert discovery_client.get(f"/api/discovery/{run}").json()["counts"]["produced"] == 0
    writer.write(json.dumps(record)[12:] + "\n")
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["counts"]["discovered"] == 2 and data["counts"]["evaluated"] == 2
    assert data["counts"]["qualified"] == data["counts"]["rejected"] == data["counts"]["produced"] == 1
    assert len([e for e in data["events"] if e["kind"] == "qualified"]) == 1
    assert data["leads"][0]["reason"] == "Synthetic director-level decision-maker."
    assert data["leads"][0]["contact_id"] is not None


def test_candidate_arrivals_are_live_idempotent_and_have_no_invented_verdict(discovery_client):
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    from openoutfind.crm.models import Company
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    lead = profile()
    lead.company = Company.objects.create(key="live.example.com", name="Synthetic dental practice")
    lead.save()
    monitor.discovered([lead])
    monitor.discovered([lead])
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["counts"]["discovered"] == 1 and data["counts"]["evaluated"] == 0
    assert len(data["events"]) == 1 and data["events"][0]["kind"] == "discovered"
    candidate = data["candidates"][0]
    assert candidate["source_id"] == lead.pk and candidate["name"] == lead.full_name
    assert candidate["title"] == lead.job_title and candidate["company"] == "Synthetic dental practice"
    assert candidate["outcome"] == "pending" and candidate["reason"] == "" and candidate["contact_id"] is None
    assert data["current_activity"] == {key: data["events"][0][key] for key in ("kind", "data", "created_at")}


@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.parametrize("entrypoint", ["qualify", "top_up"])
def test_actual_selected_candidate_is_visible_before_qualification_finishes(discovery_client, fail, entrypoint):
    import numpy as np
    from types import SimpleNamespace, ModuleType
    from contextlib import nullcontext
    from openoutfind.core.pipeline import qualify
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    lead = profile()
    lead.embedding_array = np.zeros(2)
    lead.save()
    qualifier = SimpleNamespace(predict=lambda embedding: None, n_obs=0, update=lambda embedding, label: None)

    def llm(profile_text, **kwargs):
        # Check the public live payload while the external call is in progress.
        data = discovery_client.get(f"/api/discovery/{run}").json()
        assert data["current_activity"]["kind"] == "evaluating"
        assert data["current_activity"]["data"]["source_id"] == lead.pk
        assert data["counts"]["evaluated"] == 0 and data["candidates"][0]["reason"] == ""
        if fail:
            raise RuntimeError("Synthetic qualification unavailable")
        return 1, "Synthetic decision-maker matches the saved target."

    # Reproduce top_up's cached `from qualify import run_qualification` alias
    # without loading unrelated heavyweight vocabulary/ML dependencies.
    top_up = ModuleType("openoutfind.core.pipeline.top_up")
    top_up.run_qualification = qualify.run_qualification
    alias = patch.dict("sys.modules", {top_up.__name__: top_up}) if entrypoint == "top_up" else nullcontext()
    with alias, patch.object(monitor, "boundary"), patch("openoutfind.core.ml.qualifier.qualify_with_llm", side_effect=llm):
        with monitor.adapters():
            runner = qualify.run_qualification if entrypoint == "qualify" else top_up.run_qualification
            if fail:
                with pytest.raises(RuntimeError):
                    runner(SimpleNamespace(product_docs="Synthetic product", campaign_target="Dentists"), qualifier)
            else:
                runner(SimpleNamespace(product_docs="Synthetic product", campaign_target="Dentists"), qualifier)
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["counts"]["evaluated"] == (0 if fail else 1)
    if not fail:
        assert data["current_activity"]["kind"] == "qualified"
        assert data["candidates"][0]["reason"] == "Synthetic decision-maker matches the saved target."
        assert data["candidates"][0]["contact_id"] is not None


@pytest.mark.parametrize("reason", [
    "Strong product fit despite a partial campaign-industry mismatch: this dentist serves local patients.",
    "Dental clinics fall outside the campaign's stated Restaurants and Home Services industries.",
    "This owner is not strictly in the verticals named in the campaign, but needs reviews.",
    "The practice is healthcare rather than the campaign's hospitality target.",
])
def test_explicit_campaign_mismatch_cannot_be_saved_as_qualified(discovery_client, reason):
    import numpy as np
    from types import SimpleNamespace
    from openoutfind.core.pipeline import qualify
    from openoutfind.crm.models import Deal
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession

    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    lead = profile()
    lead.embedding_array = np.zeros(2)
    lead.save()
    labels = []
    qualifier = SimpleNamespace(predict=lambda embedding: None, n_obs=0,
                                update=lambda embedding, label: labels.append(label))
    captured = {}

    def llm(profile_text, **kwargs):
        captured.update(kwargs)
        return 1, reason

    target = "Owners at Restaurants & Hospitality & Home Services in the United States, 1-10 employees"
    with patch.object(monitor, "boundary"), patch("openoutfind.core.ml.qualifier.qualify_with_llm", side_effect=llm):
        with monitor.adapters():
            qualify.run_qualification(SimpleNamespace(product_docs="Reviews for restaurants and dentists",
                                                      campaign_target=target), qualifier)

    decision = Deal.objects.get(lead=lead)
    candidate = discovery_client.get(f"/api/discovery/{run}").json()["candidates"][0]
    assert captured["campaign_target"].startswith(target)
    assert "must not broaden the requested audience" in captured["campaign_target"]
    assert labels == [0]
    assert decision.state == "Failed" and candidate["outcome"] == "rejected"
    assert candidate["contact_id"] is None


def test_live_events_continue_after_storage_limit_and_candidate_history_is_bounded(discovery_client):
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession, DiscoveryEvent, DiscoveryCandidate
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    DiscoveryEvent.objects.bulk_create([DiscoveryEvent(session=monitor.session, kind="searching", data={"offset": i}) for i in range(1000)])
    DiscoveryCandidate.objects.bulk_create([DiscoveryCandidate(session=monitor.session, source_id=i + 1, data={"name": f"Synthetic person {i}"}) for i in range(120)])
    monitor.event("search_completed", {"profiles_returned": 75})
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert monitor.session.events.count() == 1000 and len(data["events"]) == 100
    assert monitor.session.events.order_by("pk").first().data == {"offset": 0}
    assert data["current_activity"]["kind"] == "search_completed"
    assert data["current_activity"]["data"]["profiles_returned"] == 75
    assert len(data["candidates"]) == 100
    assert data["candidates"][0]["source_id"] == 21 and data["candidates"][-1]["source_id"] == 120


def test_awaiting_review_does_not_subtract_unrelated_evaluated_profiles(discovery_client):
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    from openoutfind.crm.models import Deal
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    existing, newly_found = profile("existing"), profile("newly-found")
    Deal.objects.create(lead=existing, state="Qualified", reason="Synthetic existing candidate qualified")
    monitor.verdict(existing)
    monitor.discovered([newly_found])
    statistics = discovery_client.get(f"/api/discovery/{run}").json()["counts"]
    assert statistics["discovered"] == statistics["evaluated"] == 1
    assert statistics["awaiting_evaluation"] == 1


def test_page_profiles_appear_before_the_entire_page_finishes_persisting(discovery_client):
    import numpy as np
    from openoutfind.core.models import QueryNode
    from openoutfind.core.pipeline import discover
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    node = QueryNode.objects.create(token_key="synthetic-page", country_code="US")
    rows = [{"contact_linkedin_profile_url": f"https://example.com/sample/{i}", "contact_full_name": f"Sample person {i}"} for i in range(2)]
    observations = []

    def embedding(*args, **kwargs):
        data = discovery_client.get(f"/api/discovery/{run}").json()
        observations.append(data["counts"]["discovered"])
        if len(observations) == 2:
            assert data["events"][-1]["kind"] == "discovered"
            assert data["events"][-1]["data"]["name"] == "Sample person 0"
        return np.zeros(2)

    with patch.object(monitor, "boundary"), patch("openoutfind.discovery.embed_profile", side_effect=embedding):
        with monitor.adapters():
            assert discover._harvest(node, rows) == 2
    assert observations == [0, 1]
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["counts"]["discovered"] == 2 and data["counts"]["evaluated"] == 0
    assert [e["data"]["name"] for e in data["events"]] == ["Sample person 0", "Sample person 1"]


def test_identical_firmographics_never_guess_the_current_candidate(discovery_client):
    import numpy as np
    from types import SimpleNamespace
    from openoutfind.core.pipeline import qualify
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    candidates = [profile("one"), profile("two")]
    for lead in candidates:
        lead.embedding_array = np.zeros(2)
        lead.save()
    qualifier = SimpleNamespace(acquisition_scores=lambda embeddings: None, predict=lambda embedding: None, n_obs=0,
                                update=lambda embedding, label: None)

    def llm(*args, **kwargs):
        activity = discovery_client.get(f"/api/discovery/{run}").json()["current_activity"]
        assert activity["kind"] == "evaluating"
        assert "source_id" not in activity["data"] and "name" not in activity["data"]
        return 0, "Synthetic role does not match."

    with patch.object(monitor, "boundary"), patch("openoutfind.core.ml.qualifier.qualify_with_llm", side_effect=llm):
        with monitor.adapters():
            qualify.run_qualification(SimpleNamespace(product_docs="Synthetic product", campaign_target="Dentists"), qualifier, candidates)
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["current_activity"]["kind"] == "rejected"
    assert data["current_activity"]["data"]["source_id"] == candidates[0].pk
    assert data["current_activity"]["data"]["reason"] == "Synthetic role does not match."


def test_pause_before_execution_and_resume_remaining_goal_once(discovery_client):
    from leadzen.chat.engine import drive
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import ChatRun, DiscoverySession
    run = start(discovery_client)
    assert post(discovery_client, f"/api/discovery/{run}/pause", {}).status_code == 200
    with patch("django.core.management.call_command") as command:
        drive(run)
        command.assert_not_called()
    assert ChatRun.objects.get(pk=run).status == "paused"
    session = DiscoverySession.objects.get(run_id=run)
    lead = profile()
    from openoutfind.crm.models import Deal
    Deal.objects.create(lead=lead, state="Qualified", reason="Synthetic fit")
    monitor = Monitor(session)
    monitor.verdict(lead)
    monitor.output({"lead_id": lead.pk, "email": None})
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, f"/api/discovery/{run}/resume", {}).status_code == 202
        assert post(discovery_client, f"/api/discovery/{run}/resume", {}).status_code == 409
        launch.assert_called_once()
    row = ChatRun.objects.get(pk=run)
    assert row.pending["arguments"]["count"] == 2 and row.credits_reserved == 0
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 2, "partial": False}) as finder:
        drive(run)
        drive(run)
        finder.assert_called_once_with({"count": 2, "emails": False, "audience": ""})


def test_foreign_run_controls_fail_before_credentials_or_launch(discovery_client):
    from leadzen.config.models import ChatRun
    run = start(discovery_client)
    ChatRun.objects.filter(pk=run).update(actor_id=999)
    with patch("leadzen.discovery.effective") as credentials, patch("leadzen.chat.views.launch") as launch:
        assert discovery_client.get(f"/api/discovery/{run}").status_code == 404
        for action in ("pause", "resume", "stop", "emails"):
            assert post(discovery_client, f"/api/discovery/{run}/{action}", {}).status_code == 404
        credentials.assert_not_called()
        launch.assert_not_called()


def test_free_discovery_cannot_submit_enrichment_and_credit_reports_are_idempotent(discovery_client):
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    monitor = Monitor(DiscoverySession.objects.get(run_id=start(discovery_client)))
    with pytest.raises(PermissionError):
        monitor.reserve_lookup({"data": [{"linkedin_url": profile().profile_url}], "enrich_email_address": True})
    paid = start_after_finish(discovery_client, emails=True)
    monitor = Monitor(DiscoverySession.objects.get(run_id=paid))
    from openoutfind.crm.models import Deal
    lead = profile("paid")
    Deal.objects.create(lead=lead, state="Qualified", reason="Synthetic fit")
    receipt = monitor.reserve_lookup({"data": [{"linkedin_url": lead.profile_url}], "enrich_email_address": True})
    monitor.submitted(receipt, {"id": "synthetic-provider-job"})
    monitor.report_lookup("synthetic-provider-job", {"status": "terminated", "credits_consumed": 1})
    monitor.report_lookup("synthetic-provider-job", {"status": "terminated", "credits_consumed": 1})
    assert discovery_client.get(f"/api/discovery/{paid}").json()["credits"]["used"] == 1


def start_after_finish(client, emails=False):
    from leadzen.config.models import ChatRun
    ChatRun.objects.filter(status__in=["queued", "running", "paused"]).update(status="cancelled")
    return start(client, emails)


def completed(client):
    from leadzen.config.models import ChatRun, DiscoverySession
    from leadzen.discovery_progress import Monitor
    from openoutfind.crm.models import Deal
    run = start(client)
    monitor = Monitor(DiscoverySession.objects.get(run_id=run))
    lead = profile()
    Deal.objects.create(lead=lead, state="Qualified", reason="Synthetic fit")
    monitor.discovered([lead])
    monitor.verdict(lead)
    monitor.output({"lead_id": lead.pk})
    ChatRun.objects.filter(pk=run).update(status="succeeded")
    return run, lead


def email_body(client, run):
    review = client.get(f"/api/discovery/{run}/emails").json()
    return {"candidate_ids": [c["id"] for c in review["items"]], "estimated_credits": len(review["items"]),
            "revision": review["revision"], "request_id": str(uuid.uuid4())}


def test_email_review_is_read_only_and_confirmation_is_exact_idempotent_selection(discovery_client):
    from leadzen.config.models import ChatRun, DiscoverySession
    run, lead = completed(discovery_client)
    with patch("leadzen.chat.views.launch") as launch, patch("leadzen.chat.engine.find_leads") as finder:
        body = email_body(discovery_client, run)
        launch.assert_not_called()
        finder.assert_not_called()
        assert ChatRun.objects.count() == 1
        response = post(discovery_client, f"/api/discovery/{run}/emails", body)
        assert response.status_code == 202
        assert post(discovery_client, f"/api/discovery/{run}/emails", body).json() == response.json()
        launch.assert_called_once()
        child = DiscoverySession.objects.get(pk=response.json()["run"]["id"])
        assert child.source_ids == [lead.pk] and child.goal == 1 and child.unit == "emails"
        assert child.action["single_action"] is True and child.run.credits_reserved == 1
        assert post(discovery_client, f"/api/discovery/{run}/emails", {**body, "candidate_ids": [999]}).status_code == 409


@pytest.mark.parametrize("change", ["deleted", "unqualified", "has_email", "changed_target", "inflight"])
def test_changed_email_review_never_launches_stale_selection(discovery_client, change):
    from leadzen.config.models import ContactPreferences, SiteConfig, DiscoverySession, DiscoveryLookup
    from cold_outreach.leads.models import Lead as Contact
    from openoutfind.crm.models import Deal
    run, lead = completed(discovery_client)
    body = email_body(discovery_client, run)
    if change == "deleted":
        contact = Contact.objects.get(lead_id=str(lead.pk))
        ContactPreferences.objects.update_or_create(lead=contact, defaults={"deleted_at": timezone.now()})
    elif change == "unqualified":
        Deal.objects.filter(lead=lead).update(state="Failed")
    elif change == "has_email":
        lead.email = "already@example.com"
        lead.save()
    elif change == "changed_target":
        config = SiteConfig.load()
        config.campaign_target = "Another synthetic target"
        config.save()
    else:
        DiscoveryLookup.objects.create(session=DiscoverySession.objects.get(pk=run), source_id=lead.pk)
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, f"/api/discovery/{run}/emails", body).status_code == 409
        launch.assert_not_called()


@pytest.mark.parametrize("changes", [{"candidate_ids": []}, {"candidate_ids": [True]}, {"candidate_ids": [1, 1]}, {"estimated_credits": 0}, {"request_id": "bad"}])
def test_invalid_email_approval_is_rejected(discovery_client, changes):
    run, _ = completed(discovery_client)
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, f"/api/discovery/{run}/emails", {**email_body(discovery_client, run), **changes}).status_code == 400
        launch.assert_not_called()


def test_no_email_lookup_until_discovery_ends_and_success_does_not_invent_progress(discovery_client):
    from leadzen.chat.engine import drive
    run = start(discovery_client)
    assert discovery_client.get(f"/api/discovery/{run}/emails").status_code == 409
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 3, "partial": False}):
        drive(run)
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["status"] == "succeeded" and data["goal_reached"] is False and data["counts"]["produced"] == 0


@pytest.mark.parametrize("change", ["config", "expiry", "cancel"])
def test_resume_revalidates_authorization_and_does_not_replay(discovery_client, change):
    from leadzen.config.models import ChatRun, SiteConfig
    from leadzen.chat.engine import drive
    run = start(discovery_client)
    post(discovery_client, f"/api/discovery/{run}/pause", {})
    with patch("django.core.management.call_command"):
        drive(run)
    if change == "config":
        config = SiteConfig.load()
        config.campaign_target = "Changed target"
        config.save()
    elif change == "expiry":
        ChatRun.objects.filter(pk=run).update(approval_expires_at=timezone.now() - timedelta(seconds=1))
    else:
        post(discovery_client, f"/api/discovery/{run}/stop", {})
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, f"/api/discovery/{run}/resume", {}).status_code == 409
        launch.assert_not_called()


def test_stop_retains_saved_results_and_paused_run_blocks_another(discovery_client):
    from leadzen.config.models import ChatRun
    run, _ = completed(discovery_client)
    ChatRun.objects.filter(pk=run).update(status="paused")
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, "/api/discovery", request_body(discovery_client)).status_code == 409
        assert post(discovery_client, f"/api/discovery/{run}/stop", {}).status_code == 200
        launch.assert_not_called()
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["status"] == "cancelled" and data["counts"]["produced"] == 1 and len(data["leads"]) == 1


def test_uncertain_lookup_is_not_zero_usage_or_resubmitted(discovery_client):
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    from openoutfind.crm.models import Deal
    run = start(discovery_client, emails=True)
    monitor = Monitor(DiscoverySession.objects.get(pk=run))
    lead = profile()
    Deal.objects.create(lead=lead, state="Qualified")
    body = {"data": [{"linkedin_url": lead.profile_url}], "enrich_email_address": True}
    receipt = monitor.reserve_lookup(body)
    assert discovery_client.get(f"/api/discovery/{run}").json()["credits"]["used"] is None
    with pytest.raises(PermissionError):
        monitor.reserve_lookup(body)
    with pytest.raises(PermissionError):
        monitor.submitted(receipt, {})
    monitor.submitted(receipt, {"id": "synthetic-job"})
    monitor.report_lookup("synthetic-job", {"status": "terminated"})
    assert discovery_client.get(f"/api/discovery/{run}").json()["credits"]["used"] is None
    with pytest.raises(PermissionError):
        monitor.report_lookup("foreign-job", {"credits_consumed": 1})


def test_observation_adapters_wrap_real_persisted_verdicts_and_searches(discovery_client):
    import numpy as np
    from types import SimpleNamespace
    from openoutfind.core.pipeline import discover, qualify
    from leadzen.config.models import DiscoverySession
    from leadzen.discovery_progress import Monitor
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(pk=run))
    node = SimpleNamespace(to_filters=lambda: {"job_title": "founder"})
    lead = profile()
    with patch.object(monitor, "boundary"), patch.object(discover, "_fetch", return_value="synthetic page") as fetch:
        with monitor.adapters():
            assert discover._fetch(node, 0) == "synthetic page"
            qualifier = SimpleNamespace(update=lambda embedding, label: None)
            qualify._save_qualification_result(qualifier, lead, np.zeros(2), 1, "Synthetic role matches")
    fetch.assert_called_once_with(node, 0)
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["counts"]["evaluated"] == data["counts"]["qualified"] == 1
    assert data["events"][0]["data"]["filters"] == {"job_title": "founder"}
    assert data["events"][1]["data"]["reason"] == "Synthetic role matches"


@pytest.mark.parametrize("page,count", [(None, None), ([], 0), ([{"name": "Bruce"}, {"name": "Chris"}], 2)])
def test_search_completion_records_returned_rows_not_provider_index_total(discovery_client, page, count):
    from types import SimpleNamespace
    from openoutfind.core.pipeline import discover
    from leadzen.config.models import DiscoverySession
    from leadzen.discovery_progress import Monitor
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(pk=run))
    result = None if page is None else SimpleNamespace(leads=page, leads_found=99999)
    node = SimpleNamespace(to_filters=lambda: {"job_title": "founder"})
    with patch.object(monitor, "boundary"), patch.object(discover, "_fetch", return_value=result):
        with monitor.adapters():
            assert discover._fetch(node, 0) is result
    completed = list(monitor.session.events.filter(kind="search_completed"))
    if count is None:
        assert completed == []
    else:
        assert len(completed) == 1 and completed[0].data["profiles_returned"] == count


def test_selected_email_pipeline_cannot_search_or_touch_unselected_profiles(discovery_client):
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    from openoutfind.crm.models import Deal, DealState
    from openoutfind.core import cycle
    from openoutfind.core.pipeline import ready_pool
    run, lead = completed(discovery_client)
    foreign = profile("unselected")
    Deal.objects.create(lead=foreign, state="Ready to Find Email")
    Deal.objects.filter(lead=lead).update(state="Ready to Find Email")
    with patch("leadzen.chat.views.launch"):
        response = post(discovery_client, f"/api/discovery/{run}/emails", email_body(discovery_client, run))
    monitor = Monitor(DiscoverySession.objects.get(pk=response.json()["run"]["id"]))
    with patch.object(ready_pool, "get_qualified_profiles", return_value=[{"lead_id": lead.pk}, {"lead_id": foreign.pk}]):
        with monitor.adapters():
            assert len(cycle.ROWS) == 3
            assert list(cycle._due(DealState.READY_TO_FIND_EMAIL).values_list("lead_id", flat=True)) == [lead.pk]
            assert ready_pool.get_qualified_profiles() == [{"lead_id": lead.pk}]
            with pytest.raises(PermissionError):
                monitor.reserve_lookup({"data": [{"linkedin_url": foreign.profile_url}], "enrich_email_address": True})


def test_profile_links_and_feed_are_bounded_and_secret_redacted(discovery_client):
    from leadzen.discovery_progress import Monitor, safe_profile
    from leadzen.config.models import DiscoverySession
    run = start(discovery_client)
    monitor = Monitor(DiscoverySession.objects.get(pk=run))
    for value in ["javascript:alert(1)", "data:text/html,x", "https://user:pass@example.com"]:
        assert not safe_profile(value)
    for index in range(103):
        monitor.event("searching", {"filters": {"job_title": f"synthetic-secret-ai {index}"}})
    response = discovery_client.get(f"/api/discovery/{run}")
    assert len(response.json()["events"]) == 100
    assert "synthetic-secret" not in response.content.decode()


def test_free_transport_refuses_paid_request_before_network(discovery_client):
    import requests
    from leadzen.chat.engine import drive
    from openoutfind.enrichment import bettercontact
    run = start(discovery_client)
    def command(*args, **kwargs):
        assert args[:3] == ("find", "3", "leads") and "--emails" not in args
        bettercontact._request(requests.Session(), "POST", "https://app.bettercontact.rocks/api/v2/async", json={"data": [{"linkedin_url": "https://example.com/one"}], "enrich_email_address": True})
    with patch("django.core.management.call_command", command), patch("leadzen.ai.pinned_request") as transport:
        drive(run)
        transport.assert_not_called()
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["status"] == "failed" and data["credits"]["used"] == 0


def test_paid_transport_disables_addons_and_preserves_reported_credit_truth(discovery_client):
    import requests
    from leadzen.chat.engine import drive
    from openoutfind.enrichment import bettercontact
    from openoutfind.crm.models import Deal
    run = start(discovery_client, emails=True)
    lead = profile()
    Deal.objects.create(lead=lead, state="Ready to Find Email")
    replies = [(200, {}, b'{"id":"synthetic-job"}'), (200, {}, b'{"status":"terminated","credits_consumed":1}')]
    def command(*args, **kwargs):
        assert args[:3] == ("find", "3", "emails")
        bettercontact._request(requests.Session(), "POST", "https://app.bettercontact.rocks/api/v2/async", json={"data": [{"linkedin_url": lead.profile_url}], "enrich_email_address": True, "enrich_profile": True, "verify_catch_all": True})
        bettercontact._request(requests.Session(), "GET", "https://app.bettercontact.rocks/api/v2/async/synthetic-job")
    with patch("django.core.management.call_command", command), patch("leadzen.ai.pinned_request", side_effect=replies) as transport:
        drive(run)
    submitted = json.loads(transport.call_args_list[0].args[3])
    assert submitted["enrich_phone_number"] is submitted["enrich_profile"] is submitted["verify_catch_all"] is False
    assert discovery_client.get(f"/api/discovery/{run}").json()["credits"]["used"] == 1


def test_stop_during_lookup_blocks_next_sink_but_keeps_accepted_receipt(discovery_client):
    import requests
    from leadzen.chat.engine import drive
    from openoutfind.enrichment import bettercontact
    from openoutfind.crm.models import Deal
    run = start(discovery_client, emails=True)
    lead = profile()
    Deal.objects.create(lead=lead, state="Qualified")
    def command(*args, **kwargs):
        bettercontact._request(requests.Session(), "POST", "https://app.bettercontact.rocks/api/v2/async", json={"data": [{"linkedin_url": lead.profile_url}], "enrich_email_address": True})
        assert post(discovery_client, f"/api/discovery/{run}/stop", {}).status_code == 200
        bettercontact._request(requests.Session(), "GET", "https://app.bettercontact.rocks/api/v2/async/synthetic-job")
    with patch("django.core.management.call_command", command), patch("leadzen.ai.pinned_request", return_value=(200, {}, b'{"id":"synthetic-job"}')) as transport:
        drive(run)
        assert transport.call_count == 1
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["status"] == "cancelled" and data["credits"]["used"] is None and data["credits"]["pending"] == 1


def test_malformed_and_incomplete_stream_records_never_become_progress(discovery_client):
    from leadzen.discovery_progress import Monitor, ProgressOutput
    from leadzen.config.models import DiscoverySession
    run = start(discovery_client)
    writer = ProgressOutput(Monitor(DiscoverySession.objects.get(pk=run)))
    writer.write('not-json\n{"lead_id":')
    assert discovery_client.get(f"/api/discovery/{run}").json()["counts"]["produced"] == 0


def test_domain_only_company_and_email_goal_without_address_are_honest(discovery_client):
    from openoutfind.crm.models import Company, Deal
    from leadzen.discovery_progress import Monitor
    from leadzen.config.models import DiscoverySession
    run = start(discovery_client, emails=True)
    monitor = Monitor(DiscoverySession.objects.get(pk=run))
    lead = profile()
    lead.company = Company.objects.create(key="example.com", domain="example.com", name=None)
    lead.save()
    Deal.objects.create(lead=lead, state="Qualified", reason="Synthetic fit")
    monitor.verdict(lead)
    monitor.output({"lead_id": lead.pk, "email": None})
    data = discovery_client.get(f"/api/discovery/{run}").json()
    assert data["leads"][0]["company"] == "example.com"
    assert data["counts"]["qualified"] == 1 and data["counts"]["produced"] == 0 and not data["goal_reached"]
