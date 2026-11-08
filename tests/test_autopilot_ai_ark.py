"""Daily Autopilot with AI Ark: the standing credit limits replace per-run approval."""
import json
from datetime import timedelta
from unittest.mock import patch

import numpy as np
import pytest

from leadzen import autopilot
from leadzen.autopilot_worker import discover
from leadzen.config.models import AutopilotRun, DiscoverySearch
from tests.test_chat import chat_client  # noqa: F401
from tests.test_discovery import discovery_client  # noqa: F401
from tests.test_ai_ark import ark_client, person  # noqa: F401
from tests.test_autopilot import NOW, enable_service, policy  # noqa: F401


def scheduled(**scope):
    p = policy(**scope)
    return AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(),
        checkpoint={"contact_limit": 1}, deadline_at=NOW + timedelta(minutes=12))


def search_once(run, reply):
    with patch("django.utils.timezone.now", return_value=NOW), \
         patch("leadzen.ai.pinned_request", return_value=reply) as network, \
         patch("openoutfind.discovery.embed_profile", return_value=np.zeros(384)), \
         patch("openoutfind.core.ml.qualifier.qualify_with_llm", return_value=(1, "Matches saved target")), \
         autopilot.execution(run):
        try:
            session = discover(run)
        except PermissionError:
            session = None
    return session, network


def test_setup_no_longer_blocks_ai_ark(ark_client):
    assert not any("AI Ark" in b for b in autopilot.setup(1)["blockers"])


def test_daily_ai_ark_search_spends_only_reserved_policy_credits(ark_client, enable_service):
    run = scheduled(daily_credits=4)
    session, network = search_once(run, (200, {}, json.dumps({"content": [person()]}).encode()))
    network.assert_called_once()
    assert network.call_args.args[1].endswith("/v1/people")
    assert session.action["provider"] == "ai_ark" and session.action["credits"] == 1
    assert "approved" not in session.action
    run.refresh_from_db()
    # Search page of 2 profiles = 1 credit, reserved before purchase.
    assert run.email_credits == 1
    assert DiscoverySearch.objects.get(session=session).size == 2
    assert session.candidates.filter(produced=True).count() == 1


def test_exhausted_daily_credits_never_reach_ai_ark(ark_client, enable_service):
    run = scheduled(daily_credits=1)
    AutopilotRun.objects.filter(pk=run.pk).update(email_credits=1)
    run.refresh_from_db()
    _, network = search_once(run, (200, {}, json.dumps({"content": [person()]}).encode()))
    network.assert_not_called()
    assert not DiscoverySearch.objects.exists()


def test_autopilot_authorization_is_void_outside_its_scheduled_run(ark_client, enable_service):
    from leadzen.ai_ark import authorize
    from leadzen.config.models import ChatRun, ChatThread, DiscoverySession
    from leadzen.discovery_progress import Monitor
    import uuid
    run = scheduled()
    thread = ChatThread.objects.create(actor_id=1)
    row = ChatRun.objects.create(thread=thread, actor_id=1, request_id=uuid.uuid4(), status="running", deadline_at=NOW + timedelta(minutes=10))
    session = DiscoverySession.objects.create(run=row, goal=1, unit="leads", action={
        "arguments": {"count": 1, "emails": False, "audience": ""}, "authorization": "autopilot",
        "policy_id": str(run.policy_id), "provider": "ai_ark", "credits": 1})
    with patch("django.utils.timezone.now", return_value=NOW), patch.object(Monitor, "boundary"):
        with pytest.raises(PermissionError):
            authorize(Monitor(session))
        other = policy(actor=2)
        with autopilot.execution(run):
            session.action["policy_id"] = str(other.pk)
            with pytest.raises(PermissionError):
                authorize(Monitor(session))


def test_ai_ark_day_is_sized_to_two_credits_per_contact(ark_client):
    p = policy(daily_credits=10, daily_contacts=10)
    assert autopilot.ai_ark_contact_limit(p, 10) == 5
    p.scope["daily_credits"] = 1
    assert autopilot.ai_ark_contact_limit(p, 10) == 0
    p.scope["daily_credits"] = 25
    assert autopilot.ai_ark_contact_limit(p, 25) == 12


def test_multi_credit_reservation_respects_daily_limit(ark_client, enable_service):
    run = scheduled(daily_credits=3)
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.execution(run):
        autopilot.external_guard(reserve_credit=True, credits=2)
        with pytest.raises(PermissionError):
            autopilot.external_guard(reserve_credit=True, credits=2)
        autopilot.external_guard(reserve_credit=True)
    run.refresh_from_db()
    assert run.email_credits == 3
