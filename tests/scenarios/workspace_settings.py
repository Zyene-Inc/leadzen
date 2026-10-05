"""Private settings and real consistent SQLite backups for two employees."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import django
django.setup()

from django.core.management import call_command
from django.db import connections
from django.test import Client
from django.utils import timezone
from cold_outreach.leads.models import Deal, Lead
from openoutfind.crm.models import Lead as FoundLead
from leadzen.accounts.service import create_account, login
from leadzen.config.models import SiteConfig
from leadzen.workspaces import database_path, initialize_workspace, workspace_scope

call_command("migrate", verbosity=0, interactive=False)
os.environ["LEADZEN_DASHBOARD_TOKEN"] = "synthetic-settings-token"
clients, users = [], []
schedules = [
    {"timezone": "America/New_York", "days": [0, 2, 4], "start": "09:15", "end": "17:45"},
    {"timezone": "America/New_York", "days": [1, 3, 5], "start": "10:30", "end": "18:00"},
]
for index in range(2):
    user = create_account(email=f"settings-{index}@example.com", name=f"Employee {index}", password="Synthetic-settings-9413!", require_change=False)
    profile = user.leadzen_profile
    profile.onboarding_completed_at = timezone.now()
    profile.save()
    initialize_workspace(profile)
    _, token, _ = login(user.email, "Synthetic-settings-9413!")
    users.append(user)
    clients.append(Client(HTTP_AUTHORIZATION="Bearer synthetic-settings-token", HTTP_X_LEADZEN_SESSION=token))
    with workspace_scope(profile) as alias:
        # Keep the workspace connection open so new records live in the WAL.
        # A raw copy of the main file would miss them; the SQLite backup must not.
        with connections[alias].cursor() as cursor:
            assert cursor.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        config = SiteConfig.load()
        config.operator_name, config.operator_country_code = f"Private operator {index}", "US" if index == 0 else "IN"
        config.save()
        lead = Lead.objects.create(lead_id="same-source", email=f"private-{index}@example.com")
        Deal.objects.create(lead=lead)
        FoundLead.objects.create(profile_url=f"https://example.com/private-{index}", full_name=f"Private finder {index}")
        assert Path(str(database_path(profile)) + "-wal").stat().st_size > 0

with patch("leadzen.setup_wizard.probe_ai") as ai, patch("leadzen.setup_wizard.probe_discovery") as finder, patch("leadzen.setup_wizard.probe_mailbox") as mail:
    for index, client in enumerate(clients):
        invalid = client.put("/api/settings", data=json.dumps({
            "workspace_updates": {"sending_schedule": {**schedules[index], "timezone": "Asia/Kolkata"}},
        }), content_type="application/json")
        assert invalid.status_code == 400 and "New York" in invalid.json()["error"]
        response = client.put("/api/settings", data=json.dumps({
            "workspace_id": users[1-index].pk,
            "workspace_updates": {"sending_schedule": schedules[index]},
        }), content_type="application/json")
        assert response.status_code == 200, response.content
        assert response.json()["workspace"]["sending_schedule"] == schedules[index]
    for index, client in enumerate(clients):
        data = client.get(f"/api/settings?workspace_id={users[1-index].pk}").json()["workspace"]
        assert data["identity"]["operator_name"] == f"Private operator {index}"
        assert data["sending_schedule"] == schedules[index]
        assert data["data"]["path"] == str(database_path(users[index].leadzen_profile))
        response = client.post("/api/settings/backup", data=json.dumps({"confirmed": True, "workspace_id": users[1-index].pk, "path": str(database_path(users[1-index].leadzen_profile))}), content_type="application/json")
        assert response.status_code == 200 and response["Content-Type"] == "application/vnd.sqlite3"
        assert response["Cache-Control"] == "no-store" and "attachment" in response["Content-Disposition"]
        content = b"".join(response.streaming_content)
        response.close()
        assert content.startswith(b"SQLite format 3\x00")
        assert content[18:20] == b"\x01\x01"  # Single-file rollback format, no WAL sidecars.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "copy.sqlite3"
            path.write_bytes(content)
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as copy:
                assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
                assert copy.execute("PRAGMA journal_mode").fetchone() == ("delete",)
                assert copy.execute(f'SELECT operator_name FROM "{SiteConfig._meta.db_table}"').fetchone() == (f"Private operator {index}",)
                assert json.loads(copy.execute(f'SELECT sending_schedule FROM "{SiteConfig._meta.db_table}"').fetchone()[0]) == schedules[index]
                assert copy.execute(f'SELECT email FROM "{Lead._meta.db_table}"').fetchone() == (f"private-{index}@example.com",)
                assert copy.execute(f'SELECT full_name FROM "{FoundLead._meta.db_table}"').fetchone() == (f"Private finder {index}",)
                assert copy.execute("SELECT COUNT(*) FROM leadzen_accounts_loginsession").fetchone() == (0,)
    ai.assert_not_called(); finder.assert_not_called(); mail.assert_not_called()
print("Settings and SQLite backup isolation verified")
