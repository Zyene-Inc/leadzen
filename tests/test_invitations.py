import json
import re
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.test import Client
from django.utils import timezone

from leadzen.accounts.models import EmployeeInvitation, LoginSession
from leadzen.accounts.service import create_account, login
from leadzen.email_api import DeliveryError

PASSWORD = "Synthetic-invite-fixture-9847!"


@pytest.fixture
def invite_clients(db, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-invite-service")
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("LEADZEN_RESEND_API_KEY", "synthetic-resend-key")
    monkeypatch.setenv("LEADZEN_PUBLIC_URL", "https://leadzen.zyene.com")
    user = create_account(email="admin@example.com", name="Admin", password=PASSWORD, is_admin=True, require_change=False)
    _, token, _ = login(user.email, PASSWORD)
    return Client(HTTP_AUTHORIZATION="Bearer synthetic-invite-service", HTTP_X_LEADZEN_SESSION=token), Client(HTTP_AUTHORIZATION="Bearer synthetic-invite-service")


def invite(admin, name="Employee"):
    with patch("leadzen.accounts.invitations.post_email", return_value="synthetic-message-id") as send:
        response = admin.post("/api/admin/users", data=json.dumps({"name": name, "email": "employee@example.com"}), content_type="application/json")
    assert response.status_code == 201, response.content
    token = re.search(r"#token=([\w-]+)", send.call_args.args[2]["text"])[1]
    return response.json()["user"], token, send.call_args


def test_setup_link_is_one_time_and_does_not_grant_admin(invite_clients):
    admin, public = invite_clients
    user, token, call = invite(admin)
    assert user["invitation_pending"] and not user["is_admin"]
    assert token not in json.dumps(user) and not EmployeeInvitation.objects.filter(token_hash=token).exists()
    assert public.post("/api/auth/setup", data=json.dumps({"token": token}), content_type="application/json").json()["email"] == "employee@example.com"
    response = public.post("/api/auth/setup", data=json.dumps({"token": token, "password": PASSWORD, "role": "admin"}), content_type="application/json")
    assert response.status_code == 200
    response = public.post("/api/auth/setup", data=json.dumps({"token": token, "password": "Other-synthetic-8739!"}), content_type="application/json")
    assert response.status_code == 400
    employee, session, code = login("employee@example.com", PASSWORD)
    assert code == 200 and not employee.is_staff and not employee.leadzen_profile.must_change_password
    client = Client(HTTP_AUTHORIZATION="Bearer synthetic-invite-service", HTTP_X_LEADZEN_SESSION=session)
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/overview").status_code == 403
    assert EmployeeInvitation.objects.get().encrypted_token == ""


@pytest.mark.parametrize("invalid", ["expired", "disabled", "deleted", "forged"])
def test_invalid_or_revoked_setup_cannot_change_password(invite_clients, invalid):
    admin, public = invite_clients
    user, token, _ = invite(admin)
    if invalid == "expired":
        EmployeeInvitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    elif invalid == "disabled":
        admin.put(f'/api/admin/users/{user["id"]}', data='{"is_active":false}', content_type="application/json")
    elif invalid == "deleted":
        admin.delete(f'/api/admin/users/{user["id"]}')
    else:
        token = "x" * 64
    assert public.post("/api/auth/setup", data=json.dumps({"token": token, "password": PASSWORD}), content_type="application/json").status_code == 400
    assert LoginSession.objects.count() == 1  # Only the administrator's session.


def test_resend_rotates_link_and_rate_limits_network(invite_clients):
    admin, public = invite_clients
    user, old, _ = invite(admin)
    with patch("leadzen.accounts.invitations.post_email", return_value="new-id") as send:
        assert admin.post(f'/api/admin/users/{user["id"]}/invite').status_code == 400
        send.assert_not_called()
        EmployeeInvitation.objects.update(last_attempt_at=timezone.now() - timedelta(minutes=2))
        assert admin.post(f'/api/admin/users/{user["id"]}/invite').status_code == 200
        assert send.call_count == 1
    assert public.post("/api/auth/setup", data=json.dumps({"token": old}), content_type="application/json").status_code == 400


def test_provider_failure_is_reported_without_secret_or_link(invite_clients):
    admin, _ = invite_clients
    with patch("leadzen.accounts.invitations.post_email", side_effect=DeliveryError("synthetic-secret-error")):
        response = admin.post("/api/admin/users", data='{"email":"employee@example.com","name":"Employee"}', content_type="application/json")
    assert response.status_code == 201 and response.json()["invitation_status"] == "failed"
    assert "synthetic-secret" not in response.content.decode() and "token=" not in response.content.decode()
    assert EmployeeInvitation.objects.get().delivery_status == "failed"


def test_invitation_html_escapes_employee_name(invite_clients):
    user, token, call = invite(invite_clients[0], name='<img src=x onerror="bad"> & Employee')
    assert "<img" not in call.args[2]["html"] and "&lt;img" in call.args[2]["html"]


def test_employee_cannot_issue_an_invitation_or_create_admin(invite_clients):
    admin, _ = invite_clients
    with patch("leadzen.accounts.invitations.post_email") as send:
        assert admin.post("/api/admin/users", data='{"name":"Admin","email":"extra@example.com","role":"admin"}', content_type="application/json").status_code == 400
        send.assert_not_called()


def test_provider_call_has_committed_invitation_and_holds_no_control_write_lock(transactional_db, invite_clients):
    from django.db import connections

    def accepted(*args, **kwargs):
        assert not connections["default"].in_atomic_block
        assert EmployeeInvitation.objects.get().delivery_status == "pending"
        return "synthetic-accepted-id"

    with patch("leadzen.accounts.invitations.post_email", side_effect=accepted):
        response = invite_clients[0].post("/api/admin/users", data='{"email":"employee@example.com","name":"Employee"}', content_type="application/json")
    assert response.status_code == 201
    assert EmployeeInvitation.objects.get().delivery_status == "sent"
    assert EmployeeInvitation.objects.get().encrypted_token == ""


def test_admin_revocation_before_provider_submission_blocks_invitation(invite_clients):
    from django.contrib.auth import get_user_model
    from leadzen.accounts.invitations import audit

    def revoke_after_storage(actor, action, target_id):
        audit(actor, action, target_id)
        get_user_model().objects.filter(pk=actor.pk).update(is_staff=False)

    with patch("leadzen.accounts.invitations.audit", side_effect=revoke_after_storage), patch("leadzen.accounts.invitations.post_email") as send:
        response = invite_clients[0].post("/api/admin/users", data='{"email":"employee@example.com","name":"Employee"}', content_type="application/json")
    assert response.status_code == 400
    send.assert_not_called()
    invitation = EmployeeInvitation.objects.get()
    assert invitation.delivery_status == "failed" and invitation.encrypted_token == ""
