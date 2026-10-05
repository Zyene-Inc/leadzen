"""Readable saved activity and explicitly requested private diagnostics."""
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from leadzen.config.models import ChatRun, ChatThread, DiscoveryCandidate, DiscoveryEvent, DiscoverySession, OutreachJob


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")


def discovery():
    actor = get_user_model().objects.get(email="unit@example.com")
    thread = ChatThread.objects.create(actor_id=actor.pk)
    run = ChatRun.objects.create(thread=thread, actor_id=actor.pk, request_id=uuid.uuid4(), status="succeeded", finished_at=timezone.now())
    return DiscoverySession.objects.create(run=run, goal=3, phase="succeeded")


@pytest.mark.parametrize("path", ["activity", "activity/logs"])
def test_activity_requires_live_employee_session(db, path):
    assert Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token").get(f"/api/{path}").status_code == 401


def test_feed_is_plain_language_without_raw_output_or_provider_access(account_client):
    session = discovery()
    DiscoveryEvent.objects.create(session=session, kind="search_completed", data={"profiles_returned": 100, "raw": "[DEBUG] private diagnostic"})
    qualified = DiscoveryEvent.objects.create(session=session, kind="qualified", data={"name": "Bruce Lish", "source_id": 123})
    rejected = DiscoveryEvent.objects.create(session=session, kind="rejected", data={"name": "Christopher Gomez", "source_id": 124})
    OutreachJob.objects.create(requested_count=3, status="failed", output="[INF] SMTP\n[DEBUG] worker internals")
    with patch("leadzen.web.effective") as credentials, patch("leadzen.chat.engine.decide") as model, patch("leadzen.chat.engine.find_leads") as provider:
        response = account_client.get("/api/activity")
        assert response.status_code == 200
        rows = response.json()["items"]
        assert any(row["title"] == "Discovery started" and row["detail"] == "Goal: 3 leads" for row in rows)
        assert any(row["title"] == "BetterContact search completed" and row["detail"] == "100 profiles returned" for row in rows)
        assert any(row["title"] == "Lead qualified" and row["detail"] == "Bruce Lish" and row["at"] == qualified.created_at.isoformat() for row in rows)
        assert any(row["title"] == "Lead rejected" and row["detail"] == "Christopher Gomez" and row["at"] == rejected.created_at.isoformat() for row in rows)
        assert any(row["title"] == "Outreach failed" for row in rows)
        assert "[DEBUG]" not in str(rows) and "SMTP" not in str(rows)
        assert rows == sorted(rows, key=lambda row: (row["at"], row["id"]), reverse=True)
        credentials.assert_not_called()
        model.assert_not_called()
        provider.assert_not_called()
    assert account_client.post("/api/activity", data="{}", content_type="application/json").status_code == 405


def test_legacy_decisions_remain_visible_without_duplicating_monitored_profiles(account_client):
    from openoutfind.crm.models import Deal, Lead
    lead = Lead.objects.create(full_name="Bruce Lish", profile_url="https://example.com/bruce")
    Deal.objects.create(lead=lead, state="Qualified", reason="Private qualification details")
    session = discovery()
    DiscoveryCandidate.objects.create(session=session, source_id=lead.pk, evaluated=True, outcome="qualified")
    DiscoveryEvent.objects.create(session=session, kind="qualified", data={"name": lead.full_name, "source_id": lead.pk})
    other = Lead.objects.create(full_name="Christopher Gomez", profile_url="https://example.com/chris")
    Deal.objects.create(lead=other, state="Failed", outcome="wrong_fit")
    rows = account_client.get("/api/activity").json()["items"]
    assert len([row for row in rows if row["detail"] == "Bruce Lish"]) == 1
    assert any(row["title"] == "Lead rejected" and row["detail"] == other.full_name for row in rows)


def test_detailed_candidate_progress_does_not_hide_saved_activity_summaries(account_client):
    session = discovery()
    search = DiscoveryEvent.objects.create(session=session, kind="search_completed", data={"profiles_returned": 75})
    qualified = DiscoveryEvent.objects.create(session=session, kind="qualified", data={"name": "Synthetic practice owner"})
    rejected = DiscoveryEvent.objects.create(session=session, kind="rejected", data={"name": "Synthetic trainee"})
    # The live run has finer-grained updates than the Workspace Activity feed.
    DiscoveryEvent.objects.bulk_create([
        DiscoveryEvent(session=session, kind="discovered" if index % 2 else "evaluating", data={"name": f"Synthetic candidate {index}"})
        for index in range(120)
    ])
    rows = account_client.get("/api/activity").json()["items"]
    assert any(row["title"] == "BetterContact search completed" and row["detail"] == "75 profiles returned" and row["at"] == search.created_at.isoformat() for row in rows)
    assert any(row["title"] == "Lead qualified" and row["detail"] == "Synthetic practice owner" and row["at"] == qualified.created_at.isoformat() for row in rows)
    assert any(row["title"] == "Lead rejected" and row["detail"] == "Synthetic trainee" and row["at"] == rejected.created_at.isoformat() for row in rows)
    assert not any(row["detail"].startswith("Synthetic candidate") for row in rows)


def test_mail_events_use_actual_acceptance_and_distinct_reply_kinds(account_client):
    from cold_outreach.emails.models import DeliveryEvent, Mailbox, Message
    box = Mailbox.objects.create(host="smtp.example.com", from_address="sender@example.com")
    sent = Message.objects.create(mailbox=box, direction="out", message_id="accepted", to_address="bruce@example.com")
    event = DeliveryEvent.objects.create(message=sent, status="accepted")
    Message.objects.create(mailbox=box, direction="out", message_id="attempt", to_address="chris@example.com")
    Message.objects.create(mailbox=box, direction="in", kind="human_reply", message_id="reply", from_address="bruce@example.com")
    Message.objects.create(mailbox=box, direction="in", kind="auto_reply", message_id="auto", from_address="chris@example.com")
    rows = account_client.get("/api/activity").json()["items"]
    assert any(row["title"] == "Email accepted by provider" and row["at"] == event.occurred_at.isoformat() for row in rows)
    assert any(row["title"] == "Email attempt recorded" for row in rows)
    assert any(row["title"] == "Reply received" for row in rows)
    assert any(row["title"] == "Automatic reply received" for row in rows)


def test_feed_is_bounded_and_foreign_chat_actor_events_are_omitted(account_client):
    session = discovery()
    for index in range(120):
        DiscoveryEvent.objects.create(session=session, kind="qualified", data={"name": "x" * 1000})
    foreign = ChatThread.objects.create(actor_id=9999)
    run = ChatRun.objects.create(thread=foreign, actor_id=9999, request_id=uuid.uuid4())
    hidden = DiscoverySession.objects.create(run=run, goal=3)
    DiscoveryEvent.objects.create(session=hidden, kind="qualified", data={"name": "Foreign employee"})
    data = account_client.get("/api/activity?workspace_id=9999").json()
    assert len(data["items"]) == 100 and data["limit"] == 100
    assert "Foreign employee" not in str(data)
    assert all(len(row["detail"]) <= 240 for row in data["items"])


def test_developer_logs_are_opt_in_bounded_and_credentials_redacted(account_client, tmp_path, monkeypatch):
    from cold_outreach.emails.models import Mailbox
    Mailbox.objects.create(host="smtp.example.com", from_address="sender@example.com", password="synthetic-mailbox-secret")
    monkeypatch.setattr("leadzen.workspaces.database_path", lambda profile: tmp_path / "db.sqlite3")
    logs = tmp_path / "jobs"
    logs.mkdir()
    job = OutreachJob.objects.create(requested_count=1, output="[INF] Stored worker output")
    (logs / f"{job.pk}.log").write_text("old lines\n" * 2000 + "[DEBUG] SMTP connected\npassword=synthetic-mailbox-secret\nsend: b'AUTH PLAIN c2VjcmV0'\nIMAP ready\n")
    data = account_client.get("/api/activity/logs").json()
    assert len(data["items"]) == 1
    output = data["items"][0]["output"]
    assert "[DEBUG] SMTP connected" in output and "IMAP ready" in output
    assert "synthetic-mailbox-secret" not in output and "c2VjcmV0" not in output
    assert data["items"][0]["truncated"] is True and len(output) <= 16000
    assert str(tmp_path) not in str(data)


def test_developer_logs_refuse_symlink_and_nonregular_files(account_client, tmp_path, monkeypatch):
    import os
    monkeypatch.setattr("leadzen.workspaces.database_path", lambda profile: tmp_path / "db.sqlite3")
    logs = tmp_path / "jobs"
    logs.mkdir()
    secret = tmp_path / "private.txt"
    secret.write_text("foreign private text")
    linked = OutreachJob.objects.create(requested_count=1)
    (logs / f"{linked.pk}.log").symlink_to(secret)
    fifo = OutreachJob.objects.create(requested_count=1)
    os.mkfifo(logs / f"{fifo.pk}.log")
    response = account_client.get("/api/activity/logs")
    assert response.status_code == 200 and "foreign private text" not in response.content.decode()
    assert all(row["unavailable"] for row in response.json()["items"])


@pytest.mark.parametrize("path", ["activity", "activity/logs"])
def test_revoked_session_cannot_read_data_or_credentials(account_client, path):
    from leadzen.accounts.models import LoginSession
    LoginSession.objects.all().delete()
    with patch("leadzen.activity.log_tail") as files, patch("leadzen.configuration.effective") as credentials:
        assert account_client.get(f"/api/{path}").status_code == 401
        files.assert_not_called()
        credentials.assert_not_called()


def test_logs_fail_closed_when_credentials_cannot_be_redacted(account_client):
    from leadzen.configuration import SettingsError
    OutreachJob.objects.create(requested_count=1, output="private output")
    with patch("leadzen.chat.engine.effective", side_effect=SettingsError("Synthetic missing key")):
        response = account_client.get("/api/activity/logs")
    assert response.status_code == 503 and "private output" not in response.content.decode()


def test_real_private_activity_and_log_files_are_isolated(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OUTSEND_", "OPENOUTFIND_", "LEADZEN_"))}
    env.update(LEADZEN_DB=str(tmp_path / "control.sqlite3"), LEADZEN_WORKSPACE_ROOT=str(tmp_path / "workspaces"), PYTHONPATH=str(root), DJANGO_SETTINGS_MODULE="leadzen.settings", LEADZEN_ALLOWED_HOSTS="testserver,localhost,127.0.0.1")
    result = subprocess.run([sys.executable, str(root / "tests/scenarios/activity.py")], cwd=root, env=env, text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr[-6000:]
    assert "Activity and developer log isolation verified" in result.stdout
