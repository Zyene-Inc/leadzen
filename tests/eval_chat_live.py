"""Opt-in live-model evaluation of Chat tool choice. Never collected by default.

AKML_KEY=... .venv/bin/pytest -q -s tests/eval_chat_live.py
Synthetic workspace; only the model call is real. find_leads, sync and sends are
stubbed so nothing external happens besides the LLM request.
"""
import json, os, time
from unittest.mock import patch
import pytest
from leadzen.configuration import save_dashboard_settings, effective
from dataclasses import asdict
from tests.test_chat import chat_client, turn
from tests.test_discovery import discovery_client

PROMPTS = [
    ("hi", "answer only"),
    ("give me the names and LinkedIn of my qualified leads", "list_leads, then names + links"),
    ("how many leads do I have?", "overview or list_leads, then a number"),
    ("can you find lead 3 no email", "find_leads"),
    ("what is my current target?", "get_target"),
    ("did anyone reply?", "list_replies or sync"),
    ("send emails to all my leads now", "no send without approval"),
]


def seed():
    from openoutfind.crm.models import Lead as Profile, Deal as Decision
    from cold_outreach.leads.models import Lead, Deal
    people = [("Rachel Hogancamp", "Owner", "The Waterfront Cafe"), ("Mike Koeneke", "Co-Founder", "Dexter"), ("Simon Perry", "Founder", "sierge."),
              ("Ana Ruiz", "Owner", "Ruiz Plumbing"), ("Dev Patel", "Founder", "Patel HVAC"), ("Lena Ortiz", "Owner", "Ortiz Bistro")]
    for i, (name, title, company) in enumerate(people):
        slug = name.lower().replace(" ", "-")
        profile = Profile.objects.create(full_name=name, job_title=title, profile_url=f"https://www.linkedin.com/in/{slug}", profile_text=("Long synthetic profile text. " * 60))
        Decision.objects.create(lead=profile, state="Qualified", reason=f"{title} of a small US hospitality/home-service business")
        first, last = name.split(" ", 1)
        lead = Lead.objects.create(lead_id=str(profile.pk), first_name=first, last_name=last, title=title, linkedin_url=profile.profile_url, company=company, profile_text=("Long synthetic profile text. " * 60))
        Deal.objects.create(lead=lead)


@pytest.mark.skipif(not os.environ.get("AKML_KEY"), reason="live model evaluation is opt-in")
def test_live_tool_choice(discovery_client, monkeypatch):
    monkeypatch.setenv("LEADZEN_LLM_HOSTS", "api.akashml.com")
    monkeypatch.setenv("LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS", "api.akashml.com")
    values = asdict(effective()); values.update(provider="openai_compatible", model="openai/gpt-oss-120b", base_url="https://api.akashml.com/v1")
    save_dashboard_settings(values, llm_api_key=os.environ["AKML_KEY"])
    seed()
    from leadzen.chat.engine import drive
    from leadzen.config.models import ChatRun
    for prompt, expected in PROMPTS:
        thread, run = turn(discovery_client, prompt)
        start = time.time()
        with patch("leadzen.chat.engine.find_leads", return_value={"stored": 3, "partial": False, "note": "Lead discovery completed. No emails sent."}), \
             patch("leadzen.transports.sync_replies_strict"), patch("cold_outreach.emails.sender._deliver") as deliver:
            drive(run)
        detail = discovery_client.get(f"/api/chat/threads/{thread}").json()
        tools = [m["data"].get("tool") for m in detail["messages"] if m["role"] == "tool"]
        final = [m["content"] for m in detail["messages"] if m["role"] == "assistant"]
        row = ChatRun.objects.get(pk=run)
        if row.status == "awaiting_approval":  # Record it, then decline so the next prompt can run.
            ChatRun.objects.filter(pk=run).update(status="cancelled", pending={})
        print(f"\n### {prompt!r}  (expected: {expected})\n  status={row.status} steps={row.steps} {time.time()-start:.1f}s tools={tools} sent={deliver.call_count}\n  reply: {(final[-1] if final else row.pending.get('summary') if row.pending else None)!r}"[:900])


@pytest.mark.skipif(not os.environ.get("AKML_KEY"), reason="live model evaluation is opt-in")
@pytest.mark.parametrize("attempt", range(3))
def test_live_prepare_draft(discovery_client, monkeypatch, attempt):
    """The Workspace "Prepare draft" button against the real model: valid, saved, no Chat."""
    from tests.test_campaigns import add
    from leadzen.config.models import SiteConfig, ChatThread
    monkeypatch.setenv("LEADZEN_LLM_HOSTS", "api.akashml.com")
    values = asdict(effective()); values.update(ai_enabled=True, provider="openai_compatible", model="openai/gpt-oss-120b", base_url="https://api.akashml.com/v1")
    save_dashboard_settings(values, llm_api_key=os.environ["AKML_KEY"])
    SiteConfig.objects.update(operator_name="Karthik", product_docs="Zyene Reviews helps local restaurants and home-service businesses collect more Google reviews with automatic SMS and email review requests.", campaign_target="Owners of US restaurants and home-service businesses with 1-10 employees", booking_link="https://cal.example.com/zyene")
    contact = add(discovery_client)
    start = time.time()
    response = discovery_client.post("/api/campaigns/prepare", data=json.dumps({"contact_ids": [contact]}), content_type="application/json")
    data = response.json()
    print(f"\n### prepare draft attempt {attempt}: HTTP {response.status_code} in {time.time()-start:.1f}s chat_threads={ChatThread.objects.count()}")
    if response.status_code == 201:
        print(f"  name: {data['name']!r}\n  subject: {data['steps'][0]['subject']!r}\n  body: {data['steps'][0]['body']!r}"[:1200])
    assert response.status_code == 201, data
    assert ChatThread.objects.count() == 0
