"""Employee-owned weekly sending hours, shared by review and delivery gates.

All business hours use New York time, independent of operator country or browser.
The default describes the initial-mail 08:00–20:00 window; callers with a legacy
automatic policy retain its hours. Changed approval fingerprints require review.
"""
from datetime import datetime, timedelta, timezone as datetime_timezone
import re
from zoneinfo import ZoneInfo

from django.utils import timezone

from leadzen.config.models import SiteConfig
from leadzen.configuration import SettingsError
from leadzen.timezone import TIME_ZONE


UTC = datetime_timezone.utc
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")


def normalize_schedule(value):
    """Validate untrusted settings without coercing booleans or clock strings."""
    if not isinstance(value, dict) or set(value) != {"timezone", "days", "start", "end"}:
        raise SettingsError("Choose a timezone, sending days, start time and end time")
    name = value["timezone"]
    if name != TIME_ZONE:
        raise SettingsError("LeadZen uses New York time (America/New_York) only")
    days = value["days"]
    if not isinstance(days, list) or not days or any(type(day) is not int or not 0 <= day <= 6 for day in days):
        raise SettingsError("Choose at least one valid sending day")
    if any(not isinstance(value[key], str) or not TIME_PATTERN.fullmatch(value[key]) for key in ("start", "end")):
        raise SettingsError("Choose valid start and end times")
    if value["start"] >= value["end"]:
        raise SettingsError("End time must be after start time on the same day")
    return {"timezone": name, "days": sorted(set(days)), "start": value["start"], "end": value["end"]}


def is_custom(config=None):
    """Distinguish a saved schedule from the migration's empty legacy value."""
    config = config if config is not None else SiteConfig.load()
    return getattr(config, "sending_schedule", {}) != {}


def get_schedule(config=None):
    config = config if config is not None else SiteConfig.load()
    if is_custom(config):
        # Malformed stored data must stop a send rather than broaden its hours.
        saved = config.sending_schedule
        return normalize_schedule({**saved, "timezone": TIME_ZONE} if isinstance(saved, dict) else saved)
    return {"timezone": TIME_ZONE,
            "days": [0, 1, 2, 3, 4], "start": "08:00", "end": "20:00"}


def _minutes(value):
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _clock(now):
    now = now if now is not None else timezone.now()
    if not isinstance(now, datetime) or timezone.is_naive(now):
        raise ValueError("Sending clocks must include a timezone")
    # Reconstruct through a real UTC instant. ``astimezone(same_zone)`` alone
    # preserves an imaginary local input created by ``replace(tzinfo=...)``.
    return now.astimezone(UTC)


def within_window(now=None, schedule=None):
    schedule = normalize_schedule(schedule) if schedule is not None else get_schedule()
    local = _clock(now).astimezone(ZoneInfo(schedule["timezone"]))
    minute = local.hour * 60 + local.minute
    return local.weekday() in schedule["days"] and _minutes(schedule["start"]) <= minute < _minutes(schedule["end"])


def within_sending_window():
    if is_custom():
        return within_window()
    from cold_outreach.core.sending_window import within_sending_window as legacy_window
    return legacy_window()


def next_open(now=None, schedule=None):
    """Return the first real allowed instant, including DST gaps and repeated hours.

    A nonexistent opening advances to the first valid minute inside that day's
    window. If the entire window disappears, it waits for the next selected day.
    Both folds are considered so a repeated opening is available after the first
    occurrence has closed. UTC comparisons avoid wall-clock fold ambiguity.
    """
    schedule = normalize_schedule(schedule) if schedule is not None else get_schedule()
    now = _clock(now)
    zone = ZoneInfo(schedule["timezone"])
    local = now.astimezone(zone)
    if within_window(now, schedule):
        return local
    now_utc = now.astimezone(UTC)
    start, end = _minutes(schedule["start"]), _minutes(schedule["end"])
    # One week's selected day may lose its entire window to a clock change.
    for offset in range(15):
        day = local.date() + timedelta(days=offset)
        if day.weekday() not in schedule["days"]:
            continue
        candidates = []
        for minute in range(start, end):
            wall = datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute)
            for fold in (0, 1):
                opening = wall.replace(tzinfo=zone, fold=fold)
                instant = opening.astimezone(UTC)
                if instant < now_utc:
                    continue
                if instant.astimezone(zone).replace(tzinfo=None) != wall:
                    continue
                candidates.append(opening)
        if candidates:
            return min(candidates, key=lambda opening: opening.astimezone(UTC))
    raise SettingsError("The sending schedule has no available opening")


def next_wall_open(wall, schedule=None):
    """Resolve a future local due time without inventing an instant in a DST gap.

    Calendar/working-day delays describe a local date and clock time. A missing
    02:30 therefore advances to that day's first real allowed minute, rather than
    normalizing to 03:30 and accidentally skipping a short remaining window.
    """
    if not isinstance(wall, datetime) or timezone.is_aware(wall):
        raise ValueError("Scheduled local times must not include a timezone")
    schedule = normalize_schedule(schedule) if schedule is not None else get_schedule()
    zone = ZoneInfo(schedule["timezone"])
    start, end = _minutes(schedule["start"]), _minutes(schedule["end"])
    for offset in range(15):
        day = wall.date() + timedelta(days=offset)
        if day.weekday() not in schedule["days"]:
            continue
        candidates = []
        # Preserve seconds for a real due time already inside the window.
        clocks = [wall] if offset == 0 and start <= wall.hour * 60 + wall.minute < end else []
        clocks.extend(datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute)
                      for minute in range(start, end))
        for clock in clocks:
            if clock < wall:
                continue
            for fold in (0, 1):
                opening = clock.replace(tzinfo=zone, fold=fold)
                if opening.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == clock:
                    candidates.append(opening)
        if candidates:
            return min(candidates, key=lambda opening: opening.astimezone(UTC))
    raise SettingsError("The sending schedule has no available opening")


def window_close(now=None, schedule=None):
    """First real minute outside the currently open, contiguous window.

    A clock jump can close the window before its nominal end, or repeat part of
    it. Walk actual instants so preparation cannot cross either boundary.
    """
    schedule = normalize_schedule(schedule) if schedule is not None else get_schedule()
    instant = _clock(now)
    if not within_window(instant, schedule):
        return instant
    zone = ZoneInfo(schedule["timezone"])
    start, end = _minutes(schedule["start"]), _minutes(schedule["end"])
    instant = instant.replace(second=0, microsecond=0) + timedelta(minutes=1)
    # Same-day windows always close by midnight, including a repeated day.
    for _ in range(48 * 60):
        local = instant.astimezone(zone)
        if local.weekday() not in schedule["days"] or not start <= local.hour * 60 + local.minute < end:
            return instant
        instant += timedelta(minutes=1)
    raise SettingsError("The sending schedule has no closing boundary")


def window_payload(schedule=None):
    schedule = normalize_schedule(schedule) if schedule is not None else get_schedule()
    return {"start": _minutes(schedule["start"]) / 60, "end": _minutes(schedule["end"]) / 60,
            "timezone": schedule["timezone"], "weekdays_only": all(day < 5 for day in schedule["days"]),
            "days": list(schedule["days"]), "start_time": schedule["start"], "end_time": schedule["end"]}
