"""Two real private SQLite workspaces; no provider configuration or calls."""
import json
import os
from unittest.mock import patch

import django
django.setup()

from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from cold_outreach.emails.models import DeliveryEvent, Mailbox, Message, Thread
from cold_outreach.leads.models import Deal, Lead, Suppression
from leadzen.accounts.service import create_account, login
from leadzen.config.models import CampaignRecipient, EmailCampaign
from leadzen.workspaces import initialize_workspace, workspace_scope

call_command("migrate", verbosity=0, interactive=False)
os.environ["LEADZEN_DASHBOARD_TOKEN"] = "synthetic-timeline-token"
password = "Synthetic-timeline-9413!"
clients, users, identifiers = [], [], []
for index in range(2):
    user = create_account(email=f"timeline-{index}@example.com", name=f"Employee {index}", password=password, require_change=False)
    profile = user.leadzen_profile
    profile.onboarding_completed_at = timezone.now()
    profile.save()
    initialize_workspace(profile)
    _, token, _ = login(user.email, password)
    users.append(user)
    clients.append(Client(HTTP_AUTHORIZATION="Bearer synthetic-timeline-token", HTTP_X_LEADZEN_SESSION=token))
    with workspace_scope(profile):
        box = Mailbox.objects.create(host="smtp.example.com", from_address=f"sender-{index}@example.com")
        thread = Thread.objects.create(mailbox=box)
        lead = Lead.objects.create(lead_id="same-profile-id", email="same@example.com")
        deal = Deal.objects.create(lead=lead, thread=thread, state="Emailed")
        identifiers.append(deal.pk)
        campaign = EmailCampaign.objects.create(name=f"Private campaign {index}", from_address=box.from_address, status="active",
            steps=[{"subject": "Initial", "body": "Hello", "delay_days": 0}, {"subject": "Follow-up", "body": "Hello", "delay_days": 3}])
        CampaignRecipient.objects.create(campaign=campaign, deal=deal, next_step=1, next_send_at=timezone.now())
        message = Message.objects.create(mailbox=box, thread=thread, direction="out", message_id="same-message-id", subject=f"Private subject {index}")
        DeliveryEvent.objects.create(message=message, status="accepted")

assert identifiers[0] == identifiers[1]  # IDs overlap, so authority must come from the actor.
with patch("leadzen.web.effective") as credentials, patch("leadzen.email_api.post_email") as provider:
    for index, client in enumerate(clients):
        row = client.get(f"/api/contacts/{identifiers[index]}?workspace_id={users[1-index].pk}").json()["timeline"]
        assert row["events"][0]["subject"] == f"Private subject {index}"
        assert row["sequences"][0]["name"] == f"Private campaign {index}"
    result = clients[0].post("/api/suppression", data=json.dumps({"email": "SAME@example.com", "reason": "Manually suppressed", "workspace_id": users[1].pk}), content_type="application/json")
    assert result.status_code == 201
    assert clients[0].get(f"/api/contacts/{identifiers[0]}").json()["timeline"]["blocked_reason"] == "suppressed"
    assert clients[1].get(f"/api/contacts/{identifiers[1]}").json()["timeline"]["can_stop"]
    assert clients[1].get("/api/suppression?q=same@example.com").json()["total"] == 0
    with workspace_scope(users[1].leadzen_profile):
        assert Deal.objects.get(pk=identifiers[1]).state == "Emailed"
        assert CampaignRecipient.objects.get().status == "pending"
        assert not Suppression.objects.exists()
    credentials.assert_not_called()
    provider.assert_not_called()
print("Timeline and suppression isolation verified")
