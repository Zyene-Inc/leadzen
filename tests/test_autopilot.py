"""Standing authorization, budget, restart and transport boundaries; synthetic only."""
import json
import uuid
from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from cold_outreach.emails.models import Mailbox, Message, Direction
from cold_outreach.leads.models import Deal, Suppression
from leadzen.config.models import AutopilotPolicy, AutopilotRun, CampaignRecipient, EmailCampaign, SiteConfig
from leadzen import autopilot
from leadzen.autopilot_worker import deliver_due, workspace_tick
from test_campaigns import connected, add, make

NOW = datetime(2026, 10, 5, 14, tzinfo=ZoneInfo("UTC"))  # Monday, 10 AM New York


def policy(actor=1, **scope):
    values = {k: default for k, (_, _, default) in autopilot.LIMITS.items()}
    values.update(timezone="America/New_York", followup_days=[3, 5], tone="Brief", sender="sender@example.com",
                  target="Restaurants", product="Reviews", signature="Sender", booking_link="")
    values.update(scope)
    return AutopilotPolicy.objects.create(actor_id=actor, scope=values, setup_hash=autopilot.setup_hash(), expires_at=NOW + timedelta(days=30))


def setup_run(client, **scope):
    identifier = make(client, add(client))
    p = policy(**scope)
    run = AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(), phase="sending",
        checkpoint={"delivery_authorized": True, "contact_limit": 10}, deadline_at=NOW + timedelta(minutes=12))
    campaign = EmailCampaign.objects.get(pk=identifier)
    campaign.autopilot_run = run
    campaign.status = "active"
    campaign.delay_timezone = p.scope["timezone"]
    campaign.save()
    recipient = campaign.recipients.select_related("deal__lead").get()
    recipient.personal_steps = [{"subject": "Personal Ada", "body": "A specific note for Ada", "delay_days": 0},
                                {"subject": "Personal followup", "body": "A follow-up for Ada", "delay_days": 3}]
    recipient.authorization_hash = autopilot.recipient_hash(campaign, recipient)
    recipient.save()
    return p, run, campaign, recipient


@pytest.fixture(autouse=True)
def enable_service(monkeypatch):
    monkeypatch.setenv("LEADZEN_AUTOPILOT_ENABLED", "1")


def test_read_and_enable_never_call_providers_and_require_explicit_scope(connected):
    from leadzen.configuration import save_dashboard_settings
    save_dashboard_settings({"ai_enabled": True, "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "imap_host": "imap.example.com", "smtp_port": 587, "imap_port": 993}, llm_api_key="synthetic", bettercontact_api_key="synthetic", mailbox_password="synthetic")
    SiteConfig.objects.update(product_docs="Our offer", campaign_target="Restaurants", operator_email="sender@example.com", operator_country_code="US", accepted_legal_notice=True)
    # Provider/model fixture readiness is supplied locally, with no connection tests.
    with patch("leadzen.discovery.context", return_value={"blockers": []}), patch("leadzen.ai.pinned_open") as provider:
        initial = connected.get("/api/autopilot").json()
        assert initial["policy"] is None
        body = {"enabled": True, "timezone": "America/New_York", "revision": initial["setup"]["revision"], "request_id": str(uuid.uuid4())}
        assert connected.post("/api/autopilot", json.dumps(body), content_type="application/json").status_code == 400
        body["authorize_automatic_outreach"] = True
        result = connected.post("/api/autopilot", json.dumps(body), content_type="application/json")
        assert result.status_code == 200, result.content
        assert connected.post("/api/autopilot", json.dumps(body), content_type="application/json").status_code == 200
        assert AutopilotPolicy.objects.count() == 1
        assert not AutopilotRun.objects.exists()
        assert "synthetic" not in result.content.decode()
        provider.assert_not_called()


@pytest.mark.parametrize("mutation", ["off", "expired", "setup", "wrong_actor", "service", "copy", "identity", "outside", "old_day", "unvalidated"])
def test_sink_rejects_changed_or_revoked_authorization(connected, monkeypatch, mutation):
    p, run, campaign, recipient = setup_run(connected)
    if mutation == "off": AutopilotPolicy.objects.update(enabled=False)
    if mutation == "expired": AutopilotPolicy.objects.update(expires_at=NOW - timedelta(seconds=1))
    if mutation == "setup": SiteConfig.objects.update(product_docs="Different product")
    if mutation == "wrong_actor": monkeypatch.setenv("LEADZEN_ACTOR_ID", "999")
    if mutation == "service": monkeypatch.setenv("LEADZEN_AUTOPILOT_ENABLED", "0")
    if mutation == "copy": CampaignRecipient.objects.update(personal_steps=[{"subject": "Changed", "body": "Changed", "delay_days": 0}])
    if mutation == "identity":
        recipient.deal.lead.email = "changed@example.com"
        recipient.deal.lead.save()
    if mutation == "old_day": AutopilotRun.objects.update(workday=NOW.date() - timedelta(days=1))
    if mutation == "unvalidated": AutopilotRun.objects.update(checkpoint={})
    when = NOW.replace(hour=23) if mutation == "outside" else NOW
    with patch("django.utils.timezone.now", return_value=when), pytest.raises(PermissionError):
        autopilot.send_guard(campaign, recipient)


def test_personalized_initial_and_followup_use_existing_send_engine(connected):
    p, run, campaign, recipient = setup_run(connected)
    with patch("django.utils.timezone.now", return_value=NOW), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict") as sync, patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        assert send.call_count == 1
        assert str(send.call_args.args[1]["Subject"]) == "Personal Ada"
        deliver_due(p)
        assert send.call_count == 1
        sync.assert_called_once()
    recipient.refresh_from_db()
    assert recipient.next_step == 1 and recipient.status == "pending"
    Mailbox.objects.update(next_send_at=None)
    with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=3)), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        assert send.call_count == 1
        assert str(send.call_args.args[1]["Subject"]) == "Personal followup"
    assert not campaign.followup_approval  # Never fabricate human approval.


@pytest.mark.parametrize("reason", ["reply", "suppressed", "inbox_failure", "uncertain", "off_at_sink"])
def test_reply_optout_failure_and_last_second_stop_block_sends(connected, reason):
    from cold_outreach.emails import sender
    p, run, campaign, recipient = setup_run(connected)
    if reason == "suppressed": Suppression.objects.create(email=recipient.deal.lead.email)
    def sync(*args, **kwargs):
        if reason == "inbox_failure": raise OSError("offline")
        if reason == "reply":
            # Save inbound against the deal's canonical thread before the send.
            from cold_outreach.emails.models import Thread
            thread = Thread.objects.create(mailbox=Mailbox.objects.get())
            Deal.objects.filter(pk=recipient.deal_id).update(thread=thread)
            Message.objects.create(mailbox=Mailbox.objects.get(), thread=thread, direction=Direction.INBOUND,
                message_id="reply", from_address=recipient.deal.lead.email, to_address=campaign.from_address, subject="Reply", body_text="Stop")
    original = sender._record_send
    def record(*args, **kwargs):
        row = original(*args, **kwargs)
        if reason == "off_at_sink": autopilot.disable(p)
        return row
    with patch("django.utils.timezone.now", return_value=NOW), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("leadzen.transports.sync_replies_strict", side_effect=sync), patch.object(sender, "_record_send", side_effect=record), patch.object(sender, "_deliver", side_effect=OSError("unknown") if reason == "uncertain" else None) as send:
        deliver_due(p)
        if reason != "off_at_sink": deliver_due(p)
        assert send.call_count == (1 if reason == "uncertain" else 0)


def test_budget_reservations_survive_errors_and_span_policy_versions(connected):
    p = policy(daily_ai_requests=2, monthly_ai_requests=3, daily_credits=1, monthly_credits=1)
    run = AutopilotRun.objects.create(policy=p, actor_id=1, workday=NOW.date(), deadline_at=NOW + timedelta(minutes=10))
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.execution(run):
        autopilot.external_guard(reserve_model=True, reserve_credit=True)
        autopilot.external_guard(reserve_model=True)
        with pytest.raises(PermissionError): autopilot.external_guard(reserve_model=True)
        with pytest.raises(PermissionError): autopilot.external_guard(reserve_credit=True)
    run.refresh_from_db()
    assert run.model_requests == 2 and run.email_credits == 1
    autopilot.disable(p)
    newer = policy(daily_ai_requests=2, monthly_ai_requests=3, daily_credits=1, monthly_credits=1)
    later = AutopilotRun.objects.create(policy=newer, actor_id=1, workday=NOW.date() + timedelta(days=1), deadline_at=NOW + timedelta(days=1, minutes=10))
    with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)), autopilot.execution(later):
        autopilot.external_guard(reserve_model=True)
        with pytest.raises(PermissionError): autopilot.external_guard(reserve_model=True)
        with pytest.raises(PermissionError): autopilot.external_guard(reserve_credit=True)


@pytest.mark.parametrize("when,expected", [(NOW, 1), (NOW.replace(hour=13), 0), (NOW.replace(hour=17), 0), (NOW + timedelta(days=5), 0)])
def test_scheduler_workdays_catchup_and_duplicate_ticks(connected, when, expected):
    p = policy()
    def prepared(run):
        from leadzen.autopilot_worker import checkpoint
        checkpoint(run, "completed")
    with patch("django.utils.timezone.now", return_value=when), patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.autopilot_worker.prepare", side_effect=prepared) as prepare:
        workspace_tick()
        workspace_tick()
        assert prepare.call_count == expected
        assert AutopilotRun.objects.count() == expected
    p.refresh_from_db()
    assert p.heartbeat_at == when


def test_dst_schedule_and_weekend(connected):
    p = policy()
    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 30, 16, tzinfo=ZoneInfo("UTC"))):
        start = autopilot.next_start(p)
        assert start.hour == 10 and str(start.date()) == "2026-11-02"
        assert start.utcoffset() == timedelta(hours=-5)


def test_off_stops_pending_and_cannot_restart_same_day_with_new_policy(connected):
    p, run, campaign, recipient = setup_run(connected)
    autopilot.disable(p)
    recipient.refresh_from_db()
    assert recipient.status == "stopped"
    newer = policy()
    with pytest.raises(IntegrityError), transaction.atomic():
        AutopilotRun.objects.create(policy=newer, actor_id=1, workday=run.workday)


def test_shared_preview_renders_exact_personal_sequence(connected):
    from leadzen.campaigns import sending_preview
    p, run, campaign, recipient = setup_run(connected)
    preview = sending_preview(campaign, 1)
    assert preview["recipients"][0]["subject"] == "Personal Ada"
    assert preview["recipients"][0]["followups"][0]["subject"] == "Personal followup"


def test_complete_daily_pipeline_uses_only_today_verified_results(connected):
    from leadzen.config.models import DiscoveryCandidate, DiscoveryLookup, EmailReview
    from leadzen.discovery_progress import current
    from openoutfind.crm.models import Lead as Source
    from leadzen.autopilot_worker import prepare, checkpoint
    # Existing ready contacts must never leak into today's automation.
    add(connected, "yesterday@example.com")
    Source.objects.create(profile_url="https://example.com/old", full_name="Yesterday")
    p = policy()
    run = AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(),
        checkpoint={"contact_limit": 2}, deadline_at=NOW + timedelta(minutes=12))
    def finder(args):
        monitor = current()
        if not args["emails"]:
            for index in range(2):
                source = Source.objects.create(profile_url=f"https://example.com/today{index}", full_name=f"Today {index}")
                DiscoveryCandidate.objects.create(session=monitor.session, source_id=source.pk, discovered=True, produced=True, outcome="qualified")
        else:
            assert len(monitor.session.source_ids) == 2
            for index, source_id in enumerate(monitor.session.source_ids):
                autopilot.external_guard(reserve_credit=True)
                from cold_outreach.leads.models import Lead
                lead = Lead.objects.create(lead_id=str(source_id), email=f"today{index}@example.com", first_name="Ada", company="Example")
                deal = Deal.objects.create(lead=lead)
                DiscoveryCandidate.objects.create(session=monitor.session, source_id=source_id, contact_id=deal.pk,
                    produced=True, outcome="qualified", data={"email": deal.lead.email})
                DiscoveryLookup.objects.create(session=monitor.session, source_id=source_id, state="terminated", credits=1,
                    email_status="valid" if index == 0 else "invalid")
        return {"partial": False}
    def generate(review, drafts):
        autopilot.external_guard(reserve_model=True)
        return [{"id": str(d.pk), "subject": f"For {d.deal.lead.email}", "body": "Personal message"} for d in drafts]
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.chat.engine.find_leads", side_effect=finder), patch("leadzen.outreach.generate", side_effect=generate), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver") as send:
        with autopilot.execution(run): prepare(run)
        deliver_due(p)
        assert send.call_count == 1
        assert str(send.call_args.args[1]["To"]) == "today0@example.com"
    run.refresh_from_db()
    assert run.phase == "completed" and run.email_credits == 2 and run.model_requests == 1
    recipient = CampaignRecipient.objects.get()
    assert len(recipient.personal_steps) == 3 and recipient.next_step == 1
    assert not EmailReview.objects.exists()


def test_interrupted_preparation_is_held_without_repeating_paid_work(connected):
    from leadzen.config.models import ChatRun, ChatThread
    p = policy()
    thread = ChatThread.objects.create(actor_id=p.actor_id, title="Autopilot")
    discovery = ChatRun.objects.create(actor_id=p.actor_id, thread=thread, request_id=uuid.uuid4(), status="running")
    run = AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(), phase="enriching",
        email_credits=1, checkpoint={"enrichment_id": str(discovery.pk)})
    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.autopilot_worker.prepare") as prepare:
        workspace_tick()
        prepare.assert_not_called()
    run.refresh_from_db(); discovery.refresh_from_db()
    assert run.phase == "needs_attention" and run.email_credits == 1 and discovery.status == "failed"


def test_provider_sink_checks_off_and_reserves_before_network(connected):
    from leadzen.ai import pinned_open
    p = policy(daily_ai_requests=1)
    run = AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(), deadline_at=NOW + timedelta(minutes=10))
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.execution(run), patch("leadzen.transports.public_socket", side_effect=OSError("synthetic offline")) as network:
        with pytest.raises(Exception): pinned_open("POST", "https://api.openai.com/v1/chat/completions", {}, b"{}", "api.openai.com")
        assert network.call_count == 1
        with pytest.raises(PermissionError): pinned_open("POST", "https://api.openai.com/v1/chat/completions", {}, b"{}", "api.openai.com")
        assert network.call_count == 1
        autopilot.disable(p)
        with pytest.raises(PermissionError): pinned_open("POST", "https://api.openai.com/v1/chat/completions", {}, b"{}", "api.openai.com")
        assert network.call_count == 1


def test_dispatch_is_nonblocking_bounded_and_uses_owned_workspaces(connected, tmp_path, monkeypatch):
    from leadzen import autopilot_dispatch as dispatch
    from leadzen.workspaces import database_path
    from leadzen.accounts.models import AccountProfile
    from unittest.mock import Mock
    monkeypatch.setattr(dispatch, "_workers", {})
    monkeypatch.setattr(dispatch, "_cursor", 0)
    monkeypatch.setenv("LEADZEN_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    profile = AccountProfile.objects.select_related("user").get()
    path = database_path(profile)
    path.parent.mkdir(parents=True); path.touch()
    process = Mock()
    process.poll.return_value = None
    with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.autopilot_dispatch.subprocess.Popen", return_value=process) as launch:
        dispatch.tick()
        dispatch.tick()
        launch.assert_called_once()
        env = launch.call_args.kwargs["env"]
        assert env["LEADZEN_DB"] == str(path) and env["LEADZEN_ACTOR_ID"] == str(profile.user_id)
        assert "LEADZEN_DASHBOARD_TOKEN" not in env
        process.wait.assert_not_called()  # One slow employee never blocks the control tick.
        dispatch._workers[profile.pk] = (process, -10000)
        dispatch.tick()
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)


def test_smtp_data_boundary_rechecks_autopilot_after_connection(connected):
    from leadzen.transports import smtp_class
    from unittest.mock import Mock
    p, run, campaign, recipient = setup_run(connected)
    base = type("FakeSMTP", (), {"sendmail": Mock()})
    smtp = smtp_class(base)()
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.delivery_scope(campaign, recipient):
        autopilot.disable(p)
        with pytest.raises(PermissionError): smtp.sendmail("from", ["to"], "message")
    base.sendmail.assert_not_called()


def test_manual_send_endpoint_cannot_reauthorize_autopilot(connected):
    p, run, campaign, recipient = setup_run(connected)
    result = connected.post(f"/api/campaigns/{campaign.pk}/run", data=json.dumps({"count": 1, "request_id": str(uuid.uuid4())}), content_type="application/json")
    assert result.status_code == 409
    assert not campaign.followup_approval


def test_autopilot_uses_authorized_timezone_instead_of_manual_country_window(connected):
    p, run, campaign, recipient = setup_run(connected)
    with patch("django.utils.timezone.now", return_value=NOW), patch("cold_outreach.core.sending_window.within_sending_window", return_value=False), patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as send:
        deliver_due(p)
        send.assert_called_once()


def test_personal_followups_remain_visible_in_canonical_lead_timeline(connected):
    from leadzen.timeline import outreach_timeline
    p, run, campaign, recipient = setup_run(connected)
    timeline = outreach_timeline(recipient.deal)
    assert len(timeline["sequences"][0]["steps"]) == 2
    assert timeline["sequences"][0]["automatic"]
    assert timeline["sequences"][0]["steps"][0]["subject"] == "Personal Ada"


@pytest.mark.parametrize("stop_kind", ["cancel", "pause"])
def test_stopping_discovery_cannot_continue_to_drafting_or_sending(connected, stop_kind):
    from leadzen.autopilot_worker import prepare
    from leadzen.config.models import ChatRun
    from leadzen.discovery_progress import current
    p = policy()
    run = AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(),
        checkpoint={"contact_limit": 2}, deadline_at=NOW + timedelta(minutes=12))
    def stop(args):
        if stop_kind == "cancel":
            ChatRun.objects.filter(pk=current().session.run_id).update(cancel_requested=True, status="cancelled")
        return {"partial": stop_kind == "cancel", "paused": stop_kind == "pause"}
    with patch("django.utils.timezone.now", return_value=NOW), autopilot.execution(run), patch("leadzen.chat.engine.find_leads", side_effect=stop), patch("leadzen.transports.sync_replies_strict"), patch("leadzen.outreach.generate") as generate, pytest.raises(PermissionError):
        prepare(run)
    generate.assert_not_called()
    assert ChatRun.objects.get().status == ("cancelled" if stop_kind == "cancel" else "failed")
    assert not EmailCampaign.objects.exists()


@pytest.mark.parametrize("interruption", [None, "off", "missing_handle"])
def test_real_async_enrichment_finishes_owned_lookup_without_resubmission(connected, interruption):
    """Exercise the pinned command/job/cycle/lookup, faking only HTTP and time.

    An async submission cannot become due in its first command pass. An older
    unrelated job must neither consume this selection's slots nor be polled.
    """
    from openoutfind.crm.models import Lead as Source, Deal as SourceDeal, DealState
    from leadzen.autopilot_worker import discover
    from leadzen.config.models import DiscoveryLookup, DiscoverySession
    from leadzen.configuration import save_dashboard_settings

    save_dashboard_settings({}, bettercontact_api_key="synthetic-async-key")
    outside = Source.objects.create(profile_url="https://www.linkedin.com/in/outside-ready", full_name="Outside ready")
    outside_ready = SourceDeal.objects.create(lead=outside, state=DealState.READY_TO_FIND_EMAIL, reason="Already qualified")
    old = Source.objects.create(profile_url="https://www.linkedin.com/in/outside-pending", full_name="Outside pending")
    outside_pending = SourceDeal.objects.create(lead=old, state=DealState.FINDING_EMAIL,
        lookup_request_id="outside-job", lookup_provider="bettercontact", not_before=NOW - timedelta(seconds=1), reason="Already qualified")
    selected = Source.objects.create(profile_url="https://www.linkedin.com/in/today-selected", full_name="Today's selected")
    selected_deal = SourceDeal.objects.create(lead=selected, state=DealState.READY_TO_FIND_EMAIL, reason="Matches today's saved target")
    p = policy()
    run = AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(),
        checkpoint={"contact_limit": 1}, deadline_at=NOW + timedelta(minutes=12))
    clock = [NOW]
    requests = []
    polls = []

    def advance(seconds):
        assert 0 < seconds <= 2
        clock[0] += timedelta(seconds=seconds)
        if interruption == "off":
            autopilot.disable(p)

    def provider(method, url, headers, content, host, **kwargs):
        assert host == "app.bettercontact.rocks"
        requests.append((method, url))
        if method == "POST":
            body = json.loads(content)
            assert url == "https://app.bettercontact.rocks/api/v2/async"
            assert body["data"][0]["linkedin_url"] == selected.profile_url
            response = {} if interruption == "missing_handle" else {"request_id": "today-owned-job"}
        else:
            assert method == "GET" and url == "https://app.bettercontact.rocks/api/v2/async/today-owned-job"
            polls.append(clock[0])
            response = {"status": "running"} if len(polls) == 1 else {
                "status": "terminated", "credits_consumed": 1,
                "data": [{"contact_email_address": "selected@example.com", "contact_email_address_status": "valid",
                          "contact_first_name": "Ada", "contact_last_name": "Selected"}],
            }
        return 200, [], json.dumps(response).encode()

    with patch("django.utils.timezone.now", side_effect=lambda: clock[0]), \
         patch("time.sleep", side_effect=advance), \
         patch("leadzen.ai.pinned_request", side_effect=provider), \
         patch("openoutfind.core.management.commands.find.ensure_database"), \
         patch("openoutfind.core.management.commands.find.check_ready"), \
         patch("openoutfind.core.management.commands.find.build_status", return_value={"next_action": {}}):
        with autopilot.execution(run):
            if interruption == "off":
                with pytest.raises(PermissionError):
                    discover(run, emails=True, source_ids=[selected.pk])
                run.refresh_from_db()
                session = DiscoverySession.objects.get(run_id=run.checkpoint["enrichment_id"])
            else:
                session = discover(run, emails=True, source_ids=[selected.pk])

    receipt = DiscoveryLookup.objects.get(session=session)
    assert receipt.source_id == selected.pk
    assert sum(method == "POST" for method, _ in requests) == 1
    run.refresh_from_db()
    session.run.refresh_from_db()
    assert run.email_credits == 1
    outside_ready.refresh_from_db(); outside_pending.refresh_from_db()
    assert outside_ready.state == DealState.READY_TO_FIND_EMAIL
    assert outside_pending.state == DealState.FINDING_EMAIL and outside_pending.lookup_request_id == "outside-job"
    if interruption:
        assert not polls and len(requests) == 1
        assert receipt.credits is None and receipt.state != "terminated"
        assert receipt.request_id == ("today-owned-job" if interruption == "off" else "")
        assert session.run.status == ("cancelled" if interruption == "off" else "failed")
        assert not session.candidates.filter(produced=True).exists()
        assert not EmailCampaign.objects.filter(autopilot_run=run).exists()
        return
    assert receipt.request_id == "today-owned-job"
    assert receipt.state == "terminated" and receipt.email_status == "valid" and receipt.credits == 1
    assert len(polls) == 2
    assert polls[0] >= NOW + timedelta(seconds=5) and polls[1] > polls[0]
    selected_deal.refresh_from_db(); selected.refresh_from_db()
    assert selected_deal.state == DealState.RESOLVED and selected.email == "selected@example.com"
    candidate = session.candidates.get(source_id=selected.pk)
    assert candidate.produced and candidate.data["email"] == selected.email and candidate.contact_id
    assert session.run.status == "succeeded"
