from types import SimpleNamespace

import pytest

from leadzen.operations import migrations
from leadzen.operations.recovery import RecoveryError


def test_apply_refuses_intake_and_workers_before_any_database_mutation(monkeypatch, tmp_path):
    monkeypatch.setattr(migrations, "verify_release", lambda _: {})
    targets = [SimpleNamespace(path=tmp_path / "control.sqlite3", role="control")]
    monkeypatch.setattr(migrations, "plan", lambda *_: (targets, {}))
    monkeypatch.setattr(migrations, "validate_environment", lambda _: None)
    monkeypatch.setattr(migrations, "safe_path", lambda _: targets[0].path)
    monkeypatch.setattr(migrations, "private_root", lambda _: tmp_path)
    from contextlib import nullcontext
    monkeypatch.setattr(migrations, "readonly_db", lambda _: nullcontext(None))
    monkeypatch.setattr(migrations, "namespace", lambda *_: [])
    monkeypatch.setattr(migrations.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(migrations, "maintenance_active", lambda _: False)
    with pytest.raises(RecoveryError, match="INTAKE_OR_WORKER"):
        migrations.apply(env={"LEADZEN_DB": "synthetic", "LEADZEN_WORKSPACE_ROOT": "synthetic"}, policy={"service_uid": 1000, "storage_root": "synthetic"}, candidate=tmp_path, snapshot=tmp_path, units=[])
    monkeypatch.setattr(migrations, "maintenance_active", lambda _: True)
    monkeypatch.setattr(migrations, "workers_running", lambda: 1)
    with pytest.raises(RecoveryError, match="INTAKE_OR_WORKER"):
        migrations.apply(env={"LEADZEN_DB": "synthetic", "LEADZEN_WORKSPACE_ROOT": "synthetic"}, policy={"service_uid": 1000, "storage_root": "synthetic"}, candidate=tmp_path, snapshot=tmp_path, units=[])


def test_database_fingerprint_detects_record_changes_without_dumping_values():
    import sqlite3
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, secret TEXT)")
        db.execute("INSERT INTO records VALUES(1,'private synthetic value')")
        before = migrations.fingerprint(db)
        assert "private synthetic" not in before and len(before) == 64
        db.execute("UPDATE records SET secret='changed' WHERE id=1")
        assert migrations.fingerprint(db) != before


def test_actual_migration_refuses_historical_recovery_even_with_matching_data_and_keys(monkeypatch, tmp_path):
    from contextlib import nullcontext
    import json
    import os
    import sqlite3
    storage = tmp_path / "data"
    storage.mkdir(mode=0o700)
    root = storage / "workspaces"
    root.mkdir(mode=0o700)
    (storage / "scheduler").mkdir(mode=0o700)
    control = storage / "control.sqlite3"
    with sqlite3.connect(control) as connection:
        connection.execute("CREATE TABLE records(id INTEGER PRIMARY KEY)")
    control.chmod(0o600)
    snapshot = tmp_path / "historical"
    (snapshot / "private").mkdir(parents=True, mode=0o700)
    (snapshot / "private/index.json").write_text(json.dumps({"workspaces": []}))
    env = {"LEADZEN_DB": str(control), "LEADZEN_WORKSPACE_ROOT": str(root),
           "LEADZEN_SETTINGS_KEY": "synthetic-match", "LEADZEN_SECRET_KEY": "synthetic-match",
           "LEADZEN_DASHBOARD_TOKEN": "synthetic-match"}
    target = migrations.DatabaseTarget("control", control)
    monkeypatch.setattr(migrations, "verify_release", lambda _: {})
    monkeypatch.setattr(migrations, "validate_environment", lambda _: None)
    monkeypatch.setattr(migrations, "namespace", lambda *_: [])
    monkeypatch.setattr(migrations, "maintenance_active", lambda _: True)
    monkeypatch.setattr(migrations, "workers_running", lambda: 0)
    monkeypatch.setattr(migrations, "requests_running", lambda _: 0)
    monkeypatch.setattr(migrations, "SystemdQuiescence", lambda _: SimpleNamespace(check=lambda: None))
    monkeypatch.setattr(migrations, "verify_snapshot", lambda _: {"kind": "historical", "database_count": 1})
    monkeypatch.setattr(migrations, "read_private_env", lambda *_args, **_kwargs: env)
    monkeypatch.setattr(migrations, "readonly_db", lambda _: nullcontext(None))
    monkeypatch.setattr(migrations, "fingerprint", lambda _: "same")
    monkeypatch.setattr(migrations, "plan", lambda *_: ([target], {"status": "PASS"}))
    mutated = []
    monkeypatch.setattr(migrations.subprocess, "run", lambda *_args, **_kwargs: mutated.append(True) or SimpleNamespace(returncode=0))
    with pytest.raises(RecoveryError, match="CURRENT_NATIVE_RECOVERY_REQUIRED"):
        migrations.apply(env=env, policy={"service_uid": os.geteuid(), "storage_root": str(storage)},
            candidate=tmp_path, snapshot=snapshot, units=["leadzen.service"])
    assert mutated == []
