import json
import os

import pytest
from cryptography.fernet import Fernet
from django.test import Client


@pytest.fixture(autouse=True)
def dashboard_environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_DASHBOARD_ORIGINS", "http://testserver")


def settings_body():
    return {
        "llm": {
            "provider": "openai_compatible",
            "model": "openai/gpt-oss-120b",
            "base_url": "https://api.example.com/v1",
            "api_key": "llm-secret-value",
        },
        "mailbox": {
            "address": "sender@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "password": "mailbox-secret-value",
            "signature": "Thanks",
        },
    }


def test_runtime_settings_requires_dashboard_auth(db):
    response = Client().get("/api/settings")
    assert response.status_code == 401


def test_runtime_settings_refuses_secret_write_without_encryption_key(db, account_client, monkeypatch):
    monkeypatch.delenv("LEADZEN_SETTINGS_KEY", raising=False)
    response = account_client.put("/api/settings", data=json.dumps(settings_body()), content_type="application/json")
    assert response.status_code == 503


def test_runtime_settings_masks_and_encrypts_credentials(db, monkeypatch, account_client):
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode("ascii"))
    response = account_client.put("/api/settings", data=json.dumps(settings_body()), content_type="application/json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["api_key_configured"] is True
    assert payload["mailbox"]["password_configured"] is True
    assert "llm-secret-value" not in response.content.decode()
    assert "mailbox-secret-value" not in response.content.decode()

    from leadzen.config.models import RuntimeSettings

    stored = RuntimeSettings.load()
    assert "llm-secret-value" not in stored.encrypted_secrets
    assert "mailbox-secret-value" not in stored.encrypted_secrets

    readback = account_client.get("/api/settings")
    assert readback.status_code == 200
    assert readback.json()["llm"]["model"] == "openai/gpt-oss-120b"
    assert "llm-secret-value" not in readback.content.decode()


def test_runtime_settings_apply_to_child_environment(db, monkeypatch, account_client):
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode("ascii"))
    response = account_client.put("/api/settings", data=json.dumps(settings_body()), content_type="application/json")
    assert response.status_code == 200

    from leadzen.configuration import apply_dashboard_overrides

    apply_dashboard_overrides()
    assert os.environ["OPENOUTFIND_AI_MODEL"] == "openai_compatible:openai/gpt-oss-120b"
    assert os.environ["OUTSEND_SMTP_HOST"] == "smtp.example.com"
    from django.db import connection
    from cold_outreach.emails.models import Mailbox
    from leadzen.configuration import _decode
    mailbox = Mailbox.objects.get(username="sender@example.com")
    # Worker adapters intentionally decrypt ORM values in memory. Check the
    # actual persisted bytes rather than relying on earlier tests' adapter state.
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT password FROM {connection.ops.quote_name(Mailbox._meta.db_table)} WHERE id = %s", [mailbox.pk])
        stored = cursor.fetchone()[0]
    assert "mailbox-secret-value" not in stored
    assert _decode(stored)["mailbox_password"] == "mailbox-secret-value"
    if getattr(Mailbox._meta.get_field("password"), "_leadzen_encrypted", False):
        assert mailbox.password == "mailbox-secret-value"
    else:
        assert mailbox.password == stored


def test_smtp_465_settings_save_without_network_and_keep_secrets_private(db, monkeypatch, account_client):
    from unittest.mock import patch
    from cold_outreach.emails.models import Mailbox
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    body = settings_body()
    body["mailbox"]["smtp_port"] = 465
    with patch("socket.create_connection") as connect:
        response = account_client.put("/api/settings", data=json.dumps(body), content_type="application/json")
        assert response.status_code == 200, response.content
        connect.assert_not_called()
    assert response.json()["mailbox"]["smtp_port"] == "465"
    assert Mailbox.objects.get().port == 465
    assert "mailbox-secret-value" not in response.content.decode()


@pytest.mark.parametrize("port", [25, 80, 443, 993])
def test_smtp_unsupported_ports_remain_blocked(db, monkeypatch, account_client, port):
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    body = settings_body()
    body["mailbox"]["smtp_port"] = port
    assert account_client.put("/api/settings", data=json.dumps(body), content_type="application/json").status_code == 400


def test_partial_connection_saves_preserve_other_sections_and_omitted_fields(account_client):
    from leadzen.configuration import effective
    assert account_client.put("/api/settings", json.dumps(settings_body()), content_type="application/json").status_code == 200
    before = effective()
    response = account_client.put("/api/settings", '{"llm":{"model":"updated-model"}}', content_type="application/json")
    assert response.status_code == 200, response.content
    current = effective()
    assert current.model == "updated-model"
    assert current.llm_api_key == before.llm_api_key and current.provider == before.provider
    assert current.mailbox_address == before.mailbox_address and current.mailbox_password == before.mailbox_password
    assert current.smtp_host == before.smtp_host and current.imap_host == before.imap_host
    response = account_client.put("/api/settings", '{"mailbox":{"signature":"New signature"}}', content_type="application/json")
    assert response.status_code == 200, response.content
    current = effective()
    assert current.signature == "New signature" and current.model == "updated-model"
    assert current.llm_api_key == before.llm_api_key and current.mailbox_password == before.mailbox_password
    response = account_client.put("/api/settings", '{"lead_finder":{"api_key":"synthetic-finder"}}', content_type="application/json")
    assert response.status_code == 200, response.content
    assert effective().model == current.model and effective().mailbox_address == current.mailbox_address
    assert effective().bettercontact_api_key == "synthetic-finder"


@pytest.mark.parametrize("section,flag", [("llm", "clear_api_key"), ("mailbox", "clear_password"), ("mailbox", "clear_api_key"), ("mailbox", "clear_imap_password")])
def test_non_boolean_credential_clear_flags_do_not_modify_connections(account_client, section, flag):
    from leadzen.configuration import effective
    assert account_client.put("/api/settings", json.dumps(settings_body()), content_type="application/json").status_code == 200
    before = effective()
    response = account_client.put("/api/settings", json.dumps({section: {flag: "false"}}), content_type="application/json")
    assert response.status_code == 400
    assert effective() == before
