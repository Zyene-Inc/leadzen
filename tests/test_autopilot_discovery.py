"""Daily discovery uses genuine finder lifecycle with synthetic provider/ML boundaries."""
from datetime import timedelta
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import importlib
import sys

import numpy as np
import pytest

from leadzen import autopilot
from leadzen.autopilot_worker import discover
from leadzen.config.models import AutopilotRun
from test_autopilot import NOW, policy, enable_service
from test_campaigns import connected


def source(slug):
    from openoutfind.crm.models import Lead
    lead = Lead.objects.create(profile_url=f"https://www.linkedin.com/in/{slug}",
        full_name=slug, profile_text=f"Synthetic director {slug}")
    lead.embedding_array = np.zeros(2)
    lead.save()
    return lead


@pytest.mark.parametrize("cold", [False, True])
@pytest.mark.parametrize("familiar_page", [False, True])
def test_daily_goal_ignores_old_backlog_and_only_qualifies_newly_discovered_profiles(connected, cold, familiar_page):
    """Exercise command, goal, cycle, top_up, qualification, harvest and JSON export.

    Only the provider's page acquisition, local embedding and model response are
    synthetic. Yesterday's unqualified pool is deliberately older/preferred,
    with a ready address and an in-flight paid lookup also left in the database.
    """
    from openoutfind.core import cycle
    from openoutfind.core.models import QueryNode
    from openoutfind.core.pipeline import discover as discovery, top_up
    from openoutfind.crm.models import Lead, Deal, DealState

    old_unqualified = [source(f"yesterday-unqualified-{i}") for i in range(3)]
    old_ready = source("yesterday-ready")
    ready = Deal.objects.create(lead=old_ready, state=DealState.READY_TO_FIND_EMAIL, reason="Old fit")
    old_pending = source("yesterday-pending")
    pending = Deal.objects.create(lead=old_pending, state=DealState.FINDING_EMAIL,
        lookup_provider="bettercontact", lookup_request_id="old-paid-handle", not_before=NOW)
    p = policy(daily_ai_requests=1)
    run = AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(),
        checkpoint={"contact_limit": 1}, deadline_at=NOW + timedelta(minutes=12))
    baseline = Lead.objects.order_by("-pk").first().pk
    node = QueryNode.objects.create(token_key="synthetic-today", country_code="US")
    qualifier = SimpleNamespace(is_cold=cold, n_real_positives=0, n_obs=0,
        acquisition_mode=lambda: "explore (BALD)", acquisition_scores=lambda embeddings: None,
        predict=lambda embedding: None, predict_probs=lambda embeddings: np.ones(len(embeddings)),
        update=lambda embedding, label: None)
    searches, qualifications = [], []
    incidental = []

    def search(*args):
        searches.append(True)
        if familiar_page and len(searches) == 1:
            assert discovery._harvest(node, [{
                "contact_linkedin_profile_url": old_unqualified[0].profile_url,
                "contact_job_title": "Director",
            }]) == 0
            return True  # A real page advances the frontier even without new rows.
        # A new source created outside this session must not satisfy its goal.
        unrelated = source("incidental-source")
        Deal.objects.create(lead=unrelated, state=DealState.QUALIFIED, reason="Unrelated qualification")
        incidental.append(unrelated)
        return bool(discovery._harvest(node, [{
            "contact_linkedin_profile_url": "https://www.linkedin.com/in/today-search-result",
            "contact_full_name": "Today's director", "contact_job_title": "Director",
            "contact_location_country": "United States",
        }]))

    def qualify(text, **kwargs):
        autopilot.external_guard(reserve_model=True)
        qualifications.append(text)
        assert "today" not in text  # Names stay outside qualification text.
        assert "director" in text and "yesterday" not in text
        return 1, "Fits the saved target"

    with patch("django.utils.timezone.now", return_value=NOW), \
         patch.object(cycle, "_scored_at", None), \
         patch("openoutfind.core.ml.qualifier.qualifier_for", return_value=qualifier), \
         patch.object(top_up, "discover", side_effect=search), \
         patch("openoutfind.discovery.embed_profile", return_value=np.zeros(2)), \
         patch("openoutfind.core.ml.qualifier.qualify_with_llm", side_effect=qualify), \
         patch("leadzen.ai.pinned_request", side_effect=AssertionError("No real provider permitted")), \
         patch("openoutfind.core.management.commands.find.ensure_database"), \
         patch("openoutfind.core.management.commands.find.check_ready"), \
         patch("openoutfind.core.management.commands.find.build_status", return_value={"next_action": {}}):
        with autopilot.execution(run):
            session = discover(run, new_source_after=baseline)

    assert len(searches) == (2 if familiar_page else 1)
    assert len(qualifications) == 1
    assert session.action["new_source_after"] == baseline
    assert all(not Deal.objects.filter(lead=lead).exists() for lead in old_unqualified)
    ready.refresh_from_db(); pending.refresh_from_db()
    assert ready.state == DealState.READY_TO_FIND_EMAIL
    assert pending.state == DealState.FINDING_EMAIL and pending.lookup_request_id == "old-paid-handle"
    assert not session.lookups.exists()
    assert not session.candidates.filter(source_id=incidental[0].pk).exists()
    result = session.candidates.get()
    assert result.discovered and result.evaluated and result.produced and result.outcome == "qualified"
    assert Lead.objects.get(pk=result.source_id).profile_url.endswith("today-search-result")
    assert result.contact_id
    session.run.refresh_from_db(); run.refresh_from_db()
    assert session.run.status == "succeeded" and run.model_requests == 1 and run.email_credits == 0


def test_plain_discovery_keeps_existing_backlog_available(connected):
    """The new-only policy is internal to Autopilot; manual discovery keeps its behavior."""
    from leadzen.config.models import ChatThread, ChatRun, DiscoverySession
    from leadzen.discovery_progress import Monitor
    from openoutfind.core.pipeline import qualify, top_up
    old = source("manual-existing-profile")
    thread = ChatThread.objects.create(actor_id=1)
    run = ChatRun.objects.create(thread=thread, actor_id=1, request_id=uuid.uuid4(), status="running")
    session = DiscoverySession.objects.create(run=run, action={"arguments": {}}, goal=1, unit="leads")
    monitor = Monitor(session)
    with monitor.adapters():
        assert old.pk in [lead.pk for lead in qualify.fetch_qualification_candidates()]
        assert old.pk in [lead.pk for lead in top_up.fetch_qualification_candidates()]


@pytest.mark.parametrize("prior_issue", ["", "An uncertain message needs review."])
def test_active_manual_task_is_visible_and_clears_only_its_own_warning(connected, prior_issue):
    from leadzen.config.models import ChatThread, ChatRun
    from leadzen.autopilot_worker import BUSY_ISSUE, checkpoint, workspace_tick
    p = policy()
    p.issue = prior_issue
    p.save(update_fields=["issue"])
    thread = ChatThread.objects.create(actor_id=p.actor_id)
    chat = ChatRun.objects.create(thread=thread, actor_id=p.actor_id, request_id=uuid.uuid4(), status="paused")
    with patch("django.utils.timezone.now", return_value=NOW), \
         patch("leadzen.web_worker._database_lock", return_value=nullcontext()), \
         patch("leadzen.mailboxes.prepare_worker_mailbox"), \
         patch("leadzen.workspaces.guard_worker_sends"), \
         patch("leadzen.autopilot_worker.deliver_due"), \
         patch("leadzen.autopilot_worker.prepare", side_effect=lambda run: checkpoint(run, "completed")) as prepare:
        workspace_tick()
        prepare.assert_not_called()
        assert not AutopilotRun.objects.exists()
        p.refresh_from_db(); chat.refresh_from_db()
        assert p.issue == (prior_issue or BUSY_ISSUE) and chat.status == "paused"
        chat.status = "cancelled"
        chat.save(update_fields=["status"])
        workspace_tick()
        assert prepare.call_count == 1
        p.refresh_from_db()
        assert p.issue == prior_issue


@pytest.mark.parametrize("when", [NOW.replace(hour=4), NOW + timedelta(days=5)])
def test_busy_warning_does_not_invent_a_scheduled_weekend_or_midnight_run(connected, when):
    from leadzen.config.models import ChatThread, ChatRun
    from leadzen.autopilot_worker import workspace_tick
    p = policy()
    thread = ChatThread.objects.create(actor_id=p.actor_id)
    ChatRun.objects.create(thread=thread, actor_id=p.actor_id, request_id=uuid.uuid4(), status="paused")
    with patch("django.utils.timezone.now", return_value=when), \
         patch("leadzen.web_worker._database_lock", return_value=nullcontext()), \
         patch("leadzen.mailboxes.prepare_worker_mailbox"), \
         patch("leadzen.workspaces.guard_worker_sends"), \
         patch("leadzen.autopilot_worker.deliver_due"), patch("leadzen.autopilot_worker.prepare") as prepare:
        workspace_tick()
        prepare.assert_not_called()
    p.refresh_from_db()
    assert not p.issue and not AutopilotRun.objects.exists()


def test_first_top_up_import_does_not_retain_finished_sessions_selection(connected):
    from leadzen.config.models import ChatThread, ChatRun, DiscoverySession
    from leadzen.discovery_progress import Monitor
    from openoutfind.core.pipeline import qualify
    original_qualification, original_candidates = qualify.run_qualification, qualify.fetch_qualification_candidates
    old = source("old-profile-after-autopilot")
    thread = ChatThread.objects.create(actor_id=1)
    run = ChatRun.objects.create(thread=thread, actor_id=1, request_id=uuid.uuid4(), status="running")
    session = DiscoverySession.objects.create(run=run, action={"arguments": {},
        "authorization": "autopilot", "new_source_after": old.pk}, goal=1, unit="leads")
    monitor = Monitor(session)
    name = "openoutfind.core.pipeline.top_up"
    with patch.dict(sys.modules):
        sys.modules.pop(name, None)
        with monitor.adapters():
            top_up = importlib.import_module(name)
            assert top_up.fetch_qualification_candidates() == []
        assert top_up.run_qualification is original_qualification
        assert top_up.fetch_qualification_candidates is original_candidates
        assert old.pk in [lead.pk for lead in top_up.fetch_qualification_candidates()]
