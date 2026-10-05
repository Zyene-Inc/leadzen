"""Employee flow regressions: one send boundary, stored attention, inline inbox approval."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.http import JsonResponse
from django.utils import timezone

from tests.test_chat import chat_client, post
from tests.test_campaigns import connected, add, make
from leadzen.config.models import ChatRun, EmailCampaign, OutreachJob


def queued(request, job):
    return JsonResponse({"job": {"id": str(job.pk)}}, status=202)


def test_opening_review_never_activates_but_final_confirmation_does(connected):
    campaign_id = make(connected, add(connected))
    preview = connected.get(f"/api/campaigns/{campaign_id}/preview?count=1").json()
    assert EmailCampaign.objects.get(pk=campaign_id).status == "draft"
    assert not OutreachJob.objects.exists()
    request = {"count": 1, "revision": preview["revision"], "request_id": str(uuid.uuid4()), "automatic_followups": False}
    with patch("leadzen.web._launch_job", side_effect=queued):
        response = post(connected, f"/api/campaigns/{campaign_id}/run", request)
        assert response.status_code == 202, response.content
        assert post(connected, f"/api/campaigns/{campaign_id}/run", request).status_code == 202
    assert OutreachJob.objects.count() == 1
    assert EmailCampaign.objects.get(pk=campaign_id).status == "active"
    assert not EmailCampaign.objects.get(pk=campaign_id).followup_approval
    from leadzen.chat.engine import snapshot
    job = OutreachJob.objects.get()
    assert job.campaign_approval["snapshot"] == snapshot("send_campaign", {"campaign_id": campaign_id, "recipient_ids": job.campaign_approval["recipient_ids"]}, execution=True)


def test_stale_review_cannot_activate_or_create_job(connected):
    campaign_id = make(connected, add(connected))
    preview = connected.get(f"/api/campaigns/{campaign_id}/preview?count=1").json()
    EmailCampaign.objects.filter(pk=campaign_id).update(name="Changed after review")
    with patch("leadzen.web._launch_job") as launch:
        result = post(connected, f"/api/campaigns/{campaign_id}/run", {"count": 1, "revision": preview["revision"], "request_id": str(uuid.uuid4())})
    assert result.status_code == 409
    launch.assert_not_called()
    assert EmailCampaign.objects.get(pk=campaign_id).status == "draft"
    assert not OutreachJob.objects.exists()


def test_resume_does_not_restore_old_automatic_approval(connected):
    campaign_id = make(connected, add(connected))
    EmailCampaign.objects.filter(pk=campaign_id).update(status="paused", followup_approval={"recipients": ["old"]})
    preview = connected.get(f"/api/campaigns/{campaign_id}/preview?count=1").json()
    assert EmailCampaign.objects.get(pk=campaign_id).status == "paused"
    with patch("leadzen.web._launch_job", side_effect=queued):
        result = post(connected, f"/api/campaigns/{campaign_id}/run", {"count": 1, "revision": preview["revision"], "request_id": str(uuid.uuid4()), "automatic_followups": False})
    assert result.status_code == 202, result.content
    assert EmailCampaign.objects.get(pk=campaign_id).followup_approval == {}


def test_inline_inbox_preparation_is_inert_idempotent_and_decline_cancels(chat_client):
    request = {"request_id": str(uuid.uuid4())}
    with patch("leadzen.chat.views.launch") as launch:
        response = post(chat_client, "/api/inbox/check", request)
        assert response.status_code == 201, response.content
        run = response.json()["run"]
        again = post(chat_client, "/api/inbox/check", request)
        assert again.json()["run"]["id"] == run["id"]
        assert run["status"] == "awaiting_approval"
        assert post(chat_client, f"/api/chat/runs/{run['id']}/approval", {"action_id": run["approval"]["id"], "approved": False}).status_code == 200
        launch.assert_not_called()
    assert ChatRun.objects.get().status == "cancelled"


def test_inline_inbox_approval_is_one_action_and_never_calls_agent_after_sync(chat_client):
    run = post(chat_client, "/api/inbox/check", {"request_id": str(uuid.uuid4())}).json()["run"]
    with patch("leadzen.chat.views.launch"):
        response = post(chat_client, f"/api/chat/runs/{run['id']}/approval", {"action_id": run["approval"]["id"], "approved": True})
        assert response.status_code == 202, response.content
    from leadzen.chat.engine import drive
    with patch("leadzen.chat.engine.perform", return_value={"synced": True}) as perform, patch("leadzen.chat.engine.decide") as model:
        drive(run["id"])
        drive(run["id"])
    perform.assert_called_once()
    assert perform.call_args.args[1] == "sync_mailbox"
    model.assert_not_called()
    assert ChatRun.objects.get().status == "succeeded"


def test_inline_expired_approval_cannot_launch(chat_client):
    run = post(chat_client, "/api/inbox/check", {"request_id": str(uuid.uuid4())}).json()["run"]
    ChatRun.objects.filter(pk=run["id"]).update(approval_expires_at=timezone.now() - timedelta(seconds=1))
    with patch("leadzen.chat.views.launch") as launch:
        response = post(chat_client, f"/api/chat/runs/{run['id']}/approval", {"action_id": run["approval"]["id"], "approved": True})
    assert response.status_code == 409
    launch.assert_not_called()


def test_attention_reads_saved_drafts_without_external_calls(connected):
    campaign_id = make(connected, add(connected))
    with patch("leadzen.chat.views.launch") as launch:
        response = connected.get("/api/attention")
    assert response.status_code == 200, response.content
    assert response.json()["items"][0]["href"] == f"/outreach?campaign={campaign_id}"
    launch.assert_not_called()


def test_outreach_context_is_allowed_external_paths_are_not(chat_client):
    assert chat_client.put("/api/chat/context", '{"workspacePath":"/outreach"}', content_type="application/json").status_code == 200
    assert chat_client.put("/api/chat/context", '{"workspacePath":"https://attacker.example/outreach"}', content_type="application/json").status_code == 400


def test_attention_excludes_already_answered_human_replies(connected):
    from cold_outreach.emails.models import Mailbox, Thread, Message
    box = Mailbox.objects.first()
    thread = Thread.objects.create(mailbox=box)
    incoming = Message.objects.create(mailbox=box, thread=thread, direction="in", kind="human_reply", message_id="attention-incoming", from_address="person@example.com", to_address=box.from_address, subject="A question")
    items = connected.get("/api/attention").json()["items"]
    assert any(item["id"] == f"reply-{thread.pk}" for item in items)
    outbound = Message.objects.create(mailbox=box, thread=thread, direction="out", kind="outbound", message_id="attention-reply", from_address=box.from_address, to_address=incoming.from_address, subject="Our answer")
    assert any(item["id"] == f"reply-{thread.pk}" for item in connected.get("/api/attention").json()["items"])
    from cold_outreach.emails.models import DeliveryEvent
    DeliveryEvent.objects.create(message=outbound, status="accepted")
    items = connected.get("/api/attention").json()["items"]
    assert not any(item["id"] == f"reply-{thread.pk}" for item in items)


def test_inbox_check_request_cannot_replay_another_actor_run(chat_client):
    request = {"request_id": str(uuid.uuid4())}
    assert post(chat_client, "/api/inbox/check", request).status_code == 201
    ChatRun.objects.update(actor_id=9999)
    assert post(chat_client, "/api/inbox/check", request).status_code == 409


def test_workspace_actions_require_employee_session(db, monkeypatch):
    from django.test import Client
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    client = Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token")
    assert client.get("/api/attention").status_code == 401
    assert post(client, "/api/inbox/check", {"request_id": str(uuid.uuid4())}).status_code == 401


def test_inline_pending_check_restores_after_reload_without_provider_access(chat_client):
    assert chat_client.get("/api/inbox/check").json() == {"check": None}
    run = post(chat_client, "/api/inbox/check", {"request_id": str(uuid.uuid4())}).json()["run"]
    with patch("leadzen.chat.views.launch") as launch:
        restored = chat_client.get("/api/inbox/check").json()["check"]
    assert restored["run"]["id"] == run["id"]
    assert restored["run"]["approval"]["id"] == run["approval"]["id"]
    launch.assert_not_called()
    post(chat_client, f"/api/chat/runs/{run['id']}/approval", {"action_id": run["approval"]["id"], "approved": False})
    assert chat_client.get("/api/inbox/check").json() == {"check": None}
