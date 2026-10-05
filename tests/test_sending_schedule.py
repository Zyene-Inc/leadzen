"""Minute-accurate employee hours, DST openings and atomic private Settings."""
from datetime import datetime, timezone as datetime_timezone
import json
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from leadzen.config.models import OnboardingState, RuntimeSettings, SiteConfig
from leadzen.configuration import SettingsError, effective, save_dashboard_settings
from leadzen.sending_schedule import get_schedule, is_custom, next_open, normalize_schedule, window_payload, within_window


def schedule(**changes):
    return {"timezone": "America/New_York", "days": [0, 2, 4], "start": "08:15", "end": "17:45", **changes}


def clock(value, zone="America/New_York", fold=0):
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(zone), fold=fold)


@pytest.mark.parametrize("country", ["US", "IN", "GB", "", "invalid"])
def test_empty_schedule_uses_new_york_independent_of_country(country):
    config = SimpleNamespace(operator_country_code=country, sending_schedule={})
    assert not is_custom(config)
    assert get_schedule(config) == {"timezone": "America/New_York", "days": [0, 1, 2, 3, 4], "start": "08:00", "end": "20:00"}


def test_schedule_normalizes_days_and_is_independent_of_country():
    value = schedule(days=[6, 2, 0, 2])
    expected = {**value, "days": [0, 2, 6]}
    assert normalize_schedule(value) == expected
    assert value["days"] == [6, 2, 0, 2]
    config = SimpleNamespace(operator_country_code="IN", sending_schedule=value)
    assert is_custom(config) and get_schedule(config) == expected


@pytest.mark.parametrize("zone", ["Asia/Kolkata", "Europe/London", "UTC", "US/Eastern"])
def test_existing_foreign_schedule_keeps_days_hours_but_uses_new_york(zone):
    saved = schedule(timezone=zone, days=[6, 2, 0, 2])
    config = SimpleNamespace(operator_country_code="IN", sending_schedule=saved)
    assert get_schedule(config) == schedule(days=[0, 2, 6])
    assert saved["timezone"] == zone and saved["days"] == [6, 2, 0, 2]
    with pytest.raises(SettingsError, match="New York"):
        normalize_schedule(saved)


INVALID_SCHEDULES = [
    None, [], "weekdays", {},
    {"timezone": "UTC", "days": [0], "start": "08:00"},
    schedule(extra="ignored"),
    schedule(timezone=None), schedule(timezone=5), schedule(timezone=True),
    schedule(timezone=""), schedule(timezone="No/Such_Zone"), schedule(timezone="../UTC"),
    schedule(timezone="/etc/localtime"), schedule(timezone="localtime"), schedule(timezone="posixrules"),
    schedule(timezone=" America/New_York "),
    schedule(timezone="UTC"), schedule(timezone="Asia/Kolkata"),
    schedule(timezone="Europe/London"), schedule(timezone="US/Eastern"),
    schedule(days=[]), schedule(days=[-1]), schedule(days=[7]), schedule(days=[True]),
    schedule(days=["0"]), schedule(days=[0.0]), schedule(days="0"), schedule(days={"0": True}),
    schedule(start=None), schedule(start=True), schedule(start=8), schedule(start="8:00"),
    schedule(start="08:00:00"), schedule(start="08:60"), schedule(start="24:00"),
    schedule(start=" 08:00"), schedule(end="24:00"), schedule(end="17:5"),
    schedule(start="17:45"), schedule(start="20:00"), schedule(start="23:00", end="02:00"),
]


@pytest.mark.parametrize("value", INVALID_SCHEDULES)
def test_schedule_rejects_malformed_or_broadened_inputs(value):
    with pytest.raises(SettingsError):
        normalize_schedule(value)


@pytest.mark.parametrize("stored", [None, [], "malformed", schedule(days=[]), schedule(end="08:00")])
def test_corrupt_saved_schedule_fails_closed(stored):
    config = SimpleNamespace(operator_country_code="US", sending_schedule=stored)
    assert is_custom(config)
    with pytest.raises(SettingsError):
        get_schedule(config)


@pytest.mark.parametrize("value, expected", [
    ("2026-10-05T08:14:59", False), ("2026-10-05T08:15:00", True),
    ("2026-10-05T17:44:59", True), ("2026-10-05T17:45:00", False),
    ("2026-10-06T12:00:00", False), ("2026-10-07T12:00:00", True),
    ("2026-10-10T12:00:00", False),
])
def test_selected_days_and_minute_boundaries(value, expected):
    assert within_window(clock(value), schedule()) is expected


def test_windows_convert_utc_instants_into_new_york_and_allow_weekends():
    value = schedule(days=[6], start="09:30", end="10:15")
    assert within_window(clock("2026-10-04T13:30:00", "UTC"), value)
    assert not within_window(clock("2026-10-04T14:15:00", "UTC"), value)
    assert window_payload(value) == {"start": 9.5, "end": 10.25, "timezone": "America/New_York", "weekdays_only": False,
                                     "days": [6], "start_time": "09:30", "end_time": "10:15"}


@pytest.mark.parametrize("value, expected", [
    ("2026-10-05T07:00:00", "2026-10-05T08:15:00"),
    ("2026-10-05T08:15:30", "2026-10-05T08:15:30"),
    ("2026-10-05T17:45:00", "2026-10-07T08:15:00"),
    ("2026-10-09T21:00:00", "2026-10-12T08:15:00"),
    ("2026-10-06T10:00:00", "2026-10-07T08:15:00"),
])
def test_next_open_selects_first_allowed_instant(value, expected):
    opening = next_open(clock(value), schedule())
    assert opening == clock(expected)
    assert within_window(opening, schedule())


def test_next_open_handles_spring_gap_without_inventing_local_opening():
    value = schedule(days=[6], start="02:30", end="03:30")
    opening = next_open(clock("2026-03-08T01:45:00"), value)
    assert opening.isoformat() == "2026-03-08T03:00:00-04:00"
    assert opening.astimezone(datetime_timezone.utc).isoformat() == "2026-03-08T07:00:00+00:00"
    assert within_window(opening, value)


def test_next_open_skips_day_when_entire_window_disappears_in_spring_gap():
    value = schedule(days=[6], start="02:15", end="02:45")
    opening = next_open(clock("2026-03-08T01:45:00"), value)
    assert opening.isoformat() == "2026-03-15T02:15:00-04:00"
    assert within_window(opening, value)


def test_next_open_can_use_second_fold_after_first_window_has_closed():
    value = schedule(days=[6], start="01:30", end="01:45")
    now = clock("2026-11-01T01:50:00", fold=0)
    assert not within_window(now, value)
    opening = next_open(now, value)
    assert opening.isoformat() == "2026-11-01T01:30:00-05:00" and opening.fold == 1
    assert opening.astimezone(datetime_timezone.utc) > now.astimezone(datetime_timezone.utc)
    assert within_window(opening, value)


def test_within_window_handles_both_folds_as_real_allowed_instants():
    value = schedule(days=[6], start="01:30", end="01:45")
    assert within_window(clock("2026-11-01T01:35:00", fold=0), value)
    assert within_window(clock("2026-11-01T01:35:00", fold=1), value)
    assert not within_window(clock("2026-11-01T01:45:00", fold=1), value)


def test_imaginary_input_clock_is_normalized_before_testing_new_york_gap():
    value = schedule(days=[6], start="02:00", end="03:00")
    imaginary = clock("2026-03-08T02:15:00")
    assert imaginary.astimezone(datetime_timezone.utc).astimezone(ZoneInfo("America/New_York")).hour == 3
    assert not within_window(imaginary, value)
    opening = next_open(imaginary, value)
    assert opening.isoformat() == "2026-03-15T02:00:00-04:00"
    assert within_window(opening, value)


@pytest.mark.parametrize("helper", [within_window, next_open])
def test_sending_clock_must_be_aware(helper):
    with pytest.raises(ValueError, match="include a timezone"):
        helper(datetime(2026, 10, 5, 9), schedule())


@pytest.fixture
def api_environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")


def put(client, body):
    return client.put("/api/settings", data=json.dumps(body), content_type="application/json")


def test_settings_effective_default_read_does_not_save_or_probe(account_client, api_environment):
    config = SiteConfig.load()
    config.operator_country_code = "US"
    config.save()
    with patch("leadzen.setup_wizard.probe_ai") as ai, patch("leadzen.setup_wizard.probe_discovery") as finder, patch("leadzen.setup_wizard.probe_mailbox") as mail:
        response = account_client.get("/api/settings")
        assert response.status_code == 200, response.content
        assert response.json()["workspace"]["sending_schedule"] == {"timezone": "America/New_York", "days": [0, 1, 2, 3, 4], "start": "08:00", "end": "20:00"}
        assert SiteConfig.load().sending_schedule == {} and not OnboardingState.objects.exists()
        ai.assert_not_called(); finder.assert_not_called(); mail.assert_not_called()


def test_settings_save_roundtrip_normalizes_without_changing_connections(account_client, api_environment):
    save_dashboard_settings({"provider": "groq", "model": "saved-model", "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "smtp_port": 587}, llm_api_key="synthetic-private-key")
    before = effective()
    value = schedule(days=[6, 0, 2, 0], start="09:30", end="16:45")
    expected = {**value, "days": [0, 2, 6]}
    with patch("leadzen.setup_wizard.probe_ai") as ai, patch("leadzen.setup_wizard.probe_discovery") as finder, patch("leadzen.setup_wizard.probe_mailbox") as mail:
        response = put(account_client, {"workspace_updates": {"sending_schedule": value}})
        assert response.status_code == 200, response.content
        assert response.json()["workspace"]["sending_schedule"] == expected
        assert SiteConfig.load().sending_schedule == expected
        assert OnboardingState.objects.get(pk=1).draft["sending_schedule"] == expected
        assert effective() == before and "synthetic-private-key" not in response.content.decode()
        assert account_client.get("/api/settings").json()["workspace"]["sending_schedule"] == expected
        ai.assert_not_called(); finder.assert_not_called(); mail.assert_not_called()


@pytest.mark.parametrize("value", [schedule(days=[]), schedule(days=[True]), schedule(timezone="invalid"), schedule(timezone="Asia/Kolkata"), schedule(timezone="UTC"), schedule(timezone="US/Eastern"), schedule(start="17:45"), schedule(end="04:00")])
def test_invalid_schedule_is_atomic_with_other_settings(account_client, api_environment, value):
    config = SiteConfig.load()
    config.sending_schedule = schedule()
    config.booking_link = "https://example.com/original"
    config.save()
    response = put(account_client, {"llm": {"provider": "groq", "model": "changed"}, "workspace_updates": {"sending_schedule": value, "booking_link": "https://example.com/changed"}})
    assert response.status_code == 400
    assert SiteConfig.load().sending_schedule == schedule()
    assert SiteConfig.load().booking_link == "https://example.com/original"
    assert not RuntimeSettings.objects.exists() and not OnboardingState.objects.exists()


def test_invalid_connection_rolls_back_valid_schedule_change(account_client, api_environment):
    config = SiteConfig.load()
    config.sending_schedule = schedule()
    config.save()
    response = put(account_client, {"mailbox": {"address": "invalid", "smtp_host": "smtp.example.com", "smtp_port": 587}, "workspace_updates": {"sending_schedule": schedule(days=[1, 3])}})
    assert response.status_code == 400
    assert SiteConfig.load().sending_schedule == schedule()
    assert not RuntimeSettings.objects.exists() and not OnboardingState.objects.exists()
