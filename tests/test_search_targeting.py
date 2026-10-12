"""Provider searches follow the requested target. Synthetic transports only."""
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from tests.test_chat import chat_client
from tests.test_discovery import discovery_client

AUDIENCE = {"roles": ["Dentist"], "industry": "Dental practices", "country": "US", "region": "Texas",
            "company_size": "1-10", "seniority": ["owner"], "instructions": ""}


def save_target(audience):
    from leadzen.config.models import OnboardingState, SiteConfig
    from leadzen.setup_wizard import target_preview
    config = SiteConfig.load()
    config.campaign_target = target_preview(audience)
    config.save()
    OnboardingState.objects.update_or_create(pk=1, defaults={"draft": {"audience": audience}})


def frontier(token="saas", offset=200):
    from openoutfind.core.models import Keyword, QueryNode
    from openoutfind.crm.models import Lead
    node = QueryNode.objects.create(token_key=f"node-{token}", next_offset=offset, state="fired")
    node.keywords.set(Keyword.rows_for([("lead_job_title", token)]))
    Lead.objects.create(synthetic=True, profile_text=f"ideal {token} buyer", source_fields={"contact_job_title": token}, embedding=b"\x00\x01")
    real = Lead.objects.create(profile_url=f"https://www.linkedin.com/in/real-{token}", profile_text=f"real {token}", discovered_by=node)
    return node, real


# ── AI Ark: industries, countries, states/cities ─────────────────────


@pytest.mark.parametrize("text,expected", [
    ("Dental practices", ["dental"]), ("Dentists", ["dental"]), ("HVAC", ["heating, ventilation, and air conditioning (hvac)"]),
    ("Law firms", ["legal"]), ("Restaurant & hospitality", ["restaurants", "hospitality"]),
    ("Ecommerce", ["e-commerce"]), ("Software development", ["software development"]), ("xyzzy widgets", []),
])
def test_industry_maps_to_supported_ai_ark_values(text, expected):
    from leadzen.industries import catalogue, closest
    assert closest(text) == expected
    assert set(expected) <= set(catalogue()[0])


def test_ai_ark_filters_use_supported_industry_smart_match_and_state():
    from leadzen.ai_ark import search_filters
    filters = search_filters(AUDIENCE)
    assert filters["account"]["industries"] == {"any": {"include": {"mode": "SMART", "content": ["dental"]}}}
    assert filters["contact"]["experience"]["latest"]["title"]["any"]["include"] == {"mode": "SMART", "content": ["Dentist"]}
    # Texas inside the United States, not the whole country and not Texas elsewhere.
    assert filters["contact"]["location"] == {"all": {"include": ["United States", "Texas"]}}
    city = search_filters({**AUDIENCE, "region": "Austin, Texas"})
    assert city["contact"]["location"] == {"all": {"include": ["United States", "Austin", "Texas"]}}


def test_unmapped_industry_searches_company_keywords_instead_of_nothing():
    from leadzen.ai_ark import search_filters
    filters = search_filters({**AUDIENCE, "industry": "Chiropractors", "region": ""})
    assert "industries" not in filters["account"]
    assert filters["account"]["keyword"]["any"]["include"]["content"] == ["Chiropractors"]
    assert {s["mode"] for s in filters["account"]["keyword"]["any"]["include"]["sources"]} == {"SMART"}
    assert filters["contact"]["location"] == {"any": {"include": ["United States"]}}


@pytest.mark.parametrize("code,name", [("GB", "United Kingdom"), ("KR", "South Korea"), ("CD", "Democratic Republic of the Congo"), ("US", "United States"), ("DE", "Germany")])
def test_country_names_are_plain(code, name):
    from leadzen.ai_ark import search_filters
    from leadzen.geo import countries, country_name
    assert country_name(code) == name
    assert {"code": code, "name": name} in countries()
    assert search_filters({**AUDIENCE, "country": code, "region": ""})["contact"]["location"] == {"any": {"include": [name]}}


# ── Target: optional state/city, and older saved Targets ─────────────


def test_target_saves_state_and_previews_it(discovery_client):
    response = discovery_client.put("/api/target", json.dumps({"audience": AUDIENCE, "confirmed": True, "accepted_legal_notice": True}), content_type="application/json")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["audience"]["region"] == "Texas" and body["place"] == "Texas, United States"
    assert "in Texas, United States, 1-10 employees" in body["summary"]
    bad = discovery_client.put("/api/target", json.dumps({"audience": {**AUDIENCE, "region": "Texas;\tOhio"}, "confirmed": True, "accepted_legal_notice": True}), content_type="application/json")
    assert bad.status_code == 400


def test_target_saved_before_state_support_stays_active(discovery_client):
    from leadzen.config.models import OnboardingState, SiteConfig
    from leadzen.home import current_target
    from leadzen.setup_wizard import target_preview
    legacy = {key: value for key, value in AUDIENCE.items() if key != "region"} | {"country": "GB"}
    config = SiteConfig.load()
    config.campaign_target = target_preview(legacy, legacy=True)
    config.save()
    assert "Britain (UK)" in config.campaign_target
    OnboardingState.objects.update_or_create(pk=1, defaults={"draft": {"audience": legacy}})
    assert current_target(config, OnboardingState.objects.get(pk=1))["audience"] == legacy


# ── BetterContact: the search plan follows the target ───────────────


def test_first_plan_needs_no_reset(discovery_client):
    from leadzen import search_plan
    plan, reset = search_plan.activate(search_plan.spec({"audience": ""}))
    assert plan.active and not reset
    assert search_plan.activate(search_plan.spec({"audience": ""}))[1] is False


def test_target_change_backs_up_resets_and_restores_search_plan(discovery_client):
    from leadzen import search_plan
    from leadzen.config.models import SearchPlan
    from openoutfind.core.models import Keyword, QueryNode
    from openoutfind.crm.models import Lead
    save_target({**AUDIENCE, "industry": "Software", "roles": ["CTO"], "region": ""})
    first, _ = search_plan.activate(search_plan.spec({"audience": ""}))
    node, real = frontier("saas")

    save_target(AUDIENCE)
    second, reset = search_plan.activate(search_plan.spec({"audience": ""}))
    assert reset and second.pk != first.pk
    assert not QueryNode.objects.exists() and not Keyword.objects.exists()
    assert not Lead.objects.filter(synthetic=True).exists()
    real.refresh_from_db()
    assert real.discovered_by_id is None  # Real leads are never deleted.
    first.refresh_from_db()
    assert not first.active and first.state["nodes"][0]["key"] == "node-saas"
    assert first.state["nodes"][0]["next_offset"] == 200 and len(first.state["anchors"]) == 1

    save_target({**AUDIENCE, "industry": "Software", "roles": ["CTO"], "region": ""})
    restored, reset = search_plan.activate(search_plan.spec({"audience": ""}))
    assert reset and restored.pk == first.pk and restored.active
    node = QueryNode.objects.get(token_key="node-saas")
    assert node.next_offset == 200 and node.pairs == [("lead_job_title", "saas")]
    assert bytes(Lead.objects.get(synthetic=True).embedding) == b"\x00\x01"
    assert SearchPlan.objects.get(pk=second.pk).active is False


def test_cosmetic_target_edit_keeps_the_plan(discovery_client):
    from leadzen import search_plan
    plan, _ = search_plan.activate(search_plan.spec({"audience": "Dentists in Texas"}))
    frontier("dentist")
    same, reset = search_plan.activate(search_plan.spec({"audience": "  dentists   in TEXAS. "}))
    assert same.pk == plan.pk and not reset


def test_state_from_before_tracking_is_archived_as_legacy(discovery_client):
    from leadzen import search_plan
    from leadzen.config.models import SearchPlan
    frontier("legacy")
    plan, reset = search_plan.activate(search_plan.spec({"audience": ""}))
    assert reset
    legacy = SearchPlan.objects.get(fingerprint__startswith="legacy-")
    assert legacy.state["nodes"][0]["key"] == "node-legacy" and not legacy.active


def test_archives_are_bounded(discovery_client):
    from leadzen import search_plan
    from leadzen.config.models import SearchPlan
    for index in range(search_plan.KEEP_ARCHIVES + 5):
        search_plan.activate(search_plan.spec({"audience": f"Synthetic audience {index}"}))
        frontier(f"t{index}")
    assert SearchPlan.objects.filter(active=False).count() == search_plan.KEEP_ARCHIVES
    assert SearchPlan.objects.filter(active=True).count() == 1


def test_enforce_constrains_location_size_and_seniority():
    from leadzen.search_plan import enforce
    value = {"place": "Texas, United States", "headcount": [1, 10], "seniority": ["owner", "founder"]}
    filters = enforce({"lead_job_title": {"include": ["dentist"]}, "lead_location": {"include": ["United States"]},
                       "lead_seniority": {"include": ["intern"]}, "company_headcount_min": 1, "company_headcount_max": 10000}, value)
    assert filters["lead_location"] == {"include": ["Texas, United States"]}
    assert (filters["company_headcount_min"], filters["company_headcount_max"]) == (1, 10)
    assert filters["lead_seniority"] == {"include": ["owner", "founder"]}
    assert enforce({"lead_seniority": {"include": ["founder"]}}, value)["lead_seniority"] == {"include": ["founder"]}
    assert enforce({"lead_job_title": {"include": ["cto"]}}, {"place": "", "headcount": None, "seniority": []}) == {"lead_job_title": {"include": ["cto"]}}


def test_scope_seeds_and_queries_only_the_current_target(discovery_client):
    from leadzen import search_plan
    from openoutfind.core.models import Keyword, QueryNode
    from openoutfind.core.pipeline import icp, qualify, vocabulary
    from openoutfind.crm.models import Deal, DealState, Lead
    old = Lead.objects.create(profile_url="https://www.linkedin.com/in/old-cto", profile_text="cto", source_fields={"contact_job_title": "cto"},
                              embedding=b"\x00", creation_date=timezone.now() - timedelta(days=2))
    Deal.objects.create(lead=old, state=DealState.QUALIFIED, creation_date=timezone.now() - timedelta(days=2))
    Lead.objects.create(profile_url="https://www.linkedin.com/in/old-pool", profile_text="old pool", embedding=b"\x00",
                        creation_date=timezone.now() - timedelta(days=2))
    save_target(AUDIENCE)
    plan, _ = search_plan.activate(search_plan.spec({"audience": ""}))
    fake = icp.Seed([("lead_job_title", "dentist"), ("lead_location", "United States"), ("lead_seniority", "intern")], (1, 10000), "us")
    Keyword.rows_for([("lead_seniority", s) for s in ("owner", "intern", "director")])
    with patch.object(icp, "generate_seed", return_value=fake), patch.object(icp, "ensure_anchors") as anchors, search_plan.scope(plan):
        seed = icp.generate_seed(None)
        anchors.assert_called_once()
        assert ("lead_location", "Texas, United States") in seed.keywords and ("lead_location", "United States") not in seed.keywords
        assert ("lead_seniority", "owner") in seed.keywords and ("lead_seniority", "intern") not in seed.keywords
        assert seed.headcount == (1, 10)
        admitted = vocabulary.admitted_keywords()
        assert ("lead_seniority", "owner") in admitted and ("lead_seniority", "intern") not in admitted and ("lead_seniority", "director") not in admitted
        # An earlier target's acceptances and unjudged pool do not steer this search.
        assert vocabulary._qualified_source_fields() == [] and vocabulary._accepted_count() == 0
        assert qualify.fetch_qualification_candidates() == []
        fresh = Lead.objects.create(profile_url="https://www.linkedin.com/in/new-dentist", profile_text="dentist", embedding=b"\x00")
        assert [lead.pk for lead in qualify.fetch_qualification_candidates()] == [fresh.pk]
        node = QueryNode.objects.create(token_key="dentist-only")
        node.keywords.set(Keyword.rows_for([("lead_job_title", "dentist")]))
        filters = node.to_filters()
        assert filters["lead_location"] == {"include": ["Texas, United States"]}
        assert filters["company_headcount_max"] == 10 and filters["lead_seniority"] == {"include": ["owner"]}


def test_bettercontact_request_is_constrained_and_target_changes_rebuild(discovery_client):
    """End to end through find_leads: the actual Lead Finder POST body."""
    import requests
    from leadzen.chat.engine import find_leads
    from leadzen.config.models import SearchPlan
    from openoutfind.enrichment import bettercontact
    sent = []

    def command(*args, **kwargs):
        # Stand-in for the finder: one raw, unconstrained Lead Finder request.
        session = requests.Session()
        bettercontact._request(session, "POST", "https://app.bettercontact.rocks/api/v2/lead_finder/async",
                               json={"filters": {"lead_job_title": {"include": ["dentist"]}, "lead_location": {"include": ["United States"]}}, "limit": 100, "offset": 0})

    def network(method, url, headers, content, host, **kwargs):
        sent.append(json.loads(content))
        return 200, {}, b'{"request_id": "synthetic"}'

    save_target(AUDIENCE)
    with patch("django.core.management.call_command", command), patch("leadzen.ai.pinned_request", side_effect=network):
        find_leads({"count": 1, "emails": False, "audience": ""})
        assert sent[-1]["filters"]["lead_location"] == {"include": ["Texas, United States"]}
        assert sent[-1]["filters"]["lead_seniority"] == {"include": ["owner"]}
        assert sent[-1]["enrich_email_address"] is False
        import os
        assert os.environ["OPENOUTFIND_CAMPAIGN_TARGET"].startswith("Find Dentist working at Dental practices in Texas")
        frontier("dentist")
        # A one-off Chat audience gets its own search, restricted to its own place.
        find_leads({"count": 1, "emails": False, "audience": "Plumbers in Ohio", "location": {"country": "US", "region": "Ohio"}})
        assert sent[-1]["filters"]["lead_location"] == {"include": ["Ohio, United States"]}
        assert "lead_seniority" not in sent[-1]["filters"]
        assert os.environ["OPENOUTFIND_CAMPAIGN_TARGET"] == "Plumbers in Ohio"
        assert SearchPlan.objects.filter(active=False).count() == 1
        # Back to the saved Target: its earlier frontier is restored, not rebuilt.
        find_leads({"count": 1, "emails": False, "audience": ""})
        assert os.environ["OPENOUTFIND_CAMPAIGN_TARGET"].startswith("Find Dentist")
    from openoutfind.core.models import QueryNode
    assert QueryNode.objects.filter(token_key="node-dentist").exists()


# ── Chat: one-off locations and a clear search/qualification preview ─


def test_chat_location_override_and_validation():
    from leadzen.chat.tools import engine_find_args
    args = engine_find_args({"count": 3, "targetOverrides": {"audience": "Dentists in Texas", "country": "US", "region": "Texas"}})
    assert args["location"] == {"country": "US", "region": "Texas"}
    with pytest.raises(ValueError, match="audience"):
        engine_find_args({"count": 3, "targetOverrides": {"country": "US", "region": "Texas"}})
    assert "location" not in engine_find_args({"count": 3})


def test_search_scope_says_what_changes_the_provider_search(discovery_client):
    from dataclasses import asdict
    from leadzen.configuration import effective, save_dashboard_settings
    from leadzen.lead_finder import search_scope
    save_target(AUDIENCE)
    saved = search_scope({"count": 1, "emails": False, "audience": ""})
    assert not saved["changes_search"] and "location Texas, United States" in saved["search"] and "1-10 employees" in saved["search"]
    override = search_scope({"count": 1, "emails": False, "audience": "Dentists in Texas", "location": {"country": "US", "region": "Texas"}})
    assert override["changes_search"] and "changes the BetterContact search" in override["search"] and "Texas, United States" in override["search"]
    loose = search_scope({"count": 1, "emails": False, "audience": "Dentists in Texas"})
    assert "only checked by AI qualification" in loose["search"]
    save_dashboard_settings(asdict(effective()), lead_finder_provider="ai_ark", ai_ark_api_key="synthetic-ark-key")
    ark = search_scope({"count": 1, "emails": False, "audience": ""})
    assert not ark["changes_search"] and "dental" in ark["search"] and "Texas, United States" in ark["search"]
    assert "cannot change an AI Ark search" in ark["search"] and "still charged" in ark["qualification"]


def test_chat_approval_preview_and_progress_carry_search_scope(discovery_client):
    from tests.test_ai_ark import start
    from dataclasses import asdict
    from leadzen.configuration import effective, save_dashboard_settings
    from leadzen.config.models import DiscoverySession
    from leadzen.discovery import progress_payload
    save_target(AUDIENCE)
    save_dashboard_settings(asdict(effective()), lead_finder_provider="ai_ark", ai_ark_api_key="synthetic-ark-key")
    row = start(discovery_client)
    session = DiscoverySession.objects.get(run=row)
    scope = progress_payload(session)["search_scope"]
    assert scope and "AI Ark searches your saved Target" in scope["search"]
    assert "AI Ark" in session.action["preview"]["search"]
