"""Production startup must reject unsafe settings without disclosing values."""
import secrets

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

from leadzen.production import REQUIRED, validate_environment


@pytest.fixture
def production_env(tmp_path):
    return {
        "LEADZEN_ENV": "production",
        "LEADZEN_DB": str(tmp_path / "control.sqlite3"),
        "LEADZEN_WORKSPACE_ROOT": str(tmp_path / "workspaces"),
        "LEADZEN_SETTINGS_KEY": Fernet.generate_key().decode(),
        "LEADZEN_SECRET_KEY": secrets.token_urlsafe(64),
        "LEADZEN_DASHBOARD_TOKEN": secrets.token_urlsafe(32),
        "LEADZEN_ALLOWED_HOSTS": "api.example.com,localhost,127.0.0.1",
        "LEADZEN_PUBLIC_URL": "https://app.example.com",
        "LEADZEN_DASHBOARD_ORIGINS": "https://app.example.com",
    }


def test_valid_production_environment(production_env):
    validate_environment(production_env)


@pytest.mark.parametrize("name", REQUIRED)
def test_missing_variables_fail_closed_without_values(production_env, name):
    production_env.pop(name)
    with pytest.raises(ImproperlyConfigured) as error:
        validate_environment(production_env)
    assert name in str(error.value)
    for secret in ("LEADZEN_SETTINGS_KEY", "LEADZEN_SECRET_KEY", "LEADZEN_DASHBOARD_TOKEN"):
        if secret in production_env:
            assert production_env[secret] not in str(error.value)


@pytest.mark.parametrize("name,value", [
    ("LEADZEN_ENV", "development"),
    ("DJANGO_SETTINGS_MODULE", "tests.settings"),
    ("LEADZEN_DB", "relative.sqlite3"),
    ("LEADZEN_WORKSPACE_ROOT", "relative/workspaces"),
    ("LEADZEN_SETTINGS_KEY", "invalid-private-key"),
    ("LEADZEN_SETTINGS_KEY", "\u00e9" * 44),
    ("LEADZEN_SECRET_KEY", "x" * 64),
    ("LEADZEN_DASHBOARD_TOKEN", "replace-with-a-long-random-token"),
    ("LEADZEN_ALLOWED_HOSTS", "*"),
    ("LEADZEN_ALLOWED_HOSTS", "https://api.example.com"),
    ("LEADZEN_ALLOWED_HOSTS", "testserver"),
    ("LEADZEN_PUBLIC_URL", "http://app.example.com"),
    ("LEADZEN_PUBLIC_URL", "https://private:credential@app.example.com"),
    ("LEADZEN_PUBLIC_URL", "https://app.example.com/path"),
    ("LEADZEN_PUBLIC_URL", "https://app.example.com:invalid"),
    ("LEADZEN_DASHBOARD_ORIGINS", "*"),
    ("LEADZEN_DASHBOARD_ORIGINS", "https://foreign.example.com"),
    ("LEADZEN_MCP_ALLOW_LOCAL", "1"),
])
def test_unsafe_production_environment_is_rejected(production_env, name, value):
    production_env[name] = value
    with pytest.raises(ImproperlyConfigured) as error:
        validate_environment(production_env)
    assert name in str(error.value)
    assert "private:credential" not in str(error.value)


def test_compose_does_not_restart_bounded_discovery():
    from pathlib import Path
    assert 'restart: "no"' in Path("local.yml").read_text()


def test_backend_rejects_unknown_hosts_and_protects_error_responses(client):
    response = client.get("/api/health", HTTP_HOST="untrusted.example.com")
    assert response.status_code == 400
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "no-referrer"


def test_backend_auth_errors_have_frame_and_transport_headers(client):
    response = client.get("/api/health", secure=True)
    assert response.status_code == 401
    assert response["X-Frame-Options"] == "DENY"
    assert response["Strict-Transport-Security"] == "max-age=31536000"


def test_request_metrics_never_log_body_query_headers_or_unknown_path(client, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setenv("LEADZEN_ENV", "production")
    with patch("leadzen.observability.logger.log") as log:
        response = client.post("/private-customer-path?token=synthetic-secret", data="synthetic-password", content_type="text/plain", HTTP_AUTHORIZATION="Bearer synthetic-key")
    assert response.status_code == 404 and len(response["X-Request-ID"]) == 32
    output = repr(log.call_args)
    assert "unmatched" in output and "duration_ms" in output
    for private in ("private-customer-path", "synthetic-secret", "synthetic-password", "synthetic-key"):
        assert private not in output


@pytest.mark.parametrize("origin", [
    "https://localhost", "https://localhost.localdomain", "https://service.localhost",
    "https://service.local", "https://service.internal", "https://service.home.arpa",
    "https://127.0.0.1", "https://10.0.0.1", "https://169.254.169.254", "https://192.0.2.1",
    "https://[::1]", "https://[fc00::1]", "https://[fe80::1]", "https://224.0.0.1",
    "https://127.1", "https://0x7f.0.0.1", "https://127.0.0.01", "https://2130706433",
    "https://app.example.com:443", "https://app.example.com:8443", "https://app.example.com:",
    "https://APP.EXAMPLE.COM", "HTTPS://app.example.com", "https://app.example.com.",
    "https://app.example.com?", "https://app.example.com#", "https://@app.example.com",
    "https://app\\.example.com", "https://%61pp.example.com", "https://app..example.com",
    "https://-app.example.com", "https://app-.example.com", "https://app_example.com",
    "https://app.ex\u00e4mple.com", "https://app.example.com\n", "https://app.example.com\x00",
    "https://" + "a" * 64 + ".example.com",
    "https://[2001:4860:4860:0:0:0:0:8888]", "https://[2001:4860:4860::8888%eth0]",
])
def test_runtime_rejects_noncanonical_nonpublic_origins_without_values(production_env, origin):
    production_env["LEADZEN_PUBLIC_URL"] = origin
    production_env["LEADZEN_DASHBOARD_ORIGINS"] = origin
    with pytest.raises(ImproperlyConfigured) as error:
        validate_environment(production_env)
    assert "LEADZEN_PUBLIC_URL" in str(error.value)
    assert "LEADZEN_DASHBOARD_ORIGINS" in str(error.value)
    assert origin not in str(error.value)


@pytest.mark.parametrize("origin", [
    "https://app.example.com", "https://dashboard.synthetic.example", "https://app.example.test",
    "https://trusted-preview.trycloudflare.com", "https://8.8.8.8", "https://[2001:4860:4860::8888]",
])
def test_canonical_public_origins_preserve_fixtures_and_global_literals(production_env, origin):
    production_env["LEADZEN_PUBLIC_URL"] = origin
    production_env["LEADZEN_DASHBOARD_ORIGINS"] = origin
    validate_environment(production_env)


def test_each_additional_dashboard_origin_is_validated(production_env):
    production_env["LEADZEN_DASHBOARD_ORIGINS"] += ",https://127.0.0.1"
    with pytest.raises(ImproperlyConfigured) as error:
        validate_environment(production_env)
    assert "LEADZEN_DASHBOARD_ORIGINS" in str(error.value)
