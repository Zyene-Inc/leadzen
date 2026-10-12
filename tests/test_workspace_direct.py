"""Workspace buttons do their work directly and leave no Chat conversations."""
import json
from unittest.mock import patch

from test_campaigns import connected, add
from leadzen.campaigns import PreparedStep
from leadzen.config.models import ChatRun, ChatThread, EmailCampaign, SiteConfig


def prepare(client, ids):
    return client.post("/api/campaigns/prepare", data=json.dumps({"contact_ids": ids}), content_type="application/json")


def test_prepare_draft_writes_and_saves_without_chat(connected):
    contact = add(connected)
    SiteConfig.objects.update(product_docs="Synthetic review tool", campaign_target="Synthetic dentists", booking_link="https://example.com/book")
    step = PreparedStep(name="Dental review requests", subject="Quick question, {{first_name}}", body="Hi {{first_name}}, would {{company}} like more reviews? {{booking_link}}")
    with patch("leadzen.campaigns.write_initial_step", return_value=step) as writer, patch("cold_outreach.emails.sender._deliver") as deliver:
        response = prepare(connected, [contact])
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["status"] == "draft" and data["name"] == "Dental review requests"
    assert data["steps"] == [{"subject": "Quick question, {{first_name}}", "body": "Hi {{first_name}}, would {{company}} like more reviews? {{booking_link}}", "delay_days": 0}]
    assert data["booking_link"] == "https://example.com/book" and data["signature"] == ""
    assert [r["id"] for r in data["recipients"]] == [contact]
    writer.assert_called_once()
    deliver.assert_not_called()
    assert not ChatThread.objects.exists() and not ChatRun.objects.exists()


def test_prepare_draft_rejects_invalid_selection_before_any_ai_call(connected):
    contact = add(connected)
    with patch("leadzen.campaigns.write_initial_step") as writer:
        assert prepare(connected, []).status_code == 400
        assert prepare(connected, [contact, contact]).status_code == 400
        assert prepare(connected, [999999]).status_code == 404
    writer.assert_not_called()


def test_prepare_draft_failures_save_nothing(connected):
    contact = add(connected)
    with patch("leadzen.campaigns.write_initial_step", side_effect=TimeoutError):
        response = prepare(connected, [contact])
    assert response.status_code == 502 and "write the message yourself" in response.json()["error"]
    bad = PreparedStep(name="Bad", subject="Hi {{unknown_tag}}", body="Body")
    with patch("leadzen.campaigns.write_initial_step", return_value=bad):
        assert prepare(connected, [contact]).status_code == 502
    assert not EmailCampaign.objects.exists() and not ChatThread.objects.exists()


def test_workspace_job_threads_stay_out_of_the_chat_list(connected):
    from leadzen.config.models import WORKSPACE_JOB
    talk = connected.post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]
    owner = ChatThread.objects.get(pk=talk).actor_id
    ChatThread.objects.create(actor_id=owner, title="Find 5 leads without email lookup", context=dict(WORKSPACE_JOB))
    listed = [t["id"] for t in connected.get("/api/chat/threads").json()["items"]]
    assert listed == [talk]
