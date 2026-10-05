"""Synthetic remote OAuth flows: identity, PKCE, audience, consent and replay."""
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

import pytest
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from leadzen.accounts.models import AccountAudit
from leadzen.accounts.service import create_account, login
from leadzen.mcp.auth import authenticate_mcp, connection_live, digest, pkce_challenge
from leadzen.mcp.models import MCPAccessToken, MCPAuthorizationRequest, MCPClient, MCPConnection, MCPRefreshToken

RESOURCE = "https://api.leadzen.example/mcp"
CALLBACK = "https://chatgpt.example/oauth/callback"
PASSWORD = "MCP-synthetic-account-9813!"
VERIFIER = "synthetic-verifier-that-is-long-enough-to-be-pkce-valid-93478"


@pytest.fixture(autouse=True)
def mcp_environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_MCP_PUBLIC_URL", RESOURCE)
    monkeypatch.setenv("LEADZEN_PUBLIC_URL", "https://leadzen.example")
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.delenv("LEADZEN_CONTROL_DB", raising=False)


def employee(email="mcp-member@example.com"):
    user = create_account(email=email, name="MCP member", password=PASSWORD, require_change=False)
    user.leadzen_profile.onboarding_completed_at = timezone.now()
    user.leadzen_profile.save()
    return user


def dashboard(user):
    _, token, status = login(user.email, PASSWORD)
    assert status == 200
    return Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token", HTTP_X_LEADZEN_SESSION=token)


def post(client, route, value):
    return client.post(route, data=json.dumps(value), content_type="application/json")


def register(name="ChatGPT", callback=CALLBACK):
    response = post(Client(), "/mcp/oauth/register", {"client_name": name, "redirect_uris": [callback], "token_endpoint_auth_method": "none"})
    assert response.status_code == 201, response.content
    return response.json()["client_id"]


def begin(client_id=None, *, scope="leadzen:read leadzen:write offline_access", **overrides):
    values = {"client_id": client_id or register(), "redirect_uri": CALLBACK, "response_type": "code",
              "resource": RESOURCE, "scope": scope, "state": "opaque-client-state",
              "code_challenge": pkce_challenge(VERIFIER), "code_challenge_method": "S256", **overrides}
    response = Client().get("/mcp/oauth/authorize", values)
    assert response.status_code == 302, response.content
    assert urlsplit(response.url).netloc == "leadzen.example"
    return values, parse_qs(urlsplit(response.url).query)["request"][0]


def approve(user=None, **kwargs):
    user = user or employee()
    values, handle = begin(**kwargs)
    response = post(dashboard(user), "/api/mcp/authorize", {"request": handle, "decision": "approve"})
    assert response.status_code == 200, response.content
    callback = response.json()["redirectUrl"]
    parsed = parse_qs(urlsplit(callback).query)
    assert parsed["state"] == ["opaque-client-state"]
    assert parsed["iss"] == ["https://api.leadzen.example"]
    return user, values, parsed["code"][0]


def exchange(values, code, **overrides):
    return Client().post("/mcp/oauth/token", data=urlencode({"grant_type": "authorization_code", "client_id": values["client_id"],
                         "redirect_uri": values["redirect_uri"], "resource": values["resource"], "code": code,
                         "code_verifier": VERIFIER, **overrides}), content_type="application/x-www-form-urlencoded")


def refresh(values, token, **overrides):
    return Client().post("/mcp/oauth/token", data=urlencode({"grant_type": "refresh_token", "client_id": values["client_id"],
                         "resource": RESOURCE, "refresh_token": token, **overrides}), content_type="application/x-www-form-urlencoded")


def authenticated(token):
    request = RequestFactory().post("/mcp", HTTP_AUTHORIZATION="Bearer " + token)
    return authenticate_mcp(request)


def test_metadata_is_public_no_secrets_and_advertises_s256_dcr(db):
    metadata = Client().get("/.well-known/oauth-authorization-server")
    assert metadata.status_code == 200
    assert metadata.json()["code_challenge_methods_supported"] == ["S256"]
    assert metadata.json()["client_id_metadata_document_supported"] is False
    assert metadata.json()["token_endpoint_auth_methods_supported"] == ["none"]
    resource = Client().get("/.well-known/oauth-protected-resource/mcp")
    assert resource.json()["resource"] == RESOURCE
    assert "test-dashboard-token" not in resource.content.decode()
    assert resource["Cache-Control"] == "no-store"


def test_missing_public_https_configuration_disables_connector(db, monkeypatch, account_client):
    monkeypatch.delenv("LEADZEN_MCP_PUBLIC_URL")
    response = account_client.get("/api/mcp/connections")
    assert response.status_code == 200 and not response.json()["available"]
    assert response.json()["endpoint"] is None
    assert Client().get("/.well-known/oauth-authorization-server").status_code == 503
    assert post(Client(), "/mcp/oauth/register", {"redirect_uris": [CALLBACK]}).status_code == 503
    monkeypatch.setenv("LEADZEN_MCP_PUBLIC_URL", "http://api.leadzen.example/mcp")
    assert Client().get("/.well-known/oauth-protected-resource").status_code == 503


@pytest.mark.parametrize("callback", ["http://evil.example/callback", "https://user:password@evil.example/callback", "https://evil.example/callback#fragment", "javascript:alert(1)", "https://evil.example/\\path", "https://evil.example\n/callback"])
def test_bad_registration_never_persists_or_fetches_metadata(db, callback):
    with patch("requests.get") as network:
        response = post(Client(), "/mcp/oauth/register", {"client_name": "Claude", "redirect_uris": [callback], "client_uri": "http://169.254.169.254"})
    assert response.status_code == 400
    assert MCPClient.objects.count() == 0
    network.assert_not_called()


def test_untrusted_client_name_is_not_used_to_choose_callback_and_requires_consent(db, account_client):
    identifier = register(name="Claude (unverified custom client)")
    values, handle = begin(identifier)
    metadata = account_client.get("/api/mcp/authorize", {"request": handle})
    assert metadata.json()["clientName"] == "Claude (unverified custom client)"
    assert metadata.json()["redirectHost"] == "chatgpt.example"
    assert MCPConnection.objects.count() == MCPAccessToken.objects.count() == 0
    assert Client().get("/api/mcp/authorize", {"request": handle}).status_code == 401
    assert post(Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token"), "/api/mcp/authorize", {"request": handle, "decision": "approve"}).status_code == 401
    assert MCPConnection.objects.count() == 0


def test_oauth_pkce_consent_token_and_employee_connection_round_trip(db, monkeypatch):
    monkeypatch.setattr("leadzen.workspaces.workspace_scope", lambda profile: __import__("contextlib").nullcontext("default"))
    user, values, code = approve()
    assert dashboard(user).get("/api/mcp/connections").json()["connections"] == []
    response = exchange(values, code)
    assert response.status_code == 200, response.content
    tokens = response.json()
    actor, connection = authenticated(tokens["access_token"])
    assert actor.pk == user.pk and connection.user_id == user.pk
    assert MCPAccessToken.objects.get().token_hash == digest(tokens["access_token"])
    assert MCPRefreshToken.objects.get().token_hash == digest(tokens["refresh_token"])
    assert MCPAuthorizationRequest.objects.get().code_hash == digest(code)
    assert MCPAccessToken.objects.get().token_hash != tokens["access_token"]
    listing = dashboard(user).get("/api/mcp/connections").json()
    assert len(listing["connections"]) == 1
    assert listing["connections"][0]["clientName"] == "ChatGPT"
    assert listing["connections"][0]["lastUsedAt"]
    assert not any(key in listing["connections"][0] for key in ("access_token", "refresh_token", "password"))
    assert AccountAudit.objects.filter(actor=user, action="mcp_connected").exists()


@pytest.fixture
def approved(db, monkeypatch):
    monkeypatch.setattr("leadzen.workspaces.workspace_scope", lambda profile: __import__("contextlib").nullcontext("default"))
    return approve()


@pytest.mark.parametrize("override", [{"code_verifier": "wrong-proof-that-is-long-enough-for-pkce-validation-8841"}, {"redirect_uri": "https://evil.example/callback"}, {"client_id": "other-client"}, {"resource": "https://foreign.example/mcp"}])
def test_wrong_pkce_callback_client_or_resource_never_issue_tokens(approved, override):
    _, values, code = approved
    assert exchange(values, code, **override).status_code == 400
    assert MCPAccessToken.objects.count() == MCPRefreshToken.objects.count() == 0
    assert MCPAuthorizationRequest.objects.get().consumed_at is None


def test_authorization_code_is_single_use_and_proven_replay_revokes_grant(approved):
    _, values, code = approved
    tokens = exchange(values, code).json()
    assert exchange(values, code).status_code == 400
    assert authenticated(tokens["access_token"]).status_code == 401
    assert MCPConnection.objects.get().revoked_at is not None


def test_authorization_cleanup_preserves_live_connection_visibility_and_revocation(approved):
    owner, values, code = approved
    tokens = exchange(values, code).json()
    MCPAuthorizationRequest.objects.update(expires_at=timezone.now() - timedelta(days=2))
    begin()  # Another client's request triggers global expired-request cleanup.
    listing = dashboard(owner).get("/api/mcp/connections").json()["connections"]
    assert len(listing) == 1
    assert authenticated(tokens["access_token"])[0].pk == owner.pk
    assert exchange(values, code).status_code == 400
    assert authenticated(tokens["access_token"]).status_code == 401


def test_refresh_rotation_replay_revokes_current_family_without_leaking_tokens(approved):
    _, values, code = approved
    first = exchange(values, code).json()
    second_response = refresh(values, first["refresh_token"])
    assert second_response.status_code == 200
    second = second_response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert authenticated(second["access_token"])[0].pk
    replay = refresh(values, first["refresh_token"])
    assert replay.status_code == 400
    assert "access_token" not in replay.json()
    assert authenticated(second["access_token"]).status_code == 401
    assert refresh(values, second["refresh_token"]).status_code == 400


def test_foreign_client_cannot_refresh_or_revoke_another_client_grant(approved):
    _, values, code = approved
    tokens = exchange(values, code).json()
    other = register("Other client")
    assert refresh(values, tokens["refresh_token"], client_id=other).status_code == 400
    response = Client().post("/mcp/oauth/revoke", data=urlencode({"token": tokens["access_token"], "client_id": other}), content_type="application/x-www-form-urlencoded")
    assert response.status_code == 200
    assert authenticated(tokens["access_token"])[0].pk
    assert refresh(values, tokens["refresh_token"]).status_code == 200


def test_resource_owner_revocation_via_rfc7009_invalidates_all_family_tokens(approved):
    _, values, code = approved
    tokens = exchange(values, code).json()
    response = Client().post("/mcp/oauth/revoke", data=urlencode({"token": tokens["refresh_token"], "client_id": values["client_id"]}), content_type="application/x-www-form-urlencoded")
    assert response.status_code == 200
    assert authenticated(tokens["access_token"]).status_code == 401
    assert refresh(values, tokens["refresh_token"]).status_code == 400


def test_connection_execution_checks_actor_and_live_revocation_after_context_entry(approved):
    from leadzen.mcp.guard import assert_connection_access, connection_execution
    owner, values, code = approved
    exchange(values, code)
    connection = MCPConnection.objects.get()
    with pytest.raises(PermissionError):
        connection_live(connection.pk, actor_id=owner.pk + 1)
    with connection_execution(connection.pk, owner.pk):
        assert_connection_access()
        MCPConnection.objects.filter(pk=connection.pk).update(revoked_at=timezone.now())
        with pytest.raises(PermissionError):
            assert_connection_access()
    assert_connection_access()  # Context restored for ordinary portal work.


def test_admin_disable_reactivate_and_password_reset_permanently_revoke_oauth(approved):
    owner, values, code = approved
    tokens = exchange(values, code).json()
    admin = employee("mcp-admin@example.com")
    admin.is_staff = True
    admin.save()
    admin_client = dashboard(admin)
    assert admin_client.put(f"/api/admin/users/{owner.pk}", data=json.dumps({"is_active": False}), content_type="application/json").status_code == 200
    assert admin_client.put(f"/api/admin/users/{owner.pk}", data=json.dumps({"is_active": True}), content_type="application/json").status_code == 200
    assert authenticated(tokens["access_token"]).status_code == 401
    assert MCPConnection.objects.get().revoked_at


def test_expired_unexchanged_grant_does_not_appear_connected_or_block_reconnect(approved):
    owner, _, _ = approved
    first = MCPConnection.objects.get()
    MCPAuthorizationRequest.objects.update(code_expires_at=timezone.now() - timedelta(seconds=1))
    assert dashboard(owner).get("/api/mcp/connections").json()["connections"] == []
    approve(owner)
    first.refresh_from_db()
    assert first.revoked_at is not None


def test_no_refresh_issued_without_offline_access(db, monkeypatch):
    monkeypatch.setattr("leadzen.workspaces.workspace_scope", lambda profile: __import__("contextlib").nullcontext("default"))
    _, values, code = approve(scope="leadzen:read leadzen:write")
    tokens = exchange(values, code).json()
    assert "refresh_token" not in tokens
    assert MCPRefreshToken.objects.count() == 0


@pytest.mark.parametrize("change", ["inactive", "deleted", "password", "onboarding", "temporary_password", "resource"])
def test_live_account_and_resource_changes_reject_access_and_refresh(approved, monkeypatch, change):
    user, values, code = approved
    tokens = exchange(values, code).json()
    profile = user.leadzen_profile
    if change == "inactive":
        user.is_active = False
        user.save()
    elif change == "deleted":
        profile.deleted_at = timezone.now()
        profile.save()
    elif change == "password":
        user.set_password("Replacement-MCP-password-38342!")
        user.save()
    elif change == "onboarding":
        profile.onboarding_completed_at = None
        profile.save()
    elif change == "temporary_password":
        profile.must_change_password = True
        profile.save()
    else:
        monkeypatch.setenv("LEADZEN_MCP_PUBLIC_URL", "https://other-api.example/mcp")
    assert authenticated(tokens["access_token"]).status_code == 401
    assert refresh(values, tokens["refresh_token"]).status_code == 400


def test_employee_cannot_revoke_foreign_connection_and_dashboard_bearer_is_not_mcp_token(approved):
    owner, values, code = approved
    tokens = exchange(values, code).json()
    connection = MCPConnection.objects.get()
    other = employee("mcp-other@example.com")
    assert post(dashboard(other), "/api/mcp/connections", {"connectionId": str(connection.pk)}).status_code == 404
    assert dashboard(other).get("/api/mcp/connections").json()["connections"] == []
    assert authenticated(tokens["access_token"])[0].pk == owner.pk
    assert authenticated("test-dashboard-token").status_code == 401
    assert post(dashboard(owner), "/api/mcp/connections", {"connectionId": str(connection.pk)}).json() == {"revoked": True}
    assert authenticated(tokens["access_token"]).status_code == 401
    assert refresh(values, tokens["refresh_token"]).status_code == 400


def test_denial_expiry_and_duplicate_consent_never_create_grant(db, account_client):
    _, handle = begin()
    denied = post(account_client, "/api/mcp/authorize", {"request": handle, "decision": "deny"})
    assert parse_qs(urlsplit(denied.json()["redirectUrl"]).query)["error"] == ["access_denied"]
    assert post(account_client, "/api/mcp/authorize", {"request": handle, "decision": "approve"}).status_code == 400
    _, handle = begin()
    MCPAuthorizationRequest.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert account_client.get("/api/mcp/authorize", {"request": handle}).status_code == 400
    assert MCPConnection.objects.count() == 0


def test_expired_code_and_access_and_refresh_are_rejected(approved):
    _, values, code = approved
    MCPAuthorizationRequest.objects.update(code_expires_at=timezone.now() - timedelta(seconds=1))
    assert exchange(values, code).status_code == 400
    MCPAuthorizationRequest.objects.update(code_expires_at=timezone.now() + timedelta(seconds=30))
    tokens = exchange(values, code).json()
    MCPAccessToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    MCPRefreshToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert authenticated(tokens["access_token"]).status_code == 401
    assert refresh(values, tokens["refresh_token"]).status_code == 400


@pytest.mark.parametrize("changes", [{"redirect_uri": "https://evil.example/callback"}, {"code_challenge_method": "plain"}, {"resource": "https://other.example/mcp"}, {"scope": "administrator"}, {"client_id": "https://169.254.169.254/client.json"}])
def test_invalid_authorize_is_not_an_open_redirect_and_does_not_fetch(changes, db):
    client_id = register()
    values = {"client_id": client_id, "redirect_uri": CALLBACK, "response_type": "code", "resource": RESOURCE,
              "scope": "leadzen:read leadzen:write", "code_challenge": pkce_challenge(VERIFIER), "code_challenge_method": "S256", **changes}
    with patch("requests.get") as network:
        response = Client().get("/mcp/oauth/authorize", values)
    assert response.status_code == 400
    assert "Location" not in response
    assert MCPAuthorizationRequest.objects.count() == 0
    network.assert_not_called()


def test_loopback_redirect_only_and_public_http_not_allowed_except_disposable_override(db, monkeypatch):
    assert register(callback="http://127.0.0.1:9813/callback")
    monkeypatch.setenv("LEADZEN_MCP_PUBLIC_URL", "http://127.0.0.1:8000/mcp")
    monkeypatch.setenv("LEADZEN_PUBLIC_URL", "http://localhost:3001")
    assert Client().get("/.well-known/oauth-authorization-server").status_code == 503
    with override_settings(LEADZEN_MCP_ALLOW_LOCAL=True):
        assert Client().get("/.well-known/oauth-authorization-server").status_code == 200


def test_registration_is_bounded_before_writes(db):
    for _ in range(20):
        register()
    response = post(Client(), "/mcp/oauth/register", {"redirect_uris": [CALLBACK]})
    assert response.status_code == 429 and MCPClient.objects.count() == 20


def test_malformed_internal_requests_are_safe(db, account_client):
    for value in ("not-uuid", [], {"id": "wrong"}):
        response = post(account_client, "/api/mcp/connections", {"connectionId": value})
        assert response.status_code == 404
    _, handle = begin()
    assert post(account_client, "/api/mcp/authorize", {"request": handle, "decision": []}).status_code == 400
