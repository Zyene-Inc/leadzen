"""Two interfaces, one canonical state. All providers are synthetic."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from django.test import Client

from tests.test_chat import chat_client, post, turn
from tests.test_discovery import discovery_client
from tests.test_reviewed_outreach import connected, person, synthetic_generate, accepted
from leadzen.chat.engine import Decision, drive, normalize, execute
from leadzen.config.models import ChatRun, ChatThread, ReviewedEmail, EmailReview, WorkspaceContext, DiscoverySession


@pytest.fixture(autouse=True, params=range(10))
def repetition(request):
    """Repeat every new behavior/negative case ten times with fresh isolated state."""
    return request.param


def tool_turn(client, tool, args, prompt="Inspect my Workspace"):
    thread, run = turn(client, prompt)
    with patch("leadzen.chat.engine.decide", side_effect=[Decision(tool=tool, arguments=args), Decision(tool="answer", text="Review the actual results above.")]):
        drive(run)
    row = ChatRun.objects.get(pk=run)
    return thread, row


def result(thread):
    return ChatThread.objects.get(pk=thread).messages.filter(role="tool").last().data["result"]


def saved_draft(client, deals):
    with patch("leadzen.outreach.generate", side_effect=synthetic_generate):
        thread, run = tool_turn(client, "create_drafts", {"leadIds": [d.pk for d in deals]}, "Draft for these selected leads. Do not send.")
    assert run.status == "succeeded", result(thread)
    return result(thread)


def approval(client, run):
    state = client.get(f"/api/chat/runs/{run.pk}").json()
    with patch("leadzen.chat.views.launch"):
        response = post(client, f"/api/chat/runs/{run.pk}/approval", {"approved": True, "action_id": state["approval"]["id"]})
    assert response.status_code == 202, response.content
    return state["approval"]["id"]


def test_selected_leads_and_current_record_are_server_context(discovery_client):
    a, b, c = person("a@example.com"), person("b@example.com"), person("c@example.com")
    refs = {"selectedLeadIds": [a.pk, b.pk, c.pk], "currentLeadId": b.pk, "workspacePath": f"/contacts/{b.pk}"}
    response = discovery_client.put("/api/chat/context", json.dumps(refs), content_type="application/json")
    assert response.status_code == 200
    context = response.json()
    assert context["selectedLeadIds"] == [a.pk, b.pk, c.pk]
    assert len(context["referencedLeads"]) == 3
    assert "synthetic-secret" not in json.dumps(context)
    thread, run = turn(discovery_client, "Draft emails for these three")
    assert ChatThread.objects.get(pk=thread).context["selectedLeadIds"] == refs["selectedLeadIds"]
    assert WorkspaceContext.objects.get().references["currentLeadId"] == b.pk


@pytest.mark.parametrize("refs", [{"currentLeadId": True}, {"selectedLeadIds": [1, 1]}, {"workspacePath": "https://evil.example"}, {"workspacePath": "//evil.example"}, {"currentDraftId": "bad"}, {"workspaceId": "foreign"}])
def test_context_rejects_forged_or_noncanonical_references(discovery_client, refs):
    with patch("leadzen.chat.views.launch") as launch:
        response = discovery_client.put("/api/chat/context", json.dumps(refs), content_type="application/json")
    assert response.status_code == 400
    assert not WorkspaceContext.objects.exists()
    launch.assert_not_called()


@pytest.mark.parametrize("suffix,allowed", [("", True), ("&other=1", False), ("&review=duplicate", False), ("#fragment", False)])
def test_reply_review_return_path_stays_bounded(discovery_client, suffix, allowed):
    path = f"/inbox?thread=4&review={uuid.uuid4()}{suffix}"
    response = discovery_client.put("/api/chat/context", json.dumps({"workspacePath": path}), content_type="application/json")
    assert response.status_code == (200 if allowed else 400)
    if allowed:
        assert response.json()["workspacePath"] == path


def test_saved_reply_exposes_its_canonical_conversation_for_restoration(connected):
    from tests.test_reviewed_outreach import conversation, review
    from cold_outreach.emails.models import Message
    thread, _ = conversation(person())
    before = Message.objects.count()
    data = review(connected, thread_id=thread.pk)
    assert data["thread_id"] == thread.pk
    assert connected.get(f"/api/outreach/reviews/{data['id']}").json()["thread_id"] == thread.pk
    assert Message.objects.count() == before


def test_foreign_draft_and_thread_are_unavailable_before_generation(discovery_client):
    foreign = EmailReview.objects.create(actor_id=999, request_id=uuid.uuid4(), from_address="foreign@example.com", requested_count=1, context_hash="", status="draft")
    d = ReviewedEmail.objects.create(review=foreign, deal=person())
    with patch("leadzen.outreach.generate") as generate:
        thread, row = tool_turn(discovery_client, "get_draft", {"draftId": str(d.pk)})
    assert "not found" in result(thread)["error"]
    generate.assert_not_called()
    refs = {"currentDraftId": str(d.pk)}
    assert discovery_client.put("/api/chat/context", json.dumps(refs), content_type="application/json").status_code == 400


@pytest.mark.parametrize("tool,args", [("create_drafts", {"leadIds": [True]}), ("find_leads", {"count": 2, "includeEmails": True}), ("find_leads", {"count": 26}), ("find_work_emails", {"leadIds": [1, 1]}), ("get_lead", {"leadId": 1, "shell": "echo secrets"}), ("send_email", {"draftId": str(uuid.uuid4()), "approvalToken": "model-forged"})])
def test_tool_schemas_bound_model_arguments(tool, args):
    with pytest.raises(ValueError):
        normalize(tool, args)


def test_free_discovery_starts_directly_and_persists_structured_session(discovery_client):
    from leadzen.discovery_progress import current
    def synthetic_find(args):
        assert args == {"count": 5, "emails": False, "audience": "Dental owners in Texas"}
        monitor = current()
        assert monitor.session.unit == "leads" and not monitor.session.source_ids
        return {"stored": 0, "partial": False}
    with patch("leadzen.chat.engine.find_leads", side_effect=synthetic_find) as finder:
        thread, row = tool_turn(discovery_client, "find_leads", {"count": 5, "includeEmails": False, "targetOverrides": {"audience": "Dental owners in Texas"}}, "Find 5 dental owners in Texas. No emails.")
    finder.assert_called_once()
    assert row.status == "succeeded" and not row.pending and row.credits_reserved == 0
    assert DiscoverySession.objects.get(run=row).goal == 5
    assert result(thread)["discovery"]["credits"]["used"] == 0


def test_chat_discovery_pause_resume_keeps_same_run_and_remaining_goal(discovery_client):
    from leadzen.discovery_progress import current, Monitor
    def paused_find(args):
        session = current().session
        DiscoverySession.objects.filter(pk=session.pk).update(pause_requested=True)
        return {"stored": 0, "paused": True}
    with patch("leadzen.chat.engine.find_leads", side_effect=paused_find):
        thread, row = tool_turn(discovery_client, "find_leads", {"count": 3, "includeEmails": False}, "Find three owners without emails")
    assert row.status == "paused" and row.approval_expires_at > timezone.now()
    session = DiscoverySession.objects.get(run=row)
    source, contact = qualified_contact()
    Monitor(session).verdict(source)
    Monitor(session).output({"lead_id": source.pk, "email": None})
    with patch("leadzen.chat.views.launch") as launch:
        assert post(discovery_client, f"/api/discovery/{row.pk}/resume", {}).status_code == 202
        assert post(discovery_client, f"/api/discovery/{row.pk}/resume", {}).status_code == 409
        launch.assert_called_once()
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 2, "partial": False}) as finder, patch("leadzen.chat.engine.decide") as model:
        drive(row.pk)
        drive(row.pk)
    finder.assert_called_once_with({"count": 2, "emails": False, "audience": ""})
    model.assert_not_called()
    row.refresh_from_db()
    assert row.status == "succeeded" and row.credits_reserved == 0
    assert DiscoverySession.objects.filter(run=row).count() == 1


def test_free_discovery_finishes_before_another_model_selected_action(discovery_client):
    thread, run = turn(discovery_client, "Find two owners, no emails")
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 2, "partial": False}) as finder, patch("leadzen.chat.engine.decide", side_effect=[Decision(tool="find_leads", arguments={"count": 2, "includeEmails": False}), AssertionError("No next action after discovery")]) as model:
        drive(run)
    assert ChatRun.objects.get(pk=run).status == "succeeded"
    finder.assert_called_once()
    assert model.call_count == 1


def test_partial_chat_discovery_is_not_reported_as_complete(discovery_client):
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 1, "partial": True}):
        thread, row = tool_turn(discovery_client, "find_leads", {"count": 3, "includeEmails": False}, "Find three owners")
    assert row.status == "failed"
    assert "partial results" in ChatThread.objects.get(pk=thread).messages.filter(role="assistant").latest("created_at").content


def test_stale_context_is_cleaned_when_reopening_history(discovery_client):
    a = person()
    thread, row = tool_turn(discovery_client, "get_lead", {"leadId": a.pk})
    a.delete()
    other = ChatThread.objects.create(actor_id=row.actor_id)
    from leadzen.chat.context import save
    save(row.actor_id, {"lastChatId": str(other.pk)})
    response = discovery_client.get(f"/api/chat/threads/{thread}")
    assert response.status_code == 200
    assert response.json()["context"]["currentLeadId"] is None


def test_context_rejects_a_stale_browser_account(discovery_client):
    response = discovery_client.put("/api/chat/context", json.dumps({"references": {"selectedLeadIds": []}, "expected_actor_id": 999}), content_type="application/json")
    assert response.status_code == 409
    assert not WorkspaceContext.objects.exists()


def test_only_one_stream_can_hold_an_actor_lease(discovery_client):
    thread, row = tool_turn(discovery_client, "get_workspace_status", {})
    first = discovery_client.get(f"/api/chat/threads/{thread}/stream")
    try:
        assert first.status_code == 200
        assert discovery_client.get(f"/api/chat/threads/{thread}/stream").status_code == 429
        # Consume a completed run's stream and release its lease.
        assert b'"status": "succeeded"' in b''.join(first.streaming_content)
        assert WorkspaceContext.objects.get().stream_token is None
        second = discovery_client.get(f"/api/chat/threads/{thread}/stream")
        assert second.status_code == 200
        list(second.streaming_content)
        second.close()
    finally:
        first.close()


def test_selected_drafts_are_the_same_workspace_records_and_never_send(discovery_client):
    a, b, unselected = person("a@example.com"), person("b@example.com"), person("skip@example.com")
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        data = saved_draft(discovery_client, [a, b])
    deliver.assert_not_called()
    assert set(ReviewedEmail.objects.values_list("deal_id", flat=True)) == {a.pk, b.pk}
    manual = discovery_client.get(f"/api/outreach/reviews/{data['id']}").json()
    assert manual["drafts"] == data["drafts"]
    assert discovery_client.get("/api/chat/context").json()["currentDraftId"] == data["drafts"][0]["id"]


def test_conversational_edit_and_regeneration_clear_approval(discovery_client):
    data = saved_draft(discovery_client, [person()])
    identifier = data["drafts"][0]["id"]
    thread, row = tool_turn(discovery_client, "update_draft", {"draftId": identifier, "body": "Shorter human copy."})
    d = ReviewedEmail.objects.get(pk=identifier)
    assert d.body == "Shorter human copy." and not d.approved_hash
    def revise(review, drafts):
        assert drafts[0].instructions == "Don't mention AI. Shorter."
        assert drafts[0].body == "Shorter human copy."
        return [{"id": identifier, "subject": "Quick question", "body": "Could we chat?"}]
    with patch("leadzen.outreach.generate", side_effect=revise):
        thread, row = tool_turn(discovery_client, "regenerate_draft", {"draftId": identifier, "instructions": "Don't mention AI. Shorter."})
    d.refresh_from_db()
    assert d.body == "Could we chat?" and not d.approved_hash
    assert discovery_client.get(f"/api/outreach/reviews/{data['id']}").json()["drafts"][0]["body"] == d.body


def test_send_confirmation_binds_full_copy_and_is_single_use(discovery_client):
    from cold_outreach.emails.models import Message
    data = saved_draft(discovery_client, [person()])
    identifier = data["drafts"][0]["id"]
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        thread, row = tool_turn(discovery_client, "send_email", {"draftId": identifier}, "Send it")
    assert row.status == "awaiting_approval"
    deliver.assert_not_called()
    assert row.pending["preview"]["recipients"][0]["body"] == data["drafts"][0]["preview_body"]
    token = approval(discovery_client, row)
    with patch("cold_outreach.emails.sender._deliver", side_effect=accepted) as deliver, patch("leadzen.outreach.sync_replies_strict"), patch("leadzen.outreach.within_sending_window", return_value=True), patch("cold_outreach.emails.models.Mailbox.free_now", return_value=True), patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Accepted by provider.")):
        drive(row.pk)
        drive(row.pk)
    assert deliver.call_count == 1
    assert ReviewedEmail.objects.get(pk=identifier).state == "accepted"
    assert Message.objects.filter(direction="out").count() == 1
    assert result(thread)["accepted"] == 1
    assert post(discovery_client, f"/api/chat/runs/{row.pk}/approval", {"approved": True, "action_id": token}).status_code == 409


@pytest.mark.parametrize("change", ["body", "suppression", "expiry"])
def test_changed_send_or_permission_invalidates_capability(discovery_client, change):
    from cold_outreach.leads.models import Suppression
    deal = person()
    data = saved_draft(discovery_client, [deal])
    identifier = data["drafts"][0]["id"]
    thread, row = tool_turn(discovery_client, "send_email", {"draftId": identifier}, "Send it")
    token = row.pending["id"]
    if change == "body": ReviewedEmail.objects.filter(pk=identifier).update(body="Changed after preview")
    elif change == "suppression": Suppression.objects.create(email=deal.lead.email, reason="Opted out")
    else: ChatRun.objects.filter(pk=row.pk).update(approval_expires_at=timezone.now() - timedelta(seconds=1))
    with patch("cold_outreach.emails.sender._deliver") as deliver, patch("leadzen.chat.views.launch") as launch:
        response = post(discovery_client, f"/api/chat/runs/{row.pk}/approval", {"approved": True, "action_id": token})
    assert response.status_code in {400, 409}
    deliver.assert_not_called(); launch.assert_not_called()


def test_subset_send_leaves_other_drafts_available(discovery_client):
    data = saved_draft(discovery_client, [person("a@example.com"), person("b@example.com")])
    thread, row = tool_turn(discovery_client, "send_emails", {"draftIds": [data["drafts"][0]["id"]]}, "Send only the first message")
    approval(discovery_client, row)
    with patch("cold_outreach.emails.sender._deliver", side_effect=accepted) as deliver, patch("leadzen.outreach.sync_replies_strict"), patch("leadzen.outreach.within_sending_window", return_value=True), patch("cold_outreach.emails.models.Mailbox.free_now", return_value=True), patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="One accepted.")):
        drive(row.pk)
    assert deliver.call_count == 1
    assert ReviewedEmail.objects.get(pk=data["drafts"][1]["id"]).state == "pending"
    assert EmailReview.objects.get(pk=data["id"]).status == "draft"


def test_deferred_send_reports_zero_acceptance(discovery_client):
    data = saved_draft(discovery_client, [person()])
    thread, row = tool_turn(discovery_client, "send_email", {"draftId": data["drafts"][0]["id"]}, "Send it")
    approval(discovery_client, row)
    with patch("cold_outreach.emails.sender._deliver") as deliver, patch("leadzen.outreach.within_sending_window", return_value=False), patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Deferred; no message accepted.")):
        drive(row.pk)
    deliver.assert_not_called()
    assert result(thread)["accepted"] == 0
    assert ReviewedEmail.objects.get(pk=data["drafts"][0]["id"]).state == "pending"


def test_direct_send_tool_cannot_forge_approval(discovery_client):
    data = saved_draft(discovery_client, [person()])
    thread, row = turn(discovery_client)
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        with pytest.raises(PermissionError):
            execute("send_email", {"draftId": data["drafts"][0]["id"], "approvalToken": None}, ChatRun.objects.get(pk=row))
    deliver.assert_not_called()


def test_suppression_projects_into_workspace_and_blocks_drafting(discovery_client):
    deal = person()
    thread, row = tool_turn(discovery_client, "suppress_contact", {"leadId": deal.pk}, "Don't contact Bruce again")
    manual = discovery_client.get(f"/api/contacts/{deal.pk}").json()
    assert manual["crm_status"] == "suppressed" and manual["state"] == "Completed"
    with patch("leadzen.outreach.generate") as generate:
        thread, row = tool_turn(discovery_client, "create_drafts", {"leadIds": [deal.pk]})
    generate.assert_not_called()
    assert "eligible" in result(thread)["error"]


def test_persistent_history_rename_archive_and_stream_ownership(discovery_client):
    thread, row = tool_turn(discovery_client, "get_workspace_status", {})
    renamed = discovery_client.put(f"/api/chat/threads/{thread}", json.dumps({"title": "Dental owners"}), content_type="application/json")
    assert renamed.json()["title"] == "Dental owners"
    response = discovery_client.get(f"/api/chat/threads/{thread}/stream")
    frames = b"".join(response.streaming_content).decode()
    assert '"title": "Dental owners"' in frames and "synthetic-secret" not in frames
    foreign = ChatThread.objects.create(actor_id=999)
    assert discovery_client.get(f"/api/chat/threads/{foreign.pk}/stream").status_code == 404
    archived = discovery_client.put(f"/api/chat/threads/{thread}", json.dumps({"archived": True}), content_type="application/json")
    assert archived.status_code == 200
    assert discovery_client.get(f"/api/chat/threads/{thread}").status_code == 404
    assert not discovery_client.get("/api/chat/threads").json()["items"]


def test_unauthenticated_context_and_stream_have_no_private_output(db, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    with patch("leadzen.chat.context.structured") as private:
        assert Client().get("/api/chat/context").status_code == 401
        assert Client().get(f"/api/chat/threads/{uuid.uuid4()}/stream").status_code == 401
    private.assert_not_called()


def qualified_contact():
    from openoutfind.crm.models import Lead as Profile, Deal as Qualification
    from cold_outreach.leads.models import Lead, Deal
    source = Profile.objects.create(profile_url=f"https://www.linkedin.com/in/synthetic-{uuid.uuid4().hex}", full_name="Sarah Johnson", job_title="Practice owner")
    Qualification.objects.create(lead=source, state="Qualified", reason="Actual synthetic qualification: practice owner")
    deal = Deal.objects.create(lead=Lead.objects.create(lead_id=str(source.pk), first_name="Sarah", last_name="Johnson", title="Practice owner", email=""))
    return source, deal


def test_imported_full_name_is_shared_and_bound_to_draft_approval(discovery_client):
    from leadzen.outreach import context_hash
    source, deal = qualified_contact()
    deal.lead.first_name, deal.lead.last_name, deal.lead.email = "", "", "sarah@example.com"
    deal.lead.save()
    data = saved_draft(discovery_client, [deal])
    assert data["drafts"][0]["name"] == source.full_name
    assert discovery_client.get(f"/api/contacts/{deal.pk}").json()["name"] == source.full_name
    review = EmailReview.objects.get(pk=data["id"])
    assert context_hash(review) == review.context_hash
    source.full_name = "Different saved contact name"
    source.save(update_fields=["full_name"])
    assert context_hash(review) != review.context_hash


def test_selected_enrichment_requires_confirmation_and_updates_same_lead(discovery_client):
    from leadzen.discovery_progress import current, ProgressOutput
    from openoutfind.core.export import lead_record
    from openoutfind.crm.models import Deal as Qualification
    source, deal = qualified_contact()
    unselected, other = qualified_contact()
    with patch("leadzen.chat.engine.find_leads") as finder:
        thread, row = tool_turn(discovery_client, "find_work_emails", {"leadIds": [deal.pk]}, "Get Sarah's work email")
    finder.assert_not_called()
    assert row.pending["credits"] == 1 and row.pending["preview"]["recipients"][0]["name"] == "Sarah Johnson"
    approval(discovery_client, row)
    def enrich(args):
        monitor = current()
        assert monitor.session.source_ids == [source.pk]
        assert args["emails"] and args["count"] == 1
        receipt = monitor.reserve_lookup({"data": [{"linkedin_url": source.profile_url}], "enrich_email_address": True})
        monitor.submitted(receipt, {"id": "synthetic-request"})
        monitor.report_lookup(receipt.request_id, {"status": "terminated", "credits_consumed": 1, "data": [{"contact_email_address_status": "valid"}]})
        source.email = "sarah@example.com"; source.save()
        ProgressOutput(monitor).write(json.dumps(lead_record(Qualification.objects.get(lead=source))) + "\n")
        return {"stored": 1, "partial": False}
    with patch("leadzen.chat.engine.find_leads", side_effect=enrich), patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="One email verified.")):
        drive(row.pk)
    manual = discovery_client.get(f"/api/contacts/{deal.pk}").json()
    assert manual["email"] == "sarah@example.com" and manual["email_status"] == "verified"
    assert result(thread)["credits"]["used"] == 1
    other.lead.refresh_from_db(); assert not other.lead.email


def test_selected_async_email_lookup_polls_accepted_request_until_terminal(discovery_client):
    import requests
    from openoutfind.enrichment import bettercontact
    from openoutfind.crm.models import Deal as Qualification, DealState
    from openoutfind.core.export import lead_record
    from leadzen.discovery_progress import current

    source, deal = qualified_contact()
    thread, row = tool_turn(discovery_client, "find_work_emails", {"leadIds": [deal.pk]}, "Get Sarah's work email")
    approval(discovery_client, row)
    calls = []
    terminal = json.dumps({"status": "terminated", "credits_consumed": 1, "data": [{
        "contact_email_address": "sarah@example.com", "contact_email_address_status": "valid",
        "contact_first_name": "Sarah", "contact_last_name": "Johnson",
    }]}).encode()
    replies = [(202, {}, b'{"id":"synthetic-request"}'), (202, {}, b""), (200, {}, terminal)]

    def command(*args, stdout, stderr):
        assert args[:3] == ("find", "1", "emails")
        calls.append(args)
        decision = Qualification.objects.get(lead=source)
        if len(calls) == 1:
            bettercontact._request(requests.Session(), "POST", "https://app.bettercontact.rocks/api/v2/async",
                                   json={"data": [{"linkedin_url": source.profile_url}], "enrich_email_address": True})
            receipt = current().session.lookups.get(source_id=source.pk)
            decision.state = DealState.FINDING_EMAIL
            decision.lookup_request_id = receipt.request_id
            decision.lookup_attempt = 0
            decision.not_before = timezone.now() - timedelta(seconds=1)
            decision.save()
            raise RuntimeError("The accepted lookup is still processing")

        response = bettercontact._request(requests.Session(), "GET",
                                          "https://app.bettercontact.rocks/api/v2/async/synthetic-request")
        if response.json().get("status") != "terminated":
            decision.lookup_attempt += 1
            decision.not_before = timezone.now() + timedelta(milliseconds=1)
            decision.save()
            raise RuntimeError("The accepted lookup is still processing")

        source.email = "sarah@example.com"
        source.save(update_fields=["email"])
        decision.state = DealState.RESOLVED
        decision.lookup_request_id = ""
        decision.not_before = None
        decision.save()
        stdout.write(json.dumps(lead_record(decision)) + "\n")

    with patch("django.core.management.call_command", side_effect=command), \
         patch("leadzen.ai.pinned_request", side_effect=replies) as transport, \
         patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Lookup finished.")):
        drive(row.pk)

    row.refresh_from_db()
    assert row.status == "succeeded"
    assert [call.args[0] for call in transport.call_args_list] == ["POST", "GET", "GET"]
    assert len(calls) == 3
    assert result(thread)["items"][0]["email"] == "sarah@example.com"
    assert result(thread)["credits"]["used"] == 1


def test_uncertain_purchase_is_not_repeated(discovery_client):
    from leadzen.config.models import DiscoveryLookup
    source, deal = qualified_contact()
    thread, row = tool_turn(discovery_client, "find_work_emails", {"leadIds": [deal.pk]})
    approval(discovery_client, row)
    def uncertain(args):
        from leadzen.discovery_progress import current
        current().reserve_lookup({"data": [{"linkedin_url": source.profile_url}], "enrich_email_address": True})
        return {"stored": 0, "partial": True}
    with patch("leadzen.chat.engine.find_leads", side_effect=uncertain), patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Purchase status uncertain. Review the saved receipt.")):
        drive(row.pk)
    assert DiscoveryLookup.objects.filter(source_id=source.pk, credits=None).exists()
    with patch("leadzen.chat.engine.find_leads") as finder:
        thread, second = tool_turn(discovery_client, "find_work_emails", {"leadIds": [deal.pk]})
    finder.assert_not_called()
    assert second.status == "succeeded" and not second.pending
    assert "existing lookup" in result(thread)["error"]


def test_actual_reply_read_draft_and_send_use_existing_conversation(discovery_client):
    from cold_outreach.emails.models import Message, Thread
    from leadzen.mailboxes import active_mailboxes
    deal = person()
    box = active_mailboxes().first()
    thread = Thread.objects.create(mailbox=box)
    parent = Message.objects.create(mailbox=box, thread=thread, direction="in", kind="human_reply", message_id="synthetic-reply", from_address=deal.lead.email, to_address=box.from_address, subject="Pricing", body_text="Can you send pricing?", received_at=timezone.now())
    deal.state, deal.thread, deal.mailbox = "Emailed", thread, box; deal.save()
    chat, row = tool_turn(discovery_client, "get_thread", {"threadId": thread.pk})
    assert result(chat)["messages"][0]["body"] == parent.body_text
    with patch("leadzen.outreach.generate", side_effect=synthetic_generate), patch("cold_outreach.emails.sender._deliver") as deliver:
        chat, row = tool_turn(discovery_client, "draft_reply", {"threadId": thread.pk, "instructions": "Answer the pricing question. Do not invent a price."})
    deliver.assert_not_called()
    data = result(chat)
    d = ReviewedEmail.objects.get(pk=data["drafts"][0]["id"])
    assert d.reply_to_id == parent.pk and d.review.kind == "reply" and d.instructions
    chat, row = tool_turn(discovery_client, "send_reply", {"draftId": str(d.pk)}, "Send it")
    approval(discovery_client, row)
    with patch("cold_outreach.emails.sender._deliver", side_effect=accepted) as deliver, patch("leadzen.outreach.sync_replies_strict"), patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Reply accepted.")):
        drive(row.pk)
    assert deliver.call_count == 1
    outbound = Message.objects.get(direction="out")
    assert outbound.thread_id == thread.pk
    assert result(chat)["accepted"] == 1


def test_manual_unsuppress_needs_approval_and_keeps_sequence_stopped(discovery_client):
    deal = person()
    tool_turn(discovery_client, "suppress_contact", {"leadId": deal.pk})
    chat, row = tool_turn(discovery_client, "unsuppress_contact", {"leadId": deal.pk}, "Remove my manual suppression")
    assert row.status == "awaiting_approval"
    approval(discovery_client, row)
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer", text="Manual block removed. Sequence remains stopped.")):
        drive(row.pk)
    deal.refresh_from_db(); assert deal.state == "Completed"
    from cold_outreach.leads.models import Suppression
    assert not Suppression.objects.exists()


def test_opt_out_cannot_be_removed(discovery_client):
    from cold_outreach.leads.models import Suppression
    deal = person()
    Suppression.objects.create(email=deal.lead.email, reason="Opted out")
    chat, row = tool_turn(discovery_client, "unsuppress_contact", {"leadId": deal.pk})
    approval(discovery_client, row)
    with patch("leadzen.chat.engine.decide", return_value=Decision(tool="answer")):
        drive(row.pk)
    assert Suppression.objects.filter(email=deal.lead.email).exists()


@pytest.mark.parametrize("prompt", ["Looks good.", "Draft an email. Do not send.", "Never send this."])
def test_model_cannot_turn_draft_praise_into_send_intent(discovery_client, prompt):
    data = saved_draft(discovery_client, [person()])
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        chat, row = tool_turn(discovery_client, "send_email", {"draftId": data["drafts"][0]["id"]}, prompt)
    assert not row.pending and row.status == "succeeded"
    assert "does not authorize" in result(chat)["error"]
    deliver.assert_not_called()
