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


def test_job_threads_do_not_use_up_the_conversation_limit(connected):
    from leadzen.config.models import WORKSPACE_JOB
    owner = ChatThread.objects.get(pk=connected.post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]).actor_id
    ChatThread.objects.bulk_create([ChatThread(actor_id=owner, title=f"Find 1 leads {i}", context=dict(WORKSPACE_JOB)) for i in range(120)])
    assert connected.post("/api/chat/threads", data="{}", content_type="application/json").status_code == 201


def test_opening_a_job_transcript_does_not_make_it_the_last_chat(connected):
    from leadzen.config.models import WORKSPACE_JOB
    from leadzen.chat.context import structured
    talk = connected.post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]
    owner = ChatThread.objects.get(pk=talk).actor_id
    connected.get(f"/api/chat/threads/{talk}")
    job = ChatThread.objects.create(actor_id=owner, title="Check for replies", context=dict(WORKSPACE_JOB))
    assert connected.get(f"/api/chat/threads/{job.pk}").status_code == 200
    assert structured(owner).get("lastChatId") == talk


def test_existing_job_threads_are_marked_and_conversations_are_not(connected):
    import importlib
    from django.apps import apps
    from django.db import connection
    from leadzen.config.models import ChatMessage, conversations
    owner = ChatThread.objects.get(pk=connected.post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]).actor_id
    talk = ChatThread.objects.create(actor_id=owner, title="Plan my week")
    ChatMessage.objects.create(thread=talk, role="user", content="find 5 leads", data={"context": {}})
    jobs = []
    for title, data in (("Find 5 leads without email lookup", {"discovery": {"count": 5}}), ("Find emails for 2 selected leads", {"candidate_ids": [1, 2]}),
                        ("Work email for Ada", {"contact_id": 3}), ("Check for replies", {"workspace_action": "check_replies"}), ("Autopilot · 2026-10-12 · leads", None)):
        thread = ChatThread.objects.create(actor_id=owner, title=title)
        if data is not None:
            ChatMessage.objects.create(thread=thread, role="user", content=title, data=data)
        jobs.append(thread.pk)
    migration = importlib.import_module("leadzen.config.migrations.0022_mark_workspace_job_threads")
    migration.mark(apps, type("Editor", (), {"connection": connection})())
    visible = set(conversations(ChatThread.objects.filter(actor_id=owner)).values_list("pk", flat=True))
    assert talk.pk in visible and not visible & set(jobs)


def test_prepare_refuses_enrolled_leads_before_any_ai_call(connected):
    from test_campaigns import make
    contact = add(connected)
    make(connected, contact)
    with patch("leadzen.campaigns.write_initial_step") as writer:
        response = prepare(connected, [contact])
    assert response.status_code == 409 and "already enrolled" in response.json()["error"]
    writer.assert_not_called()
