"""Fixtures for existing serialization/pacing unit tests.

Those tests use one in-memory DB deliberately. Real per-employee SQLite routing is
covered without mocks in test_accounts_integration.py and its scenario process.
"""
from contextlib import nullcontext

import pytest
from cryptography.fernet import Fernet
from django.test import Client
from django.utils import timezone


@pytest.fixture(autouse=True)
def synthetic_settings_key(monkeypatch):
    # The mailbox field adapter persists for the lifetime of a worker process.
    # Every independent test needs a fresh synthetic encryption key, including
    # read-only fixtures executed after a worker test installed that adapter.
    # Missing-key regressions explicitly remove this value in their own test.
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())


@pytest.fixture
def account_client(db, monkeypatch):
    from leadzen.accounts.service import create_account, login
    user = create_account(email="unit@example.com", name="Unit user", password="Unit-fixture-9347!", require_change=False)
    user.leadzen_profile.onboarding_completed_at = timezone.now()
    user.leadzen_profile.save()
    _, token, _ = login(user.email, "Unit-fixture-9347!")
    monkeypatch.setattr("leadzen.workspaces.workspace_scope", lambda profile: nullcontext("default"))
    monkeypatch.setenv("LEADZEN_LLM_HOSTS", "api.example.com")
    monkeypatch.setenv("LEADZEN_MAIL_HOSTS", "smtp.example.com,imap.example.com")
    return Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token", HTTP_X_LEADZEN_SESSION=token)
