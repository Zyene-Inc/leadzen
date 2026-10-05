"""BetterContact setup uses synthetic keys and never calls a paid provider."""
import json
import os
import socket
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.test import Client


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")

    def forbid_connection(*args, **kwargs):
        raise AssertionError("Saving connections must not contact any provider")

    monkeypatch.setattr(socket.socket, "connect", forbid_connection)


def body(key="synthetic-bettercontact-key"):
    return {
        "llm": {"enabled": False},
        "mailbox": {
            "address": "sender@example.com", "smtp_host": "smtp.zoho.com",
            "smtp_port": 587, "imap_host": "imap.zoho.com", "imap_port": 993,
            "password": "synthetic-mail-password",
        },
        "lead_finder": {"provider": "bettercontact", "api_key": key},
    }


def save(client, value):
    return client.put("/api/settings", data=json.dumps(value), content_type="application/json")


def test_bettercontact_key_is_encrypted_and_only_presence_is_returned(db, account_client):
    from leadzen.config.models import RuntimeSettings, SiteConfig
    from leadzen.configuration import _decode, effective

    response = save(account_client, body())
    assert response.status_code == 200
    assert response.json()["lead_finder"] == {"provider": "bettercontact", "api_key_configured": True}
    assert "synthetic-bettercontact-key" not in response.content.decode()
    assert "synthetic-bettercontact-key" not in account_client.get("/api/settings").content.decode()
    stored = RuntimeSettings.load()
    assert "synthetic-bettercontact-key" not in stored.encrypted_secrets
    assert _decode(stored.encrypted_secrets)["bettercontact_api_key"] == "synthetic-bettercontact-key"
    assert effective().bettercontact_api_key == "synthetic-bettercontact-key"
    assert SiteConfig.load().bettercontact_api_key == ""


def test_blank_or_omitted_key_preserves_it_and_replacement_updates_it(db, account_client):
    from leadzen.configuration import effective

    assert save(account_client, body()).status_code == 200
    for value in (body(""), body("   ")):
        assert save(account_client, value).status_code == 200
        assert effective().bettercontact_api_key == "synthetic-bettercontact-key"
    value = body()
    value.pop("lead_finder")  # Older clients must keep the existing connection.
    assert save(account_client, value).status_code == 200
    assert effective().bettercontact_api_key == "synthetic-bettercontact-key"
    assert save(account_client, body("synthetic-replacement-key")).status_code == 200
    assert effective().bettercontact_api_key == "synthetic-replacement-key"


def test_clear_key_removes_worker_export_and_does_not_resurrect_legacy_key(db, account_client, monkeypatch):
    from leadzen.config.models import SiteConfig
    from leadzen.configuration import apply_dashboard_overrides, effective
    from leadzen.wizard import apply_to_environment

    config = SiteConfig.load()
    config.bettercontact_api_key = "synthetic-legacy-key"
    config.save()
    assert save(account_client, body("")).status_code == 200
    assert SiteConfig.load().bettercontact_api_key == ""  # Migrated to encrypted storage.
    assert effective().bettercontact_api_key == "synthetic-legacy-key"
    monkeypatch.setenv("OPENOUTFIND_BETTERCONTACT_API_KEY", "synthetic-inherited-key")
    monkeypatch.setenv("OPENOUTFIND_EMAIL_FINDER", "apollo")
    apply_dashboard_overrides()
    assert os.environ["OPENOUTFIND_BETTERCONTACT_API_KEY"] == "synthetic-legacy-key"
    assert os.environ["OPENOUTFIND_EMAIL_FINDER"] == "bettercontact"
    value = body("")
    value["lead_finder"]["clear_api_key"] = True
    response = save(account_client, value)
    assert response.status_code == 200
    assert response.json()["lead_finder"]["api_key_configured"] is False
    apply_to_environment(SiteConfig.load())
    assert effective().bettercontact_api_key == ""
    assert "OPENOUTFIND_BETTERCONTACT_API_KEY" not in os.environ


@pytest.mark.parametrize("finder", [[], "bad", {"provider": "unknown"}, {"api_key": 7}, {"api_key": "x" * 2001}, {"api_key": "bad\nheader"}, {"clear_api_key": "false"}])
def test_invalid_finder_settings_do_not_persist(db, account_client, finder):
    from leadzen.config.models import RuntimeSettings

    value = body()
    value["lead_finder"] = finder
    response = save(account_client, value)
    assert response.status_code == 400
    assert RuntimeSettings.objects.count() == 0


def test_unauthenticated_requests_do_not_read_or_write_keys(db):
    with patch("leadzen.web.save_dashboard_settings") as write, patch("leadzen.web.effective") as read:
        for client in (Client(), Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token")):
            assert save(client, body()).status_code == 401
            assert client.get("/api/settings").status_code == 401
        write.assert_not_called()
        read.assert_not_called()


def test_cli_environment_is_preserved_when_no_dashboard_finder_key_exists(db, monkeypatch):
    from leadzen.config.models import SiteConfig
    from leadzen.wizard import apply_to_environment

    config = SiteConfig.load()
    config.bettercontact_api_key = "synthetic-legacy-key"
    config.save()
    monkeypatch.setenv("OPENOUTFIND_BETTERCONTACT_API_KEY", "synthetic-explicit-cli-key")
    monkeypatch.setenv("OPENOUTFIND_EMAIL_FINDER", "apollo")
    apply_to_environment(config)
    assert os.environ["OPENOUTFIND_BETTERCONTACT_API_KEY"] == "synthetic-explicit-cli-key"
    assert os.environ["OPENOUTFIND_EMAIL_FINDER"] == "apollo"


def test_invalid_onboarding_key_is_rejected_before_workspace_creation(db, account_client):
    value = body("invalid\nheader")
    value.update(purpose="zyene_reviews", workspace_name="Synthetic workspace", product_docs="Synthetic product",
                 campaign_target="Synthetic target", operator_country_code="US", accepted_legal_notice=True)
    with patch("leadzen.workspaces.initialize_workspace") as initialize, patch("leadzen.configuration.save_dashboard_settings") as write:
        response = account_client.put("/api/onboarding", data=json.dumps(value), content_type="application/json")
        assert response.status_code == 400
        initialize.assert_not_called()
        write.assert_not_called()


def test_revoked_employee_cannot_read_or_write_finder_credentials(db, account_client):
    from django.contrib.auth import get_user_model

    get_user_model().objects.filter(email="unit@example.com").update(is_active=False)
    with patch("leadzen.web.save_dashboard_settings") as write, patch("leadzen.web.effective") as read:
        assert save(account_client, body()).status_code == 401
        assert account_client.get("/api/settings").status_code == 401
        write.assert_not_called()
        read.assert_not_called()


def test_legacy_cli_can_start_before_runtime_settings_table_is_migrated(db, monkeypatch):
    from django.db import OperationalError
    from leadzen.config.models import SiteConfig
    from leadzen.wizard import apply_to_environment

    config = SiteConfig.load()
    config.bettercontact_api_key = "synthetic-legacy-key"
    config.save()
    monkeypatch.delenv("OPENOUTFIND_BETTERCONTACT_API_KEY", raising=False)
    with patch("leadzen.configuration.RuntimeSettings.objects.filter", side_effect=OperationalError("Synthetic legacy schema")):
        apply_to_environment(config)
    assert os.environ["OPENOUTFIND_BETTERCONTACT_API_KEY"] == "synthetic-legacy-key"
