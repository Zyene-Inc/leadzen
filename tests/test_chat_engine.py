"""Chat discovery polls only the selected asynchronous email lookups."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.utils import timezone

from leadzen.chat.engine import collect_owned_email_lookups
from leadzen.discovery_progress import DiscoveryPaused


class LookupRows:
    def __init__(self, rows):
        self.rows = rows

    def order_by(self, *_fields):
        return self

    def values(self, *_fields):
        return self.rows()


class ReceiptRows(list):
    def order_by(self, *_fields):
        return self


class LookupManager:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, **_filters):
        return LookupRows(self.rows)


class Receipts:
    def __init__(self, receipt):
        self.receipt = receipt

    def all(self):
        return ReceiptRows([self.receipt])


def monitor_with_pending_lookup():
    receipt = SimpleNamespace(request_id="owned-handle", state="submitted")
    session = SimpleNamespace(
        source_ids=[41],
        provider_calls=1,
        lookups=Receipts(receipt),
        refresh_from_db=Mock(),
    )
    return SimpleNamespace(session=session, boundary=Mock()), receipt


_DUE = timezone.now() - timedelta(seconds=1)


def pending_rows():
    return [{"pk": 9, "lookup_attempt": 1, "not_before": _DUE}]


def test_chat_collection_polls_owned_handle_until_terminal(monkeypatch):
    monitor, receipt = monitor_with_pending_lookup()
    settled = False
    manager = LookupManager(lambda: [] if settled else pending_rows())

    def poll(*, only_poll):
        nonlocal settled
        assert only_poll is True
        settled = True
        receipt.state = "terminated"
        return {"stored": 1, "suppressed": 0, "skipped": 0, "partial": False, "paused": False}

    monkeypatch.setattr("openoutfind.crm.models.Deal.objects", manager)
    result = collect_owned_email_lookups(
        monitor,
        {"stored": 0, "suppressed": 0, "skipped": 0, "partial": False, "paused": False},
        poll,
    )

    assert result["stored"] == 1
    assert result["partial"] is False
    assert "completed" in result["note"]
    monitor.boundary.assert_called_once_with()


def test_chat_collection_stops_after_an_uncertain_poll(monkeypatch):
    monitor, _receipt = monitor_with_pending_lookup()
    manager = LookupManager(pending_rows)
    poll = Mock(return_value={"stored": 0, "suppressed": 0, "skipped": 0, "partial": True, "paused": False})
    monkeypatch.setattr("openoutfind.crm.models.Deal.objects", manager)

    result = collect_owned_email_lookups(
        monitor,
        {"stored": 0, "suppressed": 0, "skipped": 0, "partial": False, "paused": False},
        poll,
    )

    assert result["partial"] is True
    poll.assert_called_once_with(only_poll=True)


def test_chat_collection_honors_pause_before_polling(monkeypatch):
    monitor, _receipt = monitor_with_pending_lookup()
    manager = LookupManager(pending_rows)
    poll = Mock()
    monitor.boundary.side_effect = DiscoveryPaused()
    monkeypatch.setattr("openoutfind.crm.models.Deal.objects", manager)

    result = collect_owned_email_lookups(
        monitor,
        {"stored": 0, "suppressed": 0, "skipped": 0, "partial": False, "paused": False},
        poll,
    )

    assert result["paused"] is True
    poll.assert_not_called()
