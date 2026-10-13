"""Independent jobs run side by side; conflicting ones never overlap."""
import os
import subprocess
import sys
import textwrap
import time
import uuid
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction

from leadzen.lanes import LaneBusy, provider_work

HOLD = textwrap.dedent("""
    import os, sys, time
    from leadzen.lanes import provider_work
    with provider_work(sys.argv[1], wait=0):
        print("held", flush=True)
        time.sleep(float(sys.argv[2]))
""")


def hold(path, seconds, env):
    process = subprocess.Popen([sys.executable, "-c", HOLD, str(path), str(seconds)], stdout=subprocess.PIPE, text=True, env=env)
    assert process.stdout.readline().strip() == "held"
    return process


def test_provider_lane_is_exclusive_per_workspace_across_processes(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADZEN_WORKSPACE_ROOT", str(tmp_path))
    env = {**os.environ, "LEADZEN_WORKSPACE_ROOT": str(tmp_path)}
    workspace = tmp_path / "one" / "db.sqlite3"
    other = hold(workspace, 3, env)
    try:
        with pytest.raises(LaneBusy, match="Another lead search"):
            with provider_work(workspace, wait=0):
                pass
    finally:
        other.wait()
    with provider_work(workspace, wait=0):
        pass  # Released when the other job ends.


def test_server_wide_provider_slots_cap_heavy_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADZEN_WORKSPACE_ROOT", str(tmp_path))
    env = {**os.environ, "LEADZEN_WORKSPACE_ROOT": str(tmp_path)}
    first, second = hold(tmp_path / "a" / "db.sqlite3", 3, env), hold(tmp_path / "b" / "db.sqlite3", 3, env)
    try:
        start = time.monotonic()
        with pytest.raises(LaneBusy, match="server is running other lead searches"):
            with provider_work(tmp_path / "c" / "db.sqlite3", wait=1):
                pass
        assert time.monotonic() - start >= 1
    finally:
        first.wait(); second.wait()


def test_a_failure_inside_the_job_is_not_retried_as_a_busy_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADZEN_WORKSPACE_ROOT", str(tmp_path))
    calls = []
    with pytest.raises(LaneBusy, match="inner"):
        with provider_work(tmp_path / "a" / "db.sqlite3", wait=0):
            calls.append(1)
            raise LaneBusy("inner")
    assert calls == [1]


def test_one_active_run_per_lane_but_lanes_run_together(chat_client):
    from leadzen.config.models import ChatRun, ChatThread
    owner = ChatThread.objects.get(pk=chat_client.post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]).actor_id
    thread = ChatThread.objects.create(actor_id=owner, title="jobs")
    for lane in ("chat", "provider", "inbox"):
        ChatRun.objects.create(thread=thread, actor_id=owner, request_id=uuid.uuid4(), lane=lane, status="running")
    with pytest.raises(IntegrityError), transaction.atomic():
        ChatRun.objects.create(thread=thread, actor_id=owner, request_id=uuid.uuid4(), lane="provider", status="queued")


def test_reply_check_starts_while_a_lead_search_runs(chat_client):
    from leadzen.config.models import ChatRun, ChatThread
    from tests.test_chat import post
    owner = ChatThread.objects.get(pk=chat_client.post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]).actor_id
    ChatRun.objects.create(thread=ChatThread.objects.create(actor_id=owner, title="Find 5 leads"), actor_id=owner, request_id=uuid.uuid4(), lane="provider", status="running", deadline_at=None)
    with patch("leadzen.chat.views.launch"):
        response = post(chat_client, "/api/inbox/check", {"request_id": str(uuid.uuid4())})
    assert response.status_code == 201, response.content
    assert ChatRun.objects.get(pk=response.json()["run"]["id"]).lane == "inbox"
    again = post(chat_client, "/api/inbox/check", {"request_id": str(uuid.uuid4())})
    assert again.status_code == 409 and "already running" in again.json()["error"]


def test_reply_check_does_not_need_ai(chat_client):
    from dataclasses import asdict
    from leadzen.configuration import effective, save_dashboard_settings
    from tests.test_chat import post
    values = asdict(effective()); values["ai_enabled"] = False
    save_dashboard_settings(values, clear_llm_api_key=True)
    with patch("leadzen.chat.views.launch"):
        response = post(chat_client, "/api/inbox/check", {"request_id": str(uuid.uuid4())})
    assert response.status_code == 201, response.content


def test_chat_lead_search_step_reports_a_busy_lane_instead_of_failing(discovery_client):
    from leadzen.chat.engine import Decision, drive
    from tests.test_chat import turn
    chat_client = discovery_client
    thread, run = turn(chat_client, "find 3 leads")
    with patch("leadzen.lanes.provider_work", side_effect=LaneBusy("Another lead search or email lookup is still running.")), \
         patch("leadzen.chat.engine.find_leads") as finder, \
         patch("leadzen.chat.engine.decide", side_effect=[Decision(tool="find_leads", arguments={"count": 3}), Decision(tool="answer", text="A lead search is already running.")]):
        drive(run)
    finder.assert_not_called()
    detail = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert detail["run"]["status"] == "succeeded"
    tool = [m for m in detail["messages"] if m["role"] == "tool"][0]
    assert "still running" in tool["data"]["result"]["error"]


def test_provider_worker_takes_the_provider_lane_not_the_send_lock(chat_client):
    from leadzen.config.models import ChatRun, ChatThread
    from leadzen import chat_worker
    owner = ChatThread.objects.get(pk=chat_client.post("/api/chat/threads", data="{}", content_type="application/json").json()["id"]).actor_id
    row = ChatRun.objects.create(thread=ChatThread.objects.create(actor_id=owner, title="Find"), actor_id=owner, request_id=uuid.uuid4(), lane="provider")
    with patch("leadzen.lanes.provider_work") as provider, patch("leadzen.web_worker._database_lock") as send_lock, patch("leadzen.chat.engine.drive"):
        assert chat_worker.main(str(row.pk)) == 0
    provider.assert_called_once()
    send_lock.assert_not_called()


from tests.test_chat import chat_client  # noqa: E402  (fixture)
from tests.test_discovery import discovery_client  # noqa: E402  (fixture)
