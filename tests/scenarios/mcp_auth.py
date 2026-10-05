"""Disposable real databases; no provider calls, passwords or tokens in output."""
import os
import json
import secrets
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import django

django.setup()

from django.core.management import call_command
from django.utils import timezone
from leadzen.accounts.service import create_account
from leadzen.mcp.auth import connection_live, digest
from leadzen.mcp.models import MCPAccessToken, MCPClient, MCPConnection
from leadzen.workspaces import assert_worker_access, initialize_workspace, worker_environment, workspace_scope


if len(sys.argv) > 1:
    connection_id, owner_id, expected = sys.argv[1:]
    # The employee default database contains no grant, even though migrations
    # create these table definitions there for dependency compatibility.
    assert not MCPConnection.objects.using("default").filter(pk=connection_id).exists()
    assert_worker_access()
    if expected == "live":
        assert connection_live(connection_id, owner_id).user_id == int(owner_id)
    else:
        try:
            connection_live(connection_id, owner_id)
        except PermissionError:
            pass
        else:
            raise AssertionError("Revoked or foreign grants reached the worker")
    print("worker control authorization verified")
    raise SystemExit(0)


call_command("migrate", verbosity=0, interactive=False)
os.environ["LEADZEN_MCP_PUBLIC_URL"] = "https://api.synthetic.example/mcp"
os.environ["LEADZEN_PUBLIC_URL"] = "https://dashboard.synthetic.example"
users = [create_account(email=f"mcp-isolation-{index}@example.com", name=f"Employee {index}",
                        password="MCP-isolation-synthetic-9823!", require_change=False) for index in range(2)]
for user in users:
    profile = user.leadzen_profile
    profile.onboarding_completed_at = timezone.now()
    profile.save(using="default")
    initialize_workspace(profile)
    from cold_outreach.leads.models import Lead, Deal, DealState
    with workspace_scope(profile):
        contact = Lead.objects.create(email=f"owned-{user.pk}@example.com", first_name=user.first_name, company=f"Employee {user.pk} company")
        Deal.objects.create(lead=contact, state=DealState.READY)

client = MCPClient.objects.using("default").create(id="synthetic-mcp-client", name="Synthetic client", redirect_uris=["https://client.synthetic.example/callback"])
grant = MCPConnection.objects.using("default").create(user=users[0], client=client, resource=os.environ["LEADZEN_MCP_PUBLIC_URL"],
    scopes=["leadzen:read", "leadzen:write"], password_fingerprint=digest(users[0].password), expires_at=timezone.now() + timedelta(days=1))

for user in users:
    with workspace_scope(user.leadzen_profile):
        assert MCPConnection.objects.get(pk=grant.pk).user_id == users[0].pk
        assert not MCPConnection.objects.using("workspace_" + user.leadzen_profile.id.hex).exists()

# Exercise the actual public MCP transport, including its workspace scope, using
# two independently issued synthetic grants. Database-local lead IDs can overlap;
# each token must still see only the canonical record in its employee database.
from django.test import Client
for user in users:
    own_grant = grant if user == users[0] else MCPConnection.objects.using("default").create(
        user=user, client=client, resource=os.environ["LEADZEN_MCP_PUBLIC_URL"],
        scopes=["leadzen:read", "leadzen:write"], password_fingerprint=digest(user.password),
        expires_at=timezone.now() + timedelta(days=1))
    bearer = secrets.token_urlsafe(48)
    MCPAccessToken.objects.using("default").create(token_hash=digest(bearer), connection=own_grant, expires_at=timezone.now() + timedelta(minutes=15))
    browser = Client(HTTP_AUTHORIZATION="Bearer " + bearer, HTTP_ACCEPT="application/json, text/event-stream", HTTP_MCP_PROTOCOL_VERSION="2025-11-25")
    response = browser.post("/mcp", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_leads", "arguments": {}}}), content_type="application/json")
    assert response.status_code == 200 and response.json()["result"]["isError"] is False, response.content
    saved = response.json()["result"]["structuredContent"]
    assert saved["total"] == 1 and saved["items"][0]["email"] == f"owned-{user.pk}@example.com"
    other = next(person for person in users if person.pk != user.pk)
    assert f"owned-{other.pk}@example.com" not in response.content.decode()

script = str(Path(__file__).resolve())
for owner, expected in [(users[0], "live"), (users[1], "revoked")]:
    result = subprocess.run([sys.executable, script, str(grant.pk), str(owner.pk), expected], env=worker_environment(owner.leadzen_profile), capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr[-3000:]

MCPConnection.objects.using("default").filter(pk=grant.pk).update(revoked_at=timezone.now())
result = subprocess.run([sys.executable, script, str(grant.pk), str(users[0].pk), "revoked"], env=worker_environment(users[0].leadzen_profile), capture_output=True, text=True, timeout=40)
assert result.returncode == 0, result.stderr[-3000:]
print("MCP control database isolation and live worker revocation verified")
