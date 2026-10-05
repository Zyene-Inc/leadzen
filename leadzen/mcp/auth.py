"""Employee-owned OAuth 2.1 grants for remote MCP clients.

Only opaque token hashes persist. The dashboard's existing session authenticates
consent; MCP tokens are independently scoped, rotated and checked against live
account state on every request and before any worker side effect.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from leadzen.accounts.models import LoginThrottle
from leadzen.mcp.models import MCPAccessToken, MCPConnection, MCPRefreshToken

SCOPES = ("leadzen:read", "leadzen:write", "offline_access")
ACCESS_SECONDS = 15 * 60
REFRESH_SECONDS = 30 * 24 * 60 * 60
CONNECTION_SECONDS = 90 * 24 * 60 * 60
REQUEST_SECONDS = 10 * 60
CODE_SECONDS = 90
OPAQUE = re.compile(r"^[A-Za-z0-9_-]{43,160}$")
VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def opaque() -> str:
    return secrets.token_urlsafe(48)


def secure_url(value, *, origin_only=False, callback=False):
    if not isinstance(value, str) or not value or len(value) > 1000 or any(ord(char) < 33 for char in value) or "\\" in value:
        raise ValueError("A valid HTTPS URL is required")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("A valid HTTPS URL is required") from exc
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    # OAuth permits loopback callbacks for desktop clients, but serving this API
    # over HTTP is restricted to deliberately configured disposable local tests.
    allow_http = local and (callback or getattr(settings, "LEADZEN_MCP_ALLOW_LOCAL", False))
    if local and not callback and not getattr(settings, "LEADZEN_MCP_ALLOW_LOCAL", False):
        raise ValueError("Configure a publicly reachable HTTPS URL")
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.scheme not in {"https", "http"} or (parsed.scheme == "http" and not allow_http):
        raise ValueError("A valid HTTPS URL is required")
    if parsed.hostname.endswith(".") or (not local and (parsed.hostname == "localhost" or "." not in parsed.hostname)):
        raise ValueError("A valid HTTPS URL is required")
    if origin_only and (parsed.path not in {"", "/"} or parsed.query):
        raise ValueError("A dashboard origin without a path is required")
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    if port and not (parsed.scheme == "https" and port == 443):
        host += ":" + str(port)
    return urlunsplit((parsed.scheme.lower(), host, "" if origin_only else parsed.path, parsed.query, ""))


def configuration():
    resource = secure_url(os.environ.get("LEADZEN_MCP_PUBLIC_URL", "").strip())
    parsed = urlsplit(resource)
    if parsed.path != "/mcp" or parsed.query:
        raise ValueError("Set the public MCP URL to https://your-api-host/mcp")
    dashboard = secure_url(os.environ.get("LEADZEN_PUBLIC_URL", "").strip(), origin_only=True)
    issuer = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return resource, issuer, dashboard


def oauth_response(value, status=200):
    response = JsonResponse(value, status=status)
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


def oauth_error(code, description, status=400):
    return oauth_response({"error": code, "error_description": description}, status)


def auth_error(description="Connect LeadZen again to continue."):
    response = oauth_error("invalid_token", description, 401)
    try:
        _, issuer, _ = configuration()
        metadata = f'{issuer}/.well-known/oauth-protected-resource/mcp'
        response["WWW-Authenticate"] = f'Bearer resource_metadata="{metadata}", scope="leadzen:read leadzen:write", error="invalid_token"'
    except ValueError:
        response["WWW-Authenticate"] = 'Bearer error="invalid_token"'
    return response


def throttle(request, name, *, limit=60, seconds=60):
    """Bound public registration/token work across web workers without network I/O."""
    address = request.META.get("REMOTE_ADDR", "unknown")
    now = timezone.now()
    keys = [("mcp:" + name + ":global", limit * 4), ("mcp:" + name + ":" + digest(address), limit)]
    with transaction.atomic(using="default"):
        for key, maximum in keys:
            counter, _ = LoginThrottle.objects.using("default").select_for_update().get_or_create(
                key=digest(key), defaults={"window_started_at": now},
            )
            if counter.window_started_at <= now - timedelta(seconds=seconds):
                counter.attempts, counter.window_started_at = 0, now
            if counter.attempts >= maximum:
                return False
            counter.attempts += 1
            counter.save(using="default", update_fields=["attempts", "window_started_at"])
    return True


def account_is_live(user, connection=None):
    try:
        profile = user.leadzen_profile
    except ObjectDoesNotExist:
        return False
    return bool(user.is_active and profile.deleted_at is None and not profile.must_change_password
                and profile.onboarding_completed_at is not None
                and (connection is None or hmac.compare_digest(connection.password_fingerprint, digest(user.password))))


def connection_live(connection_id, actor_id=None):
    # Worker guard first calls assert_worker_access(), which registers the control
    # alias. Never read employee-local copies of auth/account tables in a worker.
    alias = "control" if os.environ.get("LEADZEN_CONTROL_DB") else "default"
    try:
        resource, _, _ = configuration()
        connection = MCPConnection.objects.using(alias).select_related("user__leadzen_profile", "client").filter(
            pk=connection_id, revoked_at__isnull=True, expires_at__gt=timezone.now(), resource=resource,
        ).first()
    except (ValueError, TypeError, ValidationError):
        connection = None
    if connection is None or (actor_id is not None and str(connection.user_id) != str(actor_id)) or not account_is_live(connection.user, connection):
        raise PermissionError("This MCP connection no longer has access to this workspace.")
    if not {"leadzen:read", "leadzen:write"}.issubset(connection.scopes):
        raise PermissionError("This MCP connection does not have the required workspace permissions.")
    return connection


def revoke_actor_connections(actor_id):
    MCPConnection.objects.using("default").filter(user_id=actor_id, revoked_at__isnull=True).update(revoked_at=timezone.now())


def authenticate_mcp(request):
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return auth_error()
    token = authorization[7:]
    if not OPAQUE.fullmatch(token):
        return auth_error()
    access = MCPAccessToken.objects.using("default").filter(token_hash=digest(token), expires_at__gt=timezone.now()).first()
    if access is None:
        return auth_error()
    try:
        connection = connection_live(access.connection_id)
    except PermissionError:
        return auth_error()
    MCPConnection.objects.using("default").filter(pk=connection.pk, revoked_at__isnull=True).update(last_used_at=timezone.now())
    return connection.user, connection


def issue_tokens(connection):
    now = timezone.now()
    token = opaque()
    MCPAccessToken.objects.using("default").filter(expires_at__lte=now).delete()
    MCPAccessToken.objects.using("default").create(
        token_hash=digest(token), connection=connection,
        expires_at=min(now + timedelta(seconds=ACCESS_SECONDS), connection.expires_at),
    )
    result = {"access_token": token, "token_type": "Bearer", "expires_in": min(ACCESS_SECONDS, max(1, int((connection.expires_at - now).total_seconds()))),
              "scope": " ".join(connection.scopes)}
    if "offline_access" in connection.scopes:
        refresh = opaque()
        MCPRefreshToken.objects.using("default").create(
            token_hash=digest(refresh), connection=connection,
            expires_at=min(now + timedelta(seconds=REFRESH_SECONDS), connection.expires_at),
        )
        result["refresh_token"] = refresh
    return result


def pkce_challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
