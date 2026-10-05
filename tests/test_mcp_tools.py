"""Synthetic MCP capability tests: canonical records, exact approvals, no planner."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tests.test_reviewed_outreach import connected, person, review, synthetic_generate, accepted
from leadzen.config.models import ChatRun, ChatThread, ContactPreferences, EmailCampaign, SiteConfig, ReviewedEmail
from leadzen.configuration import save_dashboard_settings
from leadzen.mcp.auth import digest
from leadzen.mcp.models import MCPClient, MCPConnection
from leadzen.mcp.tools import call_tool, list_tools, normalized
from leadzen.mcp.worker import drive


@pytest.fixture
def identity(connected, monkeypatch):
    monkeypatch.setenv("LEADZEN_MCP_PUBLIC_URL", "https://api.example.com/mcp")
    monkeypatch.setenv("LEADZEN_PUBLIC_URL", "https://leadzen.example.com")
    actor = get_user_model().objects.get(email="unit@example.com")
    client = MCPClient.objects.create(id="synthetic-client", name="Synthetic connected assistant", redirect_uris=["https://client.example.com/callback"])
    conn = MCPConnection.objects.create(user=actor, client=client, resource="https://api.example.com/mcp",
        scopes=["leadzen:read", "leadzen:write"], password_fingerprint=digest(actor.password), expires_at=timezone.now() + timedelta(days=30))
    save_dashboard_settings({"provider": "openai", "model": "synthetic-model", "base_url": "https://api.example.com/v1", "ai_enabled": True, "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "smtp_port": 465, "imap_host": "imap.example.com", "imap_port": 993, "signature": "Synthetic Sender\nZyene"}, bettercontact_api_key="synthetic-mcp-finder")
    config = SiteConfig.load()
    config.operator_email, config.accepted_legal_notice = "sender@example.com", True
    config.save()
    return actor, conn, connected


def call(identity, name, args=None, *, request_id=None):
    actor, conn, _ = identity
    args = dict(args or {})
    from leadzen.mcp.tools import ENTRIES
    if ENTRIES[name][2]:
        args["requestId"] = str(request_id or uuid.uuid4())
    return call_tool(actor, conn, name, args)


def approve(identity, operation):
    _, _, client = identity
    row = ChatRun.objects.get(pk=operation["operationId"])
    with patch("leadzen.chat.views.launch") as launch:
        response = client.post(f"/api/chat/runs/{row.pk}/approval", json.dumps({"approved": True, "action_id": row.pending["id"]}), content_type="application/json")
    assert response.status_code == 202, response.content
    launch.assert_called_once()
    return row


def test_catalog_exposes_complete_bounded_employee_capabilities_without_admin_or_approval_controls():
    entries = list_tools()
    names = {entry["name"] for entry in entries}
    assert len(names) == 40
    assert {"find_leads", "find_work_emails", "create_drafts", "send_email", "send_campaign", "sync_mailbox", "get_settings", "pause_autopilot", "import_leads", "get_operation"} <= names
    assert not names & {"approve", "enable_autopilot", "shell", "execute_sql", "send_http", "list_users", "get_secrets"}
    for entry in entries:
        assert entry["inputSchema"]["additionalProperties"] is False
        if not entry["annotations"]["readOnlyHint"]:
            assert "requestId" in entry["inputSchema"]["required"]
    send_schema = next(entry for entry in entries if entry["name"] == "send_email")["inputSchema"]
    assert "approvalToken" not in send_schema["properties"]


@pytest.mark.parametrize("name,args", [
    ("get_lead", {"leadId": True}), ("get_lead", {"leadId": 1, "actorId": 2}),
    ("find_leads", {"count": 26}), ("find_leads", {"count": 1, "includeEmails": True}),
    ("find_work_emails", {"leadIds": [1, 1]}), ("find_work_emails", {"leadIds": [True]}),
    ("send_email", {"draftId": str(uuid.uuid4()), "approvalToken": "forged"}),
    ("send_email", {"draftId": str(uuid.uuid4()), "approved": True}),
    ("pause_autopilot", {"enabled": True}), ("update_settings", {"changes": {"llm": {"api_key": "not-allowed"}}}),
    ("update_settings", {"changes": {"sending_schedule": {"timezone": "Asia/Kolkata", "days": [0], "start": "09:00", "end": "17:00"}}}),
    ("create_lead", {"contact": {"email": "real@example.com", "opted_in": True, "consent_note": "Invented consent"}}),
    ("import_leads", {"contacts": [{"email": f"a{i}@example.com"} for i in range(26)]}),
    ("send_emails", {"draftIds": [str(uuid.uuid4()) for _ in range(26)]}),
])
def test_schemas_reject_unsafe_scope_or_unbounded_choices(name, args):
    from leadzen.mcp.tools import ENTRIES
    if ENTRIES[name][2]:
        args = {**args, "requestId": str(uuid.uuid4())}
    with pytest.raises(ValueError):
        normalized(name, args)


@pytest.mark.parametrize("value", [None, "bad", True, 1])
def test_mutations_require_a_canonical_idempotency_uuid(value):
    with pytest.raises(ValueError):
        normalized("pause_autopilot", {} if value is None else {"requestId": value})


def test_read_tools_do_not_create_runs_or_call_external_providers(identity):
    lead = person()
    with patch("leadzen.chat.engine.decide") as planner, patch("leadzen.chat.engine.find_leads") as finder, patch("leadzen.outreach.generate") as model:
        assert call(identity, "get_lead", {"leadId": lead.pk})["id"] == lead.pk
        assert call(identity, "list_leads")["total"] == 1
        for name in ("get_workspace_context", "get_workspace_status", "get_credit_usage", "get_target", "list_campaigns", "list_replies", "get_autopilot", "get_activity", "list_suppressions"):
            assert isinstance(call(identity, name), dict)
        planner.assert_not_called(); finder.assert_not_called(); model.assert_not_called()
    assert not ChatRun.objects.exists()


def test_stored_reply_search_uses_query_filter_without_mailbox_access(identity):
    with patch("leadzen.transports.sync_replies_strict") as sync:
        result = call(identity, "list_replies", {"filters": {"query": "practice"}})
    assert result["items"] == []
    sync.assert_not_called()
    assert not ChatRun.objects.exists()


def test_settings_are_nonsecret_and_storage_paths_are_omitted(identity):
    result = call(identity, "get_settings")
    text = json.dumps(result)
    assert "synthetic-mcp-finder" not in text and "synthetic-mail-password" not in text and "synthetic-ai-key" not in text
    assert "path" not in result["workspace"] and "data" not in result["workspace"]
    assert "base_url" not in text and "smtp_username" not in text and "api_url" not in text
    assert result["workspace"]["sending_schedule"]["timezone"] == "America/New_York"


def test_create_contact_is_exactly_idempotent_and_replay_cannot_change_action(identity):
    request_id = uuid.uuid4()
    args = {"contact": {"email": "new@example.com", "first_name": "New", "company": "Actual company"}}
    first = call(identity, "create_lead", args, request_id=request_id)
    second = call(identity, "create_lead", args, request_id=request_id)
    assert first["operationId"] == second["operationId"] and first["status"] == "succeeded"
    assert first["result"]["created"] == 1
    assert ChatRun.objects.count() == 1
    with pytest.raises(ValueError, match="different action"):
        call(identity, "create_lead", {"contact": {"email": "changed@example.com"}}, request_id=request_id)
    from cold_outreach.leads.models import Lead
    assert Lead.objects.count() == 1


def test_import_uses_existing_atomic_duplicate_validation(identity):
    with pytest.raises(ValueError, match="duplicate"):
        call(identity, "import_leads", {"contacts": [{"email": "same@example.com"}, {"email": "same@example.com"}]})
    from cold_outreach.leads.models import Lead
    assert Lead.objects.count() == 0 and ChatRun.objects.count() == 0


def test_update_preserves_email_and_recorded_consent_then_delete_stops_contact(identity):
    lead = person()
    ContactPreferences.objects.create(lead=lead.lead, opted_in=True, consent_note="Recorded independently by employee")
    assert call(identity, "update_lead", {"leadId": lead.pk, "title": "Owner"})["status"] == "succeeded"
    lead.lead.refresh_from_db()
    assert lead.lead.title == "Owner" and lead.lead.email == "bruce@example.com"
    assert ContactPreferences.objects.get(lead=lead.lead).opted_in is True
    assert call(identity, "delete_lead", {"leadId": lead.pk})["status"] == "succeeded"
    with pytest.raises(ValueError, match="not found"):
        call(identity, "get_lead", {"leadId": lead.pk})


def test_draft_campaign_stays_draft_and_can_be_paused(identity):
    lead = person()
    created = call(identity, "create_campaign", {"name": "Real sequence", "leadIds": [lead.pk], "steps": [{"subject": "Hello", "body": "A useful message", "delay_days": 0}]})
    campaign = EmailCampaign.objects.get(pk=created["result"]["id"])
    assert campaign.status == "draft" and campaign.followup_approval == {}
    assert call(identity, "get_campaign", {"campaignId": str(campaign.pk)})["name"] == "Real sequence"
    call(identity, "pause_campaign", {"campaignId": str(campaign.pk)})
    campaign.refresh_from_db()
    assert campaign.status == "paused"


def test_settings_update_reuses_fixed_timezone_schedule_validation_and_stays_nonsecret(identity):
    schedule = {"days": [0, 2, 5], "start": "09:30", "end": "16:45", "timezone": "America/New_York"}
    operation = call(identity, "update_settings", {"changes": {"sending_schedule": schedule}})
    assert operation["status"] == "succeeded"
    assert operation["result"]["workspace"]["sending_schedule"] == schedule
    assert "data" not in operation["result"]["workspace"]
    with pytest.raises(ValueError, match="after start"):
        call(identity, "update_settings", {"changes": {"sending_schedule": {**schedule, "end": "09:00"}}})
    assert SiteConfig.load().sending_schedule == schedule


def test_free_discovery_also_waits_for_portal_approval_then_performs_once_without_planner(identity):
    with patch("leadzen.chat.engine.find_leads") as finder, patch("leadzen.chat.engine.decide") as planner, patch("leadzen.chat.views.launch") as launch:
        operation = call(identity, "find_leads", {"count": 3, "includeEmails": False})
        assert operation["status"] == "awaiting_approval"
        assert operation["portalUrl"].startswith("https://leadzen.example.com/chat/")
        assert operation["operation"]["approval"]["credits"] == 0
        drive(operation["operationId"])
        finder.assert_not_called(); planner.assert_not_called(); launch.assert_not_called()
    row = approve(identity, operation)
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 3, "partial": False}) as finder, patch("leadzen.chat.engine.decide") as planner:
        drive(row.pk); drive(row.pk)
        finder.assert_called_once_with({"count": 3, "emails": False, "audience": ""})
        planner.assert_not_called()
    result = call(identity, "get_operation", {"operationId": str(row.pk)})
    assert result["status"] == "succeeded" and result["result"]["stored"] == 3
    assert result["result"]["discovery"]["id"] == str(row.pk)


def test_drafting_requires_portal_review_of_selected_leads_then_saves_canonical_drafts(identity):
    lead = person()
    with patch("leadzen.outreach.generate") as model:
        operation = call(identity, "create_drafts", {"leadIds": [lead.pk], "instructions": "Be concise"})
        model.assert_not_called()
    preview = operation["operation"]["approval"]["preview"]
    assert preview["recipients"][0]["id"] == lead.pk and preview["instructions"] == "Be concise"
    assert "provider charges" in preview["note"]
    row = approve(identity, operation)
    with patch("leadzen.outreach.generate", side_effect=synthetic_generate), patch("leadzen.chat.engine.decide") as planner:
        drive(row.pk)
        planner.assert_not_called()
    result = call(identity, "get_operation", {"operationId": str(row.pk)})
    assert result["status"] == "succeeded" and result["result"]["drafts"][0]["to"] == lead.lead.email
    assert ReviewedEmail.objects.count() == 1


def test_plain_draft_edit_is_local_but_instructions_need_new_model_approval(identity):
    lead = person()
    data = review(identity[2])
    draft_id = data["drafts"][0]["id"]
    with patch("leadzen.outreach.generate") as model:
        edited = call(identity, "update_draft", {"draftId": draft_id, "subject": "Human edit", "body": "Human message"})
        assert edited["status"] == "succeeded"
        operation = call(identity, "update_draft", {"draftId": draft_id, "instructions": "Improve this"})
        assert operation["status"] == "awaiting_approval"
        model.assert_not_called()
    assert operation["operation"]["approval"]["preview"]["recipients"][0]["subject"] == "Human edit"


def test_send_prepares_exact_messages_and_cannot_use_client_approval(identity):
    person()
    data = review(identity[2])
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        operation = call(identity, "send_email", {"draftId": data["drafts"][0]["id"]})
        deliver.assert_not_called()
    assert operation["status"] == "awaiting_approval"
    recipient = operation["operation"]["approval"]["preview"]["recipients"][0]
    assert recipient["email"] == "bruce@example.com" and recipient["subject"] == data["drafts"][0]["subject"]
    assert 'Reply "stop"' in recipient["body"]
    row = approve(identity, operation)
    with patch("leadzen.outreach.within_sending_window", return_value=True), patch("leadzen.outreach.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver", side_effect=accepted) as deliver, patch("leadzen.chat.engine.decide") as planner:
        drive(row.pk); drive(row.pk)
        deliver.assert_called_once()
        planner.assert_not_called()
    result = call(identity, "get_operation", {"operationId": str(row.pk)})
    assert result["status"] == "succeeded" and result["result"]["accepted"] == 1


def test_mailbox_sync_prepares_external_approval_and_never_syncs_by_read(identity):
    lead = person()
    created = call(identity, "create_campaign", {"name": "Reply-aware sequence", "leadIds": [lead.pk], "steps": [{"subject": "Hello", "body": "A useful message", "delay_days": 0}]})
    campaign = EmailCampaign.objects.get(pk=created["result"]["id"])
    with patch("leadzen.transports.sync_replies_strict") as sync:
        call(identity, "list_replies")
        operation = call(identity, "sync_mailbox")
        sync.assert_not_called()
    assert operation["operation"]["approval"]["preview"]["from_address"] == "sender@example.com"
    row = approve(identity, operation)
    with patch("leadzen.transports.sync_replies_strict") as sync, patch("leadzen.chat.engine.decide") as planner:
        drive(row.pk)
        sync.assert_called_once()
        planner.assert_not_called()
    # Checking replies must preserve the same campaign leads used by CRM and
    # sending. Mailbox preparation cannot install a global sender-only filter.
    assert call(identity, "get_lead", {"leadId": lead.pk})["id"] == lead.pk
    assert call(identity, "list_leads")["total"] == 1
    campaign.recipients.get().deal.refresh_from_db()


def test_replay_and_poll_are_connection_owned_even_for_same_actor(identity):
    first = call(identity, "pause_autopilot")
    actor, conn, _ = identity
    other = MCPConnection.objects.create(user=actor, client=conn.client, resource=conn.resource, scopes=conn.scopes,
        password_fingerprint=conn.password_fingerprint, expires_at=conn.expires_at)
    with pytest.raises(ValueError, match="not found"):
        call_tool(actor, other, "get_operation", {"operationId": first["operationId"]})
    with pytest.raises(ValueError, match="different action"):
        call_tool(actor, other, "pause_autopilot", {"requestId": str(ChatRun.objects.get(pk=first["operationId"]).request_id)})


def test_foreign_draft_fails_before_creating_approval(identity):
    lead = person()
    from leadzen.config.models import EmailReview
    review_row = EmailReview.objects.create(actor_id=999, request_id=uuid.uuid4(), requested_count=1, from_address="foreign@example.com", context_hash="")
    draft = ReviewedEmail.objects.create(review=review_row, deal=lead, subject="Private", body="Private")
    with patch("leadzen.outreach.generate") as model:
        with pytest.raises(ValueError, match="not found"):
            call(identity, "regenerate_draft", {"draftId": str(draft.pk)})
        model.assert_not_called()
    assert not ChatRun.objects.exists()


def test_setup_change_or_approval_expiry_prevents_direct_worker_effect(identity):
    operation = call(identity, "find_leads", {"count": 1})
    row = approve(identity, operation)
    config = SiteConfig.load(); config.product_docs = "Changed product"; config.save()
    with patch("leadzen.chat.engine.find_leads") as finder:
        drive(row.pk)
        finder.assert_not_called()
    row.refresh_from_db(); assert row.status == "failed"
    operation = call(identity, "find_leads", {"count": 1})
    row = approve(identity, operation)
    ChatRun.objects.filter(pk=row.pk).update(approval_expires_at=timezone.now() - timedelta(seconds=1))
    with patch("leadzen.chat.engine.find_leads") as finder:
        drive(row.pk)
        finder.assert_not_called()
    row.refresh_from_db(); assert row.status == "failed"


def test_disconnect_before_execution_prevents_provider_call(identity):
    operation = call(identity, "find_leads", {"count": 1})
    row = approve(identity, operation)
    conn = identity[1]
    MCPConnection.objects.filter(pk=conn.pk).update(revoked_at=timezone.now())
    with patch("leadzen.chat.engine.find_leads") as finder:
        drive(row.pk)
        finder.assert_not_called()
    row.refresh_from_db(); assert row.status == "failed"
    with pytest.raises(PermissionError):
        call(identity, "get_workspace_status")


def test_disconnect_or_cancel_mid_action_is_rechecked_at_existing_sink(identity):
    operation = call(identity, "find_leads", {"count": 1})
    row = approve(identity, operation)
    def fake_find(args):
        from leadzen.chat.engine import assert_action_access
        MCPConnection.objects.filter(pk=identity[1].pk).update(revoked_at=timezone.now())
        assert_action_access()
        raise AssertionError("Provider bytes must remain blocked")
    with patch("leadzen.chat.engine.find_leads", side_effect=fake_find):
        drive(row.pk)
    row.refresh_from_db(); assert row.status == "failed"


def test_cancel_pending_and_running_operations_is_available_while_active(identity):
    operation = call(identity, "find_leads", {"count": 1})
    cancelled = call(identity, "cancel_operation", {"operationId": operation["operationId"]})
    assert cancelled["result"]["status"] == "cancelled"
    operation = call(identity, "find_leads", {"count": 1})
    ChatRun.objects.filter(pk=operation["operationId"]).update(status="running")
    cancelled = call(identity, "cancel_operation", {"operationId": operation["operationId"]})
    assert cancelled["result"]["operation"]["cancel_requested"] is True


def test_manual_optout_cannot_be_removed_or_sequence_reenabled_by_client(identity):
    lead = person()
    call(identity, "suppress_contact", {"leadId": lead.pk, "reason": "Employee request"})
    operation = call(identity, "unsuppress_contact", {"leadId": lead.pk})
    assert operation["status"] == "awaiting_approval"
    assert "Stopped sequences stay stopped" in operation["operation"]["approval"]["preview"]["note"]


def test_portal_resume_continues_only_remaining_saved_discovery_goal(identity):
    from leadzen.config.models import DiscoverySession, DiscoveryCandidate
    operation = call(identity, "find_leads", {"count": 3})
    row = approve(identity, operation)
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 1, "paused": True}):
        drive(row.pk)
    row.refresh_from_db(); assert row.status == "paused"
    session = DiscoverySession.objects.get(run=row)
    DiscoveryCandidate.objects.create(session=session, source_id=1, discovered=True, evaluated=True, outcome="qualified", produced=True, data={"name": "Saved candidate"})
    with patch("leadzen.chat.views.launch"):
        response = identity[2].post(f"/api/discovery/{row.pk}/resume", "{}", content_type="application/json")
    assert response.status_code == 202, response.content
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 2, "partial": False}) as finder, patch("leadzen.chat.engine.decide") as planner:
        drive(row.pk)
        finder.assert_called_once_with({"count": 2, "emails": False, "audience": ""})
        planner.assert_not_called()
    row.refresh_from_db(); assert row.status == "succeeded"
    assert DiscoverySession.objects.filter(run=row).count() == 1
    assert call(identity, "get_operation", {"operationId": str(row.pk)})["result"]["workspaceUrl"].startswith("https://leadzen.example.com/find-leads/")


def test_resume_cannot_expand_original_saved_discovery_scope(identity):
    from leadzen.config.models import DiscoverySession
    operation = call(identity, "find_leads", {"count": 3})
    row = approve(identity, operation)
    with patch("leadzen.chat.engine.find_leads", return_value={"stored": 0, "paused": True}):
        drive(row.pk)
    session = DiscoverySession.objects.get(run=row)
    forged = {**session.action, "arguments": {**session.action["arguments"], "count": 25, "emails": True}}
    ChatRun.objects.filter(pk=row.pk).update(status="queued", pending=forged)
    with patch("leadzen.chat.engine.find_leads") as finder:
        drive(row.pk)
        finder.assert_not_called()
    row.refresh_from_db(); assert row.status == "failed"
