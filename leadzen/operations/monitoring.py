"""Private operational checks and deduplicated, explicitly authorized alerts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import fcntl
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
import uuid

from leadzen.operations.recovery import (RecoveryError, digest, fsync_dir, namespace, owned_lock,
    private_root, readonly_db, safe_path, verify_snapshot, write_json)


class MonitoringError(RuntimeError):
    pass


def atomic_json(path, value):
    path = Path(path)
    private_root(path.parent, create=True)
    if path.exists():
        safe_path(path)
    temporary = path.parent / (".pending-" + uuid.uuid4().hex)
    write_json(temporary, value)
    os.replace(temporary, path)
    fsync_dir(path.parent)


def record_scheduler_pass(database_path, *, status):
    """Safe pass evidence; no account, provider, recipient or credential text."""
    if status not in {"running", "ok", "failed", "held"}:
        raise MonitoringError("SCHEDULER_HEARTBEAT_STATUS_INVALID")
    path = Path(database_path).parent / "operations" / "scheduler.json"
    now = datetime.now(timezone.utc).isoformat()
    prior = json.loads(safe_path(path).read_text()) if path.exists() else {}
    value = {"status": status, "updated_at": now}
    if status == "failed":
        value["last_failed_at"] = now
    elif isinstance(prior.get("last_failed_at"), str):
        value["last_failed_at"] = prior["last_failed_at"]
    if status == "running":
        value["started_at"] = now
    else:
        if path.exists():
            value["started_at"] = prior.get("started_at", now)
        value["completed_at"] = now
    atomic_json(path, value)


def scheduler_status(database_path, *, now, max_age, failure_window=3600):
    path = Path(database_path).parent / "operations" / "scheduler.json"
    try:
        value = json.loads(safe_path(path).read_text())
        updated = datetime.fromisoformat(value["updated_at"]).timestamp()
        if now - updated > max_age or updated > now + 60:
            return "SCHEDULER_PROGRESS_STALE"
        if value["status"] == "failed":
            return "SCHEDULER_PASS_FAILED"
        if value["status"] == "held":
            return "MAINTENANCE_HOLD_ACTIVE"
        if value["status"] not in {"running", "ok"}:
            return "SCHEDULER_PROGRESS_INVALID"
        if "last_failed_at" in value:
            failed = datetime.fromisoformat(value["last_failed_at"]).timestamp()
            if failed > now + 60:
                return "SCHEDULER_PROGRESS_UNVERIFIED"
            if now - failed <= failure_window:
                return "SCHEDULER_RECENT_PASS_FAILED"
        return None
    except (OSError, ValueError, KeyError, RecoveryError):
        return "SCHEDULER_PROGRESS_UNVERIFIED"


def _copy_database_set(path, target):
    """Copy only an observed stable DB/WAL set, including namespace snapshots."""
    path = safe_path(path)
    sources = [path]
    if Path(str(path) + "-wal").exists():
        sources.append(safe_path(str(path) + "-wal"))
    def stamps():
        return [(p.stat().st_dev, p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns) for p in sources]
    before = stamps()
    for source in sources:
        shutil.copyfile(source, target if source == path else Path(str(target) + "-wal"))
    if stamps() != before or Path(str(path) + "-wal").exists() != (len(sources) == 2):
        raise MonitoringError("DATABASE_CHANGING")


def copy_database_check(path, *, since, stale_before):
    """No live SQLite connections: read bytes into an isolated scratch copy.

    Copy an observed stable DB+WAL set twice-checking inode/size/mtime. A busy
    source is explicitly unverified, never incorrectly declared corrupted.
    Integrity and worker queries run only against the temporary copy.
    """
    with tempfile.TemporaryDirectory(prefix="leadzen-monitor-db-") as scratch:
        target = Path(scratch) / "db.sqlite3"
        try:
            _copy_database_set(path, target)
        except MonitoringError:
            return {"status": "UNVERIFIED", "code": "DATABASE_CHANGING"}
        try:
            with sqlite3.connect(target, timeout=2) as connection:
                if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    return {"status": "FAIL", "code": "DATABASE_INTEGRITY_FAILED"}
                if connection.execute("PRAGMA foreign_key_check").fetchone():
                    return {"status": "FAIL", "code": "DATABASE_FOREIGN_KEY_FAILED"}
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                counts = {"failed_jobs": 0, "stale_jobs": 0}
                for table in ("leadzen_config_outreachjob", "leadzen_config_chatrun"):
                    if table not in tables:
                        continue
                    counts["failed_jobs"] += connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE status=\'failed\' AND finished_at >= ?', [since]).fetchone()[0]
                    counts["stale_jobs"] += connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE status=\'running\' AND started_at < ?', [stale_before]).fetchone()[0]
                return {"status": "PASS", **counts}
        except sqlite3.Error:
            return {"status": "FAIL", "code": "DATABASE_UNREADABLE"}


def service_active(unit):
    from leadzen.operations.recovery import UNIT
    if not UNIT.fullmatch(unit):
        raise MonitoringError("SERVICE_NAME_INVALID")
    try:
        result = subprocess.run(["systemctl", "show", unit, "--property=LoadState,ActiveState,SubState"],
                                capture_output=True, text=True, timeout=5, check=True)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        return fields.get("LoadState") == "loaded" and fields.get("ActiveState") == "active" and fields.get("SubState") == "running"
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def request_outcomes(unit, *, window_seconds=300, slow_ms=2000):
    """Read bounded journal evidence; return aggregates, never raw log text.

    RequestMetrics emits server-owned route patterns and fixed outcome fields.
    Missing journal access or a saturated window remains unverified.
    """
    from leadzen.operations.recovery import UNIT
    if not UNIT.fullmatch(unit) or not 60 <= window_seconds <= 3600 or not 1 <= slow_ms <= 120000:
        raise MonitoringError("REQUEST_METRICS_POLICY_INVALID")
    try:
        result = subprocess.run(["journalctl", "--unit", unit, "--since", f"{window_seconds} seconds ago",
                                 "--output=cat", "--no-pager", "--lines=5000"],
                                capture_output=True, text=True, timeout=8, check=True)
        lines = result.stdout.splitlines()
        if len(lines) >= 5000:
            return {"status": "UNVERIFIED", "code": "REQUEST_METRICS_WINDOW_SATURATED"}
        pattern = re.compile(r"request_id=[0-9a-f]{32} method=(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|OTHER) route=([^\s]+) status=([1-5][0-9]{2}) duration_ms=([0-9]{1,9})(?:\s|$)")
        counts = {"requests": 0, "server_errors": 0, "slow_requests": 0, "auth_failures": 0}
        for line in lines:
            match = pattern.search(line)
            if not match:
                continue
            route, status, duration = match.groups()
            status = int(status)
            counts["requests"] += 1
            counts["server_errors"] += status >= 500
            counts["slow_requests"] += int(duration) >= slow_ms
            counts["auth_failures"] += route.startswith("api/auth/") and status in {401, 403, 429}
        if not counts["requests"]:
            return {"status": "UNVERIFIED", "code": "REQUEST_METRICS_MISSING"}
        return {"status": "PASS", **counts}
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return {"status": "UNVERIFIED", "code": "REQUEST_METRICS_UNREADABLE"}


def lock_busy(path):
    """Observe an existing lock without creating/truncating a runtime file."""
    path = Path(path)
    if not path.exists():
        return False
    safe_path(path)
    descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(descriptor)


def http_probe(url, token):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.hostname not in {"127.0.0.1", "::1", "localhost"} or parsed.scheme != "http" or parsed.path not in {"/api/health", "/api/ready"}:
        raise MonitoringError("PRIVATE_PROBE_ENDPOINT_REQUIRED")
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=3)
    try:
        started = time.monotonic()
        connection.request("GET", parsed.path, headers={"Authorization": "Bearer " + token})
        response = connection.getresponse()
        from leadzen.provider_io import read_response
        read_response(connection, response, limit=16384, deadline=started + 3, description="Readiness")
        return {"ok": response.status == 200, "seconds": time.monotonic() - started}
    except (OSError, ValueError, http.client.HTTPException):
        return {"ok": False, "seconds": 3}
    finally:
        connection.close()


def alert_post(url, token, payload, *, allow_local_test=False):
    """One bounded attempt, exact HTTPS/public destination; redirects rejected."""
    parsed = urlsplit(url)
    local = allow_local_test and parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
    if allow_local_test and not local:
        raise MonitoringError("LOCAL_ALERT_FIXTURE_REQUIRED")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or (not local and (parsed.scheme != "https" or parsed.port not in (None, 443))) or not parsed.hostname:
        raise MonitoringError("ALERT_DESTINATION_INVALID")
    body = json.dumps(payload, sort_keys=True).encode()
    if len(body) > 16384 or any(ord(c) < 32 for c in token):
        raise MonitoringError("ALERT_PAYLOAD_INVALID")
    port = parsed.port or (80 if local else 443)
    infos = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not infos or any(not ipaddress.ip_address(item[4][0]).is_global for item in infos) and not local:
        raise MonitoringError("ALERT_DESTINATION_NOT_PUBLIC")
    family, socktype, proto, _, address = infos[0]
    raw = socket.socket(family, socktype, proto)
    raw.settimeout(3)
    connection = http.client.HTTPConnection(parsed.hostname, port, timeout=3)
    try:
        raw.connect(address)
        connection.sock = raw if local else ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
        started = time.monotonic()
        connection.request("POST", parsed.path or "/", body, {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        response = connection.getresponse()
        from leadzen.provider_io import read_response
        read_response(connection, response, limit=16384, deadline=started + 3, description="Alert")
        if not 200 <= response.status < 300:
            raise MonitoringError("ALERT_DELIVERY_FAILED")
    except (OSError, ValueError, http.client.HTTPException):
        raise MonitoringError("ALERT_DELIVERY_FAILED") from None
    finally:
        connection.close()
        raw.close()


def bounded_alert(url, token, payload, *, allow_local_test=False):
    """Hard process deadline covers DNS/TLS/headers as well as response bodies."""
    import sys
    with tempfile.TemporaryDirectory(prefix="leadzen-alert-") as scratch:
        request = Path(scratch).resolve() / "request.json"
        write_json(request, {"url": url, "token": token, "payload": payload, "local_test": allow_local_test})
        try:
            result = subprocess.run([sys.executable, "-m", "leadzen.operations.monitoring", "_alert", str(request)],
                                    env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            if result.returncode:
                raise MonitoringError("ALERT_DELIVERY_FAILED")
        except (OSError, subprocess.SubprocessError):
            raise MonitoringError("ALERT_DELIVERY_FAILED") from None


def collect(config, *, env, now=None, probe=http_probe, service=service_active, journal=request_outcomes):
    now = time.time() if now is None else now
    issues = []
    measurements = {"database_count": 0, "failed_jobs": 0, "stale_jobs": 0, "busy_locks": 0}
    def issue(code, severity="HIGH"):
        issues.append({"code": code, "severity": severity})
    for path in ("/api/health", "/api/ready"):
        result = probe(config["api_private_origin"].rstrip("/") + path, env["LEADZEN_DASHBOARD_TOKEN"])
        if not result["ok"]:
            issue("API_HEALTH_FAILED" if path == "/api/health" else "API_READINESS_FAILED")
        if result["seconds"] > config.get("latency_warning_seconds", 2):
            issue("API_LATENCY_ELEVATED", "MEDIUM")
    if not service(config.get("api_unit", "leadzen.service")):
        issue("API_SERVICE_INACTIVE")
    if config.get("request_outcomes_enabled") is True:
        outcomes = journal(config.get("api_unit", "leadzen.service"),
                           window_seconds=config.get("request_window_seconds", 300),
                           slow_ms=round(config.get("latency_warning_seconds", 2) * 1000))
        if outcomes["status"] != "PASS":
            issue(outcomes["code"], "MEDIUM")
        else:
            measurements.update({"api_" + key: value for key, value in outcomes.items() if key != "status"})
            if outcomes["server_errors"] >= config.get("server_error_threshold", 5):
                issue("API_ERROR_SPIKE")
            if outcomes["slow_requests"] >= config.get("slow_request_threshold", 5):
                issue("API_LATENCY_ELEVATED", "MEDIUM")
            if outcomes["auth_failures"] >= config.get("auth_failure_threshold", 20):
                issue("AUTHENTICATION_FAILURE_SPIKE")
    storage = private_root(Path(env["LEADZEN_DB"]).parent)
    disk = shutil.disk_usage(storage)
    measurements["disk_free_bytes"] = disk.free
    if disk.free < config.get("minimum_free_bytes", 1024 ** 3) or disk.free / disk.total < config.get("minimum_free_fraction", 0.10):
        issue("STORAGE_CAPACITY_LOW")
    memory_file = Path("/proc/meminfo")
    if memory_file.exists():
        values = {line.split(":")[0]: int(line.split()[1]) * 1024 for line in memory_file.read_text().splitlines() if ":" in line}
        measurements["memory_available_bytes"] = values.get("MemAvailable", 0)
        if measurements["memory_available_bytes"] < config.get("minimum_memory_bytes", 256 * 1024 ** 2):
            issue("MEMORY_CAPACITY_LOW")
    else:
        issue("MEMORY_METRIC_UNVERIFIED", "MEDIUM")
    try:
        # Namespace read uses the same staged byte copy to avoid live SHM writes.
        with tempfile.TemporaryDirectory(prefix="leadzen-monitor-index-") as scratch:
            source = Path(env["LEADZEN_DB"])
            target = Path(scratch) / "control.sqlite3"
            _copy_database_set(source, target)
            with sqlite3.connect(target) as control:
                rows = namespace(control, env["LEADZEN_WORKSPACE_ROOT"])
        paths = [Path(env["LEADZEN_DB"]), *[row["source"] for row in rows]]
        locks = [storage / "send.lock", storage / "scheduler/send.lock", *[path.parent / "send.lock" for path in paths[1:]]]
        measurements["busy_locks"] = sum(lock_busy(path) for path in locks)
        since = datetime.fromtimestamp(now - config.get("failure_window_seconds", 3600), timezone.utc).isoformat(sep=" ")
        stale = datetime.fromtimestamp(now - config.get("worker_deadline_seconds", 1800), timezone.utc).isoformat(sep=" ")
        for path in paths:
            result = copy_database_check(path, since=since, stale_before=stale)
            measurements["database_count"] += 1
            if result["status"] != "PASS":
                issue(result["code"], "MEDIUM" if result["status"] == "UNVERIFIED" else "HIGH")
            measurements["failed_jobs"] += result.get("failed_jobs", 0)
            measurements["stale_jobs"] += result.get("stale_jobs", 0)
        if measurements["failed_jobs"]:
            issue("BACKGROUND_JOBS_FAILED")
        if measurements["stale_jobs"]:
            issue("BACKGROUND_JOBS_STALE")
    except MonitoringError:
        issue("DATABASE_CHANGING", "MEDIUM")
    except (RecoveryError, sqlite3.Error, OSError):
        issue("DATABASE_NAMESPACE_UNVERIFIED")
    if env.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") == "1" or env.get("LEADZEN_AUTOPILOT_ENABLED") == "1":
        if not service(config.get("scheduler_unit", "leadzen-followups.service")):
            issue("SCHEDULER_SERVICE_INACTIVE")
        status = scheduler_status(env["LEADZEN_DB"], now=now, max_age=config.get("scheduler_deadline_seconds", 900),
                                  failure_window=config.get("failure_window_seconds", 3600))
        if status:
            issue(status)
    try:
        snapshots = []
        root = private_root(config["backup_root"])
        independent = private_root(config["independent_backup_root"])
        for path in root.glob("snapshot-*"):
            try:
                manifest = verify_snapshot(path)
                if manifest.get("kind") == "native" and verify_snapshot(independent / path.name) == manifest:
                    snapshots.append(datetime.fromisoformat(manifest["created_at"]).timestamp())
            except (RecoveryError, OSError):
                continue
        if not snapshots or now - max(snapshots) > config.get("backup_max_age_seconds", 86400):
            issue("FULL_BACKUP_STALE_OR_UNVERIFIED")
        if list(root.glob(".pending-*")):
            issue("BACKUP_INCOMPLETE_STAGING", "MEDIUM")
    except (RecoveryError, OSError, KeyError):
        issue("FULL_BACKUP_STALE_OR_UNVERIFIED")
    unique = {row["code"]: row for row in issues}
    return {"status": "PASS" if not unique else "FAIL", "checked_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "issues": sorted(unique.values(), key=lambda row: row["code"]), "measurements": measurements}


def run(config_file, *, deliver=False, allow_local_test=False, probe=http_probe, service=service_active, send=bounded_alert):
    config = json.loads(safe_path(config_file).read_text())
    from leadzen.operations.preflight import read_private_env
    env = read_private_env(config["backend_env_file"], expected_uid=os.geteuid())
    state_root = private_root(config["state_root"], create=True)
    state_file = state_root / "monitor.json"
    with owned_lock(state_root / ".monitor.lock"):
        result = collect(config, env=env, probe=probe, service=service)
        previous = json.loads(safe_path(state_file).read_text()) if state_file.exists() else {}
        now = time.time()
        lock_busy_since = previous.get("lock_busy_since", now) if result["measurements"]["busy_locks"] else None
        if lock_busy_since is not None and now - lock_busy_since > config.get("lock_deadline_seconds", 1800):
            result["issues"].append({"code": "WRITER_LOCKS_STALE", "severity": "HIGH"})
            result["status"] = "FAIL"
        fingerprint = hashlib.sha256(json.dumps(result["issues"], sort_keys=True).encode()).hexdigest()
        changed = fingerprint != previous.get("fingerprint")
        alert_status = previous.get("alert_status", "NOT_REQUIRED")
        retry_due = deliver and alert_status in {"BLOCKED_AUTHORIZATION_REQUIRED", "DELIVERY_FAILED"} and now >= previous.get("next_alert_attempt_at", 0)
        if (changed or retry_due) and (result["issues"] or previous.get("had_issues")):
            alert_status = "BLOCKED_AUTHORIZATION_REQUIRED"
            if deliver:
                try:
                    alert = config["alert"]
                    if not allow_local_test and alert.get("approved") is not True:
                        raise MonitoringError("ALERT_AUTHORIZATION_REQUIRED")
                    send(alert["url"], alert.get("token", ""),
                               {"source": "leadzen-monitor", "status": result["status"], "issues": result["issues"]},
                               allow_local_test=allow_local_test)
                    alert_status = "DELIVERED"
                except MonitoringError as error:
                    alert_status = "BLOCKED_AUTHORIZATION_REQUIRED" if str(error) == "ALERT_AUTHORIZATION_REQUIRED" else "DELIVERY_FAILED"
                except Exception:
                    alert_status = "DELIVERY_FAILED"
        state = {"owner": "leadzen-monitor-v1", "fingerprint": fingerprint, "had_issues": bool(result["issues"]),
                 "alert_status": alert_status, "checked_at": result["checked_at"], "issues": result["issues"],
                 "lock_busy_since": lock_busy_since,
                 "next_alert_attempt_at": now + max(60, config.get("alert_retry_seconds", 3600)) if alert_status == "DELIVERY_FAILED" else 0}
        atomic_json(state_file, state)
        result["alert_status"] = alert_status
        result["changed"] = changed
        return result


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "_alert":
        try:
            request = json.loads(safe_path(argv[1]).read_text())
            alert_post(request["url"], request["token"], request["payload"], allow_local_test=request["local_test"])
            return 0
        except Exception:
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--deliver-alert", action="store_true", help="Requires reviewed private sink approval; one bounded attempt on state change")
    parser.add_argument("--allow-local-test-alert", action="store_true", help="Synthetic 127.0.0.1 HTTP fixture only")
    args = parser.parse_args(argv)
    try:
        if args.allow_local_test_alert and not args.deliver_alert:
            raise MonitoringError("LOCAL_TEST_REQUIRES_EXPLICIT_DELIVERY")
        result = run(args.config, deliver=args.deliver_alert, allow_local_test=args.allow_local_test_alert)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PASS" and result["alert_status"] != "DELIVERY_FAILED" else 1
    except Exception:
        print(json.dumps({"status": "FAIL", "code": "MONITOR_CONFIGURATION_OR_CHECK_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
