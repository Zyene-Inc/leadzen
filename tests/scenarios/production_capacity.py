"""Bounded synthetic Gunicorn/SQLite workload; never point at existing data.

Run the candidate container with --network none and mount only a new private
fixture directory. Output is aggregate evidence, not a target-host capacity claim.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--employees", type=int, default=4)
    parser.add_argument("--contacts", type=int, default=5000, help="Per employee")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--requests", type=int, default=256)
    args = parser.parse_args()
    if not (2 <= args.employees <= 10 and 100 <= args.contacts <= 50000 and 1 <= args.concurrency <= 32 and 32 <= args.requests <= 2000):
        parser.error("Use bounded synthetic workload sizes")
    root = args.root.absolute()
    if root.is_symlink() or not root.name.startswith("leadzen-capacity.") or not root.is_dir() or any(root.iterdir()):
        parser.error("A new empty leadzen-capacity.* directory is required")
    if os.environ.get("LEADZEN_CAPACITY_NETWORK_ISOLATED") != "1":
        parser.error("Run in a network-disabled container with the explicit isolation marker")
    root.chmod(0o700)
    os.umask(0o077)
    from cryptography.fernet import Fernet
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "DJANGO_SETTINGS_MODULE": "leadzen.settings",
           "LEADZEN_ENV": "production", "LEADZEN_DB": str(root / "control.sqlite3"),
           "LEADZEN_WORKSPACE_ROOT": str(root / "workspaces"), "LEADZEN_SETTINGS_KEY": Fernet.generate_key().decode(),
           "LEADZEN_SECRET_KEY": secrets.token_urlsafe(64), "LEADZEN_DASHBOARD_TOKEN": secrets.token_urlsafe(48),
           "LEADZEN_PUBLIC_URL": "https://synthetic.example.com", "LEADZEN_DASHBOARD_ORIGINS": "https://synthetic.example.com",
           "LEADZEN_ALLOWED_HOSTS": "127.0.0.1,localhost", "LEADZEN_AUTOPILOT_ENABLED": "0",
           "LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED": "0"}
    os.environ.update(env)
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connections
    from django.utils import timezone
    from leadzen.accounts.service import create_account, login
    from leadzen.workspaces import initialize_workspace, workspace_scope
    from cold_outreach.leads.models import Lead, Deal
    call_command("migrate", verbosity=0, stdout=io.StringIO())
    sessions = []
    for employee in range(args.employees):
        password = secrets.token_urlsafe(48) + "8!Aq"
        actor = create_account(email=f"capacity-{employee}@example.invalid", name="Synthetic", password=password, require_change=False)
        profile = actor.leadzen_profile
        profile.onboarding_completed_at = timezone.now()
        profile.save(update_fields=["onboarding_completed_at"])
        initialize_workspace(profile)
        with workspace_scope(profile):
            contacts = Lead.objects.bulk_create([Lead(lead_id=f"synthetic-{employee}-{number}",
                first_name="Synthetic", email=f"person-{number}@example.invalid") for number in range(args.contacts)])
            Deal.objects.bulk_create([Deal(lead=lead) for lead in contacts])
        _, token, status = login(actor.email, password)
        if status != 200 or not token:
            raise RuntimeError("SYNTHETIC_AUTHENTICATION_FAILED")
        sessions.append(token)
    connections.close_all()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": "Bearer " + env["LEADZEN_DASHBOARD_TOKEN"]}
    def request(path, *, token=None, body=None):
        supplied = {**headers, **({"X-LeadZen-Session": token} if token else {})}
        if body is not None:
            supplied["Content-Type"] = "application/json"
        start = time.monotonic()
        try:
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers=supplied, method="PUT" if body is not None else "GET")
            with urllib.request.urlopen(req, timeout=20) as response:
                data = response.read(2 * 1024 * 1024 + 1)
                return response.status, time.monotonic() - start, len(data)
        except urllib.error.HTTPError as error:
            return error.code, time.monotonic() - start, 0
        except OSError:
            return 0, time.monotonic() - start, 0
    with (root / "private-server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-m", "gunicorn", "--bind", f"127.0.0.1:{port}",
                                   "--workers", "1", "--threads", "8", "--timeout", "120", "leadzen.wsgi:application"],
                                  env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            while request("/api/ready")[0] != 200:
                if time.monotonic() > deadline or server.poll() is not None:
                    raise RuntimeError("SYNTHETIC_STARTUP_FAILED")
                time.sleep(0.2)
            started = time.monotonic()
            def work(number):
                token = sessions[number % len(sessions)]
                if number % 8 == 0:
                    return request("/api/settings", token=token, body={"mailbox": {"signature": "Synthetic bounded write"}})
                path = ["/api/leads?limit=25", "/api/overview", "/api/settings"][number % 3]
                return request(path, token=token)
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                results = list(pool.map(work, range(args.requests)))
            elapsed = time.monotonic() - started
            durations = sorted(row[1] for row in results)
            errors = sum(not 200 <= row[0] < 300 or row[2] > 2 * 1024 * 1024 for row in results)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    integrity = True
    for database in [root / "control.sqlite3", *sorted((root / "workspaces").glob("*/db.sqlite3"))]:
        with sqlite3.connect(database) as connection:
            integrity = integrity and connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)] and not connection.execute("PRAGMA foreign_key_check").fetchall()
    print(json.dumps({"status": "PASS" if errors == 0 and integrity else "FAIL", "employees": args.employees,
                      "contacts_per_employee": args.contacts, "concurrency": args.concurrency, "requests": args.requests,
                      "write_requests": (args.requests + 7) // 8, "errors": errors, "integrity": integrity,
                      "status_counts": {str(status): sum(row[0] == status for row in results) for status in sorted({row[0] for row in results})},
                      "seconds": round(elapsed, 3), "requests_per_second": round(args.requests / elapsed, 2),
                      "p50_ms": round(durations[len(durations) // 2] * 1000),
                      "p95_ms": round(durations[min(len(durations) - 1, int(len(durations) * .95))] * 1000),
                      "max_response_bytes": max(row[2] for row in results), "target_host_capacity_verified": False}))
    return 0 if errors == 0 and integrity else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"FAIL","code":"SYNTHETIC_CAPACITY_OPERATION_FAILED"}')
        raise SystemExit(1)
