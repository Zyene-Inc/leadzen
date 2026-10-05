import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from cold_outreach.emails.models import Mailbox, Message, Direction
from cold_outreach.leads.models import Deal, Lead, Suppression
from leadzen.config.models import EmailCampaign, CampaignRecipient, ContactPreferences, SiteConfig
from leadzen.configuration import save_dashboard_settings
from leadzen.campaigns import run_campaign


@pytest.fixture
def connected(account_client, monkeypatch):
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    save_dashboard_settings({"ai_enabled": False, "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "smtp_port": 587, "imap_host": "imap.example.com", "imap_port": 993}, mailbox_password="synthetic-mail-password")
    SiteConfig.objects.update(operator_name="Synthetic Sender")
    return account_client


def add(client, email="person@example.com", opted=False):
    response = client.post("/api/contacts", data=json.dumps({"email": email, "first_name": "Ada", "company": "Example", "opted_in": opted, "consent_note": "Synthetic signup" if opted else ""}), content_type="application/json")
    assert response.status_code == 201, response.content
    return response.json()["ids"][0]


def make(client, contact_id, category="outreach"):
    response = client.post("/api/campaigns", data=json.dumps({"name": "Synthetic campaign", "category": category, "steps": [{"subject": "Hi {{first_name}}", "body": "Hello {{company}} from {{sender_name}}", "delay_days": 0}, {"subject": "Following up", "body": "Any interest?", "delay_days": 2}], "contact_ids": [contact_id]}), content_type="application/json")
    assert response.status_code == 201, response.content
    return response.json()["id"]


def test_contact_import_is_atomic_and_suppression_survives_import(connected):
    Suppression.objects.create(email="stopped@example.com")
    deal_id = add(connected, "stopped@example.com")
    assert Deal.objects.get(pk=deal_id).state == "Completed"
    count = Lead.objects.count()
    result = connected.post("/api/contacts", data=json.dumps({"contacts": [{"email": "valid@example.com"}, {"email": "bad"}]}), content_type="application/json")
    assert result.status_code == 400 and Lead.objects.count() == count


def test_sequence_enrollment_validation_and_no_duplicate_campaign(connected):
    person = add(connected)
    identifier = make(connected, person)
    assert EmailCampaign.objects.get(pk=identifier).status == "draft"
    duplicate = connected.post("/api/campaigns", data=json.dumps({"name": "Duplicate", "contact_ids": [person], "steps": [{"subject": "Hi", "body": "Hello", "delay_days": 0}]}), content_type="application/json")
    assert duplicate.status_code == 409
    assert CampaignRecipient.objects.count() == 1
    assert connected.post("/api/campaigns", data=json.dumps({"name": "Forged", "contact_ids": [999999], "steps": [{"subject": "Hi", "body": "Hello", "delay_days": 0}]}), content_type="application/json").status_code == 404


def test_campaign_sends_once_then_waits_and_stops_after_opt_out(connected):
    person = add(connected)
    identifier = make(connected, person)
    connected.put(f"/api/campaigns/{identifier}", data='{"status":"active"}', content_type="application/json")
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver") as deliver:
        assert run_campaign(identifier, 1) == 1
        recipient = CampaignRecipient.objects.get()
        assert recipient.next_step == 1 and recipient.next_send_at > timezone.now()
        assert Message.objects.get(direction=Direction.OUTBOUND).body_text == "Hello Example from Synthetic Sender"
        assert run_campaign(identifier, 1) == 0 and deliver.call_count == 1
        connected.put(f"/api/contacts/{person}", data='{"suppress":true}', content_type="application/json")
        recipient.next_send_at = timezone.now() - timedelta(days=1)
        recipient.save()
        Mailbox.objects.update(next_send_at=None)
        assert run_campaign(identifier, 1) == 0 and deliver.call_count == 1
        assert "Sent with" not in deliver.call_args.args[1].get_content()


def test_pause_and_sending_window_prevent_delivery(connected):
    identifier = make(connected, add(connected))
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        with pytest.raises(ValueError):
            run_campaign(identifier, 1)
        EmailCampaign.objects.filter(pk=identifier).update(status="active")
        with patch("cold_outreach.core.sending_window.within_sending_window", return_value=False):
            assert run_campaign(identifier, 1) == 0
        deliver.assert_not_called()


def test_provider_failure_is_not_automatically_retried(connected):
    identifier = make(connected, add(connected))
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver", side_effect=OSError("synthetic failure")) as deliver:
        with pytest.raises(OSError):
            run_campaign(identifier, 1)
        assert CampaignRecipient.objects.get().status == "review"
        assert run_campaign(identifier, 1) == 0 and deliver.call_count == 1


def test_resend_refuses_unconsented_campaign_before_network(connected):
    person = add(connected)
    save_dashboard_settings({"ai_enabled": False, "mail_transport": "resend", "mailbox_address": "sender@example.com"}, mail_api_key="synthetic-api-key")
    with patch("leadzen.email_api.post_email") as send:
        response = connected.post("/api/campaigns", data=json.dumps({"name": "Test", "category": "opted_in", "contact_ids": [person], "steps": [{"subject": "Hi", "body": "Hello", "delay_days": 0}]}), content_type="application/json")
        assert response.status_code == 400
        send.assert_not_called()


def test_follow_up_requires_successful_reply_sync(connected):
    identifier = make(connected, add(connected))
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver") as deliver:
        run_campaign(identifier, 1)
        CampaignRecipient.objects.update(next_send_at=timezone.now() - timedelta(days=1))
        Mailbox.objects.update(next_send_at=None)
        with patch("leadzen.transports.sync_replies_strict", side_effect=ValueError("inbox unavailable")):
            with pytest.raises(ValueError):
                run_campaign(identifier, 1)
        assert deliver.call_count == 1 and CampaignRecipient.objects.get().next_step == 1


def test_draft_editing_is_blocked_after_activation(connected):
    identifier = make(connected, add(connected))
    changes = {"name": "Updated draft", "steps": [{"subject": "Updated", "body": "Hello {{first_name}}", "delay_days": 0}]}
    assert connected.put(f"/api/campaigns/{identifier}", data=json.dumps(changes), content_type="application/json").status_code == 200
    connected.put(f"/api/campaigns/{identifier}", data='{"status":"active"}', content_type="application/json")
    changes["name"] = "Forbidden change"
    assert connected.put(f"/api/campaigns/{identifier}", data=json.dumps(changes), content_type="application/json").status_code == 409
    assert EmailCampaign.objects.get(pk=identifier).name == "Updated draft"


def test_opt_in_revocation_between_claim_and_transport_prevents_send(connected):
    identifier = make(connected, add(connected, opted=True), category="opted_in")
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    from cold_outreach.emails import sender
    original = sender._record_send
    def revoke(*args, **kwargs):
        row = original(*args, **kwargs)
        ContactPreferences.objects.update(opted_in=False)
        return row
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._record_send", side_effect=revoke), patch("cold_outreach.emails.sender._deliver") as deliver:
        with pytest.raises(PermissionError, match="opt-in was withdrawn"):
            run_campaign(identifier, 1)
        deliver.assert_not_called()
        assert CampaignRecipient.objects.get().status == "review"


def test_delete_hides_contact_stops_queue_and_preserves_opt_out_history(connected):
    person = add(connected, opted=True)
    identifier = make(connected, person)
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver") as deliver:
        assert run_campaign(identifier, 1) == 1
        connected.put(f"/api/contacts/{person}", data='{"suppress":true}', content_type="application/json")
        assert connected.delete(f"/api/contacts/{person}").status_code == 200
        assert connected.get("/api/leads").json()["total"] == 0
        assert connected.get("/api/overview").json()["leads"]["total"] == 0
        assert Message.objects.count() == 1
        assert Suppression.objects.filter(email="person@example.com").exists()
        assert Deal.objects.get(pk=person).outcome == "unsubscribed"
        assert ContactPreferences.objects.get().opted_in is True
        assert run_campaign(identifier, 1) == 0 and deliver.call_count == 1
    assert connected.delete(f"/api/contacts/{person}").status_code == 200
    assert connected.put(f"/api/contacts/{person}", data='{"email":"person@example.com"}', content_type="application/json").status_code == 404
    assert connected.post("/api/contacts", data='{"email":"person@example.com"}', content_type="application/json").status_code == 409


def test_stop_keeps_contact_visible_and_blocks_campaign_send(connected):
    person = add(connected)
    identifier = make(connected, person)
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    assert connected.put(f"/api/contacts/{person}", data='{"stop":true}', content_type="application/json").status_code == 200
    assert connected.get("/api/leads").json()["total"] == 1
    assert Deal.objects.get(pk=person).state == "Completed"
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        assert run_campaign(identifier, 1) == 0
        deliver.assert_not_called()


def test_delete_between_claim_and_send_blocks_delivery(connected):
    person = add(connected)
    identifier = make(connected, person)
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    from cold_outreach.emails import sender
    original = sender._record_send
    def remove(*args, **kwargs):
        row = original(*args, **kwargs)
        assert connected.delete(f"/api/contacts/{person}").status_code == 200
        return row
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch.object(sender, "_record_send", side_effect=remove), patch.object(sender, "_deliver") as deliver:
        with pytest.raises(PermissionError):
            run_campaign(identifier, 1)
        deliver.assert_not_called()


def test_delete_is_hidden_from_chat_and_cannot_be_sent_by_autonomous_worker(connected):
    from email.message import EmailMessage
    from cold_outreach.emails import sender
    from leadzen.chat.engine import execute
    from leadzen.workspaces import guard_worker_sends
    person = add(connected)
    connected.delete(f"/api/contacts/{person}")
    assert execute("list_leads", {}, None)["items"] == []
    message = EmailMessage()
    message["To"] = "person@example.com"
    with patch.object(sender, "_deliver") as deliver:
        guard_worker_sends()
        with pytest.raises(PermissionError, match="deleted"):
            sender._deliver(None, message, None)
        deliver.assert_not_called()


def test_delete_during_provider_delivery_does_not_restore_queued_outreach(connected):
    person = add(connected)
    identifier = make(connected, person)
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    def remove(*args):
        # Already-accepted mail cannot be undone; completion must not revive the
        # contact or queue another follow-up when delete wins during delivery.
        assert connected.delete(f"/api/contacts/{person}").status_code == 200
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver", side_effect=remove):
        assert run_campaign(identifier, 1) == 1
    assert Deal.objects.get(pk=person).state == "Completed"
    assert CampaignRecipient.objects.get().status == "stopped"
    assert connected.get("/api/leads").json()["items"] == []


def offer_body(person):
    return {"name": "Dental Practice Outreach", "target": "Dental owners and marketing managers", "product": "AI reputation management", "booking_link": "https://example.com/demo?team=dental", "signature": "Ashish Dikonda\nZyene", "delay_basis": "working_days", "contact_ids": [person], "steps": [
        {"subject": "Hi {{first_name}}", "body": "Demo: {{booking_link}}", "delay_days": 0},
        {"subject": "Following up", "body": "Any interest?", "delay_days": 3},
        {"subject": "Final follow-up", "body": "Last note", "delay_days": 5}]}


def test_campaign_offer_fields_are_saved_edited_and_used_in_actual_message(connected):
    from leadzen.chat.engine import prepare
    from leadzen.config.models import ChatThread, ChatRun
    from django.contrib.auth import get_user_model
    import uuid
    body = offer_body(add(connected))
    response = connected.post("/api/campaigns", data=json.dumps(body), content_type="application/json")
    assert response.status_code == 201, response.content
    data = response.json()
    for key in ("target", "product", "booking_link", "signature", "delay_basis"):
        assert data[key] == body[key]
    actor = get_user_model().objects.get(email="unit@example.com")
    thread = ChatThread.objects.create(actor_id=actor.pk)
    run = ChatRun.objects.create(thread=thread, actor_id=actor.pk, request_id=uuid.uuid4())
    from leadzen.config.models import ChatMessage
    ChatMessage.objects.create(thread=thread, role="user", content="Send this campaign after I confirm the exact recipients and messages.")
    prepare(run, "send_campaign", {"campaign_id": data["id"], "count": 1})
    run.refresh_from_db()
    preview = run.pending["preview"]["recipients"][0]["body"]
    assert "https://example.com/demo" in preview and "Ashish Dikonda\nZyene" in preview
    assert "Reply" in preview and "stop" in preview
    connected.put(f"/api/campaigns/{data['id']}", data='{"status":"active"}', content_type="application/json")
    from datetime import datetime
    from zoneinfo import ZoneInfo
    friday = datetime(2026, 10, 2, 16, tzinfo=ZoneInfo("America/New_York"))
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver") as deliver, patch("leadzen.campaigns.timezone.now", return_value=friday):
        assert run_campaign(data["id"], 1) == 1
        message = deliver.call_args.args[1].get_content()
        assert "Ashish Dikonda\nZyene" in message and "https://example.com/demo" in message
        assert Mailbox.objects.get().signature != body["signature"]
        due = CampaignRecipient.objects.get().next_send_at
        assert timezone.localtime(due, ZoneInfo("America/New_York")).date().isoformat() == "2026-10-07"


@pytest.mark.parametrize("field,value", [("booking_link", "javascript:alert(1)"), ("booking_link", "https://user:pass@example.com"), ("booking_link", "https://example.com/\nBcc:bad"), ("signature", "x" * 2001), ("delay_basis", "unknown"), ("target", ["bad"]), ("product", "x" * 2001)])
def test_campaign_offer_inputs_are_bounded_before_save(connected, field, value):
    body = offer_body(add(connected))
    body[field] = value
    assert connected.post("/api/campaigns", data=json.dumps(body), content_type="application/json").status_code == 400
    assert not EmailCampaign.objects.exists()


def test_new_campaigns_allow_only_two_followups_and_legacy_calendar_delay_is_preserved(connected):
    body = offer_body(add(connected))
    body["steps"].append({"subject": "Extra", "body": "Extra", "delay_days": 1})
    assert connected.post("/api/campaigns", data=json.dumps(body), content_type="application/json").status_code == 400
    identifier = make(connected, body["contact_ids"][0])
    assert EmailCampaign.objects.get(pk=identifier).delay_basis == "calendar_days"
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver"):
        EmailCampaign.objects.filter(pk=identifier).update(status="active")
        assert run_campaign(identifier, 1) == 1
        assert abs((CampaignRecipient.objects.get().next_send_at - timezone.now()).total_seconds() - 2 * 86400) < 3


def test_campaign_metadata_edit_invalidates_approved_snapshot(connected):
    from leadzen.chat.engine import snapshot
    person = add(connected)
    response = connected.post("/api/campaigns", data=json.dumps(offer_body(person)), content_type="application/json")
    assert response.status_code == 201
    campaign = EmailCampaign.objects.get(pk=response.json()["id"])
    args = {"campaign_id": str(campaign.pk), "recipient_ids": list(campaign.recipients.values_list("pk", flat=True))}
    original = snapshot("send_campaign", args)
    assert connected.put(f"/api/campaigns/{campaign.pk}", data='{"signature":"Updated signature"}', content_type="application/json").status_code == 200
    assert snapshot("send_campaign", args) != original
    connected.put(f"/api/campaigns/{campaign.pk}", data='{"status":"active"}', content_type="application/json")
    assert connected.put(f"/api/campaigns/{campaign.pk}", data='{"booking_link":"https://example.com/changed"}', content_type="application/json").status_code == 409


def test_readonly_send_review_freezes_exact_content_and_double_submit_queues_once(connected):
    import uuid
    from leadzen.config.models import OutreachJob
    identifier = make(connected, add(connected))
    connected.put(f"/api/campaigns/{identifier}", data='{"status":"active"}', content_type="application/json")
    with patch("leadzen.web._launch_job") as launch:
        review = connected.get(f"/api/campaigns/{identifier}/preview?count=1")
        assert review.status_code == 200, review.content
        assert "Ada" in review.json()["recipients"][0]["subject"]
        assert "stop" in review.json()["recipients"][0]["body"]
        assert not OutreachJob.objects.exists()
        launch.assert_not_called()
    body = {"count": 1, "request_id": str(uuid.uuid4()), "revision": review.json()["revision"]}
    from django.http import JsonResponse
    with patch("leadzen.web._launch_job", side_effect=lambda request, job: JsonResponse({"job": {"id": str(job.pk)}}, status=202)) as launch:
        response = connected.post(f"/api/campaigns/{identifier}/run", data=json.dumps(body), content_type="application/json")
        assert response.status_code == 202
        replay = connected.post(f"/api/campaigns/{identifier}/run", data=json.dumps(body), content_type="application/json")
        assert replay.status_code == 202 and replay.json()["job"]["id"] == response.json()["job"]["id"]
        launch.assert_called_once()
    job = OutreachJob.objects.get()
    assert job.campaign_approval["recipient_ids"] == [CampaignRecipient.objects.get().pk]
    assert job.campaign_approval["snapshot"] and job.campaign_approval["expires_at"]


def test_stale_campaign_send_review_denied_and_working_days_cross_dst(connected):
    import uuid
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from leadzen.campaigns import next_send_time
    person = add(connected)
    response = connected.post("/api/campaigns", data=json.dumps(offer_body(person)), content_type="application/json")
    campaign = EmailCampaign.objects.get(pk=response.json()["id"])
    campaign.status, campaign.delay_timezone = "active", "America/New_York"
    campaign.save()
    review = connected.get(f"/api/campaigns/{campaign.pk}/preview?count=1")
    assert review.status_code == 200
    EmailCampaign.objects.filter(pk=campaign.pk).update(signature="Changed since review")
    with patch("leadzen.web._launch_job") as launch:
        result = connected.post(f"/api/campaigns/{campaign.pk}/run", data=json.dumps({"count": 1, "revision": review.json()["revision"], "request_id": str(uuid.uuid4())}), content_type="application/json")
        assert result.status_code == 409
        launch.assert_not_called()
    friday = datetime(2026, 10, 30, 16, tzinfo=ZoneInfo("America/New_York"))
    due = next_send_time(campaign, friday, 3)
    assert due.isoformat() == "2026-11-04T16:00:00-05:00"
    final = next_send_time(campaign, due, 5)
    assert final.isoformat() == "2026-11-11T16:00:00-05:00"


@pytest.mark.parametrize("change", ["signature", "expired", "optout", "missing_approval"])
def test_queued_campaign_revalidates_review_at_worker_sink(connected, change):
    import uuid
    from leadzen.config.models import OutreachJob
    from leadzen.campaigns import approved_job_guard
    from django.http import JsonResponse
    identifier = make(connected, add(connected))
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    review = connected.get(f"/api/campaigns/{identifier}/preview?count=1").json()
    with patch("leadzen.web._launch_job", return_value=JsonResponse({}, status=202)):
        assert connected.post(f"/api/campaigns/{identifier}/run", data=json.dumps({"count": 1, "request_id": str(uuid.uuid4()), "revision": review["revision"]}), content_type="application/json").status_code == 202
    job = OutreachJob.objects.get()
    job.status = "running"
    job.save()
    approved_job_guard(job)
    if change == "signature":
        EmailCampaign.objects.filter(pk=identifier).update(signature="Changed")
    elif change == "optout":
        Suppression.objects.create(email="person@example.com")
    else:
        job.campaign_approval = {} if change == "missing_approval" else {**job.campaign_approval, "expires_at": (timezone.now() - timedelta(minutes=1)).isoformat()}
        job.save()
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        with pytest.raises(PermissionError):
            approved_job_guard(job)
        deliver.assert_not_called()


def test_campaign_worker_claim_cannot_be_replayed_and_uses_saved_limit(connected):
    from contextlib import nullcontext
    from leadzen.config.models import OutreachJob
    from leadzen.web_worker import main
    from leadzen.chat.engine import snapshot
    identifier = make(connected, add(connected))
    EmailCampaign.objects.filter(pk=identifier).update(status="active")
    ids = [CampaignRecipient.objects.get().pk]
    job = OutreachJob.objects.create(kind="campaign", campaign_id=identifier, requested_count=1,
        campaign_approval={"recipient_ids": ids, "expires_at": (timezone.now() + timedelta(minutes=15)).isoformat(),
                           "snapshot": snapshot("send_campaign", {"campaign_id": identifier, "recipient_ids": ids}, execution=True)})
    with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.ai.install_engine_adapters"), patch("leadzen.wizard.apply_to_environment"), patch("leadzen.campaigns.run_campaign", return_value=0) as sender:
        assert main(str(job.pk), 999) == 0
        assert main(str(job.pk), 999) == 0
        assert sender.call_count == 1
        assert str(sender.call_args.args[0]) == str(job.campaign_id) and sender.call_args.args[1] == 1
        assert sender.call_args.kwargs["recipient_ids"] == ids
    job.refresh_from_db()
    assert job.status == "succeeded"
