"""Read-only workspace destinations require a session and expose bounded data."""
import pytest
from django.test import Client


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")


@pytest.mark.parametrize("path", ["inbox", "suppression"])
def test_workspace_views_require_employee_session(db, path):
    response = Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token").get(f"/api/{path}")
    assert response.status_code == 401


def test_inbox_filters_and_bounds_stored_messages(account_client):
    from cold_outreach.emails.models import Mailbox, Message
    box = Mailbox.objects.create(host="smtp.example.com", from_address="sender@example.com", username="sender@example.com", password="synthetic-secret-never-returned")
    for index, kind in enumerate(["human_reply", "auto_reply", "bounce"]):
        Message.objects.create(mailbox=box, direction="in", kind=kind, message_id=f"in-{index}", from_address="person@example.com", subject=f"Saved {kind}", body_text="Stored message content")
    Message.objects.create(mailbox=box, direction="out", kind="outbound", message_id="out-1", subject="Outbound is not inbox")
    result = account_client.get("/api/inbox?kind=human_reply&limit=1").json()
    assert result["total"] == 1 and result["items"][0]["body"] == "Stored message content"
    assert result["items"][0]["kind"] == "human_reply"
    assert "synthetic-secret" not in str(result)
    assert account_client.get("/api/inbox?limit=1&offset=1").json()["total"] == 3
    assert len(account_client.get("/api/inbox?limit=1&offset=1").json()["items"]) == 1
    assert account_client.get("/api/inbox?limit=bad").status_code == 400
    assert account_client.get("/api/inbox?kind=unknown").status_code == 400
    assert account_client.get("/api/inbox?q=Saved%20bounce").json()["total"] == 1
    assert account_client.post("/api/inbox", data="{}", content_type="application/json").status_code == 405
    assert Message.objects.count() == 4


@pytest.mark.parametrize("path", ["inbox", "suppression"])
@pytest.mark.parametrize("query", ["limit=0", "offset=-1", "offset=999999999999999999999999999999", "q=" + "x" * 201])
def test_workspace_views_reject_invalid_bounds(account_client, path, query):
    assert account_client.get(f"/api/{path}?{query}").status_code == 400


def test_inbox_truncates_large_plain_text_and_clamps_page_size(account_client):
    from cold_outreach.emails.models import Mailbox, Message
    box = Mailbox.objects.create(host="smtp.example.com", from_address="sender@example.com")
    Message.objects.create(mailbox=box, direction="in", message_id="long-inbound", body_text="<script>untrusted</script>" + "x" * 13000)
    row = account_client.get("/api/inbox?limit=99999&kind=").json()
    assert row["limit"] == 100
    assert row["total"] == 1 and row["items"][0]["body_truncated"] is True
    assert len(row["items"][0]["body"]) == 12000


def test_suppression_is_searchable_read_only_and_paginated(account_client):
    from cold_outreach.leads.models import Suppression
    for index in range(3):
        Suppression.objects.create(email=f"stopped-{index}@example.com", reason="Reply stop")
    result = account_client.get("/api/suppression?limit=2&offset=1").json()
    assert result["total"] == 3 and len(result["items"]) == 2
    assert all(row["reason"] == "Reply stop" and row["suppressed_at"] for row in result["items"])
    assert account_client.get("/api/suppression?q=stopped-1").json()["total"] == 1
    assert account_client.get("/api/suppression?offset=-1").status_code == 400
    assert account_client.delete("/api/suppression").status_code == 405
    assert Suppression.objects.count() == 3
