"""Minimal real-provider check that searches hit the requested target.

Opt-in and operator-run only. Keys come from the environment of the person
running it (never from a workspace database), nothing is stored, no email lookup
or email send is made, and the summary prints locations/industries, not names.

    AI_ARK_API_KEY=... BETTERCONTACT_API_KEY=... \\
      .venv/bin/python tests/scenarios/provider_search_probe.py --spend-up-to-one-credit

Spend: AI Ark two People Search pages of size 1 (0.5 credit per returned profile,
at most 1 credit) plus free balance checks; BetterContact one Lead Finder page of 1
profile with email/phone enrichment off (documented by the finder as 0 credits).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadzen.settings")
import django  # noqa: E402

django.setup()

AUDIENCE = {"roles": ["Dentist"], "industry": "Dental practices", "country": "US", "region": "Texas",
            "company_size": "1-10", "seniority": ["owner"], "instructions": ""}


def ai_ark(key):
    from leadzen.ai import pinned_request
    from leadzen.ai_ark import BASE, describe, search_filters
    headers = {"X-TOKEN": key, "Accept": "application/json", "Content-Type": "application/json"}

    def call(method, path, body=None):
        status, _, raw = pinned_request(method, BASE + path, headers, json.dumps(body).encode() if body is not None else b"",
                                        "api.ai-ark.com", kind="AI_ARK", timeout=30)
        return status, (json.loads(raw) if raw.strip() else {})

    before = call("GET", "/v1/payments/credits")[1].get("total")
    # Mapped industry ("dental"), then an unmapped one that must use the keyword fallback.
    for audience in (AUDIENCE, {**AUDIENCE, "industry": "Chiropractors", "roles": ["Chiropractor"]}):
        body = {**search_filters(audience), "page": 0, "size": 1}
        status, result = call("POST", "/v1/people", body)
        result = result if isinstance(result, dict) else {}
        rows = result.get("content") or []
        print("AI Ark searched:", describe(audience))
        print("  account filter:", json.dumps(body["account"]), "| location filter:", json.dumps(body["contact"]["location"]))
        print("  HTTP", status, "| matching people:", result.get("totalElements"), "| returned:", len(rows))
        for person in rows:
            company = (person.get("company") or {}).get("summary") or {}
            location = person.get("location") or {}
            print("  location:", location.get("state"), location.get("country"), "| company industry:", company.get("industry"),
                  "| staff:", (company.get("staff") or {}).get("total"), "| title:", (person.get("profile") or {}).get("title"))
    after = call("GET", "/v1/payments/credits")[1].get("total")
    print("AI Ark credits before/after:", before, after)


def bettercontact(key):
    from openoutfind.discovery import LEAD_FINDER_URL
    from openoutfind.enrichment.bettercontact import submit_and_poll
    from leadzen.search_plan import enforce, HEADCOUNT
    from leadzen.geo import place
    value = {"place": place(AUDIENCE), "headcount": HEADCOUNT[AUDIENCE["company_size"]], "seniority": AUDIENCE["seniority"]}
    filters = enforce({"lead_job_title": {"include": ["dentist"], "exact_match": False}}, value)
    body = {"filters": filters, "limit": 1, "offset": 0, "enrich_email_address": False, "enrich_phone_number": False}
    result = submit_and_poll(key, LEAD_FINDER_URL, body)
    leads = result.get("leads") or []
    print("BetterContact searched:", json.dumps(filters))
    print("  matching people:", (result.get("summary") or {}).get("leads_found"), "| returned:", len(leads))
    for lead in leads:
        print("  location:", lead.get("contact_location_state"), lead.get("contact_location_country"),
              "| title:", lead.get("contact_job_title"), "| has email:", bool(lead.get("contact_email_address")))


if __name__ == "__main__":
    if "--spend-up-to-one-credit" not in sys.argv:
        sys.exit("Refusing to call real providers without --spend-up-to-one-credit")
    if os.environ.get("AI_ARK_API_KEY"):
        ai_ark(os.environ["AI_ARK_API_KEY"])
    if os.environ.get("BETTERCONTACT_API_KEY"):
        bettercontact(os.environ["BETTERCONTACT_API_KEY"])
    if not (os.environ.get("AI_ARK_API_KEY") or os.environ.get("BETTERCONTACT_API_KEY")):
        sys.exit("Set AI_ARK_API_KEY and/or BETTERCONTACT_API_KEY")
