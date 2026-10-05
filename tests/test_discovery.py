"""Structured discovery choices must never be reinterpreted by the model."""
import uuid
from unittest.mock import patch

import pytest
from django.test import Client

from tests.test_chat import chat_client, post


@pytest.fixture
def discovery_client(chat_client):
    from leadzen.config.models import SiteConfig
    config = SiteConfig.load()
    config.product_docs, config.campaign_target = "Synthetic product", "Synthetic dentists in the US"
    config.operator_name, config.operator_email = "Synthetic operator", "operator@example.com"
    config.operator_country_code, config.accepted_legal_notice = "US", True
    config.save()
    return chat_client


def request_body(client, *, emails=False, count=3):
    return {"count": count, "emails": emails, "estimated_credits": count if emails else 0,
            "revision": client.get("/api/discovery").json()["revision"], "request_id": str(uuid.uuid4())}


def test_discovery_preview_is_read_only_and_has_no_credentials(discovery_client):
    from leadzen.config.models import ChatRun
    with patch("leadzen.chat.views.launch") as launch, patch("leadzen.chat.engine.find_leads") as finder, patch("leadzen.chat.engine.decide") as model:
        response = discovery_client.get("/api/discovery")
        assert response.status_code == 200
        assert response.json()["max_count"] == 25 and response.json()["ready"] is True
        assert response.json()["target"] == "Synthetic dentists in the US"
        assert "synthetic-secret" not in response.content.decode()
        launch.assert_not_called()
        finder.assert_not_called()
        model.assert_not_called()
        assert ChatRun.objects.count() == 0


@pytest.mark.parametrize("emails", [False, True])
def test_exact_choices_start_one_bounded_action_without_model_decision(discovery_client, emails):
    from leadzen.chat.engine import drive
    from leadzen.config.models import ChatRun
    body = request_body(discovery_client, emails=emails)
    with patch("leadzen.chat.views.launch") as launch:
        response = post(discovery_client, "/api/discovery", body)
        replay = post(discovery_client, "/api/discovery", body)
        assert response.status_code == replay.status_code == 202
        assert response.json()["thread_id"] == replay.json()["thread_id"]
        launch.assert_called_once()
    row = ChatRun.objects.get(pk=response.json()["run"]["id"])
    assert row.pending["approved"] is True and row.pending["single_action"] is True
    assert row.pending["arguments"] == {"count": 3, "emails": emails, "audience": ""}
    assert row.credits_reserved == (3 if emails else 0) and row.emails_reserved == 0
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 3, "partial": False}) as finder, patch("leadzen.chat.engine.decide") as model:
        drive(row.pk)
        drive(row.pk)
        finder.assert_called_once_with({"count": 3, "emails": emails, "audience": ""})
        model.assert_not_called()
    row.refresh_from_db()
    assert row.status == "succeeded"


@pytest.mark.parametrize("changes", [{"count": 0}, {"count": 26}, {"count": True}, {"count": 3.5}, {"emails": "false"}, {"estimated_credits": 3}, {"request_id": "bad"}])
def test_invalid_or_mismatched_choices_do_not_launch(discovery_client, changes):
    from leadzen.config.models import ChatRun
    body = {**request_body(discovery_client), **changes}
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, "/api/discovery", body).status_code == 400
        launch.assert_not_called()
    assert not ChatRun.objects.exists()


def test_changed_setup_and_request_reuse_cannot_change_authorized_budget(discovery_client):
    from leadzen.config.models import SiteConfig
    body = request_body(discovery_client)
    config = SiteConfig.load()
    config.campaign_target = "Changed synthetic target"
    config.save()
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, "/api/discovery", body).status_code == 409
        launch.assert_not_called()
        body = request_body(discovery_client)
        assert post(discovery_client, "/api/discovery", body).status_code == 202
        assert post(discovery_client, "/api/discovery", {**body, "emails": True, "estimated_credits": 3}).status_code == 409
        assert post(discovery_client, "/api/discovery", request_body(discovery_client)).status_code == 409
        launch.assert_called_once()


def test_discovery_requires_session_before_reading_configuration(discovery_client):
    with patch("leadzen.discovery.effective") as credentials, patch("leadzen.chat.views.launch") as launch:
        client = Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token")
        assert client.get("/api/discovery").status_code == 401
        assert post(client, "/api/discovery", {"count": 3}).status_code == 401
        credentials.assert_not_called()
        launch.assert_not_called()


def test_single_action_partial_result_stops_without_new_model_calls(discovery_client):
    from leadzen.chat.engine import drive
    from leadzen.config.models import ChatRun
    with patch("leadzen.chat.views.launch"):
        response = post(discovery_client, "/api/discovery", request_body(discovery_client))
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 1, "partial": True}), patch("leadzen.chat.engine.decide") as model:
        drive(response.json()["run"]["id"])
        model.assert_not_called()
    assert ChatRun.objects.get(pk=response.json()["run"]["id"]).status == "failed"


@pytest.mark.parametrize("setting", ["ai", "finder", "purpose"])
def test_incomplete_setup_blocks_even_free_discovery(discovery_client, setting):
    from leadzen.config.models import SiteConfig
    from leadzen.configuration import save_dashboard_settings
    if setting == "ai":
        save_dashboard_settings({"ai_enabled": False})
    elif setting == "finder":
        save_dashboard_settings({}, clear_bettercontact_api_key=True)
    else:
        config = SiteConfig.load()
        config.campaign_target = ""
        config.save()
    setup = discovery_client.get("/api/discovery").json()
    assert setup["ready"] is False and setup["blockers"]
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, "/api/discovery", request_body(discovery_client)).status_code == 409
        launch.assert_not_called()


def test_discovery_shares_chat_rate_limit(discovery_client):
    from django.contrib.auth import get_user_model
    from leadzen.config.models import ChatRun, ChatThread
    actor = get_user_model().objects.get(email="unit@example.com")
    thread = ChatThread.objects.create(actor_id=actor.pk)
    for _ in range(15):
        ChatRun.objects.create(thread=thread, actor_id=actor.pk, request_id=uuid.uuid4(), status="succeeded")
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, "/api/discovery", request_body(discovery_client)).status_code == 429
        launch.assert_not_called()
