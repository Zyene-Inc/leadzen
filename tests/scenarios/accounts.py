"""Synthetic integration data only; no external provider or mail calls."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from datetime import timedelta
from django.utils import timezone
from unittest.mock import patch

import django
from cryptography.fernet import Fernet

django.setup()
from django.core.management import call_command
from django.db import connections
from django.test import Client
from cold_outreach.emails.models import Mailbox, Message
from cold_outreach.leads.models import Deal, Lead, Suppression
from leadzen.accounts.service import create_account, login
from leadzen.accounts.models import AccountProfile
from leadzen.config.models import SiteConfig, RuntimeSettings, OutreachJob, ChatRun, ChatThread, ChatMessage
from leadzen.workspaces import workspace_scope, worker_environment, assert_worker_access, guard_worker_sends

call_command("migrate", verbosity=0, interactive=False)
os.environ["LEADZEN_DASHBOARD_TOKEN"] = "synthetic-service-token"
os.environ["LEADZEN_SETTINGS_KEY"] = Fernet.generate_key().decode()
password = "Synthetic-user-fixture-3487!"
users = [create_account(email=f"employee{i}@example.com", name=f"Employee {i}", password=password, require_change=False) for i in (1, 2)]
clients = []
for index, user in enumerate(users):
    _, token, _ = login(user.email, password)
    client = Client(HTTP_AUTHORIZATION="Bearer synthetic-service-token", HTTP_X_LEADZEN_SESSION=token)
    clients.append(client)
    setup = {"purpose": "zyene_reviews" if index == 0 else "zyene_services", "workspace_name": f"Private {index}", "product_docs": f"Private product {index}", "campaign_target": f"Private audience {index}", "operator_country_code": "US", "accepted_legal_notice": True,
             "llm": {"provider": "groq", "model": "openai/gpt-oss-120b", "api_key": f"synthetic-ai-secret-{index}"},
             "lead_finder": {"provider": "bettercontact", "api_key": f"synthetic-finder-secret-{index}"},
             "mailbox": {"address": f"sender{index}@example.com", "smtp_host": "smtp.zoho.com", "smtp_port": 587, "imap_host": "imap.zoho.com", "imap_port": 993, "password": f"synthetic-mail-secret-{index}"}}
    with patch("smtplib.SMTP") as smtp:
        response = client.put("/api/onboarding", data=json.dumps(setup), content_type="application/json")
        assert response.status_code == 200, response.content
        smtp.assert_not_called()
    user.refresh_from_db()
    with workspace_scope(user.leadzen_profile):
        lead = Lead.objects.create(lead_id=f"lead-{index}", first_name=f"PrivatePerson{index}", email=f"lead{index}@example.com")
        Deal.objects.create(lead=lead)
        from openoutfind.crm.models import Lead as FoundLead, Deal as FoundDeal
        for ordinal in range(index + 1):
            found = FoundLead.objects.create(full_name=f"Private discovery {index}/{ordinal}")
            FoundDeal.objects.create(lead=found, reason=f"Private qualification {index}")
        OutreachJob.objects.create(requested_count=1, status=OutreachJob.Status.RUNNING)
        Message.objects.create(mailbox=Mailbox.objects.get(), direction="in", kind="human_reply", message_id=f"private-inbox-{index}", from_address=f"private-reply-{index}@example.com", subject=f"Private inbox {index}", body_text=f"Private message body {index}")
        Suppression.objects.create(email=f"private-stop-{index}@example.com", reason=f"Private suppression {index}")
        assert SiteConfig.load().product_docs == f"Private product {index}"
        assert f"synthetic-ai-secret-{index}" not in RuntimeSettings.load().encrypted_secrets
        from leadzen.configuration import effective
        assert effective().bettercontact_api_key == f"synthetic-finder-secret-{index}"
        assert f"synthetic-finder-secret-{index}" not in RuntimeSettings.load().encrypted_secrets
        assert SiteConfig.load().bettercontact_api_key == ""
        assert f"synthetic-mail-secret-{index}" not in Mailbox.objects.get().password

# Tour progress belongs to the control account while the request is routed through
# a real private workspace. A supplied employee/workspace ID cannot cross accounts.
initial_tour = {"tourStarted": False, "currentStep": "welcome", "tourCompleted": False, "tourSkipped": False}
for client in clients:
    assert client.get("/api/tour").json() == {"tour": initial_tour}
tour_response = clients[0].post("/api/tour", data='{"action":"start","currentStep":"leads"}', content_type="application/json")
assert tour_response.status_code == 200, tour_response.content
assert clients[1].get(f"/api/tour?workspace_id={users[0].leadzen_profile.pk}").json() == {"tour": initial_tour}
assert clients[1].post("/api/tour", data='{"action":"skip"}', content_type="application/json").status_code == 200
assert clients[0].get("/api/tour").json()["tour"]["currentStep"] == "leads"
assert not clients[0].get("/api/tour").json()["tour"]["tourSkipped"]
assert clients[0].post("/api/tour", data='{"action":"progress","currentStep":"outreach"}', content_type="application/json").status_code == 200
assert clients[0].get("/api/auth/me").json()["user"]["tour"]["currentStep"] == "outreach"

for index, client in enumerate(clients):
    assert client.get("/api/overview").json()["leads"]["total"] == 1
    home = client.get("/api/overview?workspace_id=" + str(users[1 - index].leadzen_profile.pk)).json()["home"]
    assert home["metrics"]["found"] == index + 1
    assert home["metrics"]["qualified"] == index + 1
    assert all(row["reason"] == f"Private qualification {index}" for row in home["recent_activity"])
    assert home["target"]["summary"] == f"Private audience {index}"
    assert client.get("/api/target?workspace_id=" + str(users[1 - index].leadzen_profile.pk)).json()["summary"] == f"Private audience {index}"
    rows = client.get("/api/leads?workspace_id=" + str(users[1 - index].leadzen_profile.pk)).json()["items"]
    assert len(rows) == 1 and rows[0]["first_name"] == f"PrivatePerson{index}"
    for route, field, expected in [("inbox", "body", f"Private message body {index}"), ("suppression", "email", f"private-stop-{index}@example.com")]:
        result = client.get(f"/api/{route}?workspace_id={users[1 - index].leadzen_profile.pk}")
        assert result.status_code == 200, result.content
        assert result.json()["total"] == 1
        assert result.json()["items"][0][field] == expected
        assert "synthetic-mail-secret" not in json.dumps(result.json())
    setup = client.get("/api/onboarding").json()
    assert setup["product_docs"] == f"Private product {index}"
    assert setup["connections"]["mailbox"]["address"] == f"sender{index}@example.com"
    assert setup["connections"]["lead_finder"]["api_key_configured"] is True
    assert "synthetic-mail-secret" not in json.dumps(setup)
    assert "synthetic-finder-secret" not in json.dumps(setup)
    with workspace_scope(users[index].leadzen_profile):
        from leadzen.configuration import apply_dashboard_overrides
        apply_dashboard_overrides()
        assert os.environ["OPENOUTFIND_BETTERCONTACT_API_KEY"] == f"synthetic-finder-secret-{index}"
    assert "OPENOUTFIND_BETTERCONTACT_API_KEY" not in worker_environment(users[index].leadzen_profile)
    with patch("leadzen.web.subprocess.Popen") as spawn:
        response = client.post("/api/jobs/send", data='{"count": 1}', content_type="application/json")
        assert response.status_code == 409
        spawn.assert_not_called()

# Discovery previews and starts are also bound to the authenticated private file.
for index, client in enumerate(clients):
    current = client.get(f"/api/discovery?workspace_id={users[1 - index].leadzen_profile.pk}").json()
    assert current["target"] == f"Private audience {index}" and current["ready"]
    body = {"count": 3, "emails": False, "estimated_credits": 0, "request_id": str(uuid.uuid4()), "revision": current["revision"], "workspace_id": str(users[1 - index].leadzen_profile.pk)}
    with patch("leadzen.chat.views.launch") as launch:
        response = client.post("/api/discovery", data=json.dumps(body), content_type="application/json")
        assert response.status_code == 202, response.content
        assert str(launch.call_args.args[1].actor_id) == str(users[index].pk)
    other = clients[1 - index]
    discovery_id = response.json()["run"]["id"]
    with patch("leadzen.discovery.effective") as credentials, patch("leadzen.chat.views.launch") as forbidden_launch:
        assert other.get(f"/api/discovery/{discovery_id}?workspace_id={users[index].leadzen_profile.pk}").status_code == 404
        for action in ["pause", "resume", "stop", "emails"]:
            assert other.post(f"/api/discovery/{discovery_id}/{action}", data="{}", content_type="application/json").status_code == 404
        credentials.assert_not_called()
        forbidden_launch.assert_not_called()
    own_progress = client.get(f"/api/discovery/{discovery_id}").json()
    assert own_progress["target"] == f"Private audience {index}" and own_progress["credits"]["used"] == 0
    assert other.get(f"/api/chat/threads/{response.json()['thread_id']}").status_code == 404
    assert other.post(f"/api/chat/runs/{response.json()['run']['id']}/cancel", data="{}", content_type="application/json").status_code == 404
    with workspace_scope(users[index].leadzen_profile):
        row = ChatRun.objects.get(pk=response.json()["run"]["id"])
        assert row.credits_reserved == 0 and row.pending["arguments"]["count"] == 3
        from leadzen.discovery_progress import Monitor
        from leadzen.config.models import DiscoverySession
        from openoutfind.crm.models import Lead as FoundLead, Deal as FoundDeal
        source = FoundLead.objects.create(full_name=f"Private live profile {index}", profile_url=f"https://example.com/private-live/{index}")
        FoundDeal.objects.create(lead=source, state="Qualified", reason=f"Private live reason {index}")
        monitor = Monitor(DiscoverySession.objects.get(run=row))
        monitor.discovered([source])
        monitor.verdict(source)
        monitor.output({"lead_id": source.pk})
    assert client.get(f"/api/discovery/{discovery_id}").json()["leads"][0]["reason"] == f"Private live reason {index}"
    contact_id = client.get(f"/api/discovery/{discovery_id}").json()["leads"][0]["contact_id"]
    own_detail = client.get(f"/api/contacts/{contact_id}?workspace_id={users[1-index].leadzen_profile.pk}")
    assert own_detail.status_code == 200, own_detail.content
    assert own_detail.json()["name"] == f"Private live profile {index}"
    assert own_detail.json()["reason"] == f"Private live reason {index}"
    assert client.get("/api/leads?stage=qualified").json()["items"][0]["name"] == f"Private live profile {index}"
    assert other.get(f"/api/discovery/{discovery_id}").status_code == 404
    assert client.post(f"/api/chat/runs/{response.json()['run']['id']}/cancel", data="{}", content_type="application/json").status_code == 200
    # Remove this disposable contact from the later sending fixtures; its recorded
    # discovery history remains durable, but a deleted contact cannot be enriched.
    live_contact = client.get(f"/api/discovery/{discovery_id}").json()["leads"][0]["contact_id"]
    assert client.delete(f"/api/contacts/{live_contact}").status_code == 200
    assert client.put(f"/api/chat/threads/{response.json()['thread_id']}", data='{"archived":true}', content_type="application/json").status_code == 200

# Saved email drafts/conversations are scoped to actual private databases, not
# a submitted workspace ID. No model, credentials or send may resolve foreign IDs.
from leadzen.config.models import EmailReview, ReviewedEmail
from cold_outreach.emails.models import Thread
with workspace_scope(users[0].leadzen_profile):
    own_deal = Deal.objects.get(lead__email="lead0@example.com")
    saved = EmailReview.objects.create(actor_id=users[0].pk, request_id=uuid.uuid4(), kind="initial", status="draft", from_address="sender0@example.com", requested_count=1, context_hash="synthetic-private-context")
    saved_draft = ReviewedEmail.objects.create(review=saved, deal=own_deal, subject="Private reviewed subject", body="Private reviewed content zero")
    conversation_thread = Thread.objects.create(mailbox=Mailbox.objects.first())
    Message.objects.create(mailbox=conversation_thread.mailbox, thread=conversation_thread, direction="in", kind="human_reply", message_id="private-thread-review-zero", from_address=own_deal.lead.email, subject="Private conversation zero", body_text="Private threaded message zero")
own_result = clients[0].get(f"/api/outreach/reviews/{saved.pk}?workspace_id={users[1].leadzen_profile.pk}")
assert own_result.status_code == 200 and own_result.json()["drafts"][0]["body"] == "Private reviewed content zero"
assert clients[0].get(f"/api/inbox/conversations/{conversation_thread.pk}").json()["messages"][0]["body"] == "Private threaded message zero"
with patch("leadzen.outreach.effective") as foreign_keys, patch("leadzen.outreach.generate") as foreign_model, patch("leadzen.web._launch_job") as foreign_send:
    assert clients[1].get(f"/api/outreach/reviews/{saved.pk}?workspace_id={users[0].leadzen_profile.pk}").status_code == 404
    assert clients[1].post(f"/api/outreach/reviews/{saved.pk}/drafts/{saved_draft.pk}", data='{"action":"approve"}', content_type="application/json").status_code == 404
    assert clients[1].delete(f"/api/outreach/reviews/{saved.pk}").status_code == 404
    assert clients[1].get(f"/api/inbox/conversations/{conversation_thread.pk}?workspace_id={users[0].leadzen_profile.pk}").status_code == 404
    assert clients[1].post("/api/outreach/reviews", data=json.dumps({"thread_id": conversation_thread.pk, "count": 1, "request_id": str(uuid.uuid4())}), content_type="application/json").status_code == 404
    foreign_keys.assert_not_called()
    foreign_model.assert_not_called()
    foreign_send.assert_not_called()

# Unified attention and restored inbox approvals still route by authenticated employee.
attention_zero = clients[0].get(f"/api/attention?workspace_id={users[1].leadzen_profile.pk}")
attention_one = clients[1].get(f"/api/attention?workspace_id={users[0].leadzen_profile.pk}")
assert attention_zero.status_code == attention_one.status_code == 200
assert any(item["id"] == f"review-{saved.pk}" for item in attention_zero.json()["items"])
assert not any(item["id"] == f"review-{saved.pk}" for item in attention_one.json()["items"])
with workspace_scope(users[0].leadzen_profile):
    pending_thread = ChatThread.objects.create(actor_id=users[0].pk, title="Private inbox approval")
    ChatMessage.objects.create(thread=pending_thread, role="user", content="Check replies", data={"workspace_action": "check_replies"})
    pending_check = ChatRun.objects.create(actor_id=users[0].pk, thread=pending_thread, request_id=uuid.uuid4(), status="awaiting_approval", pending={"id": "private-approval", "tool": "sync_mailbox", "summary": "Private mailbox", "credits": 0, "emails": 0, "preview": {}}, approval_expires_at=timezone.now() + timedelta(minutes=5))
assert clients[0].get("/api/inbox/check").json()["check"]["run"]["id"] == str(pending_check.pk)
assert clients[1].get(f"/api/inbox/check?workspace_id={users[0].leadzen_profile.pk}").json() == {"check": None}
with workspace_scope(users[0].leadzen_profile):
    ChatRun.objects.filter(pk=pending_check.pk).update(status="cancelled")

# Autopilot authorization and history live in those same private workspace files.
from leadzen.config.models import AutopilotPolicy, AutopilotRun
first_setup = clients[0].get("/api/autopilot").json()["setup"]
authorization_id = str(uuid.uuid4())
authorization = {"enabled": True, "authorize_automatic_outreach": True,
    "request_id": authorization_id, "revision": first_setup["revision"], "timezone": "America/New_York",
    "workspace_id": str(users[1].leadzen_profile.pk)}
result = clients[0].post("/api/autopilot", data=json.dumps(authorization), content_type="application/json")
assert result.status_code == 200, result.content
assert result.json()["policy"]["scope"]["target"] == "Private audience 0"
assert clients[1].get(f"/api/autopilot?workspace_id={users[0].leadzen_profile.pk}").json()["policy"] is None
with workspace_scope(users[0].leadzen_profile):
    policy = AutopilotPolicy.objects.get()
    AutopilotRun.objects.create(policy=policy, actor_id=users[0].pk, workday=timezone.now().date(), phase="needs_attention", issue="Private run issue")
assert not clients[1].get("/api/autopilot").json()["runs"]
assert clients[1].post("/api/autopilot", data=json.dumps({"enabled": False, "workspace_id": str(users[0].leadzen_profile.pk)}), content_type="application/json").status_code == 200
assert clients[0].get("/api/autopilot").json()["policy"]["enabled"]
assert clients[0].post("/api/autopilot", data='{"enabled":false}', content_type="application/json").status_code == 200
assert not clients[0].get("/api/autopilot").json()["policy"]["enabled"]
# Actual module bootstrap in an isolated synthetic workspace with no enabled policy.
# No provider work is possible; this catches imports before django.setup().
worker_env = worker_environment(users[0].leadzen_profile)
worker_env.update(LEADZEN_AUTOPILOT_ENABLED="1", LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED="0")
worker = subprocess.run([sys.executable, "-m", "leadzen.autopilot_worker"], env=worker_env, capture_output=True, text=True, timeout=30)
assert worker.returncode == 0, worker.stderr[-2000:]

# Settings switch must not overwrite another employee or erase old mailbox history.
audience_update = {"audience": {"industry": "Private updated industry", "country": "US", "company_size": "any", "roles": ["Owner"], "seniority": ["owner"], "instructions": "Only this workspace"}, "confirmed": True, "accepted_legal_notice": True, "workspace_id": str(users[1].leadzen_profile.pk)}
assert clients[0].put("/api/target", data=json.dumps(audience_update), content_type="application/json").status_code == 200
assert clients[1].get("/api/target").json()["summary"] == "Private audience 1"
assert clients[0].get("/api/overview").json()["home"]["target"]["audience"]["industry"] == "Private updated industry"

response = clients[0].put("/api/settings", data=json.dumps({"llm": {"provider": "groq", "model": "openai/gpt-oss-120b"}, "mailbox": {"address": "changed@example.com", "smtp_host": "smtp.zoho.com", "smtp_port": 587, "imap_host": "imap.zoho.com", "imap_port": 993, "password": "synthetic-new-mail-secret"}}), content_type="application/json")
assert response.status_code == 200, response.content
assert clients[1].get("/api/settings").json()["mailbox"]["address"] == "sender1@example.com"
assert clients[0].get("/api/settings").json()["lead_finder"]["api_key_configured"] is True
with workspace_scope(users[1].leadzen_profile):
    assert effective().bettercontact_api_key == "synthetic-finder-secret-1"
assert clients[0].get("/api/overview").json()["mailboxes"][0]["address"] == "changed@example.com"
with workspace_scope(users[0].leadzen_profile):
    assert Mailbox.objects.count() == 2

# A caller-supplied workspace cannot redirect a credential update to a coworker.
settings_body = clients[0].get("/api/settings").json()
settings_body["workspace_id"] = str(users[1].leadzen_profile.pk)
settings_body["lead_finder"] = {"provider": "bettercontact", "api_key": "synthetic-replacement-finder"}
assert clients[0].put("/api/settings", data=json.dumps(settings_body), content_type="application/json").status_code == 200
with workspace_scope(users[0].leadzen_profile):
    assert effective().bettercontact_api_key == "synthetic-replacement-finder"
with workspace_scope(users[1].leadzen_profile):
    assert effective().bettercontact_api_key == "synthetic-finder-secret-1"

# Revocation is checked again at transport time, including retries after a wait.
# Provider selection and encrypted keys stay in the authenticated employee's file.
for index, client in enumerate(clients):
    response = client.put("/api/settings", data=json.dumps({"workspace_id": str(users[1 - index].leadzen_profile.pk),
        "lead_finder": {"provider": "ai_ark", "api_key": f"fixtureArkToken{index}"}}), content_type="application/json")
    assert response.status_code == 200, response.content
    assert f"fixtureArkToken{index}" not in response.content.decode()
for index, user in enumerate(users):
    with workspace_scope(user.leadzen_profile):
        assert effective().lead_finder_provider == "ai_ark"
        assert effective().ai_ark_api_key == f"fixtureArkToken{index}"
        assert f"fixtureArkToken{index}" not in RuntimeSettings.load().encrypted_secrets
assert clients[0].put("/api/settings", data=json.dumps({"lead_finder": {"provider": "ai_ark", "clear_api_key": True}}), content_type="application/json").status_code == 200
provider_reset = json.dumps({"lead_finder": {"provider": "bettercontact"}})
for client in clients:
    response = client.put("/api/settings", data=provider_reset, content_type="application/json")
    assert response.status_code == 200, response.content

# Setup drafts and receipts also belong to the authenticated employee's file.
for index, client in enumerate(clients):
    result = client.get("/api/onboarding/wizard?workspace_id=" + str(users[1 - index].leadzen_profile.pk))
    assert result.status_code == 200, result.content
    assert result.json()["draft"]["product_docs"] == f"Private product {index}"
    assert not result.json()["checks"]["ai"]["connected"]
with patch("leadzen.setup_wizard.probe_ai", return_value={"answered": True}) as probe:
    result = clients[0].post("/api/onboarding/test", data=json.dumps({"kind": "ai", "workspace_id": str(users[1].leadzen_profile.pk), "llm": {"enabled": True, "provider": "groq", "model": "openai/gpt-oss-120b"}}), content_type="application/json")
    assert result.status_code == 200, result.content
    assert probe.call_args.args[0].llm_api_key == "synthetic-ai-secret-0"
assert clients[0].get("/api/onboarding/wizard").json()["checks"]["ai"]["connected"]
assert not clients[1].get("/api/onboarding/wizard").json()["checks"]["ai"]["connected"]
assert clients[0].put("/api/onboarding/wizard", data='{"step":1,"values":{}}', content_type="application/json").status_code == 200
assert clients[1].get("/api/onboarding/wizard").json()["completed_steps"] == []

# A contact ID from another private file cannot redirect a delete. Use an ID
# absent from the caller's file (IDs may overlap between employee databases).
created = clients[1].post("/api/contacts", data='{"email":"foreign-delete@example.com"}', content_type="application/json")
assert created.status_code == 201, created.content
foreign_contact = created.json()["ids"][0]
with patch("leadzen.discovery.effective") as foreign_keys, patch("leadzen.chat.views.launch") as foreign_lookup:
    for suffix in ("", "/email"):
        assert clients[0].get(f"/api/contacts/{foreign_contact}{suffix}?workspace_id={users[1].leadzen_profile.pk}").status_code == 404
    assert clients[0].post(f"/api/contacts/{foreign_contact}/email", data="{}", content_type="application/json").status_code == 404
    foreign_keys.assert_not_called()
    foreign_lookup.assert_not_called()
assert clients[0].delete(f"/api/contacts/{foreign_contact}?workspace_id={users[1].leadzen_profile.pk}").status_code == 404
anonymous = Client(HTTP_AUTHORIZATION="Bearer synthetic-service-token")
for route in ("inbox", "suppression"):
    assert anonymous.get(f"/api/{route}").status_code == 401
assert anonymous.delete(f"/api/contacts/{foreign_contact}").status_code == 401
assert clients[1].get("/api/leads").json()["total"] == 2
with workspace_scope(users[1].leadzen_profile):
    from leadzen.config.models import ContactPreferences
    assert ContactPreferences.objects.get(lead__email="foreign-delete@example.com").deleted_at is None
assert clients[1].delete(f"/api/contacts/{foreign_contact}").status_code == 200
assert clients[1].get("/api/leads").json()["total"] == 1

# Chat uses those same private files and checks ownership before retrieving keys.
chat_thread = clients[0].post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]
assert clients[1].get(f"/api/chat/threads/{chat_thread}").status_code == 404
with patch("leadzen.chat.views.launch") as launch:
    reply = clients[0].post(f"/api/chat/threads/{chat_thread}/messages", data=json.dumps({"content": "Check my workspace", "request_id": str(uuid.uuid4()), "workspace_id": str(users[1].leadzen_profile.pk)}), content_type="application/json")
    assert reply.status_code == 202, reply.content
    run_id = reply.json()["run"]["id"]
    assert launch.call_count == 1
assert clients[1].get(f"/api/chat/runs/{run_id}").status_code == 404
worker_script = str(Path(__file__).with_name("chat_worker.py"))
worker = subprocess.run([sys.executable, worker_script, run_id], env=worker_environment(users[0].leadzen_profile), capture_output=True, text=True, timeout=30)
assert worker.returncode == 0, worker.stderr[-2000:]
detail = clients[0].get(f"/api/chat/threads/{chat_thread}").json()
assert detail["run"]["status"] == "succeeded"
assert detail["messages"][1]["data"]["result"]["leads"] == 1
assert "PrivatePerson1" not in json.dumps(detail)
assert not clients[1].get("/api/chat/threads").json()["items"]
# Queue before revocation; the child must recheck live access, not trust enqueue.
with patch("leadzen.chat.views.launch"):
    denied = clients[0].post(f"/api/chat/threads/{chat_thread}/messages", data=json.dumps({"content": "Check again", "request_id": str(uuid.uuid4())}), content_type="application/json")
    denied_run = denied.json()["run"]["id"]
from cold_outreach.emails import sender
env = worker_environment(users[0].leadzen_profile)
os.environ.update({key: env[key] for key in ("LEADZEN_CONTROL_DB", "LEADZEN_ACTOR_ID", "LEADZEN_WORKSPACE_ID")})
assert_worker_access()
with patch.object(sender, "_deliver") as deliver:
    guard_worker_sends()
    sender._deliver(None, None, None)
    assert deliver.call_count == 1
    users[0].is_active = False
    users[0].save(using="default", update_fields=["is_active"])
    try:
        sender._deliver(None, None, None)
        raise AssertionError("Revoked worker reached transport")
    except PermissionError:
        pass
    assert deliver.call_count == 1
assert clients[0].get("/api/leads").status_code == 401
assert clients[0].get("/api/settings").status_code == 401
assert clients[0].delete("/api/contacts/1").status_code == 401
with patch("leadzen.setup_wizard.probe_ai") as denied_probe:
    assert clients[0].post("/api/onboarding/test", data='{"kind":"ai"}', content_type="application/json").status_code == 401
    denied_probe.assert_not_called()
worker = subprocess.run([sys.executable, worker_script, denied_run], env=worker_environment(users[0].leadzen_profile), capture_output=True, text=True, timeout=30)
assert worker.returncode == 0, worker.stderr[-2000:]
with workspace_scope(users[0].leadzen_profile):
    assert ChatRun.objects.get(pk=denied_run).status == "failed"
connections.close_all()
print("isolation and revocation verified")
