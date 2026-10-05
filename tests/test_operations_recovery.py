"""Recovery checks use synthetic SQLite/env fixtures and never installed services."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
import uuid

from cryptography.fernet import Fernet
import pytest

from leadzen.operations import recovery as r


@pytest.fixture
def recovery_set(tmp_path):
    tmp_path.chmod(0o700)
    storage = tmp_path / "data"
    storage.mkdir(mode=0o700)
    workspaces = storage / "workspaces"
    workspaces.mkdir(mode=0o700)
    key = Fernet.generate_key().decode()
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    control = storage / "control.sqlite3"
    with sqlite3.connect(control) as db:
        db.execute("CREATE TABLE auth_user(id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE leadzen_accounts_accountprofile(id TEXT PRIMARY KEY,user_id INTEGER REFERENCES auth_user(id))")
        db.executemany("INSERT INTO auth_user VALUES(?)", [(1,), (2,)])
        db.executemany("INSERT INTO leadzen_accounts_accountprofile VALUES(?,?)", [(identifier.replace('-', ''), i) for i, identifier in enumerate(ids, 1)])
    control.chmod(0o600)
    for identifier in ids:
        folder = workspaces / identifier
        folder.mkdir(mode=0o700)
        database = folder / "db.sqlite3"
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE leadzen_config_runtimesettings(encrypted_secrets TEXT)")
            token = Fernet(key.encode()).encrypt(json.dumps({"llm_api_key": "synthetic-private-token"}).encode()).decode()
            db.execute("INSERT INTO leadzen_config_runtimesettings VALUES(?)", [token])
            db.execute("CREATE TABLE customer_records(id INTEGER PRIMARY KEY,value TEXT)")
            db.execute("INSERT INTO customer_records VALUES(1,'synthetic-customer')")
        database.chmod(0o600)
        r.write_private(folder / "initialized", b"")
    env = tmp_path / "backend.env"
    r.write_private(env, f"LEADZEN_DB={control}\nLEADZEN_WORKSPACE_ROOT={workspaces}\nLEADZEN_SETTINGS_KEY={key}\nLEADZEN_SECRET_KEY=synthetic-signing-secret\n".encode())
    from leadzen.operations.release import REQUIRED_FILES, capture, add_artifact
    release_inputs = tmp_path / "release-inputs"
    release_inputs.mkdir(mode=0o700)
    for relative in REQUIRED_FILES | {"leadzen/synthetic.py"}:
        source = release_inputs / relative
        source.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        r.write_private(source, b"# Synthetic recovery source, never executed\n")
    release_root = tmp_path / "release"
    capture(release_inputs, release_root, "linux/amd64")
    runtime = tmp_path / "synthetic-runtime.tar"
    r.write_private(runtime, b"synthetic installed-runtime fixture")
    add_artifact(release_root, runtime, "backend-runtime")
    release = release_root / "manifest.json"
    # The operator capture procedure uses umask 077; fixture library calls must
    # preserve that private deployed-metadata requirement independently of pytest.
    release.chmod(0o600)
    (release_root / "source.tar").chmod(0o600)
    unit = tmp_path / "service.unit"
    r.write_private(unit, b"[Service]\nKillMode=control-group\n")
    destination = tmp_path / "backups"
    mirror = tmp_path / "independent"
    return SimpleNamespace(root=tmp_path, control=control, workspaces=workspaces, env=env,
                           release=release, unit=unit, destination=destination, mirror=mirror, key=key, ids=ids)


class SyntheticQuiescence:
    def __init__(self, after=None):
        self.calls = 0
        self.after = after

    def check(self):
        self.calls += 1
        if self.calls == 2 and self.after:
            self.after()


class SyntheticIndependentCopy:
    """Local fixture adapter; CLI has no same-volume bypass."""
    def __init__(self, root):
        self.root = root

    def publish(self, source, *, local_root):
        import shutil
        self.root.mkdir(mode=0o700, exist_ok=True)
        target = self.root / r.verify_snapshot(source)["snapshot"]
        shutil.copytree(source, target)
        r.verify_snapshot(target)
        return {"adapter": "independent-filesystem", "verified": True}


def make_backup(fixture, quiescence=None, adapter=None):
    result = r.backup(env_file=fixture.env, release_manifest=fixture.release,
                      service_files=[fixture.unit], destination=fixture.destination,
                      independent_copy=adapter or SyntheticIndependentCopy(fixture.mirror),
                      quiescence=quiescence or SyntheticQuiescence())
    return fixture.destination / result["snapshot"]


def test_full_snapshot_and_new_isolated_restore_match_keys_and_namespace(recovery_set):
    snapshot = make_backup(recovery_set)
    manifest = r.verify_snapshot(snapshot)
    assert manifest["database_count"] == 3 and manifest["workspace_count"] == 2
    public = (snapshot / "manifest.json").read_text()
    assert recovery_set.key not in public and "synthetic-private-token" not in public
    assert not any(identifier in public for identifier in recovery_set.ids)
    assert all(p.stat().st_mode & 0o077 == 0 for p in [snapshot, *snapshot.rglob("*")])
    target = recovery_set.root / "restore"
    assert r.restore(snapshot, target)["outbound_disabled"] is True
    config = json.loads((target / "private/drill-env.json").read_text())
    assert config["LEADZEN_SETTINGS_KEY"] == recovery_set.key
    assert config["LEADZEN_AUTOPILOT_ENABLED"] == config["LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED"] == "0"
    assert "LEADZEN_RESEND_API_KEY" not in config
    assert sorted(p.name for p in (target / "workspaces").iterdir()) == sorted(recovery_set.ids)
    with pytest.raises(r.RecoveryError, match="NEW_ISOLATED"):
        r.restore(snapshot, target)


def test_held_worker_lock_prevents_snapshot(recovery_set):
    with r.owned_lock(recovery_set.workspaces / recovery_set.ids[0] / "send.lock"):
        with pytest.raises(r.RecoveryError, match="WRITER_LOCK_BUSY"):
            make_backup(recovery_set)
    assert not list(recovery_set.destination.glob("snapshot-*"))


def test_matching_dashboard_and_proxy_configuration_survives_private_restore(recovery_set):
    dashboard = recovery_set.root / "dashboard.env"
    proxy = recovery_set.root / "Caddyfile.deployed"
    secret = b"LEADZEN_API_TOKEN=synthetic-sensitive-service-token\n"
    r.write_private(dashboard, secret)
    r.write_private(proxy, b"# Synthetic matching proxy configuration\n")
    result = r.backup(env_file=recovery_set.env, release_manifest=recovery_set.release,
        service_files=[recovery_set.unit], destination=recovery_set.destination,
        independent_copy=SyntheticIndependentCopy(recovery_set.mirror), quiescence=SyntheticQuiescence(),
        protected_files=[dashboard, proxy])
    snapshot = recovery_set.destination / result["snapshot"]
    assert secret.decode().strip() not in (snapshot / "manifest.json").read_text()
    index = json.loads((snapshot / "private/index.json").read_text())
    assert index["protected_files"] == [
        {"source_name": "dashboard.env", "stored": "private/protected-001.bin"},
        {"source_name": "Caddyfile.deployed", "stored": "private/protected-002.bin"},
    ]
    target = recovery_set.root / "protected-restore"
    r.restore(snapshot, target)
    assert (target / "private/protected-001.bin").read_bytes() == secret
    assert (target / "private/protected-002.bin").read_bytes() == proxy.read_bytes()
    assert (target / "private/protected-001.bin").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("changed", ["value", "deleted", "encrypted", "table", "foreign_key"])
def test_post_upgrade_validation_detects_record_decryption_and_relationship_damage(recovery_set, changed):
    database = recovery_set.control if changed == "foreign_key" else recovery_set.workspaces / recovery_set.ids[0] / "db.sqlite3"
    cipher = Fernet(recovery_set.key.encode())
    with sqlite3.connect(database) as connection:
        before = r.record_inventory(connection)
        if changed == "value":
            connection.execute("UPDATE customer_records SET value='changed during migration'")
        elif changed == "deleted":
            connection.execute("DELETE FROM customer_records")
        elif changed == "encrypted":
            connection.execute("UPDATE leadzen_config_runtimesettings SET encrypted_secrets='gAAAA-invalid'")
        elif changed == "table":
            connection.execute("DROP TABLE customer_records")
        else:
            connection.execute("UPDATE leadzen_accounts_accountprofile SET user_id=999")
        with pytest.raises(r.RecoveryError, match="DRILL_RECORD|MATCHED_SETTINGS_KEY|DATABASE_FOREIGN_KEY"):
            r.validate_restored_database(connection, cipher, before)


def test_reviewed_legacy_renames_and_clock_upgrade_preserve_all_other_record_fields():
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE openoutreach_config_siteconfig(id INTEGER PRIMARY KEY,country_code TEXT,sending_schedule TEXT,name TEXT)")
        connection.execute("INSERT INTO openoutreach_config_siteconfig VALUES(1,'US',?, 'retained')", [json.dumps({"timezone": "UTC", "days": [1]})])
        connection.execute("CREATE TABLE django_migrations(id INTEGER PRIMARY KEY,app TEXT,name TEXT)")
        connection.execute("INSERT INTO django_migrations VALUES(1,'openoutreach_config','0001_initial')")
        before = r.record_inventory(connection)
        connection.execute("ALTER TABLE openoutreach_config_siteconfig RENAME TO leadzen_config_siteconfig")
        connection.execute("ALTER TABLE leadzen_config_siteconfig RENAME COLUMN country_code TO operator_country_code")
        connection.execute("UPDATE leadzen_config_siteconfig SET sending_schedule=?", [json.dumps({"timezone": "America/New_York", "days": [1]})])
        connection.execute("UPDATE django_migrations SET app='leadzen_config'")
        connection.execute("INSERT INTO django_migrations VALUES(2,'leadzen_config','0018_new_york_time')")
        cipher = Fernet(Fernet.generate_key())
        checked = r.validate_restored_database(connection, cipher, before)
        assert checked["original_records_checked"] == 2
        connection.execute("UPDATE leadzen_config_siteconfig SET name='lost original value'")
        with pytest.raises(r.RecoveryError, match="DRILL_RECORD_PRESERVATION"):
            r.validate_restored_database(connection, cipher, before)


@pytest.mark.parametrize("table,column,original,wrong", [
    ("leadzen_config_siteconfig", "sending_schedule", '{"timezone":"UTC","days":[1]}', '{"timezone":"UTC","days":[1]}'),
    ("leadzen_config_onboardingstate", "draft", '{"sending_schedule":{"timezone":"UTC"}}', '{"sending_schedule":{"timezone":"Europe/London"}}'),
    ("leadzen_config_emailcampaign", "delay_timezone", "UTC", "Europe/London"),
])
def test_pending_clock_upgrade_checks_actual_post_upgrade_timezone(table, column, original, wrong):
    with sqlite3.connect(":memory:") as connection:
        connection.execute(f'CREATE TABLE "{table}"(id INTEGER PRIMARY KEY,"{column}" TEXT)')
        connection.execute(f'INSERT INTO "{table}" VALUES(1,?)', [original])
        before = r.record_inventory(connection)
        connection.execute(f'UPDATE "{table}" SET "{column}"=?', [wrong])
        with pytest.raises(r.RecoveryError, match="DRILL_RECORD_PRESERVATION"):
            r.validate_restored_database(connection, Fernet(Fernet.generate_key()), before)


@pytest.mark.parametrize("missing", ["table", "column", "app_label"])
def test_legacy_upgrade_checks_actual_post_upgrade_identifiers(missing):
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE openoutreach_config_siteconfig(id INTEGER PRIMARY KEY,country_code TEXT)")
        connection.execute("INSERT INTO openoutreach_config_siteconfig VALUES(1,'US')")
        connection.execute("CREATE TABLE django_content_type(id INTEGER PRIMARY KEY,app_label TEXT)")
        connection.execute("INSERT INTO django_content_type VALUES(1,'openoutreach_config')")
        before = r.record_inventory(connection)
        if missing != "table":
            connection.execute("ALTER TABLE openoutreach_config_siteconfig RENAME TO leadzen_config_siteconfig")
        if missing != "column":
            target = "openoutreach_config_siteconfig" if missing == "table" else "leadzen_config_siteconfig"
            connection.execute(f'ALTER TABLE "{target}" RENAME COLUMN country_code TO operator_country_code')
        if missing != "app_label":
            connection.execute("UPDATE django_content_type SET app_label='leadzen_config'")
        with pytest.raises(r.RecoveryError, match="DRILL_RECORD_TABLE|DRILL_RECORD_COLUMN|DRILL_RECORD_PRESERVATION"):
            r.validate_restored_database(connection, Fernet(Fernet.generate_key()), before)


def test_protected_configuration_change_aborts_backup(recovery_set):
    config = recovery_set.root / "dashboard.env"
    r.write_private(config, b"synthetic-original")
    changed = SyntheticQuiescence(lambda: config.write_bytes(b"synthetic-changed"))
    with pytest.raises(r.RecoveryError, match="PROTECTED_METADATA_CHANGED"):
        r.backup(env_file=recovery_set.env, release_manifest=recovery_set.release,
            service_files=[recovery_set.unit], destination=recovery_set.destination,
            independent_copy=SyntheticIndependentCopy(recovery_set.mirror), quiescence=changed,
            protected_files=[config])
    assert not list(recovery_set.destination.glob("snapshot-*"))


@pytest.mark.parametrize("kind", ["public", "hardlink", "oversized"])
def test_unprotected_or_oversized_configuration_cannot_enter_backup(recovery_set, kind):
    config = recovery_set.root / "dashboard.env"
    r.write_private(config, b"synthetic-configuration")
    if kind == "public":
        config.chmod(0o644)
    elif kind == "hardlink":
        os.link(config, recovery_set.root / "shared-copy")
    else:
        config.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(r.RecoveryError, match="PRIVATE_OWNED|PROTECTED_METADATA_INVALID"):
        r.backup(env_file=recovery_set.env, release_manifest=recovery_set.release,
            service_files=[recovery_set.unit], destination=recovery_set.destination,
            independent_copy=SyntheticIndependentCopy(recovery_set.mirror), quiescence=SyntheticQuiescence(),
            protected_files=[config])


def test_observed_write_prevents_cross_database_publish(recovery_set):
    def write():
        with sqlite3.connect(recovery_set.control) as db:
            db.execute("INSERT INTO auth_user VALUES(3)")
    with pytest.raises(r.RecoveryError, match="WRITE_OBSERVED"):
        make_backup(recovery_set, SyntheticQuiescence(write))
    assert not list(recovery_set.destination.glob("snapshot-*"))


@pytest.mark.parametrize("changed", ["database", "environment", "service", "protected", "writer", "release"])
def test_late_change_during_independent_copy_never_publishes_local_success(recovery_set, changed):
    config = recovery_set.root / "dashboard.env"
    r.write_private(config, b"synthetic-original")
    quiescence = SyntheticQuiescence()

    class ChangedCopy(SyntheticIndependentCopy):
        def publish(self, source, *, local_root):
            receipt = super().publish(source, local_root=local_root)
            if changed == "database":
                with sqlite3.connect(recovery_set.control) as database:
                    database.execute("INSERT INTO auth_user VALUES(3)")
            elif changed == "environment":
                recovery_set.env.write_bytes(recovery_set.env.read_bytes() + b"# changed\n")
            elif changed == "service":
                recovery_set.unit.write_bytes(b"[Service]\n# changed\n")
            elif changed == "protected":
                config.write_bytes(b"synthetic-changed")
            elif changed == "release":
                (recovery_set.release.parent / "artifacts/synthetic-runtime.tar").write_bytes(b"changed deployed runtime")
            else:
                def active():
                    raise r.RecoveryError("WRITERS_NOT_QUIESCED")
                quiescence.check = active
            return receipt

    with pytest.raises(r.RecoveryError, match="WRITE_OBSERVED|METADATA_CHANGED|WRITERS_NOT_QUIESCED|RELEASE_CHANGED"):
        r.backup(env_file=recovery_set.env, release_manifest=recovery_set.release,
            service_files=[recovery_set.unit], destination=recovery_set.destination,
            independent_copy=ChangedCopy(recovery_set.mirror), quiescence=quiescence,
            protected_files=[config])
    assert not list(recovery_set.destination.glob("snapshot-*"))
    # A completed independent copy is evidence, never silently deleted when
    # a last source-state check refuses to certify the current recovery set.
    mirrors = list(recovery_set.mirror.glob("snapshot-*"))
    assert len(mirrors) == 1
    r.verify_snapshot(mirrors[0])
    assert len(list(recovery_set.destination.glob(".pending-*"))) == 1


def test_wrong_settings_key_and_incomplete_workspace_fail_closed(recovery_set):
    recovery_set.env.write_text(recovery_set.env.read_text().replace(recovery_set.key, Fernet.generate_key().decode()))
    with pytest.raises(r.RecoveryError, match="MATCHED_SETTINGS_KEY"):
        make_backup(recovery_set)
    (recovery_set.workspaces / recovery_set.ids[0] / "initialized").unlink()
    with pytest.raises(r.RecoveryError, match="PARTIAL_WORKSPACE"):
        make_backup(recovery_set)


def test_mailbox_key_mismatch_nested_and_plaintext_are_not_certified(recovery_set):
    database = recovery_set.workspaces / recovery_set.ids[0] / "db.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE outsend_emails_mailbox(password TEXT)")
        db.execute("INSERT INTO outsend_emails_mailbox VALUES(?)", [Fernet(Fernet.generate_key()).encrypt(b'{"mailbox_password":"synthetic"}').decode()])
    with pytest.raises(r.RecoveryError, match="MATCHED_MAILBOX_KEY"):
        make_backup(recovery_set)
    cipher = Fernet(recovery_set.key.encode())
    nested = cipher.encrypt(json.dumps({"mailbox_password": cipher.encrypt(b'{"mailbox_password":"synthetic"}').decode()}).encode()).decode()
    for value in [nested, "synthetic-legacy-plaintext"]:
        with sqlite3.connect(database) as db:
            db.execute("UPDATE outsend_emails_mailbox SET password=?", [value])
        with pytest.raises(r.RecoveryError, match="LEGACY_MAILBOX"):
            make_backup(recovery_set)


def test_unknown_workspace_and_symlink_are_rejected(recovery_set):
    rogue = recovery_set.workspaces / str(uuid.uuid4())
    rogue.mkdir(mode=0o700)
    with pytest.raises(r.RecoveryError, match="ORPHAN_WORKSPACE"):
        make_backup(recovery_set)
    rogue.rmdir()
    link = recovery_set.root / "env-link"
    link.symlink_to(recovery_set.env)
    with pytest.raises(r.RecoveryError, match="SYMLINK"):
        r.safe_path(link)


def test_production_independent_adapter_refuses_same_filesystem(recovery_set):
    with pytest.raises(r.RecoveryError, match="INDEPENDENT_FILESYSTEM"):
        make_backup(recovery_set, adapter=r.FilesystemCopy(recovery_set.mirror))
    assert not list(recovery_set.destination.glob("snapshot-*"))


def test_snapshot_corruption_extra_files_and_retention_never_delete_foreign_data(recovery_set):
    snapshots = [make_backup(recovery_set) for _ in range(3)]
    foreign = recovery_set.destination / "snapshot-foreign"
    foreign.mkdir(mode=0o700)
    r.write_private(foreign / "customer.txt", b"retain me")
    r.write_private(snapshots[-1] / "extra.txt", b"untrusted")
    with pytest.raises(r.RecoveryError, match="FILE_SET"):
        r.verify_snapshot(snapshots[-1])
    assert r.retain(recovery_set.destination, keep=2, independent_root=recovery_set.mirror)["removed_owned_verified_snapshots"] == 0
    (snapshots[-1] / "extra.txt").unlink()
    assert r.retain(recovery_set.destination, keep=2, independent_root=recovery_set.mirror)["removed_owned_verified_snapshots"] == 1
    assert (foreign / "customer.txt").read_bytes() == b"retain me"
    assert len(list(recovery_set.mirror.glob("snapshot-*"))) == 3


@pytest.mark.parametrize("state", ["ActiveState=active\nSubState=running\nMainPID=123\nLoadState=loaded", "ActiveState=inactive\nSubState=dead\nMainPID=0\nLoadState=not-found"])
def test_systemd_writer_state_failures_are_safe(monkeypatch, state):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=state))
    with pytest.raises(r.RecoveryError, match="WRITERS_NOT_QUIESCED"):
        r.SystemdQuiescence(["leadzen.service"]).check()


def test_systemd_quiescence_requires_empty_cgroup(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nControlGroup="))
    r.SystemdQuiescence(["leadzen.service"]).check()
    with pytest.raises(r.RecoveryError, match="EXPLICIT_WRITER"):
        r.SystemdQuiescence(["--malicious"])


def test_recovery_cli_never_prints_exception_or_credentials(monkeypatch, capsys):
    monkeypatch.setattr(r, "verify_snapshot", lambda *args: (_ for _ in ()).throw(RuntimeError("private@example.com secret")))
    assert r.main(["verify", "synthetic"]) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "FAIL", "code": "RECOVERY_OPERATION_FAILED"}


def test_real_schema_recovery_drill_authentication_router_and_network_block(recovery_set):
    fixture = recovery_set
    # Populate only the fixture files with the actual migration graph in a
    # scrubbed process. No inherited production DB or provider exports exist.
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "DJANGO_SETTINGS_MODULE": "leadzen.settings",
           "LEADZEN_DB": str(fixture.control), "LEADZEN_WORKSPACE_ROOT": str(fixture.workspaces),
           "LEADZEN_SETTINGS_KEY": fixture.key, "LEADZEN_ENV": "development"}
    script = """
import django,io,sqlite3,os,uuid
from pathlib import Path
django.setup()
from django.core.management import call_command
from leadzen.accounts.service import create_account
from leadzen.configuration import save_dashboard_settings
from leadzen.accounts.models import AccountProfile
call_command('migrate',verbosity=0,stdout=io.StringIO())
actor=create_account(email='synthetic-fixture@example.invalid',name='Synthetic',password='SyntheticPassword!753',require_change=False)
profile=AccountProfile.objects.get(user=actor)
save_dashboard_settings({'provider':'openai','model':'synthetic'},llm_api_key='synthetic-fixture-only-key')
folder=Path(os.environ['LEADZEN_WORKSPACE_ROOT'])/str(profile.pk)
folder.mkdir(mode=0o700)
with sqlite3.connect(os.environ['LEADZEN_DB']) as source,sqlite3.connect(folder/'db.sqlite3') as target:
 source.backup(target)
(folder/'db.sqlite3').chmod(0o600)
(folder/'initialized').touch(mode=0o600)
"""
    # The earlier tiny schema is exclusively synthetic and replaced here only.
    fixture.control.unlink()
    for folder in fixture.workspaces.iterdir():
        import shutil
        shutil.rmtree(folder)
    subprocess.run([sys.executable, "-c", script], env=env, check=True, capture_output=True, timeout=120)
    fixture.control.chmod(0o600)
    snapshot = make_backup(fixture)
    target = fixture.root / "real-schema-drill"
    r.restore(snapshot, target)
    result = r.isolated_drill(target)
    assert result["status"] == "PASS" and result["network_blocked"] is True
    assert result["authentication"] and result["session_revocation"]
    assert result["workspace_routes"] == 1 and result["synthetic_isolation_workspaces"] == 2
    assert result["record_preservation"] and result["integrity_and_foreign_keys"]
    assert result["validated_database_count"] == 2
    assert result["original_records_checked"] > 0 and result["encrypted_records_checked"] >= 1
    # Original synthetic snapshot is unchanged by migration/login/write tests.
    r.verify_snapshot(snapshot)
    # Faults introduced by an isolated migration must be discovered before
    # synthetic authentication could incorrectly certify a damaged restore.
    fault_script = """
import django.core.management as commands,json,os,sqlite3,sys
original=commands.call_command
def damaged(command,*args,**kwargs):
 result=original(command,*args,**kwargs)
 if command=='migrate' and not kwargs.get('database'):
  with sqlite3.connect(os.environ['LEADZEN_DB']) as database:
   if sys.argv[2]=='record':
    database.execute("UPDATE auth_user SET first_name='isolated damage'")
   else:
    database.execute("UPDATE leadzen_config_runtimesettings SET encrypted_secrets='gAAAA-invalid'")
 return result
commands.call_command=damaged
from leadzen.operations.recovery import main
raise SystemExit(main(['_drill',sys.argv[1]]))
"""
    for fault, expected in [("record", "DRILL_RECORD_PRESERVATION_FAILED"), ("key", "MATCHED_SETTINGS_KEY_REQUIRED")]:
        damaged_target = fixture.root / ("damaged-" + fault)
        r.restore(snapshot, damaged_target)
        child = subprocess.run([sys.executable, "-c", fault_script, str(damaged_target), fault],
            cwd=damaged_target, env={"PATH": os.defpath, "LANG": "C.UTF-8",
                "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
            capture_output=True, text=True, timeout=120)
        assert child.returncode == 1
        assert json.loads(child.stdout) == {"status": "FAIL", "code": expected}
