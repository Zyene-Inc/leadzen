"""Quiesced full-server snapshots and isolated, outbound-disabled recovery.

This module never stops services or overwrites a database. It requires the
operator to stop every writer first, and refuses a snapshot without a verified
copy on another filesystem. Errors expose fixed categories, never input values.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tarfile
import time
import uuid

from cryptography.fernet import Fernet, InvalidToken

OWNER = "leadzen-full-recovery-v1"
UNIT = re.compile(r"^[A-Za-z0-9_.@-]+\.service$")


class RecoveryError(RuntimeError):
    """Safe operational failure code; no path, credentials or provider output."""


def safe_path(path, *, directory=False, private=True):
    path = Path(path).absolute()
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise RecoveryError("SYMLINK_PATH")
    info = path.stat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise RecoveryError("UNEXPECTED_FILE_TYPE")
    if info.st_uid not in ({os.geteuid()} if private else {0, os.geteuid()}) or (private and info.st_mode & 0o077):
        raise RecoveryError("PRIVATE_OWNED_PATH_REQUIRED")
    return path


def private_root(path, *, create=False):
    path = Path(path).absolute()
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise RecoveryError("SYMLINK_PATH")
    if not path.exists() and create:
        path.mkdir(mode=0o700, parents=True)
    return safe_path(path, directory=True)


def digest(path):
    result = hashlib.sha256()
    with safe_path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_private(path, data):
    with Path(path).open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path, value):
    write_private(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def owned_lock(path):
    path = Path(path)
    if path.exists():
        safe_path(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode):
            raise RecoveryError("PRIVATE_OWNED_LOCK_REQUIRED")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecoveryError("WRITER_LOCK_BUSY") from None
        yield
    finally:
        os.close(descriptor)


def readonly_db(path):
    path = safe_path(path)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    connection.execute("PRAGMA query_only=ON")
    return connection


def validate_database(connection, cipher, *, allow_legacy_mailboxes=False):
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise RecoveryError("DATABASE_INTEGRITY_FAILED")
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise RecoveryError("DATABASE_FOREIGN_KEY_FAILED")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tokens = []
    for table, column in [("leadzen_config_runtimesettings", "encrypted_secrets"),
                          ("openoutreach_config_runtimesettings", "encrypted_secrets"),
                          ("leadzen_accounts_employeeinvitation", "encrypted_token")]:
        if table in tables:
            tokens.extend(row[0] for row in connection.execute(f'SELECT "{column}" FROM "{table}" WHERE "{column}" != \'\''))
    for token in tokens:
        try:
            value = json.loads(cipher.decrypt(token.encode()).decode())
            if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
                raise ValueError
        except (InvalidToken, ValueError, UnicodeError, TypeError):
            raise RecoveryError("MATCHED_SETTINGS_KEY_REQUIRED") from None
    mailbox_count, plaintext_count, nested_count = 0, 0, 0
    for table in ("outsend_emails_mailbox", "emails_mailbox"):
        if table not in tables:
            continue
        for (token,) in connection.execute(f'SELECT password FROM "{table}" WHERE password != \'\''):
            if not token.startswith("gAAAA"):
                plaintext_count += 1
                continue
            try:
                value = json.loads(cipher.decrypt(token.encode()).decode())
                password = value["mailbox_password"]
                if not isinstance(password, str):
                    raise ValueError
                if password.startswith("gAAAA"):
                    try:
                        json.loads(cipher.decrypt(password.encode()).decode())
                        nested_count += 1
                    except (InvalidToken, ValueError, UnicodeError):
                        pass  # A legitimate password can happen to use a prefix.
                mailbox_count += 1
            except (InvalidToken, ValueError, UnicodeError, TypeError, KeyError):
                raise RecoveryError("MATCHED_MAILBOX_KEY_REQUIRED") from None
    if not allow_legacy_mailboxes and (plaintext_count or nested_count):
        raise RecoveryError("LEGACY_MAILBOX_CREDENTIALS_UNVERIFIED")
    return {"encrypted_records": len(tokens), "encrypted_mailboxes": mailbox_count,
            "legacy_plaintext_mailboxes": plaintext_count, "nested_mailboxes": nested_count}


def _quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def record_inventory(connection, baseline=None):
    """Hash existing records privately across an isolated forward upgrade.

    New columns/tables are allowed, but all original business rows and their
    existing values must survive. Only the reviewed legacy field/table renames
    and migration 0018's explicit clock normalization are canonicalized. Django
    migration/permission/content-type records may gain rows; originals must stay.
    Neither record values nor these hashes are included in ordinary drill output.
    """
    raw_tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    tables = {}
    for raw in raw_tables:
        canonical = raw.replace("openoutreach_config_", "leadzen_config_", 1) if baseline is None and raw.startswith("openoutreach_config_") else raw
        if canonical in tables:
            raise RecoveryError("DRILL_DUPLICATE_RECORD_NAMESPACE")
        tables[canonical] = raw
    if baseline is None:
        clock_upgrade = "django_migrations" not in tables or not connection.execute(
            "SELECT 1 FROM django_migrations WHERE app IN ('leadzen_config','openoutreach_config') AND name='0018_new_york_time' LIMIT 1").fetchone()
        requested = tables
    else:
        clock_upgrade = baseline["clock_upgrade"]
        requested = baseline["tables"]
    result = {}
    append_only = {"django_migrations", "django_content_type", "auth_permission"}
    for table in sorted(requested):
        if table not in tables:
            raise RecoveryError("DRILL_RECORD_TABLE_LOST")
        raw = tables[table]
        mapping = {}
        for row in connection.execute("PRAGMA table_info(" + _quoted(raw) + ")"):
            column = "operator_country_code" if baseline is None and table == "leadzen_config_siteconfig" and row[1] == "country_code" else row[1]
            mapping[column] = row[1]
        columns = list(mapping) if baseline is None else baseline["tables"][table]["columns"]
        if any(column not in mapping for column in columns):
            raise RecoveryError("DRILL_RECORD_COLUMN_LOST")
        hashes = []
        query = "SELECT " + ",".join(_quoted(mapping[column]) for column in columns) + " FROM " + _quoted(raw)
        for row in connection.execute(query):
            values = list(row)
            for index, column in enumerate(columns):
                value = values[index]
                if baseline is None and table in {"django_migrations", "django_content_type"} and column in {"app", "app_label"} and value == "openoutreach_config":
                    values[index] = "leadzen_config"
                if baseline is None and clock_upgrade and table == "leadzen_config_emailcampaign" and column == "delay_timezone":
                    values[index] = "America/New_York"
                if clock_upgrade and (table, column) in {("leadzen_config_siteconfig", "sending_schedule"), ("leadzen_config_onboardingstate", "draft")}:
                    try:
                        saved = json.loads(value)
                        if baseline is None and table == "leadzen_config_siteconfig" and isinstance(saved, dict) and saved:
                            saved = {**saved, "timezone": "America/New_York"}
                        elif baseline is None and table == "leadzen_config_onboardingstate" and isinstance(saved, dict) and isinstance(saved.get("sending_schedule"), dict):
                            saved = {**saved, "sending_schedule": {**saved["sending_schedule"], "timezone": "America/New_York"}}
                        values[index] = json.dumps(saved, sort_keys=True, separators=(",", ":"))
                    except (ValueError, TypeError):
                        pass  # Malformed saved metadata still must remain identical.
            encoded = json.dumps(values, ensure_ascii=True, separators=(",", ":"),
                default=lambda value: {"sqlite_blob_hex": bytes(value).hex()}).encode()
            hashes.append(hashlib.sha256(encoded).digest())
        row = {"columns": columns, "rows": len(hashes),
               "sha256": hashlib.sha256(b"".join(sorted(hashes))).hexdigest()}
        if table in append_only:
            row["original_rows"] = set(hashes)
        result[table] = row
    return {"clock_upgrade": clock_upgrade, "tables": result}


def validate_restored_database(connection, cipher, baseline):
    encrypted = validate_database(connection, cipher)
    after = record_inventory(connection, baseline)
    for table, before in baseline["tables"].items():
        actual = after["tables"][table]
        if "original_rows" in before:
            preserved = actual["rows"] >= before["rows"] and before["original_rows"].issubset(actual["original_rows"])
        else:
            preserved = actual["rows"] == before["rows"] and actual["sha256"] == before["sha256"]
        if not preserved:
            raise RecoveryError("DRILL_RECORD_PRESERVATION_FAILED")
    return {"original_records_checked": sum(row["rows"] for row in baseline["tables"].values()),
            "encrypted_records_checked": encrypted["encrypted_records"] + encrypted["encrypted_mailboxes"]}


def namespace(control, root):
    """Include inactive/deleted accounts too; never silently omit old customer data."""
    root = private_root(root)
    rows = control.execute("SELECT id,user_id FROM leadzen_accounts_accountprofile ORDER BY id").fetchall()
    known = {}
    for identifier, user_id in rows:
        try:
            identifier = str(uuid.UUID(identifier))
        except (ValueError, TypeError):
            raise RecoveryError("INVALID_WORKSPACE_RELATIONSHIP") from None
        if identifier in known:
            raise RecoveryError("DUPLICATE_WORKSPACE_RELATIONSHIP")
        known[identifier] = user_id
    found = []
    for folder in root.iterdir():
        safe_path(folder, directory=True)
        if folder.name not in known:
            raise RecoveryError("ORPHAN_WORKSPACE_DIRECTORY")
        db, marker = folder / "db.sqlite3", folder / "initialized"
        if db.exists() != marker.exists():
            raise RecoveryError("PARTIAL_WORKSPACE_INITIALIZATION")
        if db.exists():
            safe_path(db)
            safe_path(marker)
            found.append({"workspace_id": folder.name, "actor_id": known[folder.name], "source": db})
    return found


class SystemdQuiescence:
    """The API unit includes MCP and its children; all scheduler units are required.

    Independent/unmanaged writer processes are outside this deployment contract.
    An operator must keep intake closed and must not start a writer during backup.
    Source data_version checks additionally refuse observed writes in that window.
    """
    def __init__(self, units):
        self.units = tuple(units)
        if not self.units or any(not UNIT.fullmatch(unit) for unit in self.units):
            raise RecoveryError("EXPLICIT_WRITER_UNITS_REQUIRED")

    def check(self):
        for unit in self.units:
            try:
                result = subprocess.run(["systemctl", "show", unit, "--property=LoadState,ActiveState,SubState,MainPID,ControlGroup"],
                                        capture_output=True, text=True, timeout=5, check=True)
                properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            except (OSError, subprocess.SubprocessError, ValueError):
                raise RecoveryError("WRITER_STATE_UNVERIFIED") from None
            if properties.get("LoadState") != "loaded" or properties.get("ActiveState") != "inactive" or properties.get("SubState") != "dead" or properties.get("MainPID") != "0":
                raise RecoveryError("WRITERS_NOT_QUIESCED")
            group = properties.get("ControlGroup")
            if group:
                if not group.startswith("/") or ".." in Path(group).parts:
                    raise RecoveryError("WRITER_STATE_UNVERIFIED")
                procs = Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.procs"
                if procs.exists() and procs.read_text().strip():
                    raise RecoveryError("WRITER_CHILDREN_STILL_ACTIVE")


def verify_snapshot(path):
    path = private_root(path)
    try:
        manifest = json.loads(safe_path(path / "manifest.json").read_text())
        marker = json.loads(safe_path(path / "COMPLETE").read_text())
        if manifest.get("owner") != OWNER or marker.get("manifest_sha256") != digest(path / "manifest.json"):
            raise RecoveryError("SNAPSHOT_NOT_OWNED_COMPLETE")
        files = manifest["files"]
        expected = {"manifest.json", "COMPLETE"}
        for row in files:
            relative = Path(row["name"])
            if relative.is_absolute() or ".." in relative.parts or str(relative) in expected:
                raise RecoveryError("SNAPSHOT_PATH_INVALID")
            expected.add(str(relative))
            file = safe_path(path / relative)
            if file.stat().st_size != row["bytes"] or digest(file) != row["sha256"]:
                raise RecoveryError("SNAPSHOT_CHECKSUM_FAILED")
        actual = {str(p.relative_to(path)) for p in path.rglob("*") if not p.is_dir()}
        if actual != expected:
            raise RecoveryError("SNAPSHOT_FILE_SET_MISMATCH")
        from leadzen.operations.preflight import read_private_env
        env = read_private_env(path / "private" / "backend.env", expected_uid=os.geteuid())
        if manifest.get("kind", "native") == "native" and not env.get("LEADZEN_SECRET_KEY"):
            raise RecoveryError("MATCHED_AUTHENTICATION_KEY_REQUIRED")
        cipher = Fernet(env["LEADZEN_SETTINGS_KEY"].encode())
        index = json.loads(safe_path(path / "private" / "index.json").read_text())
        with readonly_db(path / "databases" / "control.sqlite3") as control:
            validate_database(control, cipher, allow_legacy_mailboxes=manifest.get("kind") == "historical")
            relations = {str(uuid.UUID(row[0])): row[1] for row in control.execute("SELECT id,user_id FROM leadzen_accounts_accountprofile")}
        if len(index["workspaces"]) != manifest["workspace_count"]:
            raise RecoveryError("WORKSPACE_COUNT_MISMATCH")
        identifiers = set()
        for row in index["workspaces"]:
            identifier = str(uuid.UUID(row["workspace_id"]))
            if identifier in identifiers or relations.get(identifier) != row["actor_id"]:
                raise RecoveryError("WORKSPACE_RELATIONSHIP_MISMATCH")
            identifiers.add(identifier)
            db = row["database"]
            if db not in expected or not re.fullmatch(r"databases/workspace-[0-9]{6}\.sqlite3", db):
                raise RecoveryError("WORKSPACE_PATH_INVALID")
            with readonly_db(path / db) as connection:
                validate_database(connection, cipher, allow_legacy_mailboxes=manifest.get("kind") == "historical")
        return manifest
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError("SNAPSHOT_VALIDATION_FAILED") from None


class FilesystemCopy:
    """Explicit independently mounted protected storage; no network side effects."""
    def __init__(self, destination):
        self.root = private_root(destination, create=True)

    def publish(self, source, *, local_root):
        if self.root.stat().st_dev == Path(local_root).stat().st_dev:
            raise RecoveryError("INDEPENDENT_FILESYSTEM_REQUIRED")
        target = self.root / verify_snapshot(source)["snapshot"]
        with owned_lock(self.root / ".recovery.lock"):
            if target.exists():
                raise RecoveryError("INDEPENDENT_COPY_ALREADY_EXISTS")
            staging = self.root / (".pending-" + uuid.uuid4().hex)
            shutil.copytree(source, staging, copy_function=shutil.copyfile)
            protect_tree(staging)
            verify_snapshot(staging)
            sync_tree(staging)
            os.rename(staging, target)
            fsync_dir(self.root)
        return {"adapter": "independent-filesystem", "verified": True}


def protect_tree(root):
    for path in [Path(root), *Path(root).rglob("*")]:
        if path.is_symlink():
            raise RecoveryError("SYMLINK_PATH")
        path.chmod(0o700 if path.is_dir() else 0o600)


def sync_tree(root):
    for path in Path(root).rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    for path in reversed([Path(root), *[p for p in Path(root).rglob("*") if p.is_dir()]]):
        fsync_dir(path)


def backup(*, env_file, release_manifest, service_files, destination, independent_copy, quiescence, protected_files=()):
    from leadzen.operations.preflight import read_private_env
    env_file = safe_path(env_file)
    env = read_private_env(env_file, expected_uid=os.geteuid())
    try:
        cipher = Fernet(env["LEADZEN_SETTINGS_KEY"].encode())
        control_path = safe_path(env["LEADZEN_DB"])
        workspace_root = private_root(env["LEADZEN_WORKSPACE_ROOT"])
        if not env.get("LEADZEN_SECRET_KEY"):
            raise RecoveryError("MATCHED_AUTHENTICATION_KEY_REQUIRED")
    except (KeyError, ValueError):
        raise RecoveryError("BACKUP_CONFIGURATION_INVALID") from None
    release_manifest = safe_path(release_manifest, private=False)
    try:
        from leadzen.operations.release import verify
        release = verify(release_manifest.parent)
        if release_manifest.name != "manifest.json" or not release["artifacts"]:
            raise ValueError
    except (ValueError, OSError, KeyError):
        raise RecoveryError("RELEASE_MANIFEST_INVALID") from None
    release_inputs = [(release_manifest, "private/release/manifest.json"),
                      (safe_path(release_manifest.parent / "source.tar", private=False), "private/release/source.tar")]
    for item in release["artifacts"]:
        if item.get("source_sha256") != release["source_sha256"]:
            raise RecoveryError("RELEASE_ARTIFACT_SOURCE_MISMATCH")
        release_inputs.append((safe_path(release_manifest.parent / "artifacts" / item["name"], private=False), "private/release/artifacts/" + item["name"]))
    release_before = [digest(path) for path, _ in release_inputs]
    if not service_files:
        raise RecoveryError("MATCHED_SERVICE_METADATA_REQUIRED")
    service_files = [safe_path(file, private=False) for file in service_files]
    protected_files = [safe_path(file) for file in protected_files]
    if (len(protected_files) > 32 or len(set(protected_files)) != len(protected_files)
            or any(file.stat().st_size > 1024 * 1024 or file.stat().st_nlink != 1 for file in protected_files)):
        raise RecoveryError("PROTECTED_METADATA_INVALID")
    destination = private_root(destination, create=True)
    # Storage below a source workspace would be mistaken for customer namespace.
    if destination == workspace_root or workspace_root in destination.parents:
        raise RecoveryError("BACKUP_DESTINATION_OVERLAPS_SOURCE")
    name = "snapshot-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
    with ExitStack() as stack:
        stack.enter_context(owned_lock(destination / ".recovery.lock"))
        quiescence.check()
        stack.enter_context(owned_lock(control_path.parent / "send.lock"))
        scheduler = control_path.parent / "scheduler"
        scheduler.mkdir(mode=0o700, exist_ok=True)
        private_root(scheduler)
        stack.enter_context(owned_lock(scheduler / "send.lock"))
        control = stack.enter_context(readonly_db(control_path))
        initial_control_version = control.execute("PRAGMA data_version").fetchone()[0]
        rows = namespace(control, workspace_root)
        sources = [(control, "databases/control.sqlite3")]
        for number, row in enumerate(rows, 1):
            stack.enter_context(owned_lock(row["source"].parent / "initialize.lock"))
            stack.enter_context(owned_lock(row["source"].parent / "send.lock"))
            row["database"] = f"databases/workspace-{number:06d}.sqlite3"
            sources.append((stack.enter_context(readonly_db(row["source"])), row["database"]))
        versions = [conn.execute("PRAGMA data_version").fetchone()[0] for conn, _ in sources]
        if versions[0] != initial_control_version:
            raise RecoveryError("WRITE_OBSERVED_DURING_BACKUP")
        env_bytes, release_bytes = env_file.read_bytes(), release_manifest.read_bytes()
        service_bytes = [file.read_bytes() for file in service_files]
        protected_bytes = [file.read_bytes() for file in protected_files]
        def sources_unchanged():
            # Recheck after expensive artifact/mirror copies, not merely after
            # the database copies. A completed mirror from an aborted attempt is
            # retained as evidence; it does not qualify as local backup success.
            quiescence.check()
            if versions != [conn.execute("PRAGMA data_version").fetchone()[0] for conn, _ in sources]:
                raise RecoveryError("WRITE_OBSERVED_DURING_BACKUP")
            if [(row["workspace_id"], row["actor_id"]) for row in rows] != [(row["workspace_id"], row["actor_id"]) for row in namespace(control, workspace_root)]:
                raise RecoveryError("WORKSPACE_NAMESPACE_CHANGED_DURING_BACKUP")
            if safe_path(env_file).read_bytes() != env_bytes or safe_path(release_manifest, private=False).read_bytes() != release_bytes or [safe_path(file, private=False).read_bytes() for file in service_files] != service_bytes:
                raise RecoveryError("METADATA_CHANGED_DURING_BACKUP")
            if [safe_path(file).read_bytes() for file in protected_files] != protected_bytes:
                raise RecoveryError("PROTECTED_METADATA_CHANGED_DURING_BACKUP")
            quiescence.check()
        staging = destination / (".pending-" + uuid.uuid4().hex)
        staging.mkdir(mode=0o700)
        (staging / "private").mkdir(mode=0o700)
        (staging / "databases").mkdir(mode=0o700)
        # Failed/incomplete staging is retained for operator investigation; it
        # never qualifies for restore, retention, freshness or release success.
        for connection, relative in sources:
            validate_database(connection, cipher)
            output = staging / relative
            write_private(output, b"")
            with sqlite3.connect(output) as copied:
                deadline = time.monotonic() + 120
                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise RecoveryError("DATABASE_BACKUP_DEADLINE")
                connection.backup(copied, pages=256, progress=progress, sleep=0.05)
                validate_database(copied, cipher)
        sources_unchanged()
        write_private(staging / "private/backend.env", env_bytes)
        for path, relative in release_inputs:
            output = staging / relative
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with path.open("rb") as source, output.open("xb") as target:
                os.fchmod(target.fileno(), 0o600)
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
        if release_before != [digest(path) for path, _ in release_inputs] or release_before != [digest(staging / relative) for _, relative in release_inputs]:
            raise RecoveryError("RELEASE_CHANGED_DURING_BACKUP")
        for number, content in enumerate(service_bytes, 1):
            write_private(staging / f"private/service-{number:03d}.unit", content)
        protected_index = []
        for number, (file, content) in enumerate(zip(protected_files, protected_bytes), 1):
            relative = f"private/protected-{number:03d}.bin"
            write_private(staging / relative, content)
            protected_index.append({"source_name": file.name, "stored": relative})
        write_json(staging / "private/index.json", {
            "workspaces": [{k: row[k] for k in ("workspace_id", "actor_id", "database")} for row in rows],
            "protected_files": protected_index,
        })
        files = [{"name": str(file.relative_to(staging)), "bytes": file.stat().st_size, "sha256": digest(file)}
                 for file in sorted(staging.rglob("*")) if file.is_file()]
        manifest = {"owner": OWNER, "kind": "native", "snapshot": name, "created_at": datetime.now(timezone.utc).isoformat(),
                    "workspace_count": len(rows), "database_count": len(sources), "files": files}
        write_json(staging / "manifest.json", manifest)
        write_json(staging / "COMPLETE", {"manifest_sha256": digest(staging / "manifest.json")})
        verify_snapshot(staging)
        sync_tree(staging)
        sources_unchanged()
        receipt = independent_copy.publish(staging, local_root=destination)
        if receipt != {"adapter": "independent-filesystem", "verified": True}:
            raise RecoveryError("INDEPENDENT_COPY_UNVERIFIED")
        if release_before != [digest(path) for path, _ in release_inputs]:
            raise RecoveryError("RELEASE_CHANGED_DURING_BACKUP")
        # Locks remain held through the rename. The reviewed stopped-unit/hold
        # contract bounds the remaining observation-to-rename window; this is
        # not protection against an administrator starting an unmanaged writer.
        sources_unchanged()
        os.rename(staging, destination / name)
        fsync_dir(destination)
    return {"status": "PASS", "snapshot": name, "workspace_count": len(rows), "independent_copy": True}


def restore(snapshot, target):
    """Copy a verified snapshot only into a brand-new, isolated directory."""
    snapshot = private_root(snapshot)
    manifest = verify_snapshot(snapshot)
    target = Path(target).absolute()
    if target.exists() or target.is_symlink():
        raise RecoveryError("NEW_ISOLATED_RESTORE_TARGET_REQUIRED")
    private_root(target.parent)
    if target == snapshot or snapshot in target.parents:
        raise RecoveryError("RESTORE_TARGET_OVERLAPS_SNAPSHOT")
    target.mkdir(mode=0o700)
    (target / "workspaces").mkdir(mode=0o700)
    shutil.copyfile(snapshot / "databases/control.sqlite3", target / "control.sqlite3")
    index = json.loads((snapshot / "private/index.json").read_text())
    for row in index["workspaces"]:
        folder = target / "workspaces" / str(uuid.UUID(row["workspace_id"]))
        folder.mkdir(mode=0o700)
        shutil.copyfile(snapshot / row["database"], folder / "db.sqlite3")
        write_private(folder / "initialized", b"")
    # Matching secrets remain protected, while outbound services and public
    # integrations are forcibly disabled in the separate drill runtime env.
    shutil.copytree(snapshot / "private", target / "private", copy_function=shutil.copyfile)
    protect_tree(target)
    from leadzen.operations.preflight import read_private_env
    original = read_private_env(target / "private/backend.env", expected_uid=os.geteuid())
    drill = {name: original[name] for name in ("LEADZEN_SETTINGS_KEY", "LEADZEN_SECRET_KEY") if name in original}
    drill.update({"LEADZEN_DB": str(target / "control.sqlite3"), "LEADZEN_WORKSPACE_ROOT": str(target / "workspaces"),
                  "LEADZEN_ENV": "development", "LEADZEN_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
                  "LEADZEN_DASHBOARD_TOKEN": uuid.uuid4().hex + uuid.uuid4().hex,
                  "LEADZEN_AUTOPILOT_ENABLED": "0", "LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED": "0"})
    write_json(target / "private/drill-env.json", drill)
    write_json(target / "RESTORED", {"owner": OWNER, "snapshot": manifest["snapshot"], "outbound_disabled": True})
    protect_tree(target)
    fsync_dir(target)
    return {"status": "PASS", "database_count": manifest["database_count"], "outbound_disabled": True}


def import_historical_archive(archive, target, *, historical_date):
    """Preserve a reviewed old recovery set without pretending it is current.

    Only selected regular env/database/unit members are extracted. Links and
    arbitrary archive entries are never restored. Original archive bytes, which
    contain the old release/runtime, stay in the protected bundle for review.
    """
    archive = safe_path(archive)
    target = Path(target).absolute()
    if target.exists() or target.is_symlink():
        raise RecoveryError("NEW_HISTORICAL_TARGET_REQUIRED")
    private_root(target.parent)
    try:
        datetime.strptime(historical_date, "%Y-%m-%d")
    except ValueError:
        raise RecoveryError("HISTORICAL_DATE_REQUIRED") from None
    target.mkdir(mode=0o700)
    (target / "private").mkdir(mode=0o700)
    (target / "databases").mkdir(mode=0o700)
    with tarfile.open(archive, "r:*") as tar:
        regular = [member for member in tar.getmembers() if member.isfile() and not Path(member.name).is_absolute() and ".." not in Path(member.name).parts]
        environments = [member for member in regular if Path(member.name).name.endswith(".env")]
        if len(environments) != 1 or environments[0].size > 256 * 1024:
            raise RecoveryError("HISTORICAL_MATCHED_ENV_UNVERIFIED")
        write_private(target / "private/backend.env", tar.extractfile(environments[0]).read())
        from leadzen.operations.preflight import read_private_env
        env = read_private_env(target / "private/backend.env", expected_uid=os.geteuid())
        suffix = "/".join(Path(env["LEADZEN_DB"]).parts[-2:])
        controls = [member for member in regular if member.name.endswith(suffix) and "/workspaces/" not in member.name]
        if len(controls) != 1:
            raise RecoveryError("HISTORICAL_CONTROL_DATABASE_UNVERIFIED")
        def extract(member, path):
            if member.size > 256 * 1024 ** 3:
                raise RecoveryError("HISTORICAL_DATABASE_SIZE_UNSUPPORTED")
            with tar.extractfile(member) as source, path.open("xb") as output:
                os.fchmod(output.fileno(), 0o600)
                shutil.copyfileobj(source, output, length=1024 * 1024)
        extract(controls[0], target / "databases/control.sqlite3")
        with readonly_db(target / "databases/control.sqlite3") as control:
            cipher = Fernet(env["LEADZEN_SETTINGS_KEY"].encode())
            validate_database(control, cipher, allow_legacy_mailboxes=True)
            relations = {str(uuid.UUID(identifier)): actor for identifier, actor in control.execute("SELECT id,user_id FROM leadzen_accounts_accountprofile")}
        workspaces = []
        members_by_name = {member.name: member for member in regular}
        for member in regular:
            match = re.search(r"(?:^|/)workspaces/([0-9a-f-]{36})/db\.sqlite3$", member.name)
            if not match:
                continue
            identifier = str(uuid.UUID(match.group(1)))
            if identifier not in relations or any(row["workspace_id"] == identifier for row in workspaces):
                raise RecoveryError("HISTORICAL_WORKSPACE_RELATIONSHIP_FAILED")
            if member.name.rsplit("/", 1)[0] + "/initialized" not in members_by_name:
                raise RecoveryError("HISTORICAL_INITIALIZATION_UNVERIFIED")
            relative = f"databases/workspace-{len(workspaces) + 1:06d}.sqlite3"
            extract(member, target / relative)
            with readonly_db(target / relative) as connection:
                validate_database(connection, cipher, allow_legacy_mailboxes=True)
            workspaces.append({"workspace_id": identifier, "actor_id": relations[identifier], "database": relative})
        units = [member for member in regular if member.name.endswith(".service")]
        for number, member in enumerate(units, 1):
            if member.size > 1024 * 1024:
                raise RecoveryError("HISTORICAL_SERVICE_METADATA_INVALID")
            extract(member, target / f"private/service-{number:03d}.unit")
    # Copy only; no unpacking of bundled runtime, executable source or links.
    with archive.open("rb") as source, (target / "private/historical-release.tar.gz").open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        shutil.copyfileobj(source, output, length=1024 * 1024)
    write_json(target / "private/index.json", {"workspaces": workspaces})
    files = [{"name": str(p.relative_to(target)), "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(target.rglob("*")) if p.is_file()]
    manifest = {"owner": OWNER, "kind": "historical", "snapshot": target.name,
                "created_at": historical_date + "T00:00:00+00:00", "workspace_count": len(workspaces),
                "database_count": len(workspaces) + 1, "files": files,
                "current_release_proof": False, "authentication_key_present": bool(env.get("LEADZEN_SECRET_KEY"))}
    write_json(target / "manifest.json", manifest)
    write_json(target / "COMPLETE", {"manifest_sha256": digest(target / "manifest.json")})
    verify_snapshot(target)
    sync_tree(target)
    return {"status": "PASS", "kind": "historical", "historical_date": historical_date,
            "database_count": manifest["database_count"], "workspace_count": len(workspaces),
            "current_release_proof": False, "authentication_key_present": manifest["authentication_key_present"]}


def isolated_drill(root):
    """Run canonical authentication and router checks in a scrubbed subprocess."""
    root = private_root(root)
    if json.loads(safe_path(root / "RESTORED").read_text()).get("owner") != OWNER:
        raise RecoveryError("OWNED_RESTORE_REQUIRED")
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1"}
    env.update(json.loads(safe_path(root / "private/drill-env.json").read_text()))
    result = subprocess.run([sys.executable, "-m", "leadzen.operations.recovery", "_drill", str(root)],
                            env=env, capture_output=True, text=True, timeout=120)
    if result.returncode:
        # The child emits a fixed diagnostic code rather than a traceback. Keep
        # that code in the operator-facing failure so a blocked restore can be
        # repaired without exposing paths, credentials, or customer records.
        child_code = "CHILD_FAILED"
        try:
            child_report = json.loads(result.stdout)
            candidate = child_report.get("code") if isinstance(child_report, dict) else None
            if isinstance(candidate, str) and re.fullmatch(r"[A-Z0-9_]{1,80}", candidate):
                child_code = candidate
        except (ValueError, TypeError):
            pass
        raise RecoveryError("ISOLATED_DRILL_FAILED_" + child_code)
    try:
        report = json.loads(result.stdout)
        if report.get("status") != "PASS" or report.get("network_blocked") is not True:
            raise ValueError
        write_json(root / "private/drill-result.json", report)
        return report
    except (ValueError, KeyError):
        raise RecoveryError("ISOLATED_DRILL_INVALID_RESULT") from None


def _drill(root):
    root = private_root(root)
    env = json.loads(safe_path(root / "private/drill-env.json").read_text())
    if Path(env.get("LEADZEN_DB", "")) != root / "control.sqlite3" or Path(env.get("LEADZEN_WORKSPACE_ROOT", "")) != root / "workspaces" or env.get("LEADZEN_AUTOPILOT_ENABLED") != "0" or env.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") != "0":
        raise RecoveryError("ISOLATED_DRILL_ENV_INVALID")
    # Deny sockets and child commands before Django imports. Existing provider
    # credentials in restored data cannot contact an external service in this
    # controlled drill process; this is not a general-purpose sandbox.
    def deny(*args, **kwargs):
        raise RecoveryError("DRILL_NETWORK_OR_PROCESS_DENIED")
    import ssl  # Load SSL socket subclasses before replacing socket construction.
    class DeniedSocket(socket.socket):
        connect = connect_ex = sendto = bind = listen = deny
    socket.socket = DeniedSocket
    socket.create_connection = socket.getaddrinfo = deny
    subprocess.Popen = deny
    try:
        cipher = Fernet(env["LEADZEN_SETTINGS_KEY"].encode())
    except (KeyError, ValueError):
        raise RecoveryError("DRILL_MATCHED_SETTINGS_KEY_REQUIRED") from None
    # Read the complete original namespace and private record fingerprints
    # before Django startup's historical table upgrade or any forward migration.
    with readonly_db(root / "control.sqlite3") as control:
        original_workspaces = namespace(control, root / "workspaces")
    originals = [(root / "control.sqlite3", None), *[(row["source"], row) for row in original_workspaces]]
    baselines = {}
    for database, _ in originals:
        with readonly_db(database) as connection:
            validate_database(connection, cipher)
            baselines[database] = record_inventory(connection)
    os.environ.update(env)
    os.environ["DJANGO_SETTINGS_MODULE"] = "leadzen.settings"
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import Client
    from leadzen.accounts.models import AccountProfile
    from leadzen.workspaces import workspace_scope
    from cold_outreach.leads.models import Lead
    from django.db import connections
    from django.core.management import call_command
    # Schema upgrades are restricted to this isolated restore. The original
    # archive and all original production paths remain untouched.
    call_command("migrate", verbosity=0, stdout=open(os.devnull, "w"))
    validated = []
    with readonly_db(root / "control.sqlite3") as control:
        validated.append(validate_restored_database(control, cipher, baselines[root / "control.sqlite3"]))
        current_workspaces = namespace(control, root / "workspaces")
    if [(row["workspace_id"], row["actor_id"]) for row in original_workspaces] != [(row["workspace_id"], row["actor_id"]) for row in current_workspaces]:
        raise RecoveryError("DRILL_WORKSPACE_RELATIONSHIP_CHANGED")
    scoped = []
    for row in original_workspaces:
        actual = AccountProfile.objects.get(pk=row["workspace_id"])
        with workspace_scope(actual) as alias:
            call_command("migrate", database=alias, verbosity=0, stdout=open(os.devnull, "w"))
            if Path(connections[alias].settings_dict["NAME"]) != root / "workspaces" / str(actual.pk) / "db.sqlite3":
                raise RecoveryError("DRILL_ROUTER_ISOLATION_FAILED")
            scoped.append(Lead.objects.count())
        with readonly_db(row["source"]) as connection:
            validated.append(validate_restored_database(connection, cipher, baselines[row["source"]]))
    # A synthetic actor added only to this isolated copy proves login/logout
    # without knowing or resetting a real employee password.
    from leadzen.accounts.service import create_account
    # UUIDs are also used in the actor's email. Independent random hexadecimal
    # strings can trip Django's similarity validator; generate a longer password
    # from a separate alphabet while retaining the real password validators.
    password = secrets.token_urlsafe(48) + "8!Aq"
    actor = create_account(email="recovery-drill-" + uuid.uuid4().hex + "@example.invalid",
                           name="Synthetic recovery verification", password=password, require_change=False)
    client = Client()
    assert client.get("/api/auth/me").status_code == 401
    # Canonical login service with a known isolated synthetic credential.
    headers = {"HTTP_AUTHORIZATION": "Bearer " + env["LEADZEN_DASHBOARD_TOKEN"]}
    response = client.post("/api/auth/login", json.dumps({"email": actor.email, "password": password}), content_type="application/json", **headers)
    if response.status_code != 200:
        raise RecoveryError("DRILL_AUTHENTICATION_FAILED")
    token = response.json().get("session_token")
    if not token:
        raise RecoveryError("DRILL_AUTHENTICATION_FAILED")
    headers["HTTP_X_LEADZEN_SESSION"] = token
    if client.get("/api/auth/me", **headers).status_code != 200 or client.post("/api/auth/logout", **headers).status_code != 200 or client.get("/api/auth/me", **headers).status_code != 401:
        raise RecoveryError("DRILL_SESSION_REVOCATION_FAILED")
    # Two fresh synthetic employee workspaces prove cross-actor routing even
    # when the historical restore contains only one initialized employee.
    synthetic = []
    from django.utils import timezone as django_timezone
    from cold_outreach.leads.models import Deal
    for number in range(2):
        user = create_account(email="isolation-" + uuid.uuid4().hex + "@example.invalid", name="Synthetic isolation",
                              password=secrets.token_urlsafe(48) + "8!Aq", require_change=False)
        profile = AccountProfile.objects.get(user=user)
        profile.onboarding_completed_at = django_timezone.now()
        profile.save(update_fields=["onboarding_completed_at"])
        folder = root / "workspaces" / str(profile.pk)
        folder.mkdir(mode=0o700)
        database = folder / "db.sqlite3"
        with sqlite3.connect(root / "control.sqlite3") as source, sqlite3.connect(database) as target:
            schema = source.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END").fetchall()
            for (statement,) in schema:
                target.execute(statement)
            migrations = source.execute("SELECT app,name,applied FROM django_migrations").fetchall()
            target.executemany("INSERT INTO django_migrations(app,name,applied) VALUES(?,?,?)", migrations)
        database.chmod(0o600)
        write_private(folder / "initialized", b"")
        marker = "synthetic-isolation-" + uuid.uuid4().hex
        with workspace_scope(profile):
            lead = Lead.objects.create(lead_id=marker, email="synthetic@example.invalid")
            Deal.objects.create(lead=lead)
        synthetic.append((profile, marker))
    for own, own_marker in synthetic:
        with workspace_scope(own):
            if not Lead.objects.filter(lead_id=own_marker).exists() or any(Lead.objects.filter(lead_id=other_marker).exists() for other, other_marker in synthetic if other != own):
                raise RecoveryError("DRILL_TENANT_ISOLATION_FAILED")
    return {"status": "PASS", "network_blocked": True, "authentication": True, "session_revocation": True,
            "workspace_routes": len(scoped), "synthetic_isolation_workspaces": 2,
            "record_preservation": True, "integrity_and_foreign_keys": True,
            "validated_database_count": len(validated), "encrypted_settings": True,
            "original_records_checked": sum(row["original_records_checked"] for row in validated),
            "encrypted_records_checked": sum(row["encrypted_records_checked"] for row in validated)}


def retain(root, *, keep, independent_root):
    """Delete only old owned verified snapshots with their verified second copy."""
    if keep < 2:
        raise RecoveryError("RETENTION_REQUIRES_TWO_SNAPSHOTS")
    root, independent_root = private_root(root), private_root(independent_root)
    with owned_lock(root / ".recovery.lock"), owned_lock(independent_root / ".recovery.lock"):
        verified = []
        for path in root.glob("snapshot-*"):
            try:
                manifest = verify_snapshot(path)
                mirror = verify_snapshot(independent_root / path.name)
                if manifest.get("kind") == "native" and mirror == manifest:
                    verified.append((manifest["created_at"], path))
            except (RecoveryError, OSError):
                continue
        removed = 0
        for _, path in sorted(verified, reverse=True)[keep:]:
            # The independent protected copy is intentionally retained. Remote
            # retention is a separate reviewed storage policy, never inferred.
            shutil.rmtree(path)
            removed += 1
        fsync_dir(root)
        return {"status": "PASS", "removed_owned_verified_snapshots": removed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    command = actions.add_parser("backup")
    for name in ("env-file", "release-manifest", "destination", "independent-destination"):
        command.add_argument("--" + name, required=True)
    command.add_argument("--service-unit-file", action="append", required=True)
    command.add_argument("--protected-file", action="append", default=[], help="Owned private matching dashboard env, proxy or other configuration (up to 1 MiB each)")
    command.add_argument("--writer-unit", action="append", required=True)
    for name in ("verify", "restore", "drill", "_drill"):
        command = actions.add_parser(name)
        command.add_argument("path")
        if name == "restore":
            command.add_argument("--target", required=True)
    command = actions.add_parser("import-historical")
    command.add_argument("path")
    command.add_argument("--target", required=True)
    command.add_argument("--historical-date", required=True)
    command = actions.add_parser("retain")
    command.add_argument("path")
    command.add_argument("--independent-root", required=True)
    command.add_argument("--keep", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "backup":
            from leadzen.operations.preflight import read_private_env
            env = read_private_env(args.env_file, expected_uid=os.geteuid())
            required = {"leadzen.service"}
            if env.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") == "1" or env.get("LEADZEN_AUTOPILOT_ENABLED") == "1":
                required.add("leadzen-followups.service")
            if not required.issubset(args.writer_unit):
                raise RecoveryError("ALL_WRITER_UNITS_REQUIRED")
            result = backup(env_file=args.env_file, release_manifest=args.release_manifest,
                            service_files=args.service_unit_file, destination=args.destination,
                            independent_copy=FilesystemCopy(args.independent_destination),
                            quiescence=SystemdQuiescence(args.writer_unit), protected_files=args.protected_file)
        elif args.action == "verify":
            manifest = verify_snapshot(args.path)
            result = {"status": "PASS", "database_count": manifest["database_count"]}
        elif args.action == "restore":
            result = restore(args.path, args.target)
        elif args.action == "import-historical":
            result = import_historical_archive(args.path, args.target, historical_date=args.historical_date)
        elif args.action == "retain":
            result = retain(args.path, keep=args.keep, independent_root=args.independent_root)
        else:
            result = _drill(args.path) if args.action == "_drill" else isolated_drill(args.path)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, RecoveryError) else "RECOVERY_OPERATION_FAILED"
        print(json.dumps({"status": "FAIL", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
