"""Central workspace controls, factual connection receipts and private backups."""
import json
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.test import Client
from django.utils import timezone

from leadzen.config.models import OnboardingState, RuntimeSettings, SiteConfig
from leadzen.configuration import effective, save_dashboard_settings


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())


def put(client, body):
    return client.put("/api/settings", data=json.dumps(body), content_type="application/json")


def test_settings_read_returns_canonical_identity_product_and_data_without_probes(account_client):
    config = SiteConfig.load()
    config.operator_name, config.operator_email, config.operator_country_code = "Ashish Dikonda", "operator@example.com", "US"
    config.product_docs, config.booking_link = "Saved product description", "https://example.com/book"
    config.save()
    with patch("leadzen.setup_wizard.probe_ai") as ai, patch("leadzen.setup_wizard.probe_discovery") as finder, patch("leadzen.setup_wizard.probe_mailbox") as mail:
        response = account_client.get("/api/settings")
        assert response.status_code == 200
        workspace = response.json()["workspace"]
        assert workspace["identity"]["operator_name"] == config.operator_name
        assert workspace["identity"]["country_name"] == "United States"
        assert workspace["product"]["product_docs"] == config.product_docs
        assert workspace["booking_link"] == config.booking_link
        assert workspace["data"]["engine"] == "SQLite" and workspace["data"]["combined"] is True
        ai.assert_not_called(); finder.assert_not_called(); mail.assert_not_called()


def test_public_edits_preserve_connections_and_login_identity(account_client):
    save_dashboard_settings({"provider": "groq", "model": "openai/gpt-oss-120b", "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "smtp_port": 587}, llm_api_key="synthetic-private-key")
    before = effective()
    response = put(account_client, {"workspace_updates": {"identity": {"operator_name": "Ashish Dikonda", "operator_email": "operator@example.com", "operator_country_code": "US"}, "product": {"product_name": "Reviews", "product_docs": "A saved description"}, "booking_link": "https://example.com/book"}})
    assert response.status_code == 200, response.content
    after = effective()
    assert before == after and "synthetic-private-key" not in response.content.decode()
    assert SiteConfig.load().product_docs == "Reviews\n\nA saved description"
    assert OnboardingState.objects.get(pk=1).draft["operator_name"] == "Ashish Dikonda"
    assert account_client.get("/api/auth/me").json()["user"]["email"] == "unit@example.com"


@pytest.mark.parametrize("workspace", [
    {"identity": {"operator_name": "Bad", "operator_email": "bad", "operator_country_code": "US"}},
    {"booking_link": "javascript:alert(1)"}, {"booking_link": "https://user:secret@example.com/book"},
    {"booking_link": 123}, {"product": {"product_name": "x", "product_docs": ""}},
    {"target": {"audience": {}, "confirmed": False}},
])
def test_invalid_workspace_edits_are_atomic_with_connection_edits(account_client, workspace):
    config = SiteConfig.load()
    config.booking_link = "https://example.com/old"
    config.save()
    response = put(account_client, {"llm": {"provider": "groq", "model": "changed"}, "workspace_updates": workspace})
    assert response.status_code == 400
    assert SiteConfig.load().booking_link == "https://example.com/old"
    assert not RuntimeSettings.objects.exists()


def test_settings_connections_use_receipts_and_hide_stale_credit_balance(account_client):
    from leadzen.setup_wizard import fingerprint
    from datetime import timedelta
    save_dashboard_settings({"provider": "groq", "model": "openai/gpt-oss-120b"}, llm_api_key="synthetic-ai", bettercontact_api_key="synthetic-finder")
    state = OnboardingState.objects.create(checks={"discovery": {"fingerprint": fingerprint(effective(), "discovery"), "credits": 34, "tested_at": timezone.now().isoformat(), "expires_at": (timezone.now() + timedelta(hours=24)).isoformat()}})
    checks = account_client.get("/api/settings").json()["workspace"]["checks"]
    assert checks["discovery"]["connected"] and checks["discovery"]["credits"] == 34
    assert not checks["ai"]["connected"]
    state.checks["discovery"]["fingerprint"] = "stale"
    state.save()
    checks = account_client.get("/api/settings").json()["workspace"]["checks"]
    assert not checks["discovery"]["connected"] and "credits" not in checks["discovery"]


def test_settings_target_reuses_review_validation_and_canonical_preview(account_client):
    target = {"audience": {"industry": "Dental practices", "country": "US", "company_size": "2-50", "roles": ["Owner"], "seniority": ["owner"], "instructions": ""}, "confirmed": True, "accepted_legal_notice": True}
    response = put(account_client, {"workspace_updates": {"target": target}})
    assert response.status_code == 200
    assert response.json()["workspace"]["target"]["audience"]["industry"] == "Dental practices"
    assert "Dental practices" in SiteConfig.load().campaign_target


def test_backup_requires_session_and_explicit_post(db, account_client):
    assert Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token").post("/api/settings/backup").status_code == 401
    assert account_client.get("/api/settings/backup").status_code == 405
    assert account_client.post("/api/settings/backup", data="{}", content_type="application/json").status_code == 400


def test_local_entry_redirects_to_configured_dashboard_without_provider_access(db, monkeypatch):
    monkeypatch.setenv("LEADZEN_PUBLIC_URL", "http://localhost:3001")
    assert Client().get("/", HTTP_HOST="localhost:8000")["Location"] == "http://localhost:3001"
    monkeypatch.setenv("LEADZEN_PUBLIC_URL", "javascript:alert(1)")
    assert Client().get("/", HTTP_HOST="localhost:8000").status_code == 503
    for invalid in ("http://[invalid", "http://localhost:bad", "http://localhost:8000"):
        monkeypatch.setenv("LEADZEN_PUBLIC_URL", invalid)
        assert Client().get("/", HTTP_HOST="localhost:8000").status_code == 503


def test_real_workspace_settings_and_sqlite_backup_isolation(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OUTSEND_", "OPENOUTFIND_", "LEADZEN_"))}
    env.update(LEADZEN_DB=str(tmp_path / "control.sqlite3"), LEADZEN_WORKSPACE_ROOT=str(tmp_path / "workspaces"), LEADZEN_ALLOWED_HOSTS="testserver,localhost,127.0.0.1,[::1]", PYTHONPATH=str(root), DJANGO_SETTINGS_MODULE="leadzen.settings")
    result = subprocess.run([sys.executable, str(root / "tests/scenarios/workspace_settings.py")], cwd=root, env=env, text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr[-6000:]
    assert "Settings and SQLite backup isolation verified" in result.stdout
