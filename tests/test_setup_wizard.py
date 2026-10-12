"""Six sequential setup steps, repeated ten times, without live providers."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.test import Client


@pytest.fixture
def wizard(account_client, monkeypatch):
    from leadzen.accounts.models import AccountProfile
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    monkeypatch.setenv("LEADZEN_SETTINGS_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("leadzen.workspaces.initialize_workspace", lambda profile: None)
    AccountProfile.objects.using("default").update(onboarding_completed_at=None)
    return account_client


def call(client, method, path, body):
    return getattr(client, method)("/api/onboarding/" + path, json.dumps(body), content_type="application/json")


def connections():
    return {
        "llm": {"enabled": True, "provider": "groq", "model": "openai/gpt-oss-120b", "base_url": "", "api_key": "synthetic-ai"},
        "lead_finder": {"provider": "bettercontact", "api_key": "synthetic-finder"},
        "mailbox": {"transport": "smtp", "address": "sender@example.com", "smtp_host": "smtppro.zoho.com", "smtp_port": 465, "imap_host": "imappro.zoho.com", "imap_port": 993, "password": "synthetic-mail", "imap_password": ""},
    }


STEPS = {
    1: {}, 2: {"discovery_enabled": True},
    3: {"operator_name": "Synthetic Person", "operator_email": "person@example.com", "operator_country_code": "US"},
    4: {},
    5: {"purpose": "zyene_reviews", "workspace_name": "Synthetic outreach", "product_name": "Synthetic Reviews", "product_docs": "Manage reviews for local businesses.", "booking_link": ""},
    6: {"audience": {"industry": "Dental practices", "country": "US", "company_size": "2-50", "roles": ["Owner", "Practice Manager"], "seniority": ["owner", "manager"], "instructions": "Exclude students and trainees."}, "confirmed": True, "accepted_legal_notice": True},
}


@pytest.mark.parametrize("repetition", range(1, 11))
def test_six_steps_in_order_ten_times(wizard, repetition):
    from leadzen.configuration import effective
    from leadzen.config.models import SiteConfig
    response = wizard.get("/api/onboarding/wizard")
    assert response.status_code == 200, response.content
    assert response.json()["onboarded"] is False
    settings = connections()
    with patch("leadzen.setup_wizard.probe_ai", return_value={"answered": True}) as ai, patch("leadzen.setup_wizard.probe_discovery", return_value={"credits": 40}) as finder, patch("leadzen.setup_wizard.probe_mailbox", return_value={"smtp": True, "imap": True}) as mail:
        for step in range(1, 7):
            if step in (1, 2, 4):
                kind = {1: "ai", 2: "discovery", 4: "mailbox"}[step]
                result = call(wizard, "post", "test", {"kind": kind, **settings})
                assert result.status_code == 200, result.content
                assert "synthetic-ai" not in result.content.decode()
                assert "synthetic-mail" not in result.content.decode()
                assert "synthetic-finder" not in result.content.decode()
            result = call(wizard, "put", "wizard", {"step": step, "values": STEPS[step], **settings})
            assert result.status_code == 200, (step, result.content)
            assert step in result.json()["completed_steps"]
        assert ai.call_count == finder.call_count == mail.call_count == 1
    finished = call(wizard, "post", "complete", {})
    assert finished.status_code == 200, finished.content
    config = SiteConfig.load()
    assert config.operator_email == "person@example.com"  # Not the sending mailbox.
    assert config.operator_name == "Synthetic Person"
    assert "Dental practices" in config.campaign_target and "United States" in config.campaign_target
    assert "Practice Manager" in config.campaign_target and "Exclude students" in config.campaign_target
    assert "Synthetic Reviews" in config.product_docs
    assert effective().mailbox_address == "sender@example.com"
    resumed = wizard.get("/api/onboarding/wizard").json()
    assert resumed["checks"]["ai"]["connected"] is True
    assert resumed["checks"]["discovery"]["credits"] == 40
    assert resumed["checks"]["mailbox"]["connected"] is True


def test_no_forged_or_skipped_success(wizard):
    assert call(wizard, "put", "wizard", {"step": 4, "values": {}, **connections()}).status_code == 409
    assert call(wizard, "put", "wizard", {"step": 1, "values": {"connected": True}, **connections()}).status_code == 409
    assert call(wizard, "post", "complete", {"completed_steps": list(range(1, 7))}).status_code == 409


@pytest.mark.parametrize("kind", ["ai", "discovery", "mailbox"])
def test_provider_errors_are_safe_and_do_not_mark_connected(wizard, kind):
    with patch(f"leadzen.setup_wizard.probe_{kind}", side_effect=RuntimeError("synthetic-ai synthetic-mail synthetic-finder private provider reply")):
        result = call(wizard, "post", "test", {"kind": kind, **connections()})
    assert result.status_code == 400
    assert "synthetic-" not in result.content.decode()
    assert not wizard.get("/api/onboarding/wizard").json()["checks"].get(kind, {}).get("connected")


def test_editing_tested_model_invalidates_check_and_continue(wizard):
    settings = connections()
    with patch("leadzen.setup_wizard.probe_ai", return_value={"answered": True}):
        assert call(wizard, "post", "test", {"kind": "ai", **settings}).status_code == 200
    settings["llm"]["model"] = "a-different-model"
    assert call(wizard, "put", "wizard", {"step": 1, "values": {}, **settings}).status_code == 409
    assert wizard.get("/api/onboarding/wizard").json()["connections"]["llm"]["model"] == "openai/gpt-oss-120b"


def test_identity_cannot_be_email_or_change_login_identity(wizard):
    with patch("leadzen.setup_wizard.probe_ai", return_value={"answered": True}), patch("leadzen.setup_wizard.probe_discovery", return_value={"credits": 0}):
        for kind, step in [("ai", 1), ("discovery", 2)]:
            assert call(wizard, "post", "test", {"kind": kind, **connections()}).status_code == 200
            assert call(wizard, "put", "wizard", {"step": step, "values": STEPS[step], **connections()}).status_code == 200
    value = {**STEPS[3], "operator_name": "person@example.com"}
    assert call(wizard, "put", "wizard", {"step": 3, "values": value}).status_code == 400
    assert wizard.get("/api/auth/me").json()["user"]["email"] == "unit@example.com"


def test_unauthenticated_tests_do_not_read_credentials_or_call_providers(db, monkeypatch):
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "test-dashboard-token")
    with patch("leadzen.workspaces.initialize_workspace") as initialize, patch("leadzen.setup_wizard.probe_ai") as ai:
        assert call(Client(HTTP_AUTHORIZATION="Bearer test-dashboard-token"), "post", "test", {"kind": "ai", **connections()}).status_code == 401
        initialize.assert_not_called()
        ai.assert_not_called()


def test_failed_retest_clears_previous_success(wizard):
    with patch("leadzen.setup_wizard.probe_ai", return_value={"answered": True}):
        assert call(wizard, "post", "test", {"kind": "ai", **connections()}).status_code == 200
    with patch("leadzen.setup_wizard.probe_ai", side_effect=RuntimeError("expired key")):
        assert call(wizard, "post", "test", {"kind": "ai", **connections()}).status_code == 400
    assert wizard.get("/api/onboarding/wizard").json()["checks"]["ai"]["connected"] is False


def test_settings_changed_during_probe_are_not_overwritten(wizard):
    from leadzen.configuration import effective, save_dashboard_settings
    from dataclasses import asdict
    def concurrent_change(values):
        save_dashboard_settings({**asdict(effective()), "signature": "Edited in another tab"})
        return {"answered": True}
    with patch("leadzen.setup_wizard.probe_ai", side_effect=concurrent_change):
        result = call(wizard, "post", "test", {"kind": "ai", **connections()})
    assert result.status_code == 409
    assert effective().signature == "Edited in another tab"
    assert not effective().llm_api_key


@pytest.mark.parametrize("step,values", [
    (3, {**STEPS[3], "operator_country_code": []}),
    (5, {**STEPS[5], "purpose": []}),
    (6, {**STEPS[6], "audience": {**STEPS[6]["audience"], "country": []}}),
    (6, {**STEPS[6], "audience": {**STEPS[6]["audience"], "company_size": []}}),
    (6, {**STEPS[6], "audience": {**STEPS[6]["audience"], "roles": ["Owner", " Owner "]}}),
])
def test_invalid_structured_inputs_fail_safely(step, values):
    from leadzen.setup_wizard import validate_step
    from leadzen.configuration import SettingsError
    with pytest.raises(SettingsError):
        validate_step(step, values, None, None)


def test_identity_defaults_are_employee_not_legacy_sender(wizard):
    from leadzen.config.models import SiteConfig
    config = SiteConfig.load()
    config.operator_email = "sender@example.com"
    config.save()
    assert wizard.get("/api/onboarding/wizard").json()["draft"]["operator_email"] == "unit@example.com"


@pytest.mark.parametrize("raw,expected", [(b'{"credits_left":"40.0"}', 40), (b'{"credits_left":0}', 0)])
def test_discovery_adapter_reads_actual_balance_without_search(raw, expected):
    from leadzen.setup_wizard import probe_discovery
    with patch("leadzen.ai.pinned_request", return_value=(200, {}, raw)) as request:
        assert probe_discovery(SimpleNamespace(lead_finder_provider="bettercontact", bettercontact_api_key="synthetic-finder")) == {"credits": expected}
        assert request.call_args.args[0:2] == ("GET", "https://app.bettercontact.rocks/api/v2/account")
        assert request.call_args.args[2]["X-API-Key"] == "synthetic-finder"
        assert request.call_count == 1


@pytest.mark.parametrize("raw", [b'{}', b'[]', b'{"credits_left":null}', b'{"credits_left":true}', b'{"credits_left":-1}', b'{"credits_left":"NaN"}', b'{"credits_left":"Infinity"}'])
def test_discovery_adapter_never_invents_a_credit_balance(raw):
    from leadzen.setup_wizard import probe_discovery
    with patch("leadzen.ai.pinned_request", return_value=(200, {}, raw)), pytest.raises((ValueError, TypeError)):
        probe_discovery(SimpleNamespace(lead_finder_provider="bettercontact", bettercontact_api_key="synthetic-finder"))


def test_mailbox_probe_authenticates_readonly_without_sending():
    from leadzen.setup_wizard import probe_mailbox
    values = SimpleNamespace(mail_transport="smtp", mailbox_address="sender@example.com", smtp_host="smtppro.zoho.com", smtp_port="465", imap_host="imappro.zoho.com", imap_port="993", mailbox_password="synthetic-password", imap_password="", smtp_username="")
    with patch("leadzen.transports.smtp_class") as smtp, patch("leadzen.transports.imap_class") as imap:
        inbox = imap.return_value.return_value.__enter__.return_value
        inbox.select.return_value = ("OK", [b"0"])
        assert probe_mailbox(values) == {"smtp": True, "imap": True}
        outbound = smtp.return_value.return_value.__enter__.return_value
        outbound.login.assert_called_once_with("sender@example.com", "synthetic-password")
        outbound.sendmail.assert_not_called()
        outbound.send_message.assert_not_called()
        outbound.data.assert_not_called()
        inbox.select.assert_called_once_with("INBOX", readonly=True)
        inbox.fetch.assert_not_called()


def test_revoked_session_cannot_save_connection_result(wizard):
    from leadzen.accounts.models import LoginSession
    from leadzen.configuration import effective
    def revoke(values):
        LoginSession.objects.using("default").all().delete()
        return {"answered": True}
    with patch("leadzen.setup_wizard.probe_ai", side_effect=revoke):
        assert call(wizard, "post", "test", {"kind": "ai", **connections()}).status_code == 401
    assert not effective().llm_api_key


def test_expired_receipt_requires_retest(wizard):
    from leadzen.config.models import OnboardingState
    with patch("leadzen.setup_wizard.probe_ai", return_value={"answered": True}):
        assert call(wizard, "post", "test", {"kind": "ai", **connections()}).status_code == 200
    state = OnboardingState.objects.get(pk=1)
    state.checks["ai"]["expires_at"] = "2000-01-01T00:00:00+00:00"
    state.save()
    assert call(wizard, "put", "wizard", {"step": 1, "values": {}, **connections()}).status_code == 409


def test_disallowed_endpoint_fails_before_probe(wizard):
    body = connections()
    body["llm"].update(provider="openai_compatible", base_url="https://169.254.169.254/v1")
    with patch("leadzen.setup_wizard.probe_ai") as probe:
        assert call(wizard, "post", "test", {"kind": "ai", **body}).status_code == 400
        probe.assert_not_called()


@pytest.mark.parametrize("base_url", ["", "https://api.groq.com/openai/v1", "https://api.groq.com"])
def test_real_groq_agent_probe_uses_one_bounded_request_without_tools(wizard, base_url):
    from leadzen.setup_wizard import candidate, probe_ai
    reply = {"id": "synthetic-response", "object": "chat.completion", "created": 1, "model": "openai/gpt-oss-120b", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "OK"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}}
    settings = connections()
    settings["llm"]["base_url"] = base_url
    with patch("leadzen.ai.pinned_request", return_value=(200, [("content-type", "application/json")], json.dumps(reply).encode())) as network:
        assert probe_ai(candidate(settings, "ai")) == {"answered": True}
        assert network.call_count == 1
        args = network.call_args.args
        assert args[1] == "https://api.groq.com/openai/v1/chat/completions"
        body = json.loads(args[3])
        assert "tools" not in body
        assert body["max_tokens"] == 256
        assert body["reasoning_effort"] == "low"
        # Cold providers (Kimi on akashml, etc.) take ~16s on the first call.
        # The wizard must allow enough headroom for a healthy connection.
        assert network.call_args.kwargs["timeout"] == 30


def test_active_probe_lease_and_rate_limit_prevent_provider_calls(wizard):
    from django.utils import timezone
    from datetime import timedelta
    from leadzen.config.models import OnboardingState
    from leadzen.accounts.models import LoginThrottle
    import hashlib
    state = OnboardingState.objects.create(pk=1, testing_until=timezone.now() + timedelta(seconds=45))
    with patch("leadzen.setup_wizard.probe_ai") as provider:
        assert call(wizard, "post", "test", {"kind": "ai", **connections()}).status_code == 409
        provider.assert_not_called()
    state.testing_until = None
    state.save()
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.using("default").get(email="unit@example.com")
    key = hashlib.sha256(f"setup-test/{user.pk}/ai".encode()).hexdigest()
    LoginThrottle.objects.using("default").create(key=key, attempts=30, window_started_at=timezone.now())
    with patch("leadzen.setup_wizard.probe_ai") as provider:
        assert call(wizard, "post", "test", {"kind": "ai", **connections()}).status_code == 429
        provider.assert_not_called()
    state.refresh_from_db()
    assert state.testing_until is None


def test_manual_setup_still_requires_verified_mailbox(wizard):
    body = connections()
    body["llm"]["enabled"] = False
    assert call(wizard, "put", "wizard", {"step": 1, "values": {}, **body}).status_code == 200
    assert call(wizard, "put", "wizard", {"step": 2, "values": {"discovery_enabled": False}}).status_code == 200
    assert call(wizard, "put", "wizard", {"step": 3, "values": STEPS[3]}).status_code == 200
    assert call(wizard, "put", "wizard", {"step": 4, "values": {}, **body}).status_code == 409
