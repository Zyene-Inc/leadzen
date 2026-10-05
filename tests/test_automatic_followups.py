"""Automatic sequence approval and all terminal states use synthetic transports."""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.http import JsonResponse
from django.utils import timezone
from cold_outreach.emails.models import Mailbox, Message, Direction
from cold_outreach.leads.models import Deal, Suppression
from leadzen.config.models import EmailCampaign, CampaignRecipient, OutreachJob
from leadzen.campaigns import run_campaign
from leadzen.followups import authorize, guard, run_due, within_window
from test_campaigns import connected, add, make


def setup_sequence(client):
    identifier = make(client, add(client))
    campaign = EmailCampaign.objects.get(pk=identifier)
    campaign.status = "active"
    campaign.save()
    with patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver"):
        assert run_campaign(identifier, 1) == 1
    recipient = CampaignRecipient.objects.select_related("deal__lead").get()
    authorize(campaign, [recipient.pk], 1)
    CampaignRecipient.objects.update(next_send_at=timezone.now() - timedelta(days=1))
    Mailbox.objects.update(next_send_at=None)
    return campaign, recipient


@pytest.mark.parametrize("repetition", range(10))
def test_approved_followup_runs_once_and_completes(connected, repetition):
    campaign, recipient = setup_sequence(connected)
    with patch("leadzen.followups.within_window", return_value=True), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict") as sync, patch("cold_outreach.emails.sender._deliver") as deliver:
        assert run_due() == 1
        assert run_due() == 0
        deliver.assert_called_once()
        sync.assert_called_once()
    recipient.refresh_from_db()
    assert recipient.next_step == 2 and recipient.status == "completed"
    assert Message.objects.count() == 2


@pytest.mark.parametrize("change", ["paused", "archived", "stop", "suppressed", "reply", "signature", "recipient", "expired", "revoked", "identity", "not_due", "first_step", "outside_window", "inbox_failure", "account_revoked"])
def test_automatic_followups_fail_closed(connected, change):
    campaign, recipient = setup_sequence(connected)
    if change in {"paused", "archived"}:
        EmailCampaign.objects.update(status=change)
    elif change == "stop":
        connected.put(f"/api/contacts/{recipient.deal_id}", data='{"stop":true}', content_type="application/json")
    elif change == "suppressed":
        Suppression.objects.create(email=recipient.deal.lead.email)
    elif change == "reply":
        Message.objects.create(mailbox=Mailbox.objects.get(), thread=recipient.deal.thread, direction=Direction.INBOUND, message_id="inbound", from_address=recipient.deal.lead.email, to_address=campaign.from_address, subject="Re: Hello", body_text="Interested", kind="human_reply")
    elif change == "signature":
        EmailCampaign.objects.update(signature="Changed after approval")
    elif change == "recipient":
        recipient.deal.lead.first_name = "Changed"
        recipient.deal.lead.save()
    elif change == "expired":
        campaign.refresh_from_db()
        campaign.followup_approval["recipients"][str(recipient.pk)]["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
        campaign.save()
    elif change == "revoked":
        EmailCampaign.objects.update(followup_approval={})
    elif change == "identity":
        from leadzen.config.models import SiteConfig
        SiteConfig.objects.update(operator_name="Different sender")
    elif change == "not_due":
        CampaignRecipient.objects.update(next_send_at=timezone.now() + timedelta(days=1))
    elif change == "first_step":
        CampaignRecipient.objects.update(next_step=0)
    with patch("leadzen.followups.within_window", return_value=change != "outside_window"), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict", side_effect=ValueError("unavailable") if change == "inbox_failure" else None), patch("leadzen.workspaces.assert_worker_access", side_effect=PermissionError("revoked") if change == "account_revoked" else None), patch("cold_outreach.emails.sender._deliver") as deliver:
        assert run_due() == 0
        deliver.assert_not_called()


def test_uncertain_followup_is_never_retried(connected):
    campaign, recipient = setup_sequence(connected)
    with patch("leadzen.followups.within_window", return_value=True), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver", side_effect=OSError("uncertain")) as deliver:
        assert run_due() == 0
        assert run_due() == 0
        deliver.assert_called_once()
    recipient.refresh_from_db()
    assert recipient.status == "review" and recipient.next_step == 1


def test_approval_is_scoped_to_reviewed_recipients(connected, monkeypatch):
    monkeypatch.setenv("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED", "1")
    identifier = make(connected, add(connected))
    EmailCampaign.objects.update(status="active")
    review = connected.get(f"/api/campaigns/{identifier}/preview?count=1").json()
    assert review["automatic_available"] and len(review["recipients"][0]["followups"]) == 1
    assert not EmailCampaign.objects.get().followup_approval
    body = {"count": 1, "revision": review["revision"], "request_id": str(uuid.uuid4()), "automatic_followups": True}
    with patch("leadzen.web._launch_job", return_value=JsonResponse({}, status=202)) as launch:
        assert connected.post(f"/api/campaigns/{identifier}/run", data=json.dumps(body), content_type="application/json").status_code == 202
        assert connected.post(f"/api/campaigns/{identifier}/run", data=json.dumps(body), content_type="application/json").status_code == 202
        launch.assert_called_once()
    approval = EmailCampaign.objects.get().followup_approval
    assert set(approval["recipients"]) == {str(CampaignRecipient.objects.get().pk)}
    body["automatic_followups"] = False
    assert connected.post(f"/api/campaigns/{identifier}/run", data=json.dumps(body), content_type="application/json").status_code == 409


def test_disabled_service_and_forged_approval_cannot_enable_sending(connected, monkeypatch):
    monkeypatch.delenv("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED", raising=False)
    identifier = make(connected, add(connected))
    EmailCampaign.objects.update(status="active")
    review = connected.get(f"/api/campaigns/{identifier}/preview?count=1").json()
    body = {"count": 1, "revision": review["revision"], "request_id": str(uuid.uuid4()), "automatic_followups": True}
    assert connected.post(f"/api/campaigns/{identifier}/run", data=json.dumps(body), content_type="application/json").status_code == 409
    assert not OutreachJob.objects.exists() and not EmailCampaign.objects.get().followup_approval
    from leadzen.scheduler import main
    with pytest.raises(SystemExit, match="disabled"):
        main()


@pytest.mark.parametrize("weekday,hour,expected", [(2, 8, False), (2, 9, True), (2, 16, True), (2, 17, False), (3, 12, False), (4, 12, False)])
def test_automatic_window_uses_saved_local_time(connected, weekday, hour, expected):
    campaign = EmailCampaign(delay_timezone="America/New_York")
    date = datetime(2026, 10, weekday, hour, tzinfo=ZoneInfo("America/New_York"))
    with patch("leadzen.followups.timezone.now", return_value=date):
        assert within_window(campaign) is expected


def test_reply_arriving_after_claim_blocks_transport(connected):
    campaign, recipient = setup_sequence(connected)
    from cold_outreach.emails import sender
    record = sender._record_send
    def reply(*args, **kwargs):
        result = record(*args, **kwargs)
        Message.objects.create(mailbox=Mailbox.objects.get(), thread=recipient.deal.thread, direction=Direction.INBOUND, message_id="late-reply", from_address=recipient.deal.lead.email, to_address=campaign.from_address, subject="Re: Hello", body_text="Stop following up", kind="human_reply")
        return result
    with patch("leadzen.followups.within_window", return_value=True), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict"), patch.object(sender, "_record_send", side_effect=reply), patch.object(sender, "_deliver") as deliver:
        assert run_due() == 0
        deliver.assert_not_called()


def test_stop_winning_during_claim_remains_terminal(connected):
    campaign, recipient = setup_sequence(connected)
    from cold_outreach.emails import sender
    record = sender._record_send
    def stop(*args, **kwargs):
        result = record(*args, **kwargs)
        connected.put(f"/api/contacts/{recipient.deal_id}", data='{"stop":true}', content_type="application/json")
        return result
    with patch("leadzen.followups.within_window", return_value=True), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict"), patch.object(sender, "_record_send", side_effect=stop), patch.object(sender, "_deliver") as deliver:
        assert run_due() == 0
        deliver.assert_not_called()
    recipient.refresh_from_db()
    assert recipient.status == "stopped"


def test_automatic_inbox_checks_never_spend_ai_credits(connected):
    from leadzen.transports import sync_replies_strict
    from cold_outreach.emails.models import FolderCoverage
    box = Mailbox.objects.get()
    checked_at = timezone.now()
    FolderCoverage.objects.create(mailbox=box, folder="INBOX", synced_at=checked_at)
    with patch("django.utils.timezone.now", return_value=checked_at - timedelta(seconds=1)), patch("cold_outreach.emails.sync.mirror"), patch("cold_outreach.emails.classify.classify_pending") as classify, patch("cold_outreach.emails.project.project_pending") as project, patch("leadzen.outreach.honor_saved_optouts") as honor:
        sync_replies_strict(box, classify=False)
        classify.assert_not_called()
        project.assert_not_called()
        honor.assert_called_once_with(box)


def test_unclassified_exact_stop_is_terminal_without_ai(connected):
    campaign, recipient = setup_sequence(connected)
    from leadzen.outreach import honor_saved_optouts
    box = Mailbox.objects.get()
    Message.objects.create(mailbox=box, thread=recipient.deal.thread, direction=Direction.INBOUND, message_id="stop-without-ai", from_address=recipient.deal.lead.email, to_address=campaign.from_address, subject="Re: Hello", body_text="STOP", kind="")
    honor_saved_optouts(box)
    assert Suppression.objects.filter(email=recipient.deal.lead.email).exists()
    recipient.refresh_from_db()
    assert recipient.status == "stopped"


def test_scheduler_dispatches_only_server_owned_workspace_destinations(connected, tmp_path, monkeypatch):
    from leadzen.scheduler import tick
    from leadzen.workspaces import database_path
    from leadzen.accounts.models import AccountProfile
    from contextlib import nullcontext
    monkeypatch.setenv("LEADZEN_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    profile = AccountProfile.objects.select_related("user").get()
    path = database_path(profile)
    path.parent.mkdir(parents=True)
    path.touch()
    with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.scheduler.subprocess.run") as launch:
        tick()
        launch.assert_called_once()
        env = launch.call_args.kwargs["env"]
        assert env["LEADZEN_DB"] == str(path)
        assert env["LEADZEN_ACTOR_ID"] == str(profile.user_id)
        assert env["LEADZEN_WORKSPACE_ID"] == str(profile.pk)
        assert "LEADZEN_DASHBOARD_TOKEN" not in env
    profile.user.is_active = False
    profile.user.save()
    with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.scheduler.subprocess.run") as launch:
        tick()
        launch.assert_not_called()


@pytest.mark.parametrize("dispatcher", ["leadzen.scheduler", "leadzen.autopilot_dispatch"])
@pytest.mark.parametrize("hold_at_entry", [True, False])
def test_scheduler_hold_prevents_new_children_at_entry_and_between_employees(connected, tmp_path, monkeypatch, dispatcher, hold_at_entry):
    import importlib
    from contextlib import nullcontext
    from leadzen.accounts.models import AccountProfile
    from leadzen.workspaces import database_path
    module = importlib.import_module(dispatcher)
    if hasattr(module, "_workers"):
        monkeypatch.setattr(module, "_workers", {})
    monkeypatch.setenv("LEADZEN_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    profile = AccountProfile.objects.select_related("user").get()
    path = database_path(profile)
    path.parent.mkdir(parents=True)
    path.touch()
    with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), \
         patch("leadzen.operations.maintenance.maintenance_active", side_effect=[True] if hold_at_entry else [False, True]), \
         patch(dispatcher + ".subprocess.run") as run, patch(dispatcher + ".subprocess.Popen") as launch:
        module.tick()
        run.assert_not_called()
        launch.assert_not_called()


def test_expired_worker_recovery_preserves_uncertain_send_and_does_not_replay(connected):
    from leadzen.web import recover_expired_jobs
    campaign, recipient = setup_sequence(connected)
    CampaignRecipient.objects.update(status="sending")
    job = OutreachJob.objects.create(kind="campaign", campaign_id=campaign.pk, requested_count=1, status="running", campaign_approval={"recipient_ids": [recipient.pk]})
    OutreachJob.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(minutes=21))
    with patch("cold_outreach.emails.sender._deliver") as deliver:
        recover_expired_jobs()
        recover_expired_jobs()
        deliver.assert_not_called()
    job.refresh_from_db(); recipient.refresh_from_db()
    assert job.status == "failed" and recipient.status == "review"
    assert Message.objects.count() == 1
