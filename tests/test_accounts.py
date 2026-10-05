"""Authorization is checked against live server state, not browser-supplied roles."""
import json
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from leadzen.accounts.models import AccountAudit, AccountProfile, LoginSession, LoginThrottle
from leadzen.accounts.service import create_account, login

PASSWORD = "Synthetic-account-9821!"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    from cryptography.fernet import Fernet
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("LEADZEN_RESEND_API_KEY", "synthetic-invitation-key")


def client(user):
    _, token, status = login(user.email, PASSWORD)
    assert status == 200
    return Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token", HTTP_X_LEADZEN_SESSION=token)


def account(email="member@example.com", admin=False, change=False):
    return create_account(email=email, name="Test member", password=PASSWORD, is_admin=admin, require_change=change)


def test_public_and_bearer_only_requests_do_not_access_private_data(db):
    with patch("leadzen.web.subprocess.Popen") as spawn:
        for route in ("overview", "leads", "jobs", "settings", "admin/users", "onboarding", "auth/me"):
            response = Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token").get("/api/" + route)
            assert response.status_code == 401
            assert "users" not in response.json() and "items" not in response.json()
        assert Client().post("/api/auth/signup", data="{}", content_type="application/json").status_code == 404
        spawn.assert_not_called()
    assert AccountProfile.objects.count() == 0


def test_employee_cannot_list_create_delete_or_promote_accounts(db):
    employee = account()
    target = account("other@example.com")
    employee_client = client(employee)
    before = AccountProfile.objects.count()
    assert employee_client.get("/api/admin/users").status_code == 403
    assert employee_client.post("/api/admin/users", data=json.dumps({"email": "intruder@example.com", "role": "admin", "password": PASSWORD, "name": "Intruder"}), content_type="application/json").status_code == 403
    assert employee_client.delete(f"/api/admin/users/{target.pk}").status_code == 403
    assert AccountProfile.objects.count() == before
    assert AccountAudit.objects.count() == 0
    target.refresh_from_db()
    assert target.is_active and not employee.is_staff


def test_admin_creation_sends_invitation_without_temporary_password(db):
    admin = account("administrator@example.com", admin=True)
    admin_client = client(admin)
    with patch("leadzen.accounts.invitations.post_email", return_value="synthetic-delivery-id") as send:
        response = admin_client.post("/api/admin/users", data=json.dumps({"email": "new@example.com", "name": "New employee", "role": "employee"}), content_type="application/json")
    assert send.call_count == 1
    assert response.status_code == 201
    assert response.json()["user"]["invitation_pending"]
    assert response.json()["invitation_status"] == "sent"
    assert not response.json()["user"]["is_admin"]
    assert PASSWORD not in response.content.decode()
    assert admin_client.get("/api/admin/users").json()["totals"] == {"users": 2, "active": 2, "admins": 1, "onboarded": 0}


def test_temporary_password_blocks_setup_then_change_revokes_all_sessions(db):
    user = account(change=True)
    user_client = client(user)
    second_client = client(user)
    assert user_client.get("/api/onboarding").status_code == 403
    assert user_client.get("/api/overview").json()["redirect"] == "/password"
    response = user_client.post("/api/auth/password", data=json.dumps({"current_password": PASSWORD, "new_password": "Replacement-private-8347!"}), content_type="application/json")
    assert response.status_code == 200
    assert LoginSession.objects.filter(user=user).count() == 0
    assert second_client.get("/api/auth/me").status_code == 401
    user.refresh_from_db()
    assert user.check_password("Replacement-private-8347!") and not user.leadzen_profile.must_change_password


def test_disabling_deleting_and_role_changes_take_effect_immediately(db):
    admin = account("administrator@example.com", admin=True)
    employee = account()
    admin_client, employee_client = client(admin), client(employee)
    assert admin_client.put(f"/api/admin/users/{employee.pk}", data='{"is_active": false}', content_type="application/json").status_code == 200
    assert employee_client.get("/api/auth/me").status_code == 401
    assert admin_client.put(f"/api/admin/users/{employee.pk}", data='{"is_active": true}', content_type="application/json").status_code == 200
    renewed = client(employee)
    assert admin_client.delete(f"/api/admin/users/{employee.pk}").status_code == 200
    assert renewed.get("/api/auth/me").status_code == 401
    assert AccountProfile.objects.get(user=employee).deleted_at
    assert admin_client.get("/api/admin/users").json()["totals"]["users"] == 1
    admin.is_staff = False
    admin.save(update_fields=["is_staff"])
    assert admin_client.get("/api/admin/users").status_code == 403


def test_logout_and_expiry_revoke_sessions(db):
    user = account()
    user_client = client(user)
    assert user_client.post("/api/auth/logout").status_code == 200
    assert user_client.get("/api/auth/me").status_code == 401
    user_client = client(user)
    LoginSession.objects.filter(user=user).update(expires_at=timezone.now())
    assert user_client.get("/api/auth/me").status_code == 401


def test_login_errors_rate_limit_and_no_raw_session_storage(db):
    user = account()
    public_client = Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token")
    assert public_client.post("/api/auth/login", data='{"email": "bad", "password": "bad"}', content_type="application/json").status_code == 401
    for _ in range(5):
        assert login(user.email, "wrong")[2] == 401
    assert login(user.email, PASSWORD)[2] == 429
    LoginThrottle.objects.all().delete()
    _, token, _ = login(user.email, PASSWORD)
    assert not LoginSession.objects.filter(token_hash=token).exists()
    assert len(LoginSession.objects.get(user=user).token_hash) == 64


def test_self_deletion_is_refused(db):
    admin = account(admin=True)
    admin_client = client(admin)
    assert admin_client.delete(f"/api/admin/users/{admin.pk}").status_code == 409
    admin.refresh_from_db()
    assert admin.is_active
    assert AccountAudit.objects.count() == 0


def test_invalid_connections_do_not_persist_or_reach_the_network(db, account_client, monkeypatch):
    from cryptography.fernet import Fernet
    from leadzen.config.models import RuntimeSettings
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    for url in ("http://api.example.com", "https://169.254.169.254", "https://localhost", "https://api.example.com:8000", "https://api.example.com/v1?key=secret"):
        response = account_client.put("/api/settings", data=json.dumps({"llm": {"provider": "openai_compatible", "model": "test", "base_url": url}}), content_type="application/json")
        assert response.status_code == 400
    assert RuntimeSettings.objects.count() == 0
