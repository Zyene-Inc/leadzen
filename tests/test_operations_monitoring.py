"""Operational alarms use private synthetic files and an explicit local sink."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from leadzen.operations import monitoring as m
from leadzen.operations import recovery as r
from test_operations_recovery import recovery_set, make_backup


@pytest.fixture
def monitor_config(recovery_set):
    make_backup(recovery_set)
    recovery_set.env.write_text(recovery_set.env.read_text() + "LEADZEN_DASHBOARD_TOKEN=synthetic-monitor-token\n")
    config = recovery_set.root / "monitor.json"
    value = {"backend_env_file": str(recovery_set.env), "api_private_origin": "http://127.0.0.1:8000",
             "state_root": str(recovery_set.root / "operations"), "backup_root": str(recovery_set.destination),
             "independent_backup_root": str(recovery_set.mirror), "minimum_free_bytes": 0,
             "minimum_free_fraction": 0, "minimum_memory_bytes": 0}
    r.write_json(config, value)
    return config, value, recovery_set


def good_probe(*args):
    return {"ok": True, "seconds": 0.001}


def test_actionable_alarm_deduplicates_and_never_logs_values(monitor_config):
    config, _, fixture = monitor_config
    send = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("external alerts not authorized"))
    first = m.run(config, probe=lambda *args: {"ok": False, "seconds": 3}, service=lambda unit: False, send=send)
    second = m.run(config, probe=lambda *args: {"ok": False, "seconds": 3}, service=lambda unit: False, send=send)
    assert first["status"] == "FAIL" and first["changed"] is True and second["changed"] is False
    assert first["alert_status"] == "BLOCKED_AUTHORIZATION_REQUIRED"
    codes = {issue["code"] for issue in first["issues"]}
    assert {"API_READINESS_FAILED", "API_HEALTH_FAILED", "API_SERVICE_INACTIVE", "API_LATENCY_ELEVATED"} <= codes
    output = json.dumps(first) + (Path(json.loads(config.read_text())["state_root"]) / "monitor.json").read_text()
    assert "synthetic-monitor-token" not in output and fixture.key not in output and "synthetic-customer" not in output


def test_failed_delivery_is_visible_and_bounded_retry_is_not_spam(monitor_config, monkeypatch):
    config, value, _ = monitor_config
    value["alert"] = {"url": "https://alerts.example.com/leadzen", "approved": True, "token": "synthetic-sink-token"}
    config.write_text(json.dumps(value))
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("private.person@example.com synthetic-provider-secret")
    first = m.run(config, deliver=True, probe=good_probe, service=lambda unit: False, send=fail)
    second = m.run(config, deliver=True, probe=good_probe, service=lambda unit: False, send=fail)
    assert first["alert_status"] == second["alert_status"] == "DELIVERY_FAILED"
    assert len(calls) == 1 and "synthetic-provider-secret" not in json.dumps(first)


def test_scheduler_heartbeat_reports_failed_stale_and_pass(monitor_config):
    _, _, fixture = monitor_config
    m.record_scheduler_pass(fixture.control, status="running")
    m.record_scheduler_pass(fixture.control, status="ok")
    assert m.scheduler_status(fixture.control, now=time.time(), max_age=10) is None
    assert m.scheduler_status(fixture.control, now=time.time() + 30, max_age=10) == "SCHEDULER_PROGRESS_STALE"
    m.record_scheduler_pass(fixture.control, status="failed")
    assert m.scheduler_status(fixture.control, now=time.time(), max_age=10) == "SCHEDULER_PASS_FAILED"
    heartbeat = fixture.control.parent / "operations/scheduler.json"
    assert heartbeat.stat().st_mode & 0o077 == 0
    assert set(json.loads(heartbeat.read_text())) == {"status", "updated_at", "started_at", "completed_at", "last_failed_at"}


def test_worker_failures_stale_locks_and_backup_freshness_are_detected(monitor_config):
    config, value, fixture = monitor_config
    database = fixture.workspaces / fixture.ids[0] / "db.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE leadzen_config_outreachjob(status TEXT, started_at TEXT, finished_at TEXT)")
        db.execute("INSERT INTO leadzen_config_outreachjob VALUES('failed',NULL,?)", [datetime.now(timezone.utc).isoformat(sep=" ")])
        db.execute("INSERT INTO leadzen_config_outreachjob VALUES('running','2000-01-01',NULL)")
    with r.owned_lock(database.parent / "send.lock"):
        first = m.run(config, probe=good_probe, service=lambda unit: True)
        assert first["measurements"]["busy_locks"] == 1
    codes = {issue["code"] for issue in first["issues"]}
    assert {"BACKGROUND_JOBS_FAILED", "BACKGROUND_JOBS_STALE"} <= codes
    # Source bytes are read-only; integrity checks only create scratch SHM/WAL.
    assert not Path(str(database) + "-shm").exists()
    value["backup_max_age_seconds"] = -1
    config.write_text(json.dumps(value))
    result = m.run(config, probe=good_probe, service=lambda unit: True)
    assert "FULL_BACKUP_STALE_OR_UNVERIFIED" in {issue["code"] for issue in result["issues"]}


def test_database_corruption_fails_without_customer_error_text(tmp_path):
    path = tmp_path / "database.sqlite3"
    r.write_private(path, b"private@example.com synthetic-not-sqlite")
    result = m.copy_database_check(path, since="2000-01-01", stale_before="2000-01-01")
    assert result == {"status": "FAIL", "code": "DATABASE_UNREADABLE"}


@pytest.mark.parametrize("url", ["http://alerts.example.com/", "https://127.0.0.1/", "https://user:secret@alerts.example.com/", "https://alerts.example.com/?token=secret"])
def test_notification_adapter_rejects_unapproved_destinations_before_bytes(url):
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]), patch("socket.socket") as connect:
        with pytest.raises(m.MonitoringError):
            m.alert_post(url, "synthetic", {"issues": []})
        connect.assert_not_called()


def test_explicit_local_fixture_receives_one_safe_test_alarm(monitor_config):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config, value, _ = monitor_config
    value["alert"] = {"url": f"http://127.0.0.1:{server.server_port}/alert", "token": "synthetic-local-sink"}
    config.write_text(json.dumps(value))
    try:
        result = m.run(config, deliver=True, allow_local_test=True, probe=good_probe, service=lambda unit: False)
        again = m.run(config, deliver=True, allow_local_test=True, probe=good_probe, service=lambda unit: False)
        assert result["alert_status"] == again["alert_status"] == "DELIVERED" and len(received) == 1
        assert received[0]["source"] == "leadzen-monitor" and received[0]["status"] == "FAIL"
        assert all(set(issue) == {"code", "severity"} for issue in received[0]["issues"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_bounded_alert_timeout_never_emits_subprocess_details(monkeypatch):
    def timeout(*args, **kwargs):
        raise m.subprocess.TimeoutExpired("private-token", 8, output=b"private@example.com")
    monkeypatch.setattr(m.subprocess, "run", timeout)
    with pytest.raises(m.MonitoringError, match="^ALERT_DELIVERY_FAILED$"):
        m.bounded_alert("https://alerts.example.com/", "synthetic", {})


def test_local_test_flag_cannot_authorize_external_notification():
    with patch("socket.getaddrinfo") as resolve:
        with pytest.raises(m.MonitoringError, match="LOCAL_ALERT_FIXTURE_REQUIRED"):
            m.alert_post("https://alerts.example.com/", "synthetic", {}, allow_local_test=True)
        resolve.assert_not_called()


def test_scheduler_main_records_before_after_without_changing_worker_behavior(monkeypatch, tmp_path):
    from django.conf import settings
    from leadzen import scheduler
    tmp_path.chmod(0o700)
    monkeypatch.setenv("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED", "1")
    monkeypatch.setenv("LEADZEN_AUTOPILOT_ENABLED", "0")
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "control.sqlite3")
    monkeypatch.setattr(scheduler.sys, "argv", ["scheduler"])
    ticks = []
    monkeypatch.setattr(scheduler, "tick", lambda: ticks.append(1))
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        scheduler.main()
    assert ticks == [1]
    heartbeat = json.loads((tmp_path / "operations/scheduler.json").read_text())
    assert heartbeat["status"] == "ok" and heartbeat["started_at"] <= heartbeat["completed_at"]


def test_request_outcomes_keep_only_fixed_counts_and_bound_missing_evidence(monkeypatch):
    def line(route, status, duration):
        return f"request_id={'a' * 32} method=POST route={route} status={status} duration_ms={duration}"
    records = "\n".join([line("api/auth/login", 401, 25), line("api/contacts/<int:pk>", 503, 2500),
                         line("api/health", 200, 1), "private@example.com secret-untrusted-diagnostic"])
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=records))
    assert m.request_outcomes("leadzen.service") == {"status": "PASS", "requests": 3, "server_errors": 1,
                                                    "slow_requests": 1, "auth_failures": 1}
    for records in ["private@example.com secret", "\n".join(["private"] * 5000)]:
        result = m.request_outcomes("leadzen.service")
        assert result["status"] == "UNVERIFIED" and "private" not in json.dumps(result)
    with pytest.raises(m.MonitoringError):
        m.request_outcomes("--malicious")


def test_application_error_latency_and_authentication_spikes_trigger_alarms(monitor_config):
    _, value, fixture = monitor_config
    value.update(request_outcomes_enabled=True, server_error_threshold=1, slow_request_threshold=1, auth_failure_threshold=1)
    env = {"LEADZEN_DB": str(fixture.control), "LEADZEN_WORKSPACE_ROOT": str(fixture.workspaces),
           "LEADZEN_DASHBOARD_TOKEN": "synthetic"}
    result = m.collect(value, env=env, probe=good_probe, service=lambda unit: True,
                       journal=lambda *args, **kwargs: {"status": "PASS", "requests": 3, "server_errors": 1,
                                                        "slow_requests": 1, "auth_failures": 1})
    assert {"API_ERROR_SPIKE", "API_LATENCY_ELEVATED", "AUTHENTICATION_FAILURE_SPIKE"} <= {i["code"] for i in result["issues"]}


def test_namespace_source_change_is_unverified_not_a_stable_check(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    control = tmp_path / "control.sqlite3"
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir(mode=0o700)
    with sqlite3.connect(control) as db:
        db.execute("CREATE TABLE leadzen_accounts_accountprofile(id TEXT,user_id INT)")
    control.chmod(0o600)
    original_copy = m.shutil.copyfile
    changed = False
    def change_after_copy(source, target):
        nonlocal changed
        result = original_copy(source, target)
        if Path(source) == control and not changed:
            changed = True
            with sqlite3.connect(control) as db:
                db.execute("CREATE TABLE synthetic_concurrent_change(id INTEGER)")
        return result
    monkeypatch.setattr(m.shutil, "copyfile", change_after_copy)
    env = {"LEADZEN_DB": str(control), "LEADZEN_WORKSPACE_ROOT": str(workspaces),
           "LEADZEN_DASHBOARD_TOKEN": "synthetic"}
    value = {"api_private_origin": "http://127.0.0.1:8000", "backup_root": str(tmp_path), "independent_backup_root": str(tmp_path)}
    result = m.collect(value, env=env, probe=good_probe, service=lambda unit: True)
    assert "DATABASE_CHANGING" in {row["code"] for row in result["issues"]}
    assert result["measurements"]["database_count"] == 0


@pytest.mark.parametrize("autopilot", [False, True])
def test_scheduler_main_marks_explicit_child_failure_for_monitoring(monkeypatch, tmp_path, autopilot):
    from django.conf import settings
    from leadzen import scheduler, autopilot_dispatch
    tmp_path.chmod(0o700)
    monkeypatch.setenv("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED", "0" if autopilot else "1")
    monkeypatch.setenv("LEADZEN_AUTOPILOT_ENABLED", "1" if autopilot else "0")
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "control.sqlite3")
    monkeypatch.setattr(scheduler.sys, "argv", ["scheduler"])
    monkeypatch.setattr(autopilot_dispatch if autopilot else scheduler, "tick", lambda: False)
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        scheduler.main()
    heartbeat = json.loads((tmp_path / "operations/scheduler.json").read_text())
    assert heartbeat["status"] == "failed"
    assert m.scheduler_status(tmp_path / "control.sqlite3", now=time.time(), max_age=10) == "SCHEDULER_PASS_FAILED"


def test_scheduler_failure_survives_a_later_success_until_monitor_observes_it(tmp_path):
    tmp_path.chmod(0o700)
    control = tmp_path / "control.sqlite3"
    m.record_scheduler_pass(control, status="failed")
    m.record_scheduler_pass(control, status="running")
    m.record_scheduler_pass(control, status="ok")
    assert m.scheduler_status(control, now=time.time(), max_age=10) == "SCHEDULER_RECENT_PASS_FAILED"
    assert m.scheduler_status(control, now=time.time() + 20, max_age=30, failure_window=10) is None


@pytest.mark.parametrize("autopilot", [False, True])
@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_child_exit_and_timeout_propagate_without_saved_job_state(monkeypatch, tmp_path, autopilot, failure):
    from contextlib import nullcontext
    from unittest.mock import Mock
    from django.conf import settings
    from leadzen import scheduler, autopilot_dispatch
    from leadzen.accounts.models import AccountProfile
    from leadzen import workspaces
    tmp_path.chmod(0o700)
    database = tmp_path / "synthetic.sqlite3"
    database.touch(mode=0o600)
    profile = SimpleNamespace(pk="synthetic-worker")
    monkeypatch.setattr(settings, "DATABASE_PATH", database)
    monkeypatch.setattr(workspaces, "database_path", lambda profile: database)
    monkeypatch.setattr(workspaces, "worker_environment", lambda profile: {})
    with patch("leadzen.web_worker._database_lock", return_value=nullcontext()), \
         patch("leadzen.operations.maintenance.maintenance_active", return_value=False), \
         patch.object(AccountProfile.objects, "filter") as profiles:
        if autopilot:
            process = Mock()
            process.poll.return_value = 7 if failure == "exit" else None
            monkeypatch.setattr(autopilot_dispatch, "_workers", {profile.pk: (process, time.monotonic() - 1000)})
            profiles.return_value.select_related.return_value.order_by.return_value = []
            assert autopilot_dispatch.tick() is False
            if failure == "timeout":
                process.kill.assert_called_once()
                process.wait.assert_called_once_with(timeout=5)
        else:
            profiles.return_value.select_related.return_value = [profile]
            with patch.object(scheduler.subprocess, "run", return_value=SimpleNamespace(returncode=7),
                              side_effect=m.subprocess.TimeoutExpired("synthetic-worker", 180) if failure == "timeout" else None):
                assert scheduler.tick() is False
