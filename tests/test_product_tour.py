"""The guided tour is account-owned progress, never authority for domain actions."""
import json
from contextlib import nullcontext
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.test import Client
from django.utils import timezone

from leadzen.accounts.models import AccountProfile, LoginSession
from leadzen.accounts.service import create_account, login


INITIAL = {"tourStarted": False, "currentStep": "welcome", "tourCompleted": False, "tourSkipped": False}


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")


def post(client, body):
    return client.post("/api/tour", data=json.dumps(body), content_type="application/json")


def test_tour_start_progress_refresh_back_finish_and_restart(account_client):
    assert account_client.get("/api/tour").json() == {"tour": INITIAL}
    started = post(account_client, {"action": "start"})
    assert started.status_code == 200
    assert started.json()["tour"] == {**INITIAL, "tourStarted": True}
    profile = AccountProfile.objects.get()
    started_at = profile.tour_started_at
    for step in ("leads", "add-contact", "leads", "ready"):
        result = post(account_client, {"action": "progress", "currentStep": step})
        assert result.status_code == 200
        assert account_client.get("/api/tour").json()["tour"]["currentStep"] == step
        account = account_client.get("/api/auth/me").json()["user"]
        assert account["tour"]["currentStep"] == step and account["tour_started"]
        assert not account["tour_completed"] and not account["tour_skipped"]
    profile.refresh_from_db()
    assert profile.tour_started_at == started_at
    finished = post(account_client, {"action": "complete", "currentStep": "ready"})
    assert finished.json()["tour"] == {"tourStarted": True, "currentStep": "ready", "tourCompleted": True, "tourSkipped": False}
    assert account_client.get("/api/auth/me").json()["user"]["tour_completed"]
    restarted = post(account_client, {"action": "start", "currentStep": "welcome"})
    assert restarted.json()["tour"] == {**INITIAL, "tourStarted": True}
    profile.refresh_from_db()
    assert profile.tour_started_at >= started_at and profile.tour_completed_at is None


def test_skip_is_distinct_from_complete_and_stale_progress_cannot_restart(account_client):
    assert post(account_client, {"action": "progress", "currentStep": "leads"}).status_code == 409
    skipped = post(account_client, {"action": "skip", "currentStep": "leads"})
    assert skipped.status_code == 200
    assert skipped.json()["tour"] == {"tourStarted": True, "currentStep": "leads", "tourCompleted": False, "tourSkipped": True}
    account = account_client.get("/api/auth/me").json()["user"]
    assert account["tour_skipped"] and not account["tour_completed"]
    assert post(account_client, {"action": "progress", "currentStep": "ready"}).status_code == 409
    assert account_client.get("/api/tour").json()["tour"] == skipped.json()["tour"]
    restarted = post(account_client, {"action": "start"})
    assert restarted.json()["tour"] == {**INITIAL, "tourStarted": True}
    assert post(account_client, {"action": "complete"}).status_code == 200
    assert post(account_client, {"action": "progress", "currentStep": "leads"}).status_code == 409


def test_legacy_empty_post_completes_and_old_completed_accounts_stay_terminal(account_client):
    response = account_client.post("/api/tour", data="", content_type="application/json")
    assert response.status_code == 200 and response.json()["ok"]
    assert response.json()["tour"]["tourCompleted"]
    AccountProfile.objects.update(tour_started_at=None)
    account = account_client.get("/api/auth/me").json()["user"]
    assert account["tour_started"] and account["tour_completed"]
    assert account_client.get("/api/tour").json()["tour"]["tourStarted"]


def test_migration_preserves_completed_tours_without_starting_new_accounts(account_client):
    completed_at = timezone.now()
    profile = AccountProfile.objects.get()
    AccountProfile.objects.filter(pk=profile.pk).update(tour_completed_at=completed_at)
    other = create_account(email="new-tour@example.com", name="New synthetic employee", password="Synthetic-new-tour-8194!", require_change=False)
    migration = import_module("leadzen.accounts.migrations.0004_accountprofile_tour_state")
    migration.preserve_completed_tours(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
    profile.refresh_from_db()
    other.leadzen_profile.refresh_from_db()
    assert profile.tour_completed_at == profile.tour_started_at == completed_at
    assert profile.tour_skipped_at is None
    assert other.leadzen_profile.tour_started_at is None and other.leadzen_profile.tour_completed_at is None


@pytest.mark.parametrize("body", [
    {"action": "unknown"}, {"action": None}, {"action": []}, {"action": {}},
    {"currentStep": "welcome"}, {"action": "progress"},
    {"action": "start", "currentStep": True}, {"action": "start", "currentStep": 2},
    {"action": "start", "currentStep": []}, {"action": "start", "currentStep": {}},
    {"action": "start", "currentStep": ""}, {"action": "start", "currentStep": "a" * 65},
    {"action": "start", "currentStep": "Welcome"}, {"action": "start", "currentStep": "/settings"},
    {"action": "start", "currentStep": "é"}, {"action": "start", "currentStep": "a\n"},
    {"action": "start", "actor_id": 2}, {"tourCompleted": True},
])
def test_invalid_tour_state_does_not_persist(account_client, body):
    assert post(account_client, body).status_code == 400
    assert account_client.get("/api/tour").json() == {"tour": INITIAL}


def test_request_size_and_non_objects_are_rejected_without_state_change(account_client):
    for body in ('[]', '"welcome"', 'null', '{bad', json.dumps({"action": "start", "currentStep": "a" * 65536})):
        response = account_client.post("/api/tour", data=body, content_type="application/json")
        assert response.status_code == 400
    assert account_client.get("/api/tour").json() == {"tour": INITIAL}
    assert account_client.put("/api/tour", data="{}", content_type="application/json").status_code == 405


def test_actor_is_server_owned_and_revocation_setup_checks_are_retained(account_client, monkeypatch):
    password = "Synthetic-tour-account-9263!"
    other = create_account(email="tour-other@example.com", name="Other synthetic employee", password=password, require_change=False)
    other.leadzen_profile.onboarding_completed_at = timezone.now()
    other.leadzen_profile.save()
    _, token, _ = login(other.email, password)
    other_client = Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token", HTTP_X_LEADZEN_SESSION=token)
    monkeypatch.setattr("leadzen.workspaces.workspace_scope", lambda profile: nullcontext("default"))
    own_profile = AccountProfile.objects.exclude(user=other).get()
    assert post(account_client, {"action": "start", "currentStep": "leads"}).status_code == 200
    assert other_client.get(f"/api/tour?actor_id={own_profile.user_id}&workspace_id={own_profile.pk}").json() == {"tour": INITIAL}
    assert post(other_client, {"action": "skip"}).status_code == 200
    own_profile.refresh_from_db()
    assert own_profile.tour_current_step == "leads" and own_profile.tour_skipped_at is None
    for unauthorized in (Client(), Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token")):
        assert unauthorized.get("/api/tour").status_code == 401
        assert post(unauthorized, {"action": "start"}).status_code == 401
    LoginSession.objects.filter(user=other).delete()
    assert other_client.get("/api/tour").status_code == 401
    _, token, _ = login(other.email, password)
    other_client = Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token", HTTP_X_LEADZEN_SESSION=token)
    AccountProfile.objects.filter(user=other).update(must_change_password=True)
    assert post(other_client, {"action": "start"}).json()["redirect"] == "/password"
    AccountProfile.objects.filter(user=other).update(must_change_password=False, onboarding_completed_at=None)
    assert post(other_client, {"action": "start"}).json()["redirect"] == "/onboarding"
