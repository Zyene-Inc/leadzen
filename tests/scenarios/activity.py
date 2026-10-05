"""Activity and log tails in two real employee databases and directories."""
import os
import uuid
from unittest.mock import patch

import django
django.setup()

from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from leadzen.accounts.service import create_account, login
from leadzen.config.models import ChatRun, ChatThread, DiscoveryEvent, DiscoverySession, OutreachJob
from leadzen.workspaces import database_path, initialize_workspace, workspace_scope

call_command("migrate", verbosity=0, interactive=False)
os.environ["LEADZEN_DASHBOARD_TOKEN"] = "synthetic-activity-token"
clients, users = [], []
job_id, run_id = uuid.uuid4(), uuid.uuid4()
for index in range(2):
    user = create_account(email=f"activity-{index}@example.com", name=f"Employee {index}", password="Synthetic-activity-9413!", require_change=False)
    profile = user.leadzen_profile
    profile.onboarding_completed_at = timezone.now()
    profile.save()
    initialize_workspace(profile)
    _, token, _ = login(user.email, "Synthetic-activity-9413!")
    users.append(user)
    clients.append(Client(HTTP_AUTHORIZATION="Bearer synthetic-activity-token", HTTP_X_LEADZEN_SESSION=token))
    with workspace_scope(profile):
        thread = ChatThread.objects.create(actor_id=user.pk)
        run = ChatRun.objects.create(id=run_id, thread=thread, actor_id=user.pk, request_id=uuid.uuid4())
        session = DiscoverySession.objects.create(run=run, goal=3)
        DiscoveryEvent.objects.create(session=session, kind="qualified", data={"name": f"Private lead {index}"})
        OutreachJob.objects.create(id=job_id, requested_count=1, output=f"Private worker {index}")
    directory = database_path(profile).parent / "jobs"
    directory.mkdir()
    (directory / f"{job_id}.log").write_text(f"[DEBUG] Private protocol log {index}\n")

with patch("leadzen.web.effective") as credentials, patch("leadzen.email_api.post_email") as provider:
    for index, client in enumerate(clients):
        feed = client.get(f"/api/activity?workspace_id={users[1-index].leadzen_profile.pk}").json()
        assert f"Private lead {index}" in str(feed)
        assert f"Private lead {1-index}" not in str(feed)
        assert "Private worker" not in str(feed) and "protocol log" not in str(feed)
    credentials.assert_not_called()
    provider.assert_not_called()
for index, client in enumerate(clients):
    foreign_path = database_path(users[1-index].leadzen_profile).parent / "jobs" / f"{job_id}.log"
    logs = client.get(f"/api/activity/logs?workspace_id={users[1-index].leadzen_profile.pk}&path={foreign_path}").json()
    assert f"Private worker {index}" in str(logs) and f"Private protocol log {index}" in str(logs)
    assert f"Private worker {1-index}" not in str(logs) and f"Private protocol log {1-index}" not in str(logs)
print("Activity and developer log isolation verified")
