"""Autopilot sends to free-lookup hits and buys only the misses it is allowed to buy. Synthetic only."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from cold_outreach.leads.models import Deal, Lead
from leadzen import autopilot
from leadzen.config.models import AutopilotPolicy, AutopilotRun, CampaignRecipient, DiscoveryCandidate, DiscoveryLookup, FreeEmailLookup, SiteConfig
from leadzen.autopilot_worker import deliver_due, prepare
from test_autopilot import NOW, policy
from test_campaigns import connected  # noqa: F401


@pytest.fixture(autouse=True)
def free_lookup_on(monkeypatch):
    monkeypatch.setenv("LEADZEN_FREE_EMAIL_LOOKUP", "on")


@pytest.fixture(autouse=True)
def enable_service(monkeypatch):
    monkeypatch.setenv("LEADZEN_AUTOPILOT_ENABLED", "1")


def daily_run(**scope):
    p = policy(**scope)
    return p, AutopilotRun.objects.create(policy=p, actor_id=p.actor_id, workday=NOW.date(),
                                          checkpoint={"contact_limit": 2}, deadline_at=NOW + timedelta(minutes=12))


def run_day(run, p):
    """Discovery qualifies two people; the free lookup finds the first one's email."""
    from leadzen.discovery_progress import current
    from openoutfind.crm.models import Lead as Source
    calls = []

    def finder(args):
        monitor = current()
        calls.append(list(monitor.session.source_ids))
        if not args["emails"]:
            for index in range(2):
                source = Source.objects.create(profile_url=f"https://www.linkedin.com/in/today{index}", full_name=f"Today {index}")
                email = "free0@example.com" if index == 0 else ""
                deal = Deal.objects.create(lead=Lead.objects.create(lead_id=str(source.pk), email=email, first_name="Ada", company="Example"))
                DiscoveryCandidate.objects.create(session=monitor.session, source_id=source.pk, contact_id=deal.pk, discovered=True,
                                                  produced=True, outcome="qualified", data={"email": email})
                if email:
                    FreeEmailLookup.objects.create(source_id=source.pk, status="found", email=email, checked_at=NOW)
        else:
            for source_id in monitor.session.source_ids:
                autopilot.external_guard(reserve_credit=True)
                deal = Deal.objects.get(lead__lead_id=str(source_id))
                deal.lead.email = "paid1@example.com"
                deal.lead.save()
                DiscoveryCandidate.objects.create(session=monitor.session, source_id=source_id, contact_id=deal.pk,
                                                  produced=True, outcome="qualified", data={"email": deal.lead.email})
                DiscoveryLookup.objects.create(session=monitor.session, source_id=source_id, state="terminated", credits=1, email_status="valid")
        return {"partial": False}

    def generate(review, drafts):
        autopilot.external_guard(reserve_model=True)
        return [{"id": str(d.pk), "subject": "Hello", "body": "Personal message"} for d in drafts]

    with patch("django.utils.timezone.now", return_value=NOW), patch("leadzen.chat.engine.find_leads", side_effect=finder), \
            patch("leadzen.outreach.generate", side_effect=generate), patch("leadzen.transports.sync_replies_strict"), \
            patch("cold_outreach.core.sending_window.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver") as send:
        with autopilot.execution(run):
            prepare(run)
        deliver_due(p)
    run.refresh_from_db()
    # Mailbox pacing sends one first email per slot; every approved recipient is queued.
    assert send.call_count == 1
    return calls, sorted(r.deal.lead.email for r in CampaignRecipient.objects.select_related("deal__lead"))


def test_free_hits_go_to_outreach_and_only_misses_are_bought(connected):
    p, run = daily_run()
    calls, sent = run_day(run, p)
    free_source = FreeEmailLookup.objects.get().source_id
    assert len(calls) == 2 and free_source not in calls[1] and len(calls[1]) == 1
    assert sent == ["free0@example.com", "paid1@example.com"]
    assert run.email_credits == 1


def test_policy_that_does_not_buy_sends_free_hits_and_skips_misses(connected):
    p, run = daily_run(buy_missing_emails=False)
    calls, sent = run_day(run, p)
    assert calls == [[]] and sent == ["free0@example.com"]
    assert run.email_credits == 0 and not DiscoveryLookup.objects.exists()


def test_enabling_records_the_buy_choice_and_rejects_anything_else(connected):
    from leadzen.configuration import save_dashboard_settings
    save_dashboard_settings({"ai_enabled": True, "mailbox_address": "sender@example.com", "smtp_host": "smtp.example.com", "imap_host": "imap.example.com", "smtp_port": 587, "imap_port": 993}, llm_api_key="synthetic", bettercontact_api_key="synthetic", mailbox_password="synthetic")
    SiteConfig.objects.update(product_docs="Our offer", campaign_target="Restaurants", operator_email="sender@example.com", operator_country_code="US", accepted_legal_notice=True)
    with patch("leadzen.discovery.context", return_value={"blockers": []}):
        revision = connected.get("/api/autopilot").json()["setup"]["revision"]
        body = {"enabled": True, "authorize_automatic_outreach": True, "revision": revision, "request_id": str(uuid.uuid4()), "buy_missing_emails": "yes"}
        assert connected.post("/api/autopilot", json.dumps(body), content_type="application/json").status_code == 400
        body["buy_missing_emails"] = False
        response = connected.post("/api/autopilot", json.dumps(body), content_type="application/json")
        assert response.status_code == 200, response.content
    saved = AutopilotPolicy.objects.get()
    assert saved.scope["buy_missing_emails"] is False and not autopilot.buys_missing_emails(saved)
    assert response.json()["policy"]["scope"]["buy_missing_emails"] is False
    # Policies approved before this choice existed authorized paid lookups.
    assert autopilot.buys_missing_emails(AutopilotPolicy(scope={"daily_credits": 10}))
