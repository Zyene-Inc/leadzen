"""One New York business clock across stored schedules, ledgers and legacy workers."""
import hashlib
import importlib
import json
from contextlib import nullcontext
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

from cold_outreach.emails.models import DeliveryEvent, Direction, Mailbox, Message
from leadzen import autopilot
from leadzen.autopilot_worker import checkpoint, workspace_tick
from leadzen.campaigns import campaign_schedule, next_send_time
from leadzen.chat.engine import execute, snapshot
from leadzen.config.models import (AutopilotPolicy, AutopilotRun, CampaignRecipient,
    EmailCampaign, OnboardingState, RuntimeSettings, SiteConfig)
from leadzen.timezone import NEW_YORK, TIME_ZONE, configure_business_clock
from test_autopilot import NOW, enable_service, policy, setup_run
from test_campaigns import add, connected, make

UTC = ZoneInfo("UTC")


def test_application_default_zone_is_new_york_and_storage_remains_aware():
    assert settings.TIME_ZONE == TIME_ZONE == "America/New_York"
    assert settings.USE_TZ is True
    assert timezone.get_default_timezone() == NEW_YORK
    assert timezone.is_aware(timezone.now())
    assert EmailCampaign._meta.get_field("delay_timezone").default == TIME_ZONE


@pytest.mark.parametrize("country", ["US", "IN", "GB", ""])
def test_legacy_sender_and_mailbox_clock_ignore_operator_country(db, monkeypatch, country):
    from cold_outreach.core import sending_window
    from cold_outreach.emails.models import mailbox
    SiteConfig.load()
    SiteConfig.objects.update(operator_country_code=country)
    monkeypatch.setenv("OUTSEND_OPERATOR_COUNTRY", country)
    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 6, 12, tzinfo=UTC)):
        assert sending_window.operator_timezone() == mailbox.operator_timezone() == NEW_YORK
        assert sending_window.within_sending_window()
        assert mailbox._local_midnight() == datetime(2026, 10, 6, tzinfo=NEW_YORK)
    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 6, 11, 59, tzinfo=UTC)):
        assert not sending_window.within_sending_window()


def test_legacy_working_day_age_uses_new_york_dates_and_adapter_is_idempotent():
    from cold_outreach.core import business_time
    from cold_outreach.core.agents import outreach
    # Monday UTC midnight is still Sunday in New York, so no working day passed.
    sent = datetime(2026, 10, 3, 0, 30, tzinfo=UTC)  # Friday 8:30 PM in New York.
    before_monday = datetime(2026, 10, 5, 0, 30, tzinfo=UTC)
    monday = datetime(2026, 10, 5, 4, tzinfo=UTC)
    assert business_time.business_days_between(sent, before_monday) == 0
    assert outreach.business_days_between(sent, before_monday) == 0
    assert business_time.business_days_between(sent, monday) == 1
    original = business_time.business_days_between
    configure_business_clock()
    assert business_time.business_days_between is original
    assert outreach.business_days_between(sent, monday) == 1


@pytest.mark.parametrize("month, utc_hour, offset", [(1, 13, -5), (7, 12, -4)])
def test_new_york_schedule_tracks_dst_instead_of_fixed_utc_offset(db, month, utc_hour, offset):
    from leadzen.sending_schedule import within_window
    SiteConfig.load()
    SiteConfig.objects.update(operator_country_code="IN")
    opening = datetime(2026, month, 6, utc_hour, tzinfo=UTC)
    assert opening.astimezone(NEW_YORK).hour == 8
    assert opening.astimezone(NEW_YORK).utcoffset() == timedelta(hours=offset)
    assert within_window(opening) and not within_window(opening - timedelta(seconds=1))


def test_home_and_chat_daily_counts_share_new_york_midnight(connected):
    from leadzen.accounts.models import LoginSession
    LoginSession.objects.update(expires_at=datetime(2026, 10, 8, tzinfo=UTC))
    box = Mailbox.objects.get()
    stamps = [datetime(2026, 10, 6, 3, 59, tzinfo=UTC),
              datetime(2026, 10, 6, 4, 0, tzinfo=UTC),
              datetime(2026, 10, 7, 0, 30, tzinfo=UTC),
              datetime(2026, 10, 7, 4, 0, tzinfo=UTC)]
    for index, stamp in enumerate(stamps):
        sent = Message.objects.create(mailbox=box, direction=Direction.OUTBOUND,
            message_id=f"synthetic-out-{index}", sent_at=stamp)
        DeliveryEvent.objects.create(message=sent, status="accepted")
        Message.objects.create(mailbox=box, direction=Direction.INBOUND,
            message_id=f"synthetic-in-{index}", received_at=stamp)
    # An attempt without acceptance must not inflate either count.
    Message.objects.create(mailbox=box, direction=Direction.OUTBOUND,
        message_id="synthetic-unconfirmed", sent_at=stamps[1])
    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 7, 2, tzinfo=UTC)):
        home = connected.get("/api/overview")
        assert home.status_code == 200, home.content
        assert home.json()["today"] == {"sent": 2, "inbound": 2}
        assert execute("overview", {}, None)["emails_accepted_today"] == 2


@pytest.mark.parametrize("with_schedule", [False, True])
def test_old_foreign_autopilot_scope_is_readable_but_held_even_with_current_hash(connected, with_schedule):
    values = {"timezone": "Asia/Kolkata"}
    if with_schedule:
        values["sending_schedule"] = {"timezone": "Asia/Kolkata", "days": [0, 2, 4], "start": "09:15", "end": "17:45"}
    row = policy(**values)
    saved = json.loads(json.dumps(row.scope))
    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 7, 2, tzinfo=UTC)):
        shown = autopilot.policy_payload(row)
        assert shown["scope"]["timezone"] == TIME_ZONE
        assert shown["setup_changed"] and shown["next_start"] is None
        assert autopilot.local_now(row).date().isoformat() == "2026-10-06"
        if with_schedule:
            assert shown["scope"]["sending_schedule"] == {**values["sending_schedule"], "timezone": TIME_ZONE}
        with pytest.raises(PermissionError, match="setup changed"):
            autopilot.check_policy(row)
    row.refresh_from_db()
    assert row.scope == saved and row.enabled


def test_business_clock_change_invalidates_even_existing_new_york_approval(connected):
    from leadzen.mailboxes import active_mailboxes
    # Historical setup hashing did not include the tool's fixed business clock.
    old_snapshot = hashlib.sha256(json.dumps({"runtime": list(RuntimeSettings.objects.values()),
        "site": list(SiteConfig.objects.values())}, sort_keys=True, default=str).encode()).hexdigest()
    old_hash = hashlib.sha256(json.dumps({"setup": old_snapshot,
        "mailboxes": list(active_mailboxes().order_by("pk").values("from_address", "signature"))}, sort_keys=True).encode()).hexdigest()
    row = policy()
    row.setup_hash = old_hash
    row.save(update_fields=["setup_hash"])
    assert old_snapshot != snapshot("find_leads", {})
    with patch("django.utils.timezone.now", return_value=NOW):
        assert autopilot.policy_payload(row)["setup_changed"]
        with pytest.raises(PermissionError):
            autopilot.check_policy(row)


def test_business_clock_change_holds_old_followup_approval_without_sending(connected):
    from leadzen.campaigns import OFFER_FIELDS
    from leadzen.followups import fingerprint, guard
    from leadzen.mailboxes import active_mailboxes
    campaign = EmailCampaign.objects.get(pk=make(connected, add(connected)))
    campaign.status = "active"
    recipient = campaign.recipients.select_related("deal__lead").get()
    recipient.next_step = 1
    recipient.save(update_fields=["next_step"])
    # Reproduce the saved pre-change approval evidence, excluding the new clock key.
    old_data = {
        "campaign": {key: getattr(campaign, key) for key in (
            "name", "category", "steps", "from_address", *OFFER_FIELDS, "delay_timezone")},
        "runtime": list(RuntimeSettings.objects.values()), "site": list(SiteConfig.objects.values()),
        "signatures": list(active_mailboxes().order_by("pk").values("from_address", "signature")),
        "personal_steps": recipient.personal_steps,
        "recipient": {key: getattr(recipient.deal.lead, key) for key in ("email", "first_name", "last_name", "company")},
    }
    old_fingerprint = hashlib.sha256(json.dumps(old_data, sort_keys=True, default=str).encode()).hexdigest()
    assert old_fingerprint != fingerprint(campaign, recipient)
    campaign.followup_approval = {"actor_id": 1, "recipients": {str(recipient.pk): {
        "fingerprint": old_fingerprint, "expires_at": (NOW + timedelta(days=365)).isoformat()}}}
    campaign.save(update_fields=["status", "followup_approval"])
    with patch("django.utils.timezone.now", return_value=NOW), patch("cold_outreach.emails.sender._deliver") as send:
        with pytest.raises(PermissionError, match="approval changed"):
            guard(campaign, recipient)
        send.assert_not_called()


def test_autopilot_creates_one_workday_using_new_york_date_after_utc_midnight(connected):
    schedule = {"timezone": TIME_ZONE, "days": [2], "start": "22:00", "end": "23:00"}
    SiteConfig.objects.update(sending_schedule=schedule)
    policy(sending_schedule=schedule)
    instant = datetime(2026, 10, 8, 2, tzinfo=UTC)  # Wednesday 10 PM New York.
    def prepared(run):
        assert str(run.workday) == "2026-10-07"
        checkpoint(run, "completed")
    with patch("django.utils.timezone.now", return_value=instant), patch("leadzen.web_worker._database_lock", return_value=nullcontext()), patch("leadzen.mailboxes.prepare_worker_mailbox"), patch("leadzen.workspaces.guard_worker_sends"), patch("leadzen.autopilot_worker.prepare", side_effect=prepared) as prepare:
        workspace_tick()
        workspace_tick()
        prepare.assert_called_once()
    assert AutopilotRun.objects.count() == 1


def test_legacy_campaign_preview_and_working_day_delay_use_new_york(connected):
    row = EmailCampaign.objects.get(pk=make(connected, add(connected)))
    row.delay_timezone = "Asia/Kolkata"
    row.delay_basis = "working_days"
    assert campaign_schedule(row, automatic=True)["timezone"] == TIME_ZONE
    # This is Friday evening in New York, but already Saturday in Kolkata.
    due = next_send_time(row, datetime(2026, 10, 3, 0, 30, tzinfo=UTC), 1)
    assert due == datetime(2026, 10, 5, 20, 30, tzinfo=NEW_YORK)


def test_new_york_migration_preserves_immutable_approvals_and_absolute_timestamps(connected):
    saved_schedule = {"timezone": "Asia/Kolkata", "days": [1, 5], "start": "08:45", "end": "09:15"}
    SiteConfig.objects.update(operator_country_code="IN", sending_schedule=saved_schedule)
    OnboardingState.objects.create(draft={"sending_schedule": saved_schedule, "operator_country_code": "IN", "product_docs": "Keep offer"})
    row, run, campaign, recipient = setup_run(connected, timezone="Asia/Kolkata", sending_schedule=saved_schedule)
    immutable_scope = json.loads(json.dumps(row.scope))
    campaign.followup_approval = {"actor_id": row.actor_id, "recipients": {str(recipient.pk): {"fingerprint": "existing-evidence"}}}
    campaign.save(update_fields=["followup_approval"])
    recipient.next_send_at = datetime(2026, 10, 7, 2, 15, tzinfo=UTC)
    recipient.save(update_fields=["next_send_at"])
    accepted = Message.objects.create(mailbox=Mailbox.objects.get(), direction=Direction.OUTBOUND,
        message_id="synthetic-migration-accepted", sent_at=NOW)
    DeliveryEvent.objects.create(message=accepted, status="accepted")
    before = {"policy_hash": row.setup_hash, "expires": row.expires_at,
        "authorization": recipient.authorization_hash, "personal_steps": recipient.personal_steps,
        "due": recipient.next_send_at, "workday": run.workday, "approval": campaign.followup_approval,
        "runtime": list(RuntimeSettings.objects.values()), "messages": Message.objects.count(),
        "events": DeliveryEvent.objects.count()}
    loader = MigrationLoader(connection)
    historical_apps = loader.project_state([("leadzen_config", "0017_siteconfig_sending_schedule")]).apps
    migration = importlib.import_module("leadzen.config.migrations.0018_new_york_time")
    with patch("leadzen.ai.pinned_open") as provider, patch("cold_outreach.emails.sender._deliver") as send:
        migration.use_new_york(historical_apps, SimpleNamespace(connection=connection))
        migration.use_new_york(historical_apps, SimpleNamespace(connection=connection))  # Reruns are harmless.
        provider.assert_not_called(); send.assert_not_called()
    for obj in [row, run, campaign, recipient, accepted]:
        obj.refresh_from_db()
    assert SiteConfig.load().sending_schedule == {**saved_schedule, "timezone": TIME_ZONE}
    assert SiteConfig.load().operator_country_code == "IN"
    draft = OnboardingState.objects.get(pk=1).draft
    assert draft == {"sending_schedule": {**saved_schedule, "timezone": TIME_ZONE}, "operator_country_code": "IN", "product_docs": "Keep offer"}
    assert campaign.delay_timezone == TIME_ZONE and campaign.followup_approval == before["approval"]
    assert row.scope == immutable_scope and row.setup_hash == before["policy_hash"] and row.expires_at == before["expires"]
    assert recipient.authorization_hash == before["authorization"] and recipient.personal_steps == before["personal_steps"]
    assert recipient.next_send_at == before["due"] and run.workday == before["workday"] and accepted.sent_at == NOW
    assert list(RuntimeSettings.objects.values()) == before["runtime"]
    assert Message.objects.count() == before["messages"] and DeliveryEvent.objects.count() == before["events"]
    migrated_model = loader.project_state([("leadzen_config", "0018_new_york_time")]).apps.get_model("leadzen_config", "EmailCampaign")
    assert migrated_model._meta.get_field("delay_timezone").default == TIME_ZONE
    with patch("django.utils.timezone.now", return_value=NOW), pytest.raises(PermissionError):
        autopilot.check_policy(row)
