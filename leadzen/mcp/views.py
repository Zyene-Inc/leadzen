"""Remote OAuth endpoints and authenticated employee connection management."""
from __future__ import annotations

import hmac
import json
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from leadzen.accounts.service import access, audit, payload
from leadzen.mcp.auth import (
    CHALLENGE, CODE_SECONDS, CONNECTION_SECONDS, OPAQUE, REQUEST_SECONDS, SCOPES, VERIFIER,
    account_is_live, configuration, connection_live, digest, issue_tokens, oauth_error,
    oauth_response, opaque, pkce_challenge, secure_url, throttle,
)
from leadzen.mcp.models import MCPAccessToken, MCPAuthorizationRequest, MCPClient, MCPConnection, MCPRefreshToken


def _ready():
    try:
        return configuration()
    except ValueError:
        return None


def _parameters(request):
    if len(request.body) > 16384 or len(request.META.get("QUERY_STRING", "")) > 8192:
        raise ValueError("Request is too large")
    values = request.GET if request.method == "GET" else request.POST
    if request.method != "GET" and request.content_type != "application/x-www-form-urlencoded":
        raise ValueError("Use application/x-www-form-urlencoded")
    if any(len(values.getlist(key)) != 1 for key in values):
        raise ValueError("Repeated OAuth parameters are not supported")
    return values


def _scopes(value):
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError("Invalid scope")
    scopes = list(dict.fromkeys(value.split()))
    if not scopes:
        scopes = list(SCOPES[:2])
    if any(scope not in SCOPES for scope in scopes) or not set(SCOPES[:2]).issubset(scopes):
        raise ValueError("Choose leadzen:read and leadzen:write for your workspace")
    return scopes


def _redirect(pending, values):
    parsed = urlsplit(pending.redirect_uri)
    # Remove security-sensitive duplicate keys already present in a registered
    # callback so the response has exactly one code/error/state/issuer parameter.
    pairs = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if key not in {"code", "state", "error", "error_description", "iss"}]
    pairs.extend(values.items())
    if pending.state:
        pairs.append(("state", pending.state))
    pairs.append(("iss", configuration()[1]))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), ""))


@require_http_methods(["GET"])
def resource_metadata(request):
    ready = _ready()
    if ready is None:
        return oauth_error("temporarily_unavailable", "The public MCP endpoint is not configured.", 503)
    resource, issuer, _ = ready
    return oauth_response({"resource": resource, "resource_name": "LeadZen by Zyene",
                           "authorization_servers": [issuer], "bearer_methods_supported": ["header"],
                           "scopes_supported": list(SCOPES)})


@require_http_methods(["GET"])
def authorization_metadata(request):
    ready = _ready()
    if ready is None:
        return oauth_error("temporarily_unavailable", "The public MCP endpoint is not configured.", 503)
    _, issuer, _ = ready
    return oauth_response({"issuer": issuer,
                           "authorization_endpoint": issuer + "/mcp/oauth/authorize",
                           "token_endpoint": issuer + "/mcp/oauth/token",
                           "registration_endpoint": issuer + "/mcp/oauth/register",
                           "revocation_endpoint": issuer + "/mcp/oauth/revoke",
                           "response_types_supported": ["code"],
                           "grant_types_supported": ["authorization_code", "refresh_token"],
                           "token_endpoint_auth_methods_supported": ["none"],
                           "revocation_endpoint_auth_methods_supported": ["none"],
                           "code_challenge_methods_supported": ["S256"],
                           "scopes_supported": list(SCOPES),
                           "client_id_metadata_document_supported": False,
                           "authorization_response_iss_parameter_supported": True})


@csrf_exempt
@require_http_methods(["POST"])
def register_client(request):
    if _ready() is None:
        return oauth_error("temporarily_unavailable", "The public MCP endpoint is not configured.", 503)
    if not throttle(request, "register", limit=20, seconds=600):
        return oauth_error("temporarily_unavailable", "Too many registrations. Try again later.", 429)
    try:
        if request.content_type != "application/json":
            raise ValueError("Use application/json")
        body = payload(request)
        uris = body.get("redirect_uris")
        name = body.get("client_name", "MCP client")
        if not isinstance(name, str) or not name.strip() or len(name) > 160 or any(ord(char) < 32 for char in name):
            raise ValueError("A short client name is required")
        if not isinstance(uris, list) or not 1 <= len(uris) <= 5 or len(set(uris)) != len(uris):
            raise ValueError("Register one to five redirect URLs")
        redirects = [secure_url(uri, callback=True) for uri in uris]
        # Exact original URLs are persisted and compared; canonical validation
        # never silently substitutes a different callback at consent or exchange.
        if any(uri != canonical for uri, canonical in zip(uris, redirects)):
            raise ValueError("Use canonical lowercase HTTPS redirect URLs")
        if body.get("token_endpoint_auth_method", "none") != "none":
            raise ValueError("Only public clients using PKCE are supported")
        if body.get("response_types", ["code"]) != ["code"]:
            raise ValueError("Only authorization code responses are supported")
        grants = body.get("grant_types", ["authorization_code", "refresh_token"])
        if not isinstance(grants, list) or "authorization_code" not in grants or any(item not in {"authorization_code", "refresh_token"} for item in grants):
            raise ValueError("Unsupported grant type")
        if "scope" in body:
            _scopes(body["scope"])
        with transaction.atomic(using="default"):
            if MCPClient.objects.using("default").count() >= 5000:
                return oauth_error("temporarily_unavailable", "Registration capacity reached.", 503)
            client = MCPClient.objects.using("default").create(id=opaque(), name=name.strip(), redirect_uris=uris)
        return oauth_response({"client_id": client.pk, "client_name": client.name, "redirect_uris": uris,
                               "token_endpoint_auth_method": "none", "response_types": ["code"],
                               "grant_types": ["authorization_code", "refresh_token"],
                               "client_id_issued_at": int(client.created_at.timestamp())}, 201)
    except (ValueError, TypeError, json.JSONDecodeError):
        return oauth_error("invalid_client_metadata", "Register valid HTTPS callbacks and a public PKCE client.")


@require_http_methods(["GET"])
def authorize(request):
    ready = _ready()
    if ready is None:
        return oauth_error("temporarily_unavailable", "The public MCP endpoint is not configured.", 503)
    if not throttle(request, "authorize", limit=30, seconds=60):
        return oauth_error("temporarily_unavailable", "Too many requests. Try again later.", 429)
    resource, _, dashboard = ready
    try:
        values = _parameters(request)
        client = MCPClient.objects.using("default").filter(pk=values.get("client_id", "")).first()
        redirect = values.get("redirect_uri", "")
        if client is None or redirect not in client.redirect_uris:
            raise ValueError("Unregistered client or callback")
        if values.get("response_type") != "code" or values.get("code_challenge_method") != "S256" or not CHALLENGE.fullmatch(values.get("code_challenge", "")):
            raise ValueError("Authorization code with S256 PKCE is required")
        if values.get("resource") != resource:
            return oauth_error("invalid_target", "Use the configured MCP resource URL.")
        scopes = _scopes(values.get("scope", ""))
        state = values.get("state", "")
        if len(state) > 2000:
            raise ValueError("State is too long")
        now = timezone.now()
        handle = opaque()
        with transaction.atomic(using="default"):
            # A consumed authorization request remains the connection's consent
            # and replay record. Removing it while its grant is live hides the
            # client from Settings and disables proven-code replay revocation.
            MCPAuthorizationRequest.objects.using("default").filter(expires_at__lte=now - timedelta(days=1)).filter(
                Q(connection__isnull=True) | Q(connection__revoked_at__isnull=False) | Q(connection__expires_at__lte=now),
            ).delete()
            if MCPAuthorizationRequest.objects.using("default").filter(expires_at__gt=now).count() >= 5000:
                return oauth_error("temporarily_unavailable", "Try connecting again later.", 503)
            MCPAuthorizationRequest.objects.using("default").create(
                request_hash=digest(handle), client=client, redirect_uri=redirect, resource=resource, scopes=scopes,
                code_challenge=values["code_challenge"], state=state, expires_at=now + timedelta(seconds=REQUEST_SECONDS),
            )
        response = HttpResponseRedirect(dashboard + "/mcp/connect?" + urlencode({"request": handle}))
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response
    except (ValueError, TypeError):
        # Never redirect an invalid authorization request to an untrusted URI.
        return oauth_error("invalid_request", "Use a registered callback, the LeadZen resource and S256 PKCE.")


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def consent(request):
    ready = _ready()
    if ready is None:
        return oauth_response({"error": "The public MCP endpoint is not configured."}, 503)
    body = payload(request) if request.method == "POST" else request.GET
    handle = body.get("request", "")
    if not isinstance(handle, str) or not OPAQUE.fullmatch(handle):
        return oauth_response({"error": "This connection request is invalid or expired."}, 400)
    now = timezone.now()
    with transaction.atomic(using="default"):
        pending = MCPAuthorizationRequest.objects.using("default").select_for_update().select_related("client").filter(
            request_hash=digest(handle), expires_at__gt=now, decided_at__isnull=True, resource=ready[0],
        ).first()
        if pending is None or pending.redirect_uri not in pending.client.redirect_uris:
            return oauth_response({"error": "This connection request is invalid or expired."}, 400)
        if request.method == "GET":
            return oauth_response({"request": handle, "clientName": pending.client.name,
                                   "redirectHost": urlsplit(pending.redirect_uri).netloc,
                                   "scopes": pending.scopes, "expiresAt": pending.expires_at.isoformat()})
        decision = body.get("decision")
        if not isinstance(decision, str) or decision not in {"approve", "deny"}:
            return oauth_response({"error": "Choose whether to connect this client."}, 400)
        pending.decided_at = now
        if decision == "deny":
            pending.save(using="default", update_fields=["decided_at"])
            return oauth_response({"redirectUrl": _redirect(pending, {"error": "access_denied"})})
        if not account_is_live(request.actor):
            return oauth_response({"error": "Your account cannot connect this workspace."}, 403)
        # Consent alone is not a connected client. Abandoned exchanges neither
        # appear as connected nor permanently exhaust the employee's grant cap.
        MCPConnection.objects.using("default").filter(
            user=request.actor, revoked_at__isnull=True,
            mcpauthorizationrequest__consumed_at__isnull=True,
            mcpauthorizationrequest__code_expires_at__lte=now,
        ).update(revoked_at=now)
        if MCPConnection.objects.using("default").filter(user=request.actor, revoked_at__isnull=True, expires_at__gt=now).count() >= 20:
            return oauth_response({"error": "Disconnect an unused client before adding another."}, 409)
        connection = MCPConnection.objects.using("default").create(
            user=request.actor, client=pending.client, resource=pending.resource, scopes=pending.scopes,
            password_fingerprint=digest(request.actor.password), expires_at=now + timedelta(seconds=CONNECTION_SECONDS),
        )
        code = opaque()
        pending.connection, pending.code_hash = connection, digest(code)
        pending.code_expires_at = now + timedelta(seconds=CODE_SECONDS)
        pending.save(using="default", update_fields=["connection", "code_hash", "code_expires_at", "decided_at"])
        audit(request.actor, "mcp_connected", request.actor.pk)
        return oauth_response({"redirectUrl": _redirect(pending, {"code": code})})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def connections(request):
    now = timezone.now()
    if request.method == "POST":
        body = payload(request)
        identifier = body.get("connectionId")
        try:
            connection = MCPConnection.objects.using("default").filter(pk=identifier, user=request.actor).first()
        except (ValueError, TypeError, ValidationError):
            connection = None
        if connection is None:
            return oauth_response({"error": "Connection not found."}, 404)
        MCPConnection.objects.using("default").filter(pk=connection.pk, user=request.actor).update(revoked_at=now)
        audit(request.actor, "mcp_disconnected", request.actor.pk)
        return oauth_response({"revoked": True})
    ready = _ready()
    items = MCPConnection.objects.using("default").select_related("client").filter(
        user=request.actor, revoked_at__isnull=True, expires_at__gt=now,
        mcpauthorizationrequest__consumed_at__isnull=False,
    ).distinct().order_by("-created_at")[:20]
    return oauth_response({"endpoint": ready[0] if ready else None, "available": ready is not None,
                           "reason": None if ready else "A public HTTPS MCP endpoint is required before connecting.",
                           "connections": [{"id": str(item.pk), "clientName": item.client.name,
                                            "createdAt": item.created_at.isoformat(),
                                            "lastUsedAt": item.last_used_at.isoformat() if item.last_used_at else None}
                                           for item in items]})


@csrf_exempt
@require_http_methods(["POST"])
def token(request):
    ready = _ready()
    if ready is None:
        return oauth_error("temporarily_unavailable", "The public MCP endpoint is not configured.", 503)
    if not throttle(request, "token", limit=60, seconds=60):
        return oauth_error("temporarily_unavailable", "Too many token requests. Try again later.", 429)
    try:
        values = _parameters(request)
        if values.get("resource") != ready[0]:
            return oauth_error("invalid_target", "Use the configured MCP resource URL.")
        client_id = values.get("client_id", "")
        if "client_secret" in values or request.headers.get("Authorization"):
            return oauth_error("invalid_client", "Use a public PKCE client.")
        now = timezone.now()
        with transaction.atomic(using="default"):
            if values.get("grant_type") == "authorization_code":
                code, verifier = values.get("code", ""), values.get("code_verifier", "")
                if not OPAQUE.fullmatch(code) or not VERIFIER.fullmatch(verifier):
                    return oauth_error("invalid_grant", "The authorization code or proof is invalid.")
                grant = MCPAuthorizationRequest.objects.using("default").select_for_update().filter(code_hash=digest(code)).first()
                if grant is None or grant.client_id != client_id or grant.resource != ready[0] or grant.redirect_uri != values.get("redirect_uri") or not hmac.compare_digest(grant.code_challenge, pkce_challenge(verifier)):
                    return oauth_error("invalid_grant", "The authorization code or proof is invalid.")
                if grant.consumed_at is not None:
                    MCPConnection.objects.using("default").filter(pk=grant.connection_id).update(revoked_at=now)
                    return oauth_error("invalid_grant", "This authorization code has already been used.")
                if grant.code_expires_at is None or grant.code_expires_at <= now:
                    return oauth_error("invalid_grant", "The authorization code expired. Connect again.")
                connection = connection_live(grant.connection_id)
                grant.consumed_at = now
                grant.save(using="default", update_fields=["consumed_at"])
            elif values.get("grant_type") == "refresh_token":
                refresh = values.get("refresh_token", "")
                if not OPAQUE.fullmatch(refresh):
                    return oauth_error("invalid_grant", "Invalid refresh token.")
                grant = MCPRefreshToken.objects.using("default").select_for_update().select_related("connection").filter(token_hash=digest(refresh)).first()
                if grant is None or grant.connection.client_id != client_id or grant.connection.resource != ready[0]:
                    return oauth_error("invalid_grant", "Invalid refresh token.")
                if grant.consumed_at is not None:
                    MCPConnection.objects.using("default").filter(pk=grant.connection_id).update(revoked_at=now)
                    return oauth_error("invalid_grant", "Refresh token replay detected. Connect again.")
                if grant.expires_at <= now:
                    return oauth_error("invalid_grant", "Refresh token expired. Connect again.")
                connection = connection_live(grant.connection_id)
                if values.get("scope") and set(_scopes(values["scope"])) != set(connection.scopes):
                    return oauth_error("invalid_scope", "Reconnect to change the granted scopes.")
                grant.consumed_at = now
                grant.save(using="default", update_fields=["consumed_at"])
            else:
                return oauth_error("unsupported_grant_type", "Use authorization_code or refresh_token.")
            return oauth_response(issue_tokens(connection))
    except PermissionError:
        return oauth_error("invalid_grant", "This connection no longer has workspace access.")
    except (ValueError, TypeError):
        return oauth_error("invalid_request", "Use valid form-encoded OAuth parameters.")


@csrf_exempt
@require_http_methods(["POST"])
def revoke(request):
    if _ready() is None:
        return oauth_error("temporarily_unavailable", "The public MCP endpoint is not configured.", 503)
    if not throttle(request, "revoke", limit=60, seconds=60):
        return oauth_error("temporarily_unavailable", "Too many requests. Try again later.", 429)
    try:
        values = _parameters(request)
        supplied = values.get("token", "")
        if not OPAQUE.fullmatch(supplied):
            return oauth_response({})
        with transaction.atomic(using="default"):
            connection_ids = set(MCPAccessToken.objects.using("default").filter(token_hash=digest(supplied)).values_list("connection_id", flat=True))
            connection_ids.update(MCPRefreshToken.objects.using("default").filter(token_hash=digest(supplied)).values_list("connection_id", flat=True))
            MCPConnection.objects.using("default").filter(pk__in=connection_ids, client_id=values.get("client_id", "")).update(revoked_at=timezone.now())
        return oauth_response({})
    except (ValueError, TypeError):
        return oauth_error("invalid_request", "Use form-encoded OAuth parameters.")
