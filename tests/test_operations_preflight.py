"""Read-only preflight against disposable, fully migrated SQLite databases."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import uuid

from cryptography.fernet import Fernet
import pytest

from leadzen.operations import preflight


@pytest.fixture(scope="module")
def graph():
    return preflight.migration_graph()


@pytest.fixture(scope="module")
def migrated_database(tmp_path_factory):
    root = tmp_path_factory.mktemp("preflight-schema").resolve()
    path = root / "database.sqlite3"
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("LEADZEN_", "OUTSEND_", "OPENOUTFIND_"))}
    environment.update(LEADZEN_DB=str(path), DJANGO_SETTINGS_MODULE="leadzen.settings")
    program = """
import django
django.setup()
from django.core.management import call_command
call_command('migrate', interactive=False, verbosity=0)
from django.contrib.auth.models import User
from leadzen.accounts.models import AccountProfile
from leadzen.config.models import SiteConfig, RuntimeSettings
user=User.objects.create(username='synthetic-preflight',is_active=True)
AccountProfile.objects.create(id='31f34d40-9dfd-4e2a-8033-5e986b048705',user=user)
SiteConfig.load()
RuntimeSettings.load()
from django.db import connection
connection.close()
"""
    result = subprocess.run([sys.executable, "-c", program], env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, "Disposable schema initialization failed"
    return path


@pytest.fixture
def fixture(tmp_path, migrated_database, graph, monkeypatch):
    root = tmp_path.resolve()
    root.chmod(0o700)
    storage = root / "storage"
    storage.mkdir(mode=0o700)
    workspaces = storage / "workspaces"
    workspaces.mkdir(mode=0o700)
    control = storage / "control.sqlite3"
    shutil.copyfile(migrated_database, control)
    control.chmod(0o600)
    directory = workspaces / "31f34d40-9dfd-4e2a-8033-5e986b048705"
    directory.mkdir(mode=0o700)
    employee = directory / "db.sqlite3"
    shutil.copyfile(migrated_database, employee)
    employee.chmod(0o600)
    # Synthetic fixtures use rollback journals so later SQL test mutations are
    # fully committed in the main file even while a test still holds a handle.
    for target in (control, employee):
        database = sqlite3.connect(target)
        database.execute("PRAGMA journal_mode=DELETE")
        database.close()
    (directory / "initialized").touch(mode=0o600)
    backend = {
        "LEADZEN_ENV": "production", "LEADZEN_DB": str(control), "LEADZEN_WORKSPACE_ROOT": str(workspaces),
        "LEADZEN_SETTINGS_KEY": Fernet.generate_key().decode(), "LEADZEN_SECRET_KEY": "synthetic-signing-key-for-fixtures-only-0123456789-abcdef-ABCDEFG",
        "LEADZEN_DASHBOARD_TOKEN": "synthetic-service-token-for-fixtures-0123456789-ABCDEF",
        "LEADZEN_PUBLIC_URL": "https://dashboard.example.com", "LEADZEN_ALLOWED_HOSTS": "api.example.com",
        "LEADZEN_DASHBOARD_ORIGINS": "https://dashboard.example.com",
    }
    dashboard = {"LEADZEN_API_URL": "https://api.example.com", "LEADZEN_API_TOKEN": backend["LEADZEN_DASHBOARD_TOKEN"],
                 "LEADZEN_DASHBOARD_PUBLIC_URL": "https://dashboard.example.com"}
    policy = {"service_uid": os.geteuid(), "env_owner_uid": os.geteuid(), "storage_root": str(storage), "persistent_storage": True,
              "expected_hostname": socket.gethostname(), "expected_machine": os.uname().machine,
              "dashboard_origin": "https://dashboard.example.com", "api_origin": "https://api.example.com", "private_listen_addresses": ["127.0.0.1"],
              "trusted_proxy_networks": ["127.0.0.1/32"], "forwarded_proxy_addresses": ["127.0.0.1"],
              "features": {name: False for name in preflight.FEATURES}}
    paths = [root / name for name in ("backend.env", "dashboard.env", "policy.json")]
    monkeypatch.setattr(preflight, "migration_graph", lambda: graph)

    def run(schema_policy="current"):
        for path, values in zip(paths[:2], (backend, dashboard)):
            path.write_text("\n".join(name + "=" + json.dumps(value) for name, value in values.items()) + "\n")
            path.chmod(0o600)
        paths[2].write_text(json.dumps(policy))
        paths[2].chmod(0o600)
        return preflight.run_preflight(*paths, schema_policy=schema_policy)
    return {"run": run, "backend": backend, "dashboard": dashboard, "policy": policy, "paths": paths,
            "control": control, "employee": employee, "workspace_root": workspaces, "root": root}


def codes(report):
    def recurse(value):
        if isinstance(value, dict):
            if "code" in value:
                yield value["code"]
            for child in value.values():
                yield from recurse(child)
        elif isinstance(value, list):
            for child in value:
                yield from recurse(child)
    return set(recurse(report))


def test_current_schema_two_databases_read_only_and_no_values_in_report(fixture):
    key = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode())
    private = {"llm_api_key": "fixture-private-provider-value"}
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET encrypted_secrets=?", (key.encrypt(json.dumps(private).encode()).decode(),))
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (fixture["control"], fixture["employee"])}
    report = fixture["run"]()
    assert report["status"] == "PASS"
    assert report["database_count"] == 2
    assert report["databases"][1]["checks"]["credentials"]["encrypted_rows_checked"] == 1
    assert "FEATURE_DISABLED" in codes(report)
    encoded = json.dumps(report)
    assert str(fixture["root"]) not in encoded
    assert fixture["employee"].parent.name not in encoded
    assert not any(value in encoded for value in private.values())
    assert fixture["backend"]["LEADZEN_SETTINGS_KEY"] not in encoded
    for path, digest in before.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert not Path(str(path) + "-wal").exists()
        assert not Path(str(path) + "-shm").exists()


def test_service_token_mismatch(fixture):
    fixture["dashboard"]["LEADZEN_API_TOKEN"] = "synthetic-foreign-service-token"
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert "SERVICE_TOKEN_MISMATCH" in codes(report)


@pytest.mark.parametrize("target", ["control", "employee"])
def test_foreign_key_and_settings_key_validation_every_database(fixture, target):
    wrong_key = Fernet(Fernet.generate_key())
    with sqlite3.connect(fixture[target]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET encrypted_secrets=?", (wrong_key.encrypt(b'{"mailbox_password":"synthetic-private"}').decode(),))
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert "SETTINGS_KEY_INCOMPATIBLE" in codes(report)
    assert "synthetic-private" not in json.dumps(report)


def test_foreign_workspace_uuid_rejected_before_read(fixture):
    foreign = fixture["workspace_root"] / str(uuid.uuid4())
    foreign.mkdir(mode=0o700)
    (foreign / "db.sqlite3").write_bytes(b"untrusted-file-must-not-be-opened")
    (foreign / "db.sqlite3").chmod(0o600)
    (foreign / "initialized").touch(mode=0o600)
    report = fixture["run"]()
    assert "WORKSPACE_NOT_SERVER_OWNED" in codes(report)
    assert report["databases"] == []


@pytest.mark.parametrize("target", ["control", "employee"])
def test_database_symlink_rejected(fixture, target):
    path = fixture[target]
    moved = path.with_name("private-original.sqlite3")
    path.rename(moved)
    path.symlink_to(moved)
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert "SYMLINK_FORBIDDEN" in codes(report)


def test_env_reader_rejects_permissive_modes_symlinks_duplicates_substitution(tmp_path):
    path = tmp_path.resolve() / "private.env"
    path.write_text("TOKEN=synthetic-only\n")
    path.chmod(0o644)
    with pytest.raises(preflight.PreflightError, match="STORAGE_MODE_INVALID"):
        preflight.read_private_env(path, expected_uid=os.geteuid())
    path.chmod(0o600)
    for data in ("TOKEN=first\nTOKEN=second", "TOKEN=$(echo forbidden)", "TOKEN=`echo forbidden`"):
        path.write_text(data)
        with pytest.raises(preflight.PreflightError):
            preflight.read_private_env(path, expected_uid=os.geteuid())
    link = path.with_name("link.env")
    link.symlink_to(path)
    with pytest.raises(preflight.PreflightError, match="SYMLINK_FORBIDDEN"):
        preflight.read_private_env(link, expected_uid=os.geteuid())


def test_old_schema_pending_is_never_release_pass(fixture):
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("DELETE FROM django_migrations WHERE app='leadzen_config' AND name='0019_discoverylookup_source_index'")
        index = next(row[1] for row in db.execute("PRAGMA index_list('leadzen_config_discoverylookup')")
                     if [item[2] for item in db.execute('PRAGMA index_info("' + row[1] + '")')] == ["source_id"])
        db.execute('DROP INDEX "' + index + '"')
    strict = fixture["run"]()
    assert strict["status"] == "FAIL"
    assert "SCHEMA_PENDING" in codes(strict)
    pending = fixture["run"]("allow-pending")
    assert pending["status"] == "BLOCKED"
    assert pending["databases"][1]["checks"]["schema"]["pending_migrations"] == 1


def test_migration_record_without_current_column_is_failure(fixture):
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("ALTER TABLE leadzen_accounts_accountprofile DROP COLUMN tour_current_step")
    report = fixture["run"]()
    assert "SCHEMA_LAYOUT_MISMATCH" in codes(report)


def test_applied_migration_cannot_hide_missing_automatic_index(fixture):
    with sqlite3.connect(fixture["employee"]) as db:
        index = next(row[1] for row in db.execute("PRAGMA index_list('leadzen_config_discoverylookup')")
                     if [item[2] for item in db.execute('PRAGMA index_info("' + row[1] + '")')] == ["source_id"])
        db.execute('DROP INDEX "' + index + '"')
    assert "SCHEMA_INDEX_MISSING" in codes(fixture["run"]())


def test_partial_unique_execution_constraint_cannot_be_missing(fixture):
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute('DROP INDEX "one_active_chat_per_actor"')
    assert "SCHEMA_PARTIAL_UNIQUE_MISSING" in codes(fixture["run"]())


def test_file_ownership_mode_and_hardlinks_are_checked(fixture):
    fixture["employee"].chmod(0o644)
    assert "STORAGE_MODE_INVALID" in codes(fixture["run"]())
    fixture["employee"].chmod(0o600)
    fixture["policy"]["service_uid"] += 1
    assert "STORAGE_OWNER_INVALID" in codes(fixture["run"]())
    fixture["policy"]["service_uid"] -= 1
    os.link(fixture["employee"], fixture["root"] / "untrusted-alias.sqlite3")
    assert "STORAGE_HARDLINK_FORBIDDEN" in codes(fixture["run"]())


def test_symlinked_workspace_marker_rejected(fixture):
    marker = fixture["employee"].parent / "initialized"
    marker.unlink()
    marker.symlink_to(fixture["control"])
    assert "SYMLINK_FORBIDDEN" in codes(fixture["run"]())


def test_foreign_key_violation_not_exposed(fixture):
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_accounts_accountprofile SET user_id=987654321")
    report = fixture["run"]()
    assert "DATABASE_FOREIGN_KEY_FAILED" in codes(report)
    assert "987654321" not in json.dumps(report)


def test_legacy_plaintext_only_aggregate_count(fixture):
    with sqlite3.connect(fixture["control"]) as db:
        db.execute("UPDATE leadzen_config_siteconfig SET mailbox_password='private-legacy-value', llm_api_key='private-legacy-provider'")
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert report["databases"][0]["checks"]["credentials"]["legacy_plaintext_fields"] == 2
    assert "private-legacy" not in json.dumps(report)


@pytest.mark.parametrize("encrypted", [True, False])
def test_sender_mailbox_key_compatibility_and_plaintext_count(fixture, encrypted):
    password = "synthetic-legacy-mailbox-password"
    if encrypted:
        password = Fernet(Fernet.generate_key()).encrypt(b'{"mailbox_password":"synthetic-secret"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("INSERT INTO outsend_emails_mailbox(username,from_address,password,signature,host,port,imap_host,imap_port,daily_limit) VALUES (?,?,?,?,?,?,?,?,?)",
                   ("synthetic-mailbox", "synthetic@example.com", password, "", "smtp.gmail.com", 465, "imap.gmail.com", 993, 10))
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert ("SETTINGS_KEY_INCOMPATIBLE" if encrypted else "LEGACY_PLAINTEXT_PRESENT") in codes(report)
    assert password not in json.dumps(report)


@pytest.mark.parametrize("field,value", [("private_listen_addresses", ["0.0.0.0"]), ("trusted_proxy_networks", ["0.0.0.0/0"]),
                                        ("forwarded_proxy_addresses", ["8.8.8.8"]), ("api_origin", "https://127.0.0.1")])
def test_private_topology_required(fixture, field, value):
    fixture["policy"][field] = value
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert {"TRUSTED_PROXY_BOUNDARY_INVALID", "PUBLIC_ORIGIN_INVALID"} & codes(report)


@pytest.mark.parametrize("origin", ["https://dashboard.example.com:443", "https://DASHBOARD.EXAMPLE.COM"])
def test_public_origins_must_match_browser_canonical_origin(fixture, origin):
    fixture["policy"]["dashboard_origin"] = origin
    fixture["backend"]["LEADZEN_PUBLIC_URL"] = origin
    fixture["backend"]["LEADZEN_DASHBOARD_ORIGINS"] = origin
    fixture["dashboard"]["LEADZEN_DASHBOARD_PUBLIC_URL"] = origin
    assert "PUBLIC_ORIGIN_INVALID" in codes(fixture["run"]())


def test_missing_persistence_evidence_blocks(fixture):
    fixture["policy"].pop("persistent_storage")
    assert fixture["run"]()["status"] == "BLOCKED"


def test_feature_flags_must_match_explicit_release_policy(fixture):
    fixture["backend"]["LEADZEN_AUTOPILOT_ENABLED"] = "1"
    assert "FEATURE_FLAG_MISMATCH" in codes(fixture["run"]())


def test_missing_env_names_are_reported_without_values(fixture):
    fixture["backend"].pop("LEADZEN_SECRET_KEY")
    fixture["dashboard"].pop("LEADZEN_DASHBOARD_PUBLIC_URL")
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert report["checks"]["environment"]["backend_missing_names"] == ["LEADZEN_SECRET_KEY"]
    assert report["checks"]["environment"]["dashboard_missing_names"] == ["LEADZEN_DASHBOARD_PUBLIC_URL"]


def test_frontend_public_env_must_be_reviewed(fixture):
    fixture["dashboard"]["NEXT_PUBLIC_API_TOKEN"] = "synthetic-private-token"
    report = fixture["run"]()
    assert "PUBLIC_ENV_UNREVIEWED" in codes(report)
    assert "synthetic-private-token" not in json.dumps(report)


def test_enabled_feature_requires_configuration_but_disabled_does_not(fixture):
    fixture["policy"]["features"]["chat"] = True
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert report["databases"][1]["features"]["chat"]["code"] == "FEATURE_CONFIGURATION_INCOMPLETE"
    fixture["policy"]["features"]["chat"] = False
    assert fixture["run"]()["status"] == "PASS"


def test_enabled_chat_and_mail_configuration_succeeds(fixture):
    fixture["policy"]["features"].update(chat=True, mail=True)
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"llm_api_key":"synthetic-model-key","mail_api_key":"synthetic-mail-key","imap_password":"synthetic-inbox-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET llm_provider='groq',llm_model='synthetic-model',mailbox_address='synthetic@example.com',mail_transport='resend',mail_api_url='https://api.resend.com/emails',imap_host='imap.gmail.com',encrypted_secrets=?", (encrypted,))
    report = fixture["run"]()
    assert report["status"] == "PASS"
    assert report["databases"][1]["features"]["chat"]["code"] == "FEATURE_CONFIGURED"
    assert report["databases"][1]["features"]["mail"]["code"] == "FEATURE_CONFIGURED"


@pytest.mark.parametrize("cleared", ["llm_provider", "llm_model"])
def test_runtime_clears_do_not_fall_back_to_legacy_ai_configuration(fixture, cleared):
    fixture["policy"]["features"]["chat"] = True
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"llm_api_key":"synthetic-model-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_siteconfig SET ai_model='groq:synthetic-model'")
        db.execute("UPDATE leadzen_config_runtimesettings SET llm_provider='groq',llm_model='synthetic-model',encrypted_secrets=?", (encrypted,))
        db.execute('UPDATE leadzen_config_runtimesettings SET "' + cleared + '"=\'\'')
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert report["databases"][1]["features"]["chat"]["code"] == "FEATURE_CONFIGURATION_INCOMPLETE"


@pytest.mark.parametrize("provider", ["groq", "openai", "openai_compatible"])
@pytest.mark.parametrize("endpoint", ["http://api.groq.com", "https://127.0.0.1/v1", "https://[::1]/v1", "https://localhost/v1"])
def test_every_ai_provider_rejects_unusable_explicit_endpoints(fixture, provider, endpoint):
    fixture["policy"]["features"]["chat"] = True
    fixture["backend"]["LEADZEN_LLM_HOSTS"] = "127.0.0.1,::1,localhost"
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"llm_api_key":"synthetic-model-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET llm_provider=?,llm_model='synthetic-model',llm_base_url=?,encrypted_secrets=?", (provider, endpoint, encrypted))
    assert fixture["run"]()["databases"][1]["features"]["chat"]["status"] == "FAIL"


@pytest.mark.parametrize("host", ["", "localhost", "127.0.0.1", "::1", "169.254.169.254", "private.example.com"])
@pytest.mark.parametrize("field", ["smtp_host", "imap_host"])
def test_enabled_smtp_requires_both_approved_public_hostnames(fixture, host, field):
    fixture["policy"]["features"]["mail"] = True
    fixture["backend"]["LEADZEN_MAIL_HOSTS"] = "localhost,127.0.0.1,::1,169.254.169.254"
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"mailbox_password":"synthetic-mail-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET mailbox_address='synthetic@example.com',smtp_host='smtp.gmail.com',imap_host='imap.gmail.com',encrypted_secrets=?", (encrypted,))
        db.execute('UPDATE leadzen_config_runtimesettings SET "' + field + '"=?', (host,))
    assert fixture["run"]()["databases"][1]["features"]["mail"]["status"] == "FAIL"


@pytest.mark.parametrize("field,port", [("smtp_port", 25), ("smtp_port", 0), ("imap_port", 143), ("imap_port", 0)])
def test_enabled_smtp_rejects_ports_without_verified_tls(fixture, field, port):
    fixture["policy"]["features"]["mail"] = True
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"mailbox_password":"synthetic-mail-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET mailbox_address='synthetic@example.com',smtp_host='smtp.gmail.com',imap_host='imap.gmail.com',encrypted_secrets=?", (encrypted,))
        db.execute('UPDATE leadzen_config_runtimesettings SET "' + field + '"=?', (port,))
    assert fixture["run"]()["databases"][1]["features"]["mail"]["status"] == "FAIL"


def test_declared_index_name_cannot_hide_wrong_columns(fixture, graph):
    table, definition = next((table, definition) for table, definition in graph["tables"].items() if definition["indexes"])
    name = definition["indexes"][0]
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute('DROP INDEX "' + name + '"')
        db.execute('CREATE INDEX "' + name + '" ON "' + table + '" (id)')
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert "SCHEMA_INDEX_DEFINITION_MISMATCH" in codes(report)


def test_partial_unique_index_predicate_must_match_migration(fixture, graph):
    table, definition = next((table, definition) for table, definition in graph["tables"].items() if definition["partial_unique_indexes"])
    name, columns = next(iter(definition["partial_unique_indexes"].items()))
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute('DROP INDEX "' + name + '"')
        db.execute('CREATE UNIQUE INDEX "' + name + '" ON "' + table + '" (' + ','.join('"' + column + '"' for column in columns) + ') WHERE 0')
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert "SCHEMA_INDEX_DEFINITION_MISMATCH" in codes(report)


def test_enabled_smtp_accepts_configured_hosts_with_runtime_tls_defaults(fixture):
    fixture["policy"]["features"]["mail"] = True
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"mailbox_password":"synthetic-mail-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET mailbox_address='synthetic@example.com',smtp_host='smtp.gmail.com',imap_host='imap.gmail.com',encrypted_secrets=?", (encrypted,))
    assert fixture["run"]()["databases"][1]["features"]["mail"]["status"] == "PASS"


def test_unselected_runtime_row_cannot_supply_missing_current_credentials(fixture):
    fixture["policy"]["features"]["chat"] = True
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"llm_api_key":"synthetic-unselected-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET llm_provider='groq',llm_model='synthetic-model'")
        columns = [row[1] for row in db.execute("PRAGMA table_info(leadzen_config_runtimesettings)") if row[1] != "id"]
        names = ','.join('"' + column + '"' for column in columns)
        db.execute('INSERT INTO leadzen_config_runtimesettings(id,' + names + ') SELECT 2,' + names + ' FROM leadzen_config_runtimesettings WHERE id=1')
        db.execute("UPDATE leadzen_config_runtimesettings SET encrypted_secrets=? WHERE id=2", (encrypted,))
    report = fixture["run"]()
    assert report["databases"][1]["features"]["chat"]["status"] == "FAIL"
    assert "synthetic-unselected-key" not in json.dumps(report)


@pytest.mark.parametrize("endpoint", ["https://api.sendgrid.com/v3/mail/send", "https://api.resend.com/wrong-path"])
def test_named_mail_provider_requires_its_official_endpoint(fixture, endpoint):
    fixture["policy"]["features"]["mail"] = True
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"mail_api_key":"synthetic-mail-key","imap_password":"synthetic-inbox-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET mailbox_address='synthetic@example.com',mail_transport='resend',mail_api_url=?,imap_host='imap.gmail.com',encrypted_secrets=?", (endpoint, encrypted))
    assert fixture["run"]()["databases"][1]["features"]["mail"]["status"] == "FAIL"


@pytest.mark.parametrize("nested", [False, True])
def test_sender_mailbox_requires_single_decryption_with_password_field(fixture, nested):
    cipher = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode())
    value = {"unrelated": "synthetic"}
    if nested:
        value = {"mailbox_password": cipher.encrypt(b'{"mailbox_password":"synthetic-only-password"}').decode()}
    encrypted = cipher.encrypt(json.dumps(value).encode()).decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("INSERT INTO outsend_emails_mailbox(username,from_address,password,signature,host,port,imap_host,imap_port,daily_limit) VALUES (?,?,?,?,?,?,?,?,?)",
                   ("synthetic-mailbox", "synthetic@example.com", encrypted, "", "smtp.gmail.com", 465, "imap.gmail.com", 993, 10))
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert ("MAILBOX_NESTED_ENCRYPTION_PRESENT" if nested else "MAILBOX_CREDENTIALS_MALFORMED") in codes(report)
    assert "synthetic-only-password" not in json.dumps(report)


@pytest.mark.parametrize("origin", [
    "https://127.1", "https://0x7f.0.0.1", "https://service.internal", "https://224.0.0.1",
    "https://invalid_domain.example.com", "https://[2001:4860:4860:0:0:0:0:8888]",
    "https://api.example.com:443", "https://api.example.com:",
])
def test_api_origin_must_use_same_canonical_public_rules_as_runtime(fixture, origin):
    from urllib.parse import urlsplit
    fixture["policy"]["api_origin"] = origin
    fixture["dashboard"]["LEADZEN_API_URL"] = origin
    host = urlsplit(origin).hostname
    fixture["backend"]["LEADZEN_ALLOWED_HOSTS"] = "[" + host + "]" if ":" in host else host
    report = fixture["run"]()
    assert report["status"] == "FAIL"
    assert report["checks"]["network"]["code"] == "PUBLIC_ORIGIN_INVALID"
    assert origin not in json.dumps(report)


def test_canonical_public_ipv6_api_matches_bracketed_django_host_allowlist(fixture):
    fixture["policy"]["api_origin"] = "https://[2001:4860:4860::8888]"
    fixture["dashboard"]["LEADZEN_API_URL"] = fixture["policy"]["api_origin"]
    fixture["backend"]["LEADZEN_ALLOWED_HOSTS"] = "[2001:4860:4860::8888]"
    assert fixture["run"]()["status"] == "PASS"


@pytest.mark.parametrize("host", ["127.1", "0x7f.0.0.1", "224.0.0.1", "service.internal", "invalid_domain.example.com"])
@pytest.mark.parametrize("kind", ["LLM", "MAIL"])
def test_allowlist_cannot_waive_public_provider_host_boundary(host, kind):
    assert not preflight._approved_public_host(host, {"LEADZEN_" + kind + "_HOSTS": host}, kind)


@pytest.mark.parametrize("host", ["127.1", "0x7f.0.0.1", "224.0.0.1"])
def test_enabled_chat_rejects_allowlisted_numeric_aliases_and_multicast(fixture, host):
    fixture["policy"]["features"]["chat"] = True
    fixture["backend"]["LEADZEN_LLM_HOSTS"] = host
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"llm_api_key":"synthetic-model-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET llm_provider='openai_compatible',llm_model='synthetic-model',llm_base_url=?,encrypted_secrets=?",
                   ("https://" + host + "/v1", encrypted))
    assert fixture["run"]()["databases"][1]["features"]["chat"]["status"] == "FAIL"


@pytest.mark.parametrize("host", ["127.1", "0x7f.0.0.1", "224.0.0.1"])
def test_enabled_mail_rejects_allowlisted_numeric_aliases_and_multicast(fixture, host):
    fixture["policy"]["features"]["mail"] = True
    fixture["backend"]["LEADZEN_MAIL_HOSTS"] = host
    encrypted = Fernet(fixture["backend"]["LEADZEN_SETTINGS_KEY"].encode()).encrypt(
        b'{"mailbox_password":"synthetic-mail-key"}').decode()
    with sqlite3.connect(fixture["employee"]) as db:
        db.execute("UPDATE leadzen_config_runtimesettings SET mailbox_address='synthetic@example.com',smtp_host=?,imap_host='imap.gmail.com',encrypted_secrets=?", (host, encrypted))
    assert fixture["run"]()["databases"][1]["features"]["mail"]["status"] == "FAIL"


@pytest.mark.parametrize("host,kind", [("SMTP.GMAIL.COM", "MAIL"), ("API.OPENAI.COM", "LLM"), ("2001:4860:4860::8888", "MAIL")])
def test_valid_transport_dns_case_and_global_ipv6_are_preserved(host, kind):
    assert preflight._approved_public_host(host, {"LEADZEN_" + kind + "_HOSTS": host.lower()}, kind)


def test_wrong_host_identity_fails_without_hostname_output(fixture):
    fixture["policy"]["expected_hostname"] = "synthetic-unexpected-host"
    report = fixture["run"]()
    assert "HOST_IDENTITY_MISMATCH" in codes(report)
    assert "synthetic-unexpected-host" not in json.dumps(report)


def test_nonempty_wal_blocks_instead_of_creating_shared_memory(fixture):
    wal = Path(str(fixture["employee"]) + "-wal")
    wal.write_bytes(b"synthetic-outstanding-wal")
    wal.chmod(0o600)
    report = fixture["run"]()
    assert report["status"] == "BLOCKED"
    assert "DATABASE_WAL_PENDING" in codes(report)
    assert wal.read_bytes() == b"synthetic-outstanding-wal"
    assert not Path(str(fixture["employee"]) + "-shm").exists()


def test_real_graph_child_does_not_load_application_settings_or_touch_selected_db(tmp_path):
    original = tmp_path / "untouched.sqlite3"
    original.write_bytes(b"not-a-database")
    result = subprocess.run([sys.executable, "-m", "leadzen.operations.preflight", "--graph"],
                            env={**os.environ, "LEADZEN_DB": str(original), "DJANGO_SETTINGS_MODULE": "must_never_be_imported"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert ["leadzen_accounts", "0004_accountprofile_tour_state"] in payload["leaves"]
    assert ["leadzen_config", "0019_discoverylookup_source_index"] in payload["leaves"]
    assert original.read_bytes() == b"not-a-database"
    assert str(original) not in result.stdout + result.stderr


def test_cli_private_report_creation_and_existing_report_not_overwritten(fixture, capsys):
    assert fixture["run"]()["status"] == "PASS"
    output = fixture["root"] / "safe-report.json"
    arguments = ["--backend-env", str(fixture["paths"][0]), "--dashboard-env", str(fixture["paths"][1]),
                 "--policy", str(fixture["paths"][2]), "--report", str(output)]
    assert preflight.main(arguments) == 0
    assert (output.stat().st_mode & 0o777) == 0o600
    saved = output.read_bytes()
    assert json.loads(saved)["status"] == "PASS"
    assert str(fixture["root"]) not in capsys.readouterr().out
    assert preflight.main(arguments) == 2
    assert output.read_bytes() == saved
    assert "REPORT_WRITE_FAILED" in capsys.readouterr().out
