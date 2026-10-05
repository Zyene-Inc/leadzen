"""Offline release checks. Never import the application settings or mutate data.

The report contains fixed check codes and aggregate counts only. Path and secret
values are retained in process for validation, never included in diagnostics.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from dataclasses import dataclass
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import socket
import sqlite3
import stat
import subprocess
import sys
import time
from typing import Mapping
from urllib.parse import urlsplit
import uuid

from cryptography.fernet import Fernet, InvalidToken

from leadzen.production import REQUIRED, _https_origin as production_origin_valid, validate_environment


class PreflightError(ValueError):
    """A deliberately value-free diagnostic safe for operator reports."""

    def __init__(self, code: str, *, blocked: bool = False):
        self.code = code
        self.blocked = blocked
        super().__init__(code)


@dataclass(frozen=True)
class DatabaseTarget:
    role: str
    path: Path


def _no_symlinks(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise PreflightError("PATH_NOT_CANONICAL")
    for component in reversed((path, *path.parents)):
        try:
            if stat.S_ISLNK(component.lstat().st_mode):
                raise PreflightError("SYMLINK_FORBIDDEN")
        except FileNotFoundError:
            raise PreflightError("PATH_MISSING", blocked=True) from None
        except OSError:
            raise PreflightError("PATH_UNREADABLE", blocked=True) from None


def _private_path(path: Path, uid: int, *, directory: bool = False) -> None:
    _no_symlinks(path)
    info = path.stat()
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(info.st_mode):
        raise PreflightError("STORAGE_TYPE_INVALID")
    if info.st_uid != uid:
        raise PreflightError("STORAGE_OWNER_INVALID")
    if stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
        raise PreflightError("STORAGE_MODE_INVALID")
    if not directory and info.st_nlink != 1:
        raise PreflightError("STORAGE_HARDLINK_FORBIDDEN")


def _read_private_file(path: str | Path, expected_uid: int, limit: int) -> bytes:
    target = Path(path)
    _private_path(target, expected_uid)
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as source:
            actual = os.fstat(source.fileno())
            if actual.st_uid != expected_uid or stat.S_IMODE(actual.st_mode) != 0o600 or not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1:
                raise PreflightError("PRIVATE_FILE_CHANGED")
            data = source.read(limit + 1)
        if len(data) > limit:
            raise PreflightError("PRIVATE_FILE_TOO_LARGE")
        return data
    except OSError:
        raise PreflightError("PRIVATE_FILE_UNREADABLE", blocked=True) from None


def read_private_env(path: str | Path, *, expected_uid: int) -> dict[str, str]:
    """Read a mode-600 file without shell execution, interpolation or logging.

    One NAME=value per line; whole-line comments and quoted single-line values
    are supported. Ambiguous duplicates, substitutions and multiline values fail.
    """
    try:
        contents = _read_private_file(path, expected_uid, 256 * 1024).decode("utf-8")
    except UnicodeError:
        raise PreflightError("ENV_ENCODING_INVALID") from None
    values: dict[str, str] = {}
    for line in contents.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in values:
            raise PreflightError("ENV_SYNTAX_INVALID")
        value = value.strip()
        if "$(" in value or "`" in value or "\x00" in value:
            raise PreflightError("ENV_SUBSTITUTION_FORBIDDEN")
        if value.startswith(("'", '"')):
            try:
                parsed = shlex.split(value, comments=False, posix=True)
            except ValueError:
                raise PreflightError("ENV_SYNTAX_INVALID") from None
            if len(parsed) != 1:
                raise PreflightError("ENV_SYNTAX_INVALID")
            value = parsed[0]
        elif "'" in value or '"' in value or "\\" in value:
            raise PreflightError("ENV_SYNTAX_INVALID")
        values[key] = value
    return values


def _read_policy(path: str | Path) -> dict:
    # Policies contain no secrets, but treating them as private configuration
    # avoids mixing permissive report files with authoritative operator inputs.
    try:
        result = json.loads(_read_private_file(path, os.geteuid(), 64 * 1024))
    except PreflightError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise PreflightError("POLICY_INVALID") from None
    if not isinstance(result, dict):
        raise PreflightError("POLICY_INVALID")
    return result


def _https_origin(value: str) -> str:
    if not production_origin_valid(value):
        raise PreflightError("PUBLIC_ORIGIN_INVALID")
    return value


def _network_policy(policy: Mapping, backend: Mapping, dashboard: Mapping) -> None:
    required = ("dashboard_origin", "api_origin", "private_listen_addresses", "trusted_proxy_networks", "forwarded_proxy_addresses")
    if any(name not in policy for name in required):
        raise PreflightError("NETWORK_POLICY_MISSING", blocked=True)
    public = _https_origin(policy["dashboard_origin"])
    api = _https_origin(policy["api_origin"])
    if backend.get("LEADZEN_PUBLIC_URL") != public or dashboard.get("LEADZEN_DASHBOARD_PUBLIC_URL") != public or dashboard.get("LEADZEN_API_URL") != api:
        raise PreflightError("PUBLIC_ORIGIN_MISMATCH")
    origins = [item.strip() for item in backend.get("LEADZEN_DASHBOARD_ORIGINS", "").split(",")]
    if origins != [public]:
        raise PreflightError("DASHBOARD_ORIGINS_NOT_EXACT")
    hosts = [item.strip() for item in backend.get("LEADZEN_ALLOWED_HOSTS", "").split(",")]
    api_host = urlsplit(api).hostname
    # Django's Host allowlist uses bracketed IPv6 literals, matching HTTP Host.
    if ":" in api_host:
        api_host = "[" + api_host + "]"
    if api_host not in hosts or any(not re.fullmatch(r"[A-Za-z0-9.-]+|\[[0-9a-fA-F:]+\]", host) or host.startswith(".") or host.endswith(".") for host in hosts):
        raise PreflightError("API_HOSTS_INVALID")
    try:
        lists = [policy[name] for name in required[2:]]
        if any(not isinstance(values, list) or not values for values in lists):
            raise ValueError
        listeners = [ipaddress.ip_address(value) for value in lists[0]]
        networks = [ipaddress.ip_network(value, strict=True) for value in lists[1]]
        proxies = [ipaddress.ip_address(value) for value in lists[2]]
        if any(address.is_unspecified or address.is_global or address.is_multicast or not (address.is_private or address.is_loopback) for address in listeners + proxies):
            raise ValueError
        if any(network.prefixlen == 0 or not network.network_address.is_private or not network.broadcast_address.is_private for network in networks):
            raise ValueError
        if any(not any(address in network for network in networks) for address in proxies):
            raise ValueError
    except (ValueError, TypeError):
        raise PreflightError("TRUSTED_PROXY_BOUNDARY_INVALID") from None


def _host_policy(policy: Mapping) -> None:
    if not policy.get("expected_hostname") or not policy.get("expected_machine"):
        raise PreflightError("HOST_IDENTITY_MISSING", blocked=True)
    if policy["expected_hostname"] != socket.gethostname() or policy["expected_machine"] != os.uname().machine:
        raise PreflightError("HOST_IDENTITY_MISMATCH")


@contextmanager
def readonly_database(target: DatabaseTarget, *, seconds: float = 30):
    """Open a prevalidated target without Django, schema changes or WAL writes."""
    _no_symlinks(target.path)
    before = target.path.stat()
    try:
        # mode=ro can still create/write a WAL shared-memory file. Immutable reads
        # cannot do so, but ignore WAL: refuse outstanding WAL instead of silently
        # examining an older database image. Operators checkpoint after quiescence.
        wal = Path(str(target.path) + "-wal")
        if wal.exists() or wal.is_symlink():
            _no_symlinks(wal)
            if wal.stat().st_size:
                raise PreflightError("DATABASE_WAL_PENDING", blocked=True)
        db = sqlite3.connect(target.path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1)
        after = target.path.stat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            db.close()
            raise PreflightError("DATABASE_CHANGED")
        deadline = time.monotonic() + seconds
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        yield db
    except sqlite3.Error:
        raise PreflightError("DATABASE_READ_FAILED", blocked=True) from None
    finally:
        if "db" in locals():
            db.close()


def validated_database_index(backend_env: Mapping, policy: Mapping) -> list[DatabaseTarget]:
    """Return private canonical targets for recovery; never serialize their paths."""
    uid = policy.get("service_uid")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        raise PreflightError("SERVICE_OWNER_MISSING", blocked=True)
    if policy.get("persistent_storage") is not True:
        raise PreflightError("PERSISTENCE_EVIDENCE_MISSING", blocked=True)
    root = Path(policy.get("storage_root", ""))
    control = Path(backend_env.get("LEADZEN_DB", ""))
    workspace_root = Path(backend_env.get("LEADZEN_WORKSPACE_ROOT", ""))
    _private_path(root, uid, directory=True)
    for path in (control, workspace_root):
        if not path.is_relative_to(root) or path == root:
            raise PreflightError("STORAGE_OUTSIDE_BOUNDARY")
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_relative_to(root):
                _private_path(parent, uid, directory=True)
    _private_path(control.parent, uid, directory=True)
    _private_path(control, uid)
    _private_path(workspace_root, uid, directory=True)
    for sidecar in (Path(str(control) + "-wal"), Path(str(control) + "-shm")):
        if sidecar.exists() or sidecar.is_symlink():
            _private_path(sidecar, uid)
    targets = [DatabaseTarget("control", control)]
    with readonly_database(targets[0]) as db:
        try:
            rows = db.execute("SELECT id FROM leadzen_accounts_accountprofile LIMIT 10001").fetchall()
            if len(rows) > 10000:
                raise PreflightError("DATABASE_INVENTORY_LIMIT", blocked=True)
            owned = {str(uuid.UUID(str(row[0]))) for row in rows}
        except (sqlite3.Error, ValueError, TypeError):
            raise PreflightError("CONTROL_OWNERSHIP_SCHEMA_INVALID") from None
    try:
        entries = []
        for entry in workspace_root.iterdir():
            entries.append(entry)
            if len(entries) > 10000:
                raise PreflightError("DATABASE_INVENTORY_LIMIT", blocked=True)
    except OSError:
        raise PreflightError("WORKSPACE_INDEX_UNREADABLE", blocked=True) from None
    for directory in entries:
        _private_path(directory, uid, directory=True)
        try:
            identifier = str(uuid.UUID(directory.name))
        except ValueError:
            raise PreflightError("WORKSPACE_NAME_INVALID") from None
        if identifier != directory.name or identifier not in owned:
            raise PreflightError("WORKSPACE_NOT_SERVER_OWNED")
        marker = directory / "initialized"
        dbpath = directory / "db.sqlite3"
        if marker.exists() or marker.is_symlink():
            _private_path(marker, uid)
            _private_path(dbpath, uid)
            if dbpath.samefile(control):
                raise PreflightError("WORKSPACE_DATABASE_ALIAS")
            for sidecar in (Path(str(dbpath) + "-wal"), Path(str(dbpath) + "-shm")):
                if sidecar.exists() or sidecar.is_symlink():
                    _private_path(sidecar, uid)
            targets.append(DatabaseTarget("workspace", dbpath))
        elif dbpath.exists() or dbpath.is_symlink():
            raise PreflightError("WORKSPACE_INITIALIZATION_INCOMPLETE", blocked=True)
    return targets


def _graph_payload() -> dict:
    """Run only in a fresh child: load migration definitions, not current settings.

    AppConfig descriptors provide labels/modules to MigrationLoader. There is no
    apps.populate/django.setup/ready call and no configured database connection.
    Historical migration data functions are inspected as definitions, never run.
    """
    from django.apps import AppConfig, apps as registry
    from django.conf import settings
    from django.db.migrations import loader as loader_module

    tree = ast.parse((Path(__file__).parents[1] / "settings.py").read_text())
    installed = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "INSTALLED_APPS" for target in node.targets))
    settings.configure(INSTALLED_APPS=[], DATABASES={}, SECRET_KEY="offline-graph-no-capabilities", AUTH_USER_MODEL="auth.User", DEFAULT_AUTO_FIELD="django.db.models.BigAutoField", USE_TZ=True)
    for entry in installed:
        descriptor = AppConfig.create(entry)
        descriptor.apps = registry
        descriptor.models = registry.all_models[descriptor.label]
        registry.app_configs[descriptor.label] = descriptor
    registry.apps_ready = True
    registry.models_ready = True
    registry.ready = True
    loader_module.apps = registry
    loader = loader_module.MigrationLoader(None, ignore_no_migrations=True)
    state = loader.project_state()
    models = state.apps.get_models(include_auto_created=True)
    # SQL compilation uses an unconnected in-memory backend descriptor. It does
    # not open SQLite or load the application's current settings/database.
    from django.db.backends.sqlite3.base import DatabaseWrapper
    compiler_connection = DatabaseWrapper({"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"})
    schema_editor = compiler_connection.schema_editor()

    def index_definition(model, index, *, unique=False):
        fields = [(field.removeprefix("-"), field.startswith("-")) for field in index.fields]
        return {"columns": [model._meta.get_field(field).column for field, descending in fields],
                "descending": [descending for field, descending in fields], "unique": unique,
                "condition": index._get_condition_sql(model, schema_editor)}
    tables = {model._meta.db_table: {
        "columns": sorted(field.column for field in model._meta.local_concrete_fields),
        "indexes": sorted(index.name for index in model._meta.indexes if index.name),
        "index_definitions": {index.name: index_definition(model, index) for index in model._meta.indexes if index.name}
                             | {constraint.name: index_definition(model, constraint, unique=True) for constraint in model._meta.constraints
                                if constraint.__class__.__name__ == "UniqueConstraint" and constraint.fields and constraint.condition},
        "indexed_columns": sorted(field.column for field in model._meta.local_concrete_fields if field.db_index and not field.primary_key),
        "unique_columns": sorted(field.column for field in model._meta.local_concrete_fields if field.unique and not field.primary_key),
        "not_null_columns": sorted(field.column for field in model._meta.local_concrete_fields if not field.null and not field.primary_key),
        "foreign_keys": sorted((field.column, field.remote_field.model._meta.db_table, field.target_field.column)
                               for field in model._meta.local_concrete_fields if field.is_relation and (field.many_to_one or field.one_to_one)),
        "unique_groups": [[model._meta.get_field(name).column for name in fields] for fields in model._meta.unique_together]
                         + [[model._meta.get_field(name).column for name in constraint.fields] for constraint in model._meta.constraints
                            if constraint.__class__.__name__ == "UniqueConstraint" and constraint.fields and not constraint.condition],
        "partial_unique_indexes": {constraint.name: [model._meta.get_field(name).column for name in constraint.fields]
                                   for constraint in model._meta.constraints if constraint.__class__.__name__ == "UniqueConstraint" and constraint.fields and constraint.condition},
    } for model in models if model._meta.managed and not model._meta.proxy}
    if compiler_connection.connection is not None:
        raise PreflightError("MIGRATION_GRAPH_DATABASE_OPENED")
    nodes = sorted(loader.graph.nodes)
    return {"migrations": [list(node) for node in nodes], "leaves": [list(node) for node in sorted(loader.graph.leaf_nodes())],
            "parents": {"/".join(node): [list(parent.key) for parent in loader.graph.node_map[node].parents] for node in nodes}, "tables": tables}


def migration_graph() -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("LEADZEN_", "OUTSEND_", "OPENOUTFIND_"))
           and not key.endswith(("API_KEY", "TOKEN", "SECRET")) and key != "DJANGO_SETTINGS_MODULE"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = subprocess.run([sys.executable, "-m", "leadzen.operations.preflight", "--graph"],
                                env=env, capture_output=True, text=True, timeout=30)
        payload = json.loads(result.stdout) if result.returncode == 0 else None
        if not isinstance(payload, dict) or not payload.get("migrations") or not payload.get("tables"):
            raise ValueError
        return payload
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise PreflightError("MIGRATION_GRAPH_UNAVAILABLE", blocked=True) from None


def _schema_check(db: sqlite3.Connection, graph: Mapping, allow_pending: bool) -> dict:
    required = {tuple(node) for node in graph["migrations"]}
    applied = set(db.execute("SELECT app, name FROM django_migrations").fetchall())
    if applied - required:
        raise PreflightError("SCHEMA_UNKNOWN_MIGRATION")
    for node in applied:
        if any(tuple(parent) not in applied for parent in graph["parents"]["/".join(node)]):
            raise PreflightError("SCHEMA_HISTORY_INCONSISTENT")
    pending = len(required - applied)
    if pending:
        if allow_pending:
            return {"status": "BLOCKED", "code": "SCHEMA_PENDING", "pending_migrations": pending}
        raise PreflightError("SCHEMA_PENDING")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    for table, definition in graph["tables"].items():
        if table not in tables:
            raise PreflightError("SCHEMA_TABLE_MISSING")
        column_details = list(db.execute('PRAGMA table_info("' + table.replace('"', '""') + '")'))
        columns = {row[1] for row in column_details}
        if not set(definition["columns"]).issubset(columns) or not set(definition["indexes"]).issubset(indexes):
            raise PreflightError("SCHEMA_LAYOUT_MISMATCH")
        found_indexes = []
        for index in db.execute('PRAGMA index_list("' + table.replace('"', '""') + '")'):
            indexed = [row[2] for row in db.execute('PRAGMA index_info("' + index[1].replace('"', '""') + '")')]
            found_indexes.append((indexed, bool(index[2])))
        if any(not any(indexed and indexed[0] == column for indexed, unique in found_indexes) for column in definition["indexed_columns"]):
            raise PreflightError("SCHEMA_INDEX_MISSING")
        if any(not any(indexed == [column] and unique for indexed, unique in found_indexes) for column in definition["unique_columns"]):
            raise PreflightError("SCHEMA_UNIQUE_MISSING")
        detailed_indexes = {}
        for index in db.execute('PRAGMA index_list("' + table.replace('"', '""') + '")'):
            indexed = [row[2] for row in db.execute('PRAGMA index_info("' + index[1].replace('"', '""') + '")')]
            detailed_indexes[index[1]] = (indexed, bool(index[2]), bool(index[4]))
        if any(not any(indexed == group and unique and not partial for indexed, unique, partial in detailed_indexes.values()) for group in definition["unique_groups"]):
            raise PreflightError("SCHEMA_COMPOSITE_UNIQUE_MISSING")
        if any(detailed_indexes.get(name) != (group, True, True) for name, group in definition["partial_unique_indexes"].items()):
            raise PreflightError("SCHEMA_PARTIAL_UNIQUE_MISSING")
        for name, expected in definition["index_definitions"].items():
            details = list(db.execute('PRAGMA index_xinfo("' + name.replace('"', '""') + '")'))
            key_columns = [row for row in details if row[5]]
            sql = db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=? AND tbl_name=?", (name, table)).fetchone()
            predicate = re.search(r"\)\s+WHERE\s+(.+)$", sql[0], re.IGNORECASE | re.DOTALL) if sql and sql[0] else None
            actual_condition = predicate.group(1) if predicate else None
            if ([row[2] for row in key_columns] != expected["columns"]
                    or [bool(row[3]) for row in key_columns] != expected["descending"]
                    or detailed_indexes.get(name, (None, None, None))[1] != expected["unique"]
                    or _sql_tokens(actual_condition) != _sql_tokens(expected["condition"])):
                raise PreflightError("SCHEMA_INDEX_DEFINITION_MISMATCH")
        if not set(definition["not_null_columns"]).issubset({row[1] for row in column_details if row[3]}):
            raise PreflightError("SCHEMA_NULLABILITY_MISMATCH")
        actual_foreign = {(row[3], row[2], row[4]) for row in db.execute('PRAGMA foreign_key_list("' + table.replace('"', '""') + '")')}
        if not {tuple(relation) for relation in definition["foreign_keys"]}.issubset(actual_foreign):
            raise PreflightError("SCHEMA_FOREIGN_KEY_MISSING")
    return {"status": "PASS", "code": "SCHEMA_CURRENT", "pending_migrations": 0}


def _sql_tokens(value):
    if value is None:
        return None
    # Ignore SQL formatting while preserving quoted identifiers/string contents.
    tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\s+|.", value)
    return "".join(token if token.startswith(("'", '"')) else token.lower() for token in tokens if not token.isspace())


LEGACY_COLUMNS = ("llm_api_key", "bettercontact_api_key", "apollo_api_key", "mailbox_password", "contacts_api_token")
FEATURES = ("invitations", "mcp", "chat", "discovery", "mail", "autopilot", "automatic_followups")


def _credential_check(db: sqlite3.Connection, fernet: Fernet) -> tuple[dict, dict]:
    legacy = sum(db.execute('SELECT count(*) FROM leadzen_config_siteconfig WHERE "' + column + '" IS NOT NULL AND "' + column + '" != ?', ("",)).fetchone()[0] for column in LEGACY_COLUMNS)
    # The sender's mailbox adapter also stores Fernet ciphertext. Legacy CLI
    # plaintext is counted in SQL and is never loaded into the report/process.
    legacy += db.execute("SELECT count(*) FROM outsend_emails_mailbox WHERE password != '' AND substr(password,1,6) != 'gAAAAA'").fetchone()[0]
    secrets: dict[str, str] = {}
    encrypted_count = 0
    for table, column in (("leadzen_config_runtimesettings", "encrypted_secrets"), ("leadzen_accounts_employeeinvitation", "encrypted_token"), ("outsend_emails_mailbox", "password")):
        if db.execute('SELECT count(*) FROM "' + table + '" WHERE length("' + column + '") > 1048576').fetchone()[0]:
            raise PreflightError("ENCRYPTED_SETTINGS_SIZE_INVALID")
        selection = 'SELECT "' + column + '"' + (", id" if table == "leadzen_config_runtimesettings" else "") + ' FROM "' + table + '" WHERE "' + column + '" != ?'
        if table == "outsend_emails_mailbox":
            selection += " AND substr(password,1,6)='gAAAAA'"
        for row in db.execute(selection, ("",)):
            encrypted_count += 1
            if encrypted_count > 10000:
                raise PreflightError("ENCRYPTED_SETTINGS_LIMIT", blocked=True)
            try:
                decoded = json.loads(fernet.decrypt(row[0].encode("ascii")))
                if not isinstance(decoded, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in decoded.items()):
                    raise ValueError
                if table == "outsend_emails_mailbox":
                    password = decoded.get("mailbox_password")
                    if not isinstance(password, str) or not password:
                        raise PreflightError("MAILBOX_CREDENTIALS_MALFORMED")
                    if password.startswith("gAAAA"):
                        try:
                            nested = json.loads(fernet.decrypt(password.encode("ascii")))
                        except (InvalidToken, ValueError, UnicodeError):
                            pass  # A legitimate password can use a token prefix.
                        else:
                            if isinstance(nested, dict):
                                raise PreflightError("MAILBOX_NESTED_ENCRYPTION_PRESENT")
                if table == "leadzen_config_runtimesettings" and row[1] == 1:
                    secrets.update(decoded)
            except PreflightError:
                raise
            except (InvalidToken, ValueError, UnicodeError, AttributeError, RecursionError):
                raise PreflightError("SETTINGS_KEY_INCOMPATIBLE") from None
    return {"status": "FAIL" if legacy else "PASS", "code": "LEGACY_PLAINTEXT_PRESENT" if legacy else "CREDENTIALS_DECRYPTABLE",
            "encrypted_rows_checked": encrypted_count, "legacy_plaintext_fields": legacy}, secrets


def _approved_public_host(host, backend: Mapping, kind: str) -> bool:
    default_hosts = {
        "LLM": {"api.groq.com", "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com", "api.mistral.ai", "api.cohere.com"},
        "EMAIL": {"api.resend.com", "api.sendgrid.com", "api.zeptomail.com", "api.zeptomail.in", "api.zeptomail.eu", "zeptomail.zoho.com", "cpaas.zoho.com"},
        "MAIL": {f"{protocol}.{domain}" for protocol in ("smtp", "smtppro", "imap", "imappro")
                 for domain in ("zoho.com", "zoho.in", "zoho.eu", "zoho.com.au", "zoho.jp", "zoho.ca")}
                | {"smtp.gmail.com", "imap.gmail.com", "smtp.office365.com", "outlook.office365.com",
                   "smtp.resend.com", "smtp.sendgrid.net", "smtp.zeptomail.com", "smtp.zeptomail.in", "smtp.zeptomail.eu"},
    }
    if not isinstance(host, str) or len(host) > 255 or "[" in host or "]" in host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        canonical_host = host.lower()
    else:
        canonical_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    # Explicit server allowlists cannot waive the public-address boundary.
    # Normalize DNS case/IP presentation as the transport does, then apply the
    # shared rules so numeric loopback aliases and multicast cannot pass as DNS.
    if not production_origin_valid("https://" + canonical_host):
        return False
    extras = {item.strip().lower() for item in backend.get("LEADZEN_" + kind + "_HOSTS", "").split(",") if item.strip()}
    return host.lower() in default_hosts[kind] | extras


def _endpoint_valid(value, backend: Mapping, kind: str) -> bool:
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme == "https" and _approved_public_host(parsed.hostname, backend, kind) and parsed.port in (None, 443)
                    and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and "\\" not in value
                    and not any(char.isspace() for char in value))
    except (TypeError, ValueError):
        return False


def _workspace_features(db: sqlite3.Connection, secrets: Mapping, features: Mapping, backend: Mapping) -> dict:
    db.row_factory = sqlite3.Row
    runtime = db.execute("SELECT * FROM leadzen_config_runtimesettings WHERE id=1").fetchone()
    config = db.execute("SELECT * FROM leadzen_config_siteconfig WHERE id=1").fetchone()
    current = dict(runtime) if runtime else {}
    legacy = dict(config) if config else {}
    legacy_provider, separator, legacy_model = legacy.get("ai_model", "").partition(":")
    if not separator:
        legacy_provider, legacy_model = "", legacy_provider
    # RuntimeSettings overrides every public legacy field, including explicit
    # clears. A fallback here would certify settings the application never uses.
    def effective(runtime_name, legacy_name=None, default=""):
        return current.get(runtime_name) if runtime is not None else legacy.get(legacy_name or runtime_name, default)
    provider = current.get("llm_provider") if runtime is not None else legacy_provider
    model = current.get("llm_model") if runtime is not None else legacy_model
    base_url = effective("llm_base_url", "llm_api_base")
    ai = bool(current.get("ai_enabled", True))
    address = effective("mailbox_address")
    transport = current.get("mail_transport", "smtp")
    smtp_host, imap_host = effective("smtp_host"), effective("imap_host")
    def port_allowed(value, allowed):
        if value in (None, ""):
            return True  # Verified runtime defaults: SMTP 587 / IMAP 993.
        try:
            return isinstance(value, (int, str)) and not isinstance(value, bool) and int(value) in allowed
        except (ValueError, TypeError):
            return False
    mail_ready = bool(isinstance(address, str) and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address)
                      and transport in {"smtp", "resend", "sendgrid", "zeptomail", "compatible"}
                      and (secrets.get("mailbox_password") if transport == "smtp" else secrets.get("mail_api_key"))
                      and (secrets.get("imap_password") or secrets.get("mailbox_password"))
                      and _approved_public_host(imap_host, backend, "MAIL")
                      and port_allowed(effective("imap_port"), {993}))
    if transport != "smtp":
        endpoint = current.get("mail_api_url", "")
        mail_ready = mail_ready and _endpoint_valid(endpoint, backend, "EMAIL")
        official = {"resend": "https://api.resend.com/emails", "sendgrid": "https://api.sendgrid.com/v3/mail/send"}
        if transport in official:
            mail_ready = mail_ready and endpoint == official[transport]
        if transport == "zeptomail" and mail_ready:
            mail_ready = mail_ready and urlsplit(endpoint).hostname in {"api.zeptomail.com", "api.zeptomail.in", "api.zeptomail.eu", "zeptomail.zoho.com", "cpaas.zoho.com"}
    else:
        mail_ready = mail_ready and _approved_public_host(smtp_host, backend, "MAIL") and port_allowed(effective("smtp_port"), {465, 587, 2525})
    results = {}
    for feature in ("chat", "discovery", "mail", "autopilot", "automatic_followups"):
        enabled = features.get(feature)
        if not enabled:
            results[feature] = {"status": "PASS", "code": "FEATURE_DISABLED", "enabled": False, "scope": "RELEASE_POLICY"}
            continue
        valid = True
        if feature in {"chat", "autopilot"} or (feature == "discovery" and ai):
            valid = ai and bool(provider in {"groq", "openai", "anthropic", "google", "mistral", "cohere", "openai_compatible"}
                                and model and secrets.get("llm_api_key"))
            if base_url or provider == "openai_compatible":
                valid = valid and _endpoint_valid(base_url, backend, "LLM")
        if feature in {"discovery", "autopilot"}:
            valid = valid and bool(secrets.get("bettercontact_api_key"))
        if feature in {"mail", "autopilot", "automatic_followups"}:
            valid = valid and mail_ready
        results[feature] = {"status": "PASS" if valid else "FAIL", "code": "FEATURE_CONFIGURED" if valid else "FEATURE_CONFIGURATION_INCOMPLETE", "enabled": True, "scope": "RELEASE_POLICY"}
    return results


def _feature_policy(policy: Mapping, backend: Mapping) -> dict:
    features = policy.get("features")
    if not isinstance(features, dict) or set(features) != set(FEATURES) or any(not isinstance(features[name], bool) for name in FEATURES):
        raise PreflightError("FEATURE_POLICY_MISSING", blocked=True)
    for name, variable in (("autopilot", "LEADZEN_AUTOPILOT_ENABLED"), ("automatic_followups", "LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED")):
        value = backend.get(variable, "0")
        if value not in {"0", "1"} or (value == "1") != features[name]:
            raise PreflightError("FEATURE_FLAG_MISMATCH")
    return features


def run_preflight(backend_env_path: str | Path, dashboard_env_path: str | Path, policy_path: str | Path, *, schema_policy: str = "current") -> dict:
    """Return bounded, value-free JSON metadata; never write the supplied files."""
    if schema_policy not in {"current", "allow-pending"}:
        raise PreflightError("SCHEMA_POLICY_INVALID")
    report = {"format": 1, "status": "BLOCKED", "read_only": True, "checks": {}, "databases": [],
              "limits": ["HOST_POLICY_IS_OPERATOR_ATTESTATION", "PERSISTENT_VOLUME_AND_NETWORK_NOT_OBSERVED", "FEATURE_POLICY_DOES_NOT_CHANGE_RUNTIME_BEHAVIOR",
                         "QUIESCENT_CHECKPOINTED_SNAPSHOT_REQUIRED", "NO_LIVE_PROVIDER_OR_BROWSER_PROBE", "NO_RELEASE_APPROVAL"]}
    checks = report["checks"]

    def perform(name, operation):
        try:
            value = operation()
            checks[name] = {"status": "PASS", "code": name.upper() + "_VALID"}
            return value
        except PreflightError as exc:
            checks[name] = {"status": "BLOCKED" if exc.blocked else "FAIL", "code": exc.code}
        except Exception:
            # No exception string/trace can contain paths, database content or env.
            checks[name] = {"status": "BLOCKED", "code": "CHECK_UNAVAILABLE"}
        return None

    policy = perform("policy", lambda: _read_policy(policy_path))
    if policy is not None:
        uid = policy.get("env_owner_uid")
        if not isinstance(uid, int) or isinstance(uid, bool) or uid < 0:
            checks["policy"] = {"status": "BLOCKED", "code": "ENV_OWNER_MISSING"}
        else:
            backend = perform("backend_env", lambda: read_private_env(backend_env_path, expected_uid=uid))
            dashboard = perform("dashboard_env", lambda: read_private_env(dashboard_env_path, expected_uid=uid))
            if backend is not None and dashboard is not None:
                def environment():
                    try:
                        validate_environment(backend)
                    except Exception:
                        raise PreflightError("BACKEND_ENV_INVALID") from None
                    if any(key.startswith("NEXT_PUBLIC_") for key in dashboard):
                        raise PreflightError("PUBLIC_ENV_UNREVIEWED")
                    # Next production hosts inject NODE_ENV; absent in a pulled
                    # Vercel file is allowed, an explicit development override is not.
                    if dashboard.get("NODE_ENV", "production") != "production":
                        raise PreflightError("DASHBOARD_ENV_INVALID")
                    if not backend.get("LEADZEN_DASHBOARD_TOKEN", "").isascii() or not dashboard.get("LEADZEN_API_TOKEN", "").isascii():
                        raise PreflightError("SERVICE_TOKEN_HEADER_INVALID")
                    if not hmac.compare_digest(backend.get("LEADZEN_DASHBOARD_TOKEN", "").encode(), dashboard.get("LEADZEN_API_TOKEN", "").encode()):
                        raise PreflightError("SERVICE_TOKEN_MISMATCH")
                perform("environment", environment)
                checks["environment"]["backend_missing_names"] = [name for name in REQUIRED if not backend.get(name, "").strip()]
                checks["environment"]["dashboard_missing_names"] = [name for name in ("LEADZEN_API_URL", "LEADZEN_API_TOKEN", "LEADZEN_DASHBOARD_PUBLIC_URL") if not dashboard.get(name, "").strip()]
                perform("network", lambda: _network_policy(policy, backend, dashboard))
                perform("host", lambda: _host_policy(policy))
                features = perform("features", lambda: _feature_policy(policy, backend))
                targets = perform("storage", lambda: validated_database_index(backend, policy))
                graph = perform("migration_graph", migration_graph)
                if targets is not None and graph is not None:
                    try:
                        fernet = Fernet(backend.get("LEADZEN_SETTINGS_KEY", "").encode("ascii"))
                    except (ValueError, UnicodeError):
                        checks["key"] = {"status": "FAIL", "code": "SETTINGS_KEY_INVALID"}
                        fernet = None
                    for target in targets:
                        entry = {"role": target.role, "checks": {}}
                        report["databases"].append(entry)
                        try:
                            with readonly_database(target) as db:
                                entry["checks"]["schema"] = _schema_check(db, graph, schema_policy == "allow-pending")
                                if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                                    raise PreflightError("DATABASE_INTEGRITY_FAILED")
                                if db.execute("PRAGMA foreign_key_check").fetchone():
                                    raise PreflightError("DATABASE_FOREIGN_KEY_FAILED")
                                entry["checks"]["integrity"] = {"status": "PASS", "code": "DATABASE_INTEGRITY_VALID"}
                                if entry["checks"]["schema"]["status"] == "PASS" and fernet is not None:
                                    credential, secrets = _credential_check(db, fernet)
                                    entry["checks"]["credentials"] = credential
                                    if target.role == "workspace" and features is not None:
                                        entry["features"] = _workspace_features(db, secrets, features, backend)
                                    secrets.clear()
                                elif entry["checks"]["schema"]["status"] != "PASS":
                                    entry["checks"]["credentials"] = {"status": "BLOCKED", "code": "CREDENTIALS_REQUIRE_CURRENT_SCHEMA"}
                        except PreflightError as exc:
                            entry["checks"]["database"] = {"status": "BLOCKED" if exc.blocked else "FAIL", "code": exc.code}
                        except Exception:
                            entry["checks"]["database"] = {"status": "BLOCKED", "code": "DATABASE_CHECK_UNAVAILABLE"}
                if features is not None:
                    checks["feature_services"] = {}
                    for name in ("invitations", "mcp"):
                        enabled = features[name]
                        valid = not enabled
                        if name == "invitations" and enabled:
                            sender = backend.get("LEADZEN_INVITATION_FROM", "")
                            valid = bool(backend.get("LEADZEN_RESEND_API_KEY") and sender and "\n" not in sender and "\r" not in sender)
                        if name == "mcp" and enabled:
                            valid = backend.get("LEADZEN_MCP_PUBLIC_URL") == str(policy.get("api_origin", "")) + "/mcp" and backend.get("LEADZEN_MCP_ALLOW_LOCAL", "0") == "0"
                        checks["feature_services"][name] = {"status": "PASS" if valid else "FAIL", "enabled": enabled,
                                                              "scope": "RELEASE_POLICY", "code": "FEATURE_DISABLED" if not enabled else "FEATURE_CONFIGURED" if valid else "FEATURE_CONFIGURATION_INCOMPLETE"}
    def statuses(value):
        if isinstance(value, dict):
            if value.get("status") in {"PASS", "FAIL", "BLOCKED"}:
                yield value["status"]
            for child in value.values():
                yield from statuses(child)
        elif isinstance(value, list):
            for child in value:
                yield from statuses(child)
    outcomes = list(statuses(checks)) + list(statuses(report["databases"]))
    report["status"] = "FAIL" if "FAIL" in outcomes else "BLOCKED" if "BLOCKED" in outcomes else "PASS"
    report["database_count"] = len(report["databases"])
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-env")
    parser.add_argument("--dashboard-env")
    parser.add_argument("--policy")
    parser.add_argument("--report")
    parser.add_argument("--schema-policy", choices=("current", "allow-pending"), default="current")
    parser.add_argument("--graph", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.graph:
        try:
            print(json.dumps(_graph_payload(), sort_keys=True))
            return 0
        except Exception:
            print('{"status":"BLOCKED","code":"MIGRATION_GRAPH_UNAVAILABLE"}')
            return 2
    if not all((args.backend_env, args.dashboard_env, args.policy)):
        parser.error("--backend-env, --dashboard-env and --policy are required")
    report = run_preflight(args.backend_env, args.dashboard_env, args.policy, schema_policy=args.schema_policy)
    serialized = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.report:
        try:
            _no_symlinks(Path(args.report).absolute().parent)
            descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write(serialized)
        except (OSError, PreflightError):
            print('{"status":"BLOCKED","code":"REPORT_WRITE_FAILED"}')
            return 2
    print(serialized, end="")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
