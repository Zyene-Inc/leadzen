"""Release-audit regressions at credential and session-issuance boundaries."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.test import Client, RequestFactory
from django.utils import timezone

from leadzen.accounts.models import AccountProfile, LoginSession
from leadzen.accounts.service import create_account, login, payload

PASSWORD = "Synthetic-account-9821!"


@pytest.mark.parametrize("change", ["password", "deactivate", "delete"])
def test_login_rechecks_account_before_issuing_session(db, monkeypatch, change):
    user = create_account(email="race@example.com", name="Synthetic employee", password=PASSWORD, require_change=False)

    def verify_then_change(password, encoded):
        valid = check_password(password, encoded)
        if change == "password":
            get_user_model().objects.filter(pk=user.pk).update(password=make_password("Replacement-private-8347!"))
        elif change == "deactivate":
            get_user_model().objects.filter(pk=user.pk).update(is_active=False)
        else:
            AccountProfile.objects.filter(user=user).update(deleted_at=timezone.now())
        return valid

    monkeypatch.setattr("leadzen.accounts.service.check_password", verify_then_change)
    assert login(user.email, PASSWORD) == (None, None, 401)
    assert not LoginSession.objects.filter(user=user).exists()


@pytest.mark.parametrize("change", ["password", "session", "deactivate"])
def test_password_change_rechecks_live_authority_before_mutation(db, monkeypatch, change):
    import json
    from leadzen.accounts.service import password_value

    user = create_account(email="change-race@example.com", name="Synthetic employee", password=PASSWORD, require_change=False)
    _, token, _ = login(user.email, PASSWORD)
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-dashboard-token")
    reset_password = "Replacement-private-8347!"

    def validate_then_revoke(value, actor):
        result = password_value(value, actor)
        if change == "password":
            get_user_model().objects.filter(pk=user.pk).update(password=make_password(reset_password))
        elif change == "session":
            LoginSession.objects.filter(user=user).delete()
        else:
            get_user_model().objects.filter(pk=user.pk).update(is_active=False)
        return result

    monkeypatch.setattr("leadzen.accounts.views.password_value", validate_then_revoke)
    response = Client(HTTP_AUTHORIZATION="Bearer synthetic-dashboard-token", HTTP_X_LEADZEN_SESSION=token).post(
        "/api/auth/password", json.dumps({"current_password": PASSWORD, "new_password": "Proposed-private-7724!"}), content_type="application/json",
    )
    assert response.status_code == 401
    user.refresh_from_db()
    assert user.check_password(reset_password if change == "password" else PASSWORD)


def test_non_ascii_dashboard_token_is_rejected_without_server_error(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-dashboard-token")
    response = Client(HTTP_AUTHORIZATION="Bearer invalid-\u00e9").get("/api/health")
    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}


def test_deeply_nested_json_returns_a_validation_error():
    request = RequestFactory().post("/api/settings", '{"nested":' + "[" * 10000 + "0" + "]" * 10000 + "}", content_type="application/json")
    with pytest.raises(ValueError, match="valid JSON"):
        payload(request)


def test_readiness_requires_private_dashboard_token(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-dashboard-token")
    with patch("leadzen.web.MigrationExecutor") as migrations:
        response = Client().get("/api/ready")
    assert response.status_code == 401
    migrations.assert_not_called()


def test_readiness_reports_applied_schema_and_restores_timeout(db, monkeypatch):
    from django.db import connections
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-dashboard-token")
    connection = connections["default"]
    before = connection.cursor().execute("PRAGMA busy_timeout").fetchone()
    response = Client(HTTP_AUTHORIZATION="Bearer synthetic-dashboard-token").get("/api/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": True, "migrations": True}
    assert connection.cursor().execute("PRAGMA busy_timeout").fetchone() == before


def test_readiness_rejects_unapplied_migrations(db, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-dashboard-token")
    with patch("leadzen.web.MigrationExecutor") as migrations:
        migrations.return_value.migration_plan.return_value = [object()]
        response = Client(HTTP_AUTHORIZATION="Bearer synthetic-dashboard-token").get("/api/ready")
    assert response.status_code == 503
    assert response.json() == {"error": "Required database migrations have not been applied"}


def test_readiness_hides_database_error_details(db, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-dashboard-token")
    with patch("leadzen.web.MigrationExecutor", side_effect=RuntimeError("/private/customer.db synthetic-sensitive-detail")):
        response = Client(HTTP_AUTHORIZATION="Bearer synthetic-dashboard-token").get("/api/ready")
    assert response.status_code == 503
    assert "private" not in response.content.decode() and "sensitive" not in response.content.decode()
    assert response["Cache-Control"] == "no-store"
