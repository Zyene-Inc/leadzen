"""Plan or apply the candidate graph to all server-owned initialized databases.

Applying requires a complete matched recovery set, inactive systemd writers,
an intake hold and explicit --execute. There are no reverse migrations here.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import sqlite3

from leadzen.operations.maintenance import maintenance_active, requests_running, workers_running
from leadzen.operations.preflight import (DatabaseTarget, read_private_env, validated_database_index,
    migration_graph, readonly_database, _read_policy, _schema_check)
from leadzen.operations.recovery import (RecoveryError, SystemdQuiescence, owned_lock,
    readonly_db, safe_path, namespace, private_root, verify_snapshot)
from leadzen.operations.release import verify as verify_release
from leadzen.production import validate_environment


def fingerprint(connection) -> str:
    digest = hashlib.sha256()
    for statement in connection.iterdump():
        # Hash locally; never persist dump text (it contains personal data/secrets).
        digest.update(statement.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def plan(env: dict, policy: dict) -> tuple[list, dict]:
    validate_environment(env)
    targets = validated_database_index(env, policy)
    graph = migration_graph()
    summary = []
    for target in targets:
        with readonly_database(target) as connection:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or connection.execute("PRAGMA foreign_key_check").fetchone():
                raise RecoveryError("MIGRATION_INTEGRITY_FAILED")
            summary.append({"role": target.role, **_schema_check(connection, graph, True)})
    return targets, {"status": "BLOCKED" if any(row["status"] != "PASS" for row in summary) else "PASS",
                     "databases": summary, "database_count": len(targets), "mutation_performed": False}


def apply(*, env: dict, policy: dict, candidate: Path, snapshot: Path, units: list[str]) -> dict:
    verify_release(candidate)
    validate_environment(env)
    if os.geteuid() != policy["service_uid"]:
        raise RecoveryError("MIGRATE_AS_STORAGE_OWNER")
    control = safe_path(env["LEADZEN_DB"])
    root = private_root(env["LEADZEN_WORKSPACE_ROOT"])
    storage = private_root(policy["storage_root"])
    if not control.is_relative_to(storage) or not root.is_relative_to(storage):
        raise RecoveryError("MIGRATION_STORAGE_OUTSIDE_BOUNDARY")
    with readonly_db(control) as connection:
        rows = namespace(connection, root)
    targets = [DatabaseTarget("control", control), *[DatabaseTarget("workspace", row["source"]) for row in rows]]
    if not maintenance_active(targets[0].path) or workers_running() or requests_running(targets[0].path):
        raise RecoveryError("MIGRATION_INTAKE_OR_WORKER_ACTIVE")
    if "leadzen.service" not in units or ((env.get("LEADZEN_AUTOPILOT_ENABLED") == "1" or env.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") == "1") and "leadzen-followups.service" not in units):
        raise RecoveryError("MIGRATION_WRITER_UNITS_INCOMPLETE")
    quiescence = SystemdQuiescence(units)
    quiescence.check()
    manifest = verify_snapshot(snapshot)
    if manifest.get("kind") != "native":
        raise RecoveryError("CURRENT_NATIVE_RECOVERY_REQUIRED")
    if manifest["database_count"] != len(targets):
        raise RecoveryError("MIGRATION_BACKUP_NAMESPACE_MISMATCH")
    recovered_env = read_private_env(snapshot / "private/backend.env", expected_uid=os.geteuid())
    for key in ("LEADZEN_SETTINGS_KEY", "LEADZEN_SECRET_KEY", "LEADZEN_DASHBOARD_TOKEN"):
        if not env.get(key) or not hmac.compare_digest(env[key].encode(), recovered_env.get(key, "").encode()):
            raise RecoveryError("MIGRATION_MATCHING_KEYS_REQUIRED")
    index = json.loads((snapshot / "private/index.json").read_text())["workspaces"]
    workspaces = {row["workspace_id"]: snapshot / row["database"] for row in index}
    if {t.path.parent.name for t in targets[1:]} != set(workspaces):
        raise RecoveryError("MIGRATION_BACKUP_NAMESPACE_MISMATCH")
    with ExitStack() as stack:
        stack.enter_context(owned_lock(targets[0].path.parent / "send.lock"))
        stack.enter_context(owned_lock(targets[0].path.parent / "scheduler/send.lock"))
        for target in targets[1:]:
            stack.enter_context(owned_lock(target.path.parent / "initialize.lock"))
            stack.enter_context(owned_lock(target.path.parent / "send.lock"))
        # Prove no customer changes are missing from the recovery set before the
        # first database changes. Revalidate all writers after the comparisons.
        for target in targets:
            backup_path = snapshot / "databases/control.sqlite3" if target.role == "control" else workspaces[target.path.parent.name]
            with readonly_db(target.path) as live, readonly_db(backup_path) as backup:
                if fingerprint(live) != fingerprint(backup):
                    raise RecoveryError("MIGRATION_BACKUP_STALE")
        quiescence.check()
        # A verified backup includes WAL contents. Checkpoint only after the full
        # matched comparison, with every writer stopped and locks held. Default
        # read-only planning never checkpoints or creates a shared-memory file.
        for target in targets:
            with sqlite3.connect(target.path, timeout=3) as connection:
                if connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] != 0:
                    raise RecoveryError("MIGRATION_CHECKPOINT_BUSY")
        _, _ = plan(env, policy)
        child = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TZ", "HOME"}}
        child.update(env)
        child["PYTHONPATH"] = str(candidate / "source")
        child["DJANGO_SETTINGS_MODULE"] = "leadzen.settings"
        for name in ("LEADZEN_ACTOR_ID", "LEADZEN_WORKSPACE_ID", "LEADZEN_CONTROL_DB"):
            child.pop(name, None)
        for target in targets:
            child["LEADZEN_DB"] = str(target.path)
            # No provider operation is part of migration or import verification.
            child["LEADZEN_AUTOPILOT_ENABLED"] = child["LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED"] = "0"
            result = subprocess.run([sys.executable, "-m", "leadzen", "migrate", "--noinput"],
                cwd=candidate / "source", env=child, capture_output=True, timeout=600)
            if result.returncode:
                raise RecoveryError("MIGRATION_FAILED_KEEP_INTAKE_HELD")
            target.path.chmod(0o600)
            quiescence.check()
        _, result = plan(env, policy)
        if result["status"] != "PASS":
            raise RecoveryError("MIGRATION_POSTCHECK_FAILED_KEEP_INTAKE_HELD")
        result["mutation_performed"] = True
        result["intake_held"] = True
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-env", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--recovery-set", type=Path)
    parser.add_argument("--writer-unit", action="append", default=[])
    args = parser.parse_args()
    try:
        policy = _read_policy(args.policy)
        env = read_private_env(args.backend_env, expected_uid=policy["env_owner_uid"])
        if args.execute:
            if not args.candidate or not args.recovery_set:
                raise RecoveryError("VERIFIED_CANDIDATE_AND_RECOVERY_REQUIRED")
            result = apply(env=env, policy=policy, candidate=args.candidate,
                snapshot=args.recovery_set, units=args.writer_unit)
        else:
            _, result = plan(env, policy)
        print(json.dumps(result))
        return 0 if result["status"] == "PASS" else 2
    except Exception:
        print('{"status":"FAIL","reason":"Migration precondition or execution failed; leave intake held and inspect protected recovery evidence. No rollback was attempted."}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
