"""Bounded AI Ark adapter over LeadZen's existing finder and CRM records.

Official contract: https://docs.ai-ark.com/docs/ai-agents
No retries, bulk jobs, phone purchases, external list writes or provider fallback.
"""
import hashlib
import io
import json
import time
from decimal import Decimal
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Max

from leadzen.configuration import SettingsError, effective
from leadzen.config.models import DiscoveryLookup, DiscoverySearch, OnboardingState, SiteConfig

BASE = "https://api.ai-ark.com/api/developer-portal"
_last_request = 0.0


def request(method, path, body=None, *, values=None, receipt=None):
    from leadzen.ai import pinned_request
    from leadzen.chat.engine import assert_action_access
    global _last_request
    values = values or effective()
    if values.lead_finder_provider != "ai_ark" or not values.ai_ark_api_key:
        raise SettingsError("Connect AI Ark in Settings first")
    if (method, path) not in {("GET", "/v1/payments/credits"), ("POST", "/v1/people"), ("POST", "/v1/people/export/single")}:
        raise PermissionError("Unapproved AI Ark operation")
    if method == "POST":
        from leadzen.discovery_progress import current
        monitor = current()
        if not monitor:
            raise PermissionError("A paid provider request requires a discovery approval")
        authorize(monitor)
        # The transport consumes one persisted reservation for this exact payload.
        # A retry, arbitrary body or foreign session cannot reuse that capability.
        if not receipt or receipt.session_id != monitor.session.pk:
            raise PermissionError("This paid request has no owned reservation")
        if path == "/v1/people":
            if not isinstance(receipt, DiscoverySearch) or not isinstance(body, dict):
                raise PermissionError("Invalid search reservation")
            digest = hashlib.sha256(json.dumps({k: v for k, v in body.items() if k != "page"}, sort_keys=True).encode()).hexdigest()
            if body.get("size") != receipt.size or body.get("page") != receipt.page or digest != receipt.query_hash:
                raise PermissionError("The reserved search changed")
        else:
            from openoutfind.crm.models import Lead
            if not isinstance(receipt, DiscoveryLookup):
                raise PermissionError("Invalid email reservation")
            lead = Lead.objects.filter(pk=receipt.source_id, synthetic=False, disqualified=False).first()
            if not lead or body != {"url": linkedin(lead.profile_url)}:
                raise PermissionError("The reserved contact changed")
        if type(receipt).objects.filter(pk=receipt.pk, session=monitor.session, state="uncertain").update(state="submitting") != 1:
            raise PermissionError("This paid request was already attempted")
    time.sleep(max(0, .21 - (time.monotonic() - _last_request)))
    assert_action_access()
    _last_request = time.monotonic()
    status, headers, raw = pinned_request(method, BASE + path,
        {"X-TOKEN": values.ai_ark_api_key, "Accept": "application/json", "Content-Type": "application/json"},
        json.dumps(body).encode() if body is not None else b"", "api.ai-ark.com", kind="AI_ARK", timeout=30 if method == "POST" else 7)
    if status == 404 and method == "POST":
        return None
    if status != 200:
        raise SettingsError({401: "AI Ark rejected the API key", 402: "AI Ark has insufficient credits", 429: "AI Ark rate limit reached"}.get(status, "AI Ark did not complete the request; no automatic retry was made"))
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise SettingsError("AI Ark returned an unreadable response") from None
    if not isinstance(result, dict):
        raise SettingsError("AI Ark returned an invalid response")
    return result


def credit_balance(values=None):
    raw = request("GET", "/v1/payments/credits", values=values).get("total")
    try:
        value = Decimal(str(raw))
        if isinstance(raw, bool) or not value.is_finite() or value < 0:
            raise ValueError
    except (ValueError, ArithmeticError):
        raise SettingsError("AI Ark did not return a valid credit balance") from None
    return float(value)


def authorize(monitor):
    monitor.boundary()
    from django.utils import timezone
    from leadzen.config.models import ChatRun
    row = ChatRun.objects.get(pk=monitor.session.run_id)
    if not row.approval_expires_at or row.approval_expires_at <= timezone.now():
        raise PermissionError("The AI Ark approval expired")
    action = monitor.session.action
    from leadzen.lead_finder import budget
    maximum = budget(monitor.session.goal, monitor.session.unit == "emails", selected=bool(monitor.session.source_ids))
    if (action.get("approved") is not True or action.get("provider") != "ai_ark"
            or type(action.get("credits")) is not int or not maximum <= action["credits"] <= 25):
        raise PermissionError("Review and approve the AI Ark credit budget before searching")


def match(values, *, text=False):
    return {"any": {"include": {"mode": "WORD", "content": values} if text else values}}


def search_filters(audience):
    """Use saved structured targeting verbatim; never silently broaden a filter."""
    from pytz import country_names
    from leadzen.setup_wizard import SIZES, SENIORITY
    if not isinstance(audience, dict) or not audience.get("roles") or audience.get("country") not in country_names or not audience.get("industry"):
        raise SettingsError("Save a structured audience in Target before using AI Ark")
    if audience.get("company_size") not in SIZES or any(v not in SENIORITY for v in audience.get("seniority", [])):
        raise SettingsError("Review your audience size and seniority before using AI Ark")
    account = {"industries": match([audience["industry"]], text=True)}
    size = audience["company_size"]
    if size != "any":
        low, _, high = size.rstrip("+").partition("-")
        band = {"start": int(low)}
        if high:
            band["end"] = int(high)
        account["employeeSize"] = {"type": "RANGE", "range": [band]}
    contact = {"experience": {"latest": {"title": match(audience["roles"], text=True)}},
               "location": match([country_names[audience["country"]]])}
    if audience.get("seniority"):
        contact["seniority"] = match(audience["seniority"])
    return {"account": account, "contact": contact}


def linkedin(value):
    if not isinstance(value, str) or len(value) > 500:
        return ""
    try:
        p = urlsplit(value)
        if p.scheme == "https" and p.hostname in {"linkedin.com", "www.linkedin.com"} and p.path.startswith("/in/") and len(p.path.strip("/").split("/")) == 2 and not (p.username or p.password or p.query or p.fragment) and p.port in (None, 443):
            return "https://www.linkedin.com" + p.path.rstrip("/")
    except ValueError:
        pass
    return ""


def profile(person):
    if not isinstance(person, dict):
        raise SettingsError("AI Ark returned an invalid profile")
    def obj(value):
        return value if isinstance(value, dict) else {}
    p, link, location, company = [obj(person.get(k)) for k in ("profile", "link", "location", "company")]
    summary, company_link = obj(company.get("summary")), obj(company.get("link"))
    row = {"contact_linkedin_profile_url": linkedin(link.get("linkedin")), "contact_full_name": p.get("full_name"),
           "contact_job_title": p.get("title"), "contact_headline": p.get("headline"), "contact_industry": person.get("industry"),
           "contact_location_country": location.get("country"), "contact_location_state": location.get("state"),
           "contact_seniority": obj(person.get("department")).get("seniority"),
           "company_name": summary.get("name"), "company_domain": company_link.get("domain"), "company_industry": summary.get("industry")}
    row = {k: v[:2000] if isinstance(v, str) else "" for k, v in row.items()}
    # The existing qualification text omits headcount. Preserve evidence explicitly,
    # so the campaign rule can reject unknown company sizes rather than invent them.
    staff = obj(summary.get("staff"))
    row["qualification_evidence"] = json.dumps({"staff": staff, "description": summary.get("description")}, ensure_ascii=False)[:4000]
    return row


def search(monitor):
    authorize(monitor)
    session = monitor.session
    if session.source_ids:
        raise PermissionError("Selected email lookup cannot search for new profiles")
    receipt = DiscoverySearch.objects.filter(session=session).first()
    if receipt:
        if receipt.state != "terminated":
            raise PermissionError("An earlier AI Ark search is uncertain and will not be repeated")
        return receipt.profiles
    state = OnboardingState.objects.filter(pk=1).first()
    from leadzen.home import current_target
    filters = search_filters(current_target(SiteConfig.load(), state)["audience"])
    size = session.goal * 2
    query_hash = hashlib.sha256(json.dumps({**filters, "size": size}, sort_keys=True).encode()).hexdigest()
    with transaction.atomic(using=session._state.db):
        previous = DiscoverySearch.objects.filter(query_hash=query_hash).aggregate(last=Max("page"))["last"]
        page = 0 if previous is None else previous + 1
        if (page + 1) * size > 10000:
            raise SettingsError("AI Ark pagination limit reached; refine your audience")
        receipt = DiscoverySearch.objects.create(session=session, query_hash=query_hash, page=page, size=size)
    monitor.event("searching", {"provider": "AI Ark", "profiles_limit": size, "credits_limit": session.goal})
    response = request("POST", "/v1/people", {**filters, "page": page, "size": size}, receipt=receipt)
    rows = [] if response is None else response.get("content")
    if not isinstance(rows, list) or len(rows) > size:
        raise SettingsError("AI Ark returned an invalid search page")
    receipt.profiles = [profile(p) for p in rows]
    receipt.credits, receipt.state = Decimal(len(rows)) / 2, "terminated"
    receipt.save()
    monitor.event("search_completed", {"provider": "AI Ark", "profiles_returned": len(rows), "credits": float(receipt.credits)})
    return receipt.profiles


def enrich(monitor, lead):
    authorize(monitor)
    url = linkedin(lead.profile_url)
    if not url:
        raise SettingsError("AI Ark requires a valid LinkedIn person URL")
    if DiscoveryLookup.objects.filter(source_id=lead.pk).exists():
        # Missing handles/ambiguous responses are not permission for a second charge.
        return
    receipt = monitor.reserve_lookup({"data": [{"linkedin_url": lead.profile_url}], "enrich_email_address": True})
    result = request("POST", "/v1/people/export/single", {"url": url}, receipt=receipt)
    output = []
    if result is not None:
        if linkedin((result.get("link") or {}).get("linkedin")) != url:
            raise SettingsError("AI Ark returned a different profile; the email was not saved")
        block = result.get("email")
        if not isinstance(block, dict) or block.get("state") != "DONE" or not isinstance(block.get("output"), list):
            raise SettingsError("AI Ark did not return a completed email result")
        output = block["output"]
    valid = [e for e in output if isinstance(e, dict) and e.get("found") is True and e.get("status") == "VALID"]
    usable = [e for e in valid if e.get("domainType") == "SMTP" and e.get("free") is False and e.get("generic") is False]
    address = usable[0].get("address", "") if usable else ""
    if address:
        try:
            validate_email(address)
        except (ValidationError, TypeError):
            address = ""
    receipt.credits = Decimal(1 if valid else 0)
    receipt.state, receipt.email_status = "terminated", "valid" if address else "not_found"
    receipt.save()
    monitor.guard()
    if address:
        lead.email = address
        lead.save(update_fields=["email"])
        from openoutfind.core.db.deals import set_profile_state
        from openoutfind.crm.models import DealState
        set_profile_state(lead.profile_url, DealState.RESOLVED)
    monitor.event("email_lookup", {"provider": "AI Ark", "email_status": receipt.email_status, "credits": float(receipt.credits)})


def run(args, monitor):
    """One bounded page, existing qualification policy, same canonical CRM ingest."""
    from openoutfind.core.db.leads import create_lead, promote_lead_to_deal
    from openoutfind.core.db.deals import create_disqualified_deal
    from openoutfind.core.ml.qualifier import qualify_with_llm
    from openoutfind.core.export import lead_record
    from openoutfind.crm.models import Lead, Deal
    from cold_outreach.leads.ingest import ingest
    from leadzen.discovery_progress import DiscoveryPaused, _qualify_for_campaign, counts
    from leadzen.discovery import progress_payload
    from leadzen.home import QUALIFIED
    stored, partial, paused = 0, False, False
    try:
        if not monitor:
            raise PermissionError("An approved discovery session is required")
        authorize(monitor)
        session = monitor.session
        if args.get("audience"):
            raise SettingsError("Save your AI Ark audience in Target before starting a search")
        if not session.source_ids:
            for row in search(monitor):
                monitor.boundary()
                if not row["contact_linkedin_profile_url"]:
                    continue
                if create_lead(row):
                    lead = Lead.objects.get(profile_url=row["contact_linkedin_profile_url"])
                    lead.profile_text += "\nCompany evidence: " + row["qualification_evidence"]
                    lead.save(update_fields=["profile_text"])
                    monitor.discovered([lead])
            sources = list(session.candidates.filter(discovered=True).values_list("source_id", flat=True))
        else:
            sources = session.source_ids
        config = SiteConfig.load()
        for lead in Lead.objects.filter(pk__in=sources, synthetic=False, disqualified=False).select_related("company").order_by("pk"):
            monitor.boundary()
            if counts(session)["produced"] >= session.goal:
                break
            deal = Deal.objects.filter(lead=lead).first()
            if not deal:
                monitor.evaluating(lead)
                verdict, reason = _qualify_for_campaign(lead.profile_text, config.product_docs, session.target, qualify_with_llm)
                monitor.boundary()
                if verdict == 1:
                    promote_lead_to_deal(lead.profile_url, reason=reason)
                else:
                    create_disqualified_deal(lead.profile_url, reason=reason)
                deal = Deal.objects.get(lead=lead)
            monitor.verdict(lead)
            if deal.state not in QUALIFIED or deal.outcome == "wrong_fit":
                continue
            if args["emails"] and not lead.email:
                enrich(monitor, lead)
                deal.refresh_from_db()
            record = lead_record(deal)
            result = ingest(io.StringIO(json.dumps(record) + "\n"))
            stored += result.stored
            monitor.output(record)
        partial = counts(session)["produced"] < session.goal
    except DiscoveryPaused:
        paused = True
    except Exception:
        partial = True
        if monitor:
            monitor.event("provider_stopped", {"message": "AI Ark stopped. Completed results are kept; uncertain charges are not retried. Check your connection, balance and saved audience."})
    return {"stored": stored, "partial": partial, "paused": paused,
            "note": "AI Ark paused at a saved boundary." if paused else "AI Ark finished within the approved budget. Partial results are kept; no emails were sent.",
            **({"discovery": progress_payload(monitor.session), "workspaceUrl": f"/find-leads/{monitor.session.pk}"} if monitor else {})}
