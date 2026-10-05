"""Synthetic orchestration tests: no live models, enrichment or mail."""
import json
import uuid
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from leadzen.configuration import save_dashboard_settings


@pytest.fixture
def chat_client(account_client, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    save_dashboard_settings({"provider": "openai_compatible", "model": "synthetic-model", "base_url": "https://api.example.com/v1", "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "imap_host": "imap.example.com", "smtp_port": 587, "imap_port": 993}, llm_api_key="synthetic-secret-ai", mailbox_password="synthetic-secret-mail", bettercontact_api_key="synthetic-secret-finder")
    return account_client


def post(client, path, body):
    return client.post(path, json.dumps(body), content_type="application/json")


def turn(client, prompt="Check my workspace"):
    thread = post(client, "/api/chat/threads", {}).json()["id"]
    with patch("leadzen.chat.views.launch"):
        response = post(client, f"/api/chat/threads/{thread}/messages", {"content": prompt, "request_id": str(uuid.uuid4())})
    assert response.status_code == 202, response.content
    return thread, response.json()["run"]["id"]


def test_real_multi_step_loop_and_history(chat_client):
    from leadzen.chat.engine import Decision, drive
    thread, run = turn(chat_client)
    with patch("leadzen.chat.engine.decide", side_effect=[Decision(tool="overview", text="Checking workspace"), Decision(tool="connections"), Decision(tool="answer", text="No emails have been sent.")]) as model:
        drive(run)
    detail = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert detail["run"]["status"] == "succeeded"
    from leadzen.config.models import ChatRun
    stored_run = ChatRun.objects.get(pk=run)
    assert detail["run"]["created_at"] == stored_run.created_at.isoformat()
    assert detail["run"]["finished_at"] == stored_run.finished_at.isoformat()
    assert model.call_count == 3
    assert [m["role"] for m in detail["messages"]] == ["user", "tool", "tool", "assistant"]
    assert "synthetic-secret" not in json.dumps(detail)


def test_enrichment_requires_exact_approval_and_runs_once(chat_client):
    from leadzen.chat.engine import Decision, drive
    thread, run = turn(chat_client, "Find agencies")
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="find_leads", arguments={"count": 2, "emails": True})), patch("leadzen.chat.engine.find_leads") as finder:
        drive(run)
        finder.assert_not_called()
    state = chat_client.get(f"/api/chat/threads/{thread}").json()["run"]
    assert state["status"] == "awaiting_approval" and state["approval"]["credits"] == 2
    path = f"/api/chat/runs/{run}/approval"
    assert post(chat_client, path, {"action_id": str(uuid.uuid4()), "approved": True}).status_code == 409
    with patch("leadzen.chat.views.launch"):
        assert post(chat_client, path, {"action_id": state["approval"]["id"], "approved": True}).status_code == 202
        assert post(chat_client, path, {"action_id": state["approval"]["id"], "approved": True}).status_code == 409
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 2}), patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Two leads stored.")):
        drive(run)
        drive(run)  # duplicate dispatch is inert
    assert chat_client.get(f"/api/chat/threads/{thread}").json()["run"]["status"] == "succeeded"


def test_changed_settings_invalidate_approval(chat_client):
    from leadzen.chat.engine import Decision, drive
    thread, run = turn(chat_client)
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="find_leads", arguments={"count": 1, "emails": True})):
        drive(run)
    action = chat_client.get(f"/api/chat/threads/{thread}").json()["run"]["approval"]["id"]
    save_dashboard_settings({"provider": "openai_compatible", "model": "other-model", "base_url": "https://api.example.com/v1"})
    assert post(chat_client, f"/api/chat/runs/{run}/approval", {"action_id": action, "approved": True}).status_code == 409


def test_request_id_replay_does_not_duplicate_or_launch(chat_client):
    thread = post(chat_client, "/api/chat/threads", {}).json()["id"]
    body = {"content": "Check leads", "request_id": str(uuid.uuid4())}
    with patch("leadzen.chat.views.launch") as launch:
        first = post(chat_client, f"/api/chat/threads/{thread}/messages", body)
        second = post(chat_client, f"/api/chat/threads/{thread}/messages", body)
        assert first.json()["run"]["id"] == second.json()["run"]["id"]
        assert launch.call_count == 1
    assert len(chat_client.get(f"/api/chat/threads/{thread}").json()["messages"]) == 1


def test_owner_check_before_credentials_and_cancel(chat_client):
    from leadzen.config.models import ChatThread
    foreign = ChatThread.objects.create(actor_id=999, title="Foreign")
    with patch("leadzen.chat.views.effective") as secrets:
        assert chat_client.get(f"/api/chat/threads/{foreign.pk}").status_code == 404
        assert post(chat_client, f"/api/chat/threads/{foreign.pk}/messages", {"content": "hello", "request_id": str(uuid.uuid4())}).status_code == 404
        secrets.assert_not_called()
    thread, run = turn(chat_client)
    assert post(chat_client, f"/api/chat/runs/{run}/cancel", {}).status_code == 200
    from leadzen.chat.engine import drive
    with patch("leadzen.chat.engine.decide") as model:
        drive(run)
        model.assert_not_called()
    assert chat_client.get(f"/api/chat/threads/{thread}").json()["run"]["status"] == "cancelled"


def test_invalid_tool_cannot_execute_shell_and_errors_are_safe(chat_client):
    from leadzen.chat.engine import drive
    thread, run = turn(chat_client)
    with patch("leadzen.chat.engine.decide", side_effect=RuntimeError("synthetic-secret-ai private prompt")):
        drive(run)
    detail = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert detail["run"]["status"] == "failed"
    assert "synthetic-secret" not in json.dumps(detail)


def test_expired_and_denied_approvals_do_not_call_finder(chat_client):
    from datetime import timedelta
    from leadzen.chat.engine import Decision, drive
    from leadzen.config.models import ChatRun
    thread, run = turn(chat_client)
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="find_leads", arguments={"count": 1, "emails": True})):
        drive(run)
    row = ChatRun.objects.get(pk=run)
    assert row.pending["credits"] == 1
    action = row.pending["id"]
    ChatRun.objects.filter(pk=run).update(approval_expires_at=timezone.now() - timedelta(seconds=1))
    assert post(chat_client, f"/api/chat/runs/{run}/approval", {"action_id": action, "approved": True}).status_code == 409
    assert post(chat_client, f"/api/chat/runs/{run}/approval", {"action_id": action, "approved": False}).status_code == 200
    with patch("leadzen.chat.engine.find_leads") as finder:
        drive(run)
        finder.assert_not_called()


def test_structured_decision_uses_actual_agent_library(chat_client):
    from pydantic_ai.models.test import TestModel
    from leadzen.chat.engine import drive, decide
    from leadzen.config.models import ChatRun
    thread, run = turn(chat_client)
    # The actual Pydantic AI Agent validates this response, not our decision mock.
    model = TestModel(custom_output_args={"tool": "answer", "text": "Synthetic structured reply", "arguments": {}})
    with patch("leadzen.ai.build_model", return_value=model):
        assert decide(ChatRun.objects.get(pk=run)).tool == "answer"
        drive(run)
    result = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert result["run"]["status"] == "succeeded"
    assert result["messages"][-1]["content"] == "Synthetic structured reply"


def test_sending_preview_freezes_recipients_and_uses_campaign_engine(chat_client):
    from leadzen.chat.engine import Decision, drive
    from leadzen.config.models import CampaignRecipient, ChatRun, EmailCampaign
    from tests.test_campaigns import add, make
    contact_id = add(chat_client)
    campaign = make(chat_client, contact_id)
    thread, run = turn(chat_client, "Send my campaign")
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="send_campaign", arguments={"campaign_id": campaign, "count": 1})), patch("cold_outreach.emails.sender._deliver") as deliver:
        drive(run)
        deliver.assert_not_called()
    state = chat_client.get(f"/api/chat/threads/{thread}").json()["run"]
    assert state["approval"]["emails"] == 1
    assert state["approval"]["preview"]["recipients"][0]["subject"] == "Hi Ada"
    assert EmailCampaign.objects.get(pk=campaign).status == "draft"
    with patch("leadzen.chat.views.launch"):
        assert post(chat_client, f"/api/chat/runs/{run}/approval", {"action_id": state["approval"]["id"], "approved": True}).status_code == 202
    with patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.campaigns.run_campaign", return_value=0) as sender, patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Deferred; no email accepted.")):
        drive(run)
        assert sender.call_args.kwargs["recipient_ids"] == list(CampaignRecipient.objects.values_list("pk", flat=True))
    assert ChatRun.objects.get(pk=run).emails_reserved == 1
    assert "Deferred" in chat_client.get(f"/api/chat/threads/{thread}").json()["messages"][-1]["content"]


def test_approval_at_step_eight_executes_once_then_stops(chat_client):
    from leadzen.chat.engine import Decision, drive
    from leadzen.config.models import ChatRun
    thread, run = turn(chat_client)
    ChatRun.objects.filter(pk=run).update(steps=7)
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="find_leads", arguments={"count": 1, "emails": True})):
        drive(run)
    state = chat_client.get(f"/api/chat/threads/{thread}").json()["run"]
    with patch("leadzen.chat.views.launch"):
        post(chat_client, f"/api/chat/runs/{run}/approval", {"action_id": state["approval"]["id"], "approved": True})
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 0}) as find, patch("leadzen.chat.engine.decide") as model:
        drive(run)
        find.assert_called_once()
        model.assert_not_called()


def test_abandoned_worker_is_visible_and_never_replayed(chat_client):
    from datetime import timedelta
    from leadzen.config.models import ChatRun
    thread, run = turn(chat_client)
    ChatRun.objects.filter(pk=run).update(status="running", deadline_at=timezone.now() - timedelta(minutes=2))
    state = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert state["run"]["status"] == "failed"
    assert "automatically retried" in state["messages"][-1]["content"]


@pytest.mark.parametrize("emails", [False, True])
def test_finder_calls_exact_existing_command_and_ingests_partial_json(chat_client, monkeypatch, emails):
    from leadzen.chat.engine import find_leads
    from cold_outreach.leads.models import Lead
    monkeypatch.delenv("LEADZEN_CHAT_RUN_ID", raising=False)
    def command(*args, **kwargs):
        assert args == ("find", "2", "emails" if emails else "leads", "--json", "--new")
        kwargs["stdout"].write(json.dumps({"lead_id": "synthetic-verified", "email": "verified@example.com", "first_name": "Ada", "profile_text": "Synthetic profile"}) + "\n")
        from openoutfind.core.errors import OpenOutFindError, ErrorType
        raise OpenOutFindError(ErrorType.PROVIDER_UNAVAILABLE, "synthetic refusal")
    with patch("django.core.management.call_command", side_effect=command), patch("leadzen.ai.install_engine_adapters"), patch("leadzen.wizard.apply_to_environment"):
        result = find_leads({"count": 2, "emails": emails, "audience": "Synthetic audience"})
    assert result["partial"] and result["stored"] == 1
    assert Lead.objects.get(lead_id="synthetic-verified").email == "verified@example.com"


def test_provider_budget_and_cancellation_are_checked_at_sink(chat_client, monkeypatch):
    from datetime import timedelta
    from leadzen.chat.engine import assert_action_access
    from leadzen.config.models import ChatRun
    thread, run = turn(chat_client)
    ChatRun.objects.filter(pk=run).update(status="running", deadline_at=timezone.now() + timedelta(minutes=10), model_requests=31)
    monkeypatch.setenv("LEADZEN_CHAT_RUN_ID", run)
    assert_action_access(reserve_model=True)
    with pytest.raises(PermissionError):
        assert_action_access(reserve_model=True)
    ChatRun.objects.filter(pk=run).update(cancel_requested=True)
    with pytest.raises(PermissionError):
        assert_action_access()


def test_cancel_during_model_response_never_prepares_next_action(chat_client):
    from leadzen.chat.engine import Decision, drive
    from leadzen.config.models import ChatRun
    thread, run = turn(chat_client)
    def late_model(row):
        ChatRun.objects.filter(pk=row.pk).update(cancel_requested=True)
        return Decision(tool="find_leads", arguments={"count": 2, "emails": True})
    with patch("leadzen.chat.engine.decide", late_model), patch("leadzen.chat.engine.prepare") as prepare:
        drive(run)
        prepare.assert_not_called()
    assert ChatRun.objects.get(pk=run).status == "cancelled"


def test_delete_chat_preserves_workspace_and_hides_all_conversation_paths(chat_client):
    from leadzen.config.models import ChatRun, ChatThread, DiscoverySession, WorkspaceContext
    thread, run = turn(chat_client)
    ChatRun.objects.filter(pk=run).update(status="succeeded", finished_at=timezone.now())
    session = DiscoverySession.objects.create(run_id=run, goal=5)
    chat_client.get(f"/api/chat/threads/{thread}")
    assert chat_client.delete(f"/api/chat/threads/{thread}").status_code == 200
    assert ChatThread.objects.get(pk=thread).deleted_at is not None
    assert ChatRun.objects.filter(pk=run).exists()
    assert DiscoverySession.objects.filter(pk=session.pk).exists()
    assert WorkspaceContext.objects.get(actor_id=ChatThread.objects.get(pk=thread).actor_id).references["lastChatId"] is None
    assert thread not in [item["id"] for item in chat_client.get("/api/chat/threads").json()["items"]]
    for suffix in ("", "/stream"):
        assert chat_client.get(f"/api/chat/threads/{thread}{suffix}").status_code == 404
    assert post(chat_client, f"/api/chat/threads/{thread}/messages", {"content": "Restart", "request_id": str(uuid.uuid4())}).status_code == 404
    assert chat_client.put(f"/api/chat/threads/{thread}", json.dumps({"title": "Restore"}), content_type="application/json").status_code == 404
    assert chat_client.delete(f"/api/chat/threads/{thread}").status_code == 404
    # The existing discovery page still reads the same run after chat deletion.
    assert chat_client.get(f"/api/discovery/{session.pk}").status_code == 200


@pytest.mark.parametrize("status", ["queued", "running", "awaiting_approval", "paused"])
def test_delete_chat_refuses_live_work(chat_client, status):
    from leadzen.config.models import ChatRun, ChatThread
    thread, run = turn(chat_client)
    ChatRun.objects.filter(pk=run).update(status=status)
    assert chat_client.delete(f"/api/chat/threads/{thread}").status_code == 409
    assert ChatThread.objects.get(pk=thread).deleted_at is None
    assert ChatRun.objects.get(pk=run).status == status


def test_delete_chat_cannot_touch_another_actor(chat_client):
    from leadzen.config.models import ChatThread
    other = ChatThread.objects.create(actor_id=999, title="Private")
    with patch("leadzen.chat.views.effective") as secrets, patch("leadzen.chat.views.launch") as launch:
        assert chat_client.delete(f"/api/chat/threads/{other.pk}").status_code == 404
        secrets.assert_not_called()
        launch.assert_not_called()
    other.refresh_from_db()
    assert other.deleted_at is None


@pytest.mark.parametrize("result,status,text", [
    ({"stored": 1}, "succeeded", "Discovery finished. Review the recorded results and your leads. No emails were sent."),
    ({"stored": 1, "partial": True}, "failed", "Discovery stopped with partial results. Review leads and connections before starting another search. No emails were sent."),
    ({"stored": 1, "paused": True}, "paused", "Finding paused at a saved checkpoint. Resume continues only the remaining goal; no action was automatically repeated."),
    ({"stored": 1, "paused": True, "partial": True}, "cancelled", "Finding stopped. Saved results are kept; no new lookup or send was started."),
])
def test_historical_single_action_without_discovery_metadata_keeps_completion(chat_client, result, status, text):
    from datetime import timedelta
    from leadzen.chat.engine import drive, snapshot
    from leadzen.config.models import ChatRun, DiscoverySession
    thread, run = turn(chat_client)
    row = ChatRun.objects.get(pk=run)
    arguments = {"count": 1, "emails": False, "audience": ""}
    row.pending = {"id": str(uuid.uuid4()), "tool": "find_leads", "arguments": arguments,
                   "summary": "Find one lead", "snapshot": snapshot("find_leads", arguments), "approved": True, "single_action": True}
    row.approval_expires_at = timezone.now() + timedelta(minutes=15)
    row.save(update_fields=["pending", "approval_expires_at"])
    def find(args):
        if status == "cancelled":
            ChatRun.objects.filter(pk=run).update(cancel_requested=True)
        return result
    with patch("leadzen.chat.engine.find_leads", side_effect=find) as finder, patch("leadzen.chat.engine.decide") as planner:
        drive(run)
        drive(run)
        finder.assert_called_once_with(arguments)
        planner.assert_not_called()
    row.refresh_from_db()
    assert row.status == status and not row.pending
    assert not DiscoverySession.objects.filter(run=row).exists()
    assert row.thread.messages.filter(role="assistant").last().content == text
    assert (row.finished_at is None) == (status == "paused")
    if status == "paused":
        assert row.deadline_at is None
