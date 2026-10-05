"""Synthetic protocol and external-sink boundaries; no provider calls."""
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from leadzen.mcp import transport
from leadzen.mcp.guard import connection_execution

pytestmark = pytest.mark.django_db


@pytest.fixture
def rpc(monkeypatch):
    monkeypatch.setenv("LEADZEN_MCP_PUBLIC_URL", "https://api.example.com/mcp")
    monkeypatch.setenv("LEADZEN_PUBLIC_URL", "https://leadzen.example.com")
    actor = SimpleNamespace(pk=1, leadzen_profile=object())
    connection = SimpleNamespace(pk="synthetic-connection")
    monkeypatch.setattr(transport, "authenticate_mcp", lambda request: (actor, connection))
    monkeypatch.setattr(transport, "workspace_scope", lambda profile: nullcontext())
    monkeypatch.setattr("leadzen.mcp.auth.connection_live", lambda *args: connection)
    monkeypatch.setattr(transport, "throttle", lambda *args, **kwargs: True)

    def invoke(method="ping", params=None, *, raw=None, **headers):
        request = RequestFactory().post("/mcp", raw if raw is not None else json.dumps({"jsonrpc": "2.0", "id": 7, "method": method, "params": params or {}}), content_type="application/json", HTTP_ACCEPT="application/json, text/event-stream", **headers)
        return transport.endpoint(request)
    return invoke


def test_protocol_negotiation_stateless_and_no_sensitive_cache(rpc):
    response = rpc("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "Synthetic client", "version": "1"}, "capabilities": {}})
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["result"]["protocolVersion"] == "2025-06-18"
    assert body["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert "America/New_York" in body["result"]["instructions"]
    assert response["Cache-Control"] == "no-store"
    assert not response.has_header("MCP-Session-Id")


def test_unsupported_version_origin_and_method_fail_before_tool(rpc):
    assert rpc(HTTP_MCP_PROTOCOL_VERSION="unsupported").status_code == 400
    assert rpc(HTTP_ORIGIN="https://foreign.example").status_code == 403
    assert json.loads(rpc("unknown/method").content)["error"]["code"] == -32601
    assert rpc(HTTP_ORIGIN="https://claude.ai").status_code == 200
    assert rpc(HTTP_ORIGIN="https://claude.ai/anything").status_code == 403


@pytest.mark.parametrize("raw", ["{", "[]", "null", '{"jsonrpc":"2.0","id":true,"method":"ping"}', '{"jsonrpc":"2.0","id":null,"method":"ping"}', '{"jsonrpc":"1.0","id":1,"method":"ping"}', '{"nested":' + "[" * 10000 + "0" + "]" * 10000 + "}"])
def test_invalid_rpc_never_exposes_internal_errors(rpc, raw):
    response = rpc(raw=raw)
    assert response.status_code == 400
    assert "error" in json.loads(response.content)


def test_notifications_and_get_do_not_execute(rpc):
    response = rpc(raw='{"jsonrpc":"2.0","method":"notifications/initialized"}')
    assert response.status_code == 202 and response.content == b""
    response = transport.endpoint(RequestFactory().get("/mcp"))
    assert response.status_code == 405 and response["Allow"] == "POST"


def test_body_type_size_accept_and_rate_bounds(rpc, monkeypatch):
    assert rpc(raw="x" * 65537).status_code == 413
    req = RequestFactory().post("/mcp", "{}", content_type="application/json", HTTP_ACCEPT="application/json")
    assert transport.endpoint(req).status_code == 406
    req = RequestFactory().post("/mcp", "{}", content_type="text/plain", HTTP_ACCEPT="application/json, text/event-stream")
    assert transport.endpoint(req).status_code == 415
    monkeypatch.setattr(transport, "throttle", lambda *args, **kwargs: False)
    assert rpc().status_code == 429


def test_revocation_rechecked_at_transport_sink(monkeypatch):
    from leadzen.transports import delivery_guard
    checks = []
    def live(*identity):
        checks.append(identity)
        if len(checks) > 1:
            raise PermissionError("Disconnected")
    monkeypatch.setattr("leadzen.mcp.auth.connection_live", live)
    with connection_execution("owned-connection", 1):
        with pytest.raises(PermissionError, match="Disconnected"):
            delivery_guard()
    assert checks == [("owned-connection", 1), ("owned-connection", 1)]
    delivery_guard()  # Guard does not spill into a different employee/request.


def test_public_endpoint_requires_independent_oauth_not_dashboard_secret(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-dashboard-token")
    response = transport.endpoint(RequestFactory().post("/mcp", "{}", content_type="application/json", HTTP_AUTHORIZATION="Bearer synthetic-dashboard-token"))
    assert response.status_code == 401
    assert "Bearer" in response["WWW-Authenticate"]


def test_real_tool_registry_is_discoverable_and_cannot_select_private_handlers(rpc):
    result = json.loads(rpc("tools/list").content)["result"]
    tools = {tool["name"]: tool for tool in result["tools"]}
    assert len(tools) == 40
    assert tools["get_settings"]["annotations"]["readOnlyHint"]
    assert tools["send_email"]["inputSchema"]["additionalProperties"] is False
    assert "approvalToken" not in tools["send_email"]["inputSchema"]["properties"]
    assert "requestId" in tools["send_email"]["inputSchema"]["required"]
    with patch("leadzen.mcp.tools._execute_local") as handler:
        result = json.loads(rpc("tools/call", {"name": "admin_users", "arguments": {}}).content)["result"]
    assert result["isError"] and "Unknown employee capability" in result["content"][0]["text"]
    handler.assert_not_called()


def test_tool_success_and_unexpected_error_are_protocol_results(rpc):
    with patch("leadzen.mcp.tools.call_tool", return_value={"items": [], "total": 0}) as capability:
        response = rpc("tools/call", {"name": "list_leads", "arguments": {}})
    result = json.loads(response.content)["result"]
    assert result["structuredContent"] == {"items": [], "total": 0}
    assert result["isError"] is False
    capability.assert_called_once()
    with patch("leadzen.mcp.tools.call_tool", side_effect=RuntimeError("synthetic-private-provider-token")):
        response = rpc("tools/call", {"name": "list_leads", "arguments": {}})
    result = json.loads(response.content)["result"]
    assert result["isError"] and "synthetic-private" not in response.content.decode()


def test_large_tool_results_and_ambiguous_arguments_are_bounded(rpc):
    with patch("leadzen.mcp.tools.call_tool", return_value={"body": "x" * 129000}):
        result = json.loads(rpc("tools/call", {"name": "get_lead", "arguments": {"leadId": 1}}).content)["result"]
    assert result["isError"] and "too large" in result["content"][0]["text"]
    with patch("leadzen.mcp.tools.call_tool") as capability:
        response = rpc("tools/call", {"name": "get_lead", "arguments": [], "url": "https://foreign.example"})
    assert json.loads(response.content)["error"]["code"] == -32602
    capability.assert_not_called()
