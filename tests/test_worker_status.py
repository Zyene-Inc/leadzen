"""A busy workspace is a quiet skip; a real worker failure names its error type only."""
import logging
import tempfile
import time
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


def test_held_workspace_lock_raises_the_typed_busy_error(tmp_path):
    from leadzen.web_worker import _database_lock
    from leadzen.worker_status import DatabaseBusy
    database = tmp_path / "db.sqlite3"
    with _database_lock(database):
        with pytest.raises(DatabaseBusy, match="already owns the database"):
            with _database_lock(database):
                pass
    with _database_lock(database):
        pass  # Released: the next pass gets it.


def test_pass_exits_busy_quietly_and_reports_only_the_error_type(capsys):
    from leadzen.worker_status import BUSY_EXIT, DatabaseBusy, reported_error, run_pass

    def busy():
        raise DatabaseBusy("another LeadZen by Zyene job already owns the database")

    with pytest.raises(SystemExit) as exit_:
        run_pass(busy)
    assert exit_.value.code == BUSY_EXIT and capsys.readouterr().err == ""

    def broken():
        try:
            raise KeyError("synthetic-secret@example.com")
        except KeyError as exc:
            raise RuntimeError("smtp password synthetic-secret") from exc

    with pytest.raises(SystemExit) as exit_:
        run_pass(broken)
    err = capsys.readouterr().err
    assert exit_.value.code == 1 and err == "LEADZEN_WORKER_ERROR=KeyError\n"
    with tempfile.TemporaryFile() as stream:
        stream.write(b"warning: noise\n" + err.encode() + b"LEADZEN_WORKER_ERROR=not a name!\n")
        assert reported_error(stream) == "KeyError"
    assert reported_error(None) == ""


def dispatch_once(dispatch, code, stream=None):
    process = Mock()
    process.poll.return_value = code
    dispatch._workers["0f0f0f0f-synthetic"] = (process, time.monotonic())
    if stream is not None:
        dispatch._errors["0f0f0f0f-synthetic"] = stream
    with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), \
            patch("leadzen.operations.maintenance.maintenance_active", return_value=False), \
            patch("leadzen.accounts.models.AccountProfile.objects.filter") as profiles:
        profiles.return_value.select_related.return_value.order_by.return_value = []
        return dispatch.tick()


@pytest.mark.django_db
def test_dispatch_skips_a_busy_workspace_and_names_real_failures(monkeypatch, caplog):
    from leadzen import autopilot_dispatch as dispatch
    from leadzen.worker_status import BUSY_EXIT
    monkeypatch.setattr(dispatch, "_workers", {})
    monkeypatch.setattr(dispatch, "_errors", {})
    monkeypatch.setattr(dispatch, "_busy", {})
    monkeypatch.setattr(dispatch, "BUSY_ALERT", 3)
    caplog.set_level(logging.INFO, logger="leadzen.autopilot_dispatch")

    # A Chat run held the lock: not a failure, nothing logged.
    stream = tempfile.TemporaryFile()
    assert dispatch_once(dispatch, BUSY_EXIT, stream) is True
    assert stream.closed and not caplog.records and not dispatch._errors
    # Still busy long after any Chat run would end: say so once, and count it failed.
    assert dispatch_once(dispatch, BUSY_EXIT) is True
    assert dispatch_once(dispatch, BUSY_EXIT) is False
    assert dispatch_once(dispatch, BUSY_EXIT) is False
    warnings = [r.getMessage() for r in caplog.records]
    assert warnings == ["Workspace 0f0f0f0f has been busy for about 15 minutes; follow-ups and Autopilot wait until its running job ends."]
    # A completed pass resets the count.
    assert dispatch_once(dispatch, 0) is True and dispatch._busy == {}

    caplog.clear()
    stream = tempfile.TemporaryFile()
    stream.write(b"LEADZEN_WORKER_ERROR=SettingsError\n")
    assert dispatch_once(dispatch, 1, stream) is False
    assert [r.getMessage() for r in caplog.records] == [
        "Workspace Autopilot worker failed for workspace 0f0f0f0f (exit code 1, SettingsError). Check account access, schema and connection settings."]


@pytest.mark.django_db
def test_follow_up_scheduler_treats_a_busy_workspace_as_a_skip(monkeypatch, tmp_path, caplog):
    from django.conf import settings
    from leadzen import scheduler, workspaces
    from leadzen.worker_status import BUSY_EXIT
    database = tmp_path / "synthetic.sqlite3"
    database.touch()
    monkeypatch.setattr(settings, "DATABASE_PATH", database)
    monkeypatch.setattr(workspaces, "database_path", lambda profile: database)
    monkeypatch.setattr(workspaces, "worker_environment", lambda profile: {})
    caplog.set_level(logging.ERROR, logger="leadzen.scheduler")
    for code, ok in ((BUSY_EXIT, True), (1, False)):
        with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), \
                patch("leadzen.operations.maintenance.maintenance_active", return_value=False), \
                patch("leadzen.accounts.models.AccountProfile.objects.filter") as profiles, \
                patch.object(scheduler.subprocess, "run", return_value=SimpleNamespace(returncode=code)):
            profiles.return_value.select_related.return_value = [SimpleNamespace(pk="0f0f0f0f-synthetic")]
            assert scheduler.tick() is ok
    assert len(caplog.records) == 1 and "exit code 1)" in caplog.records[0].getMessage()
