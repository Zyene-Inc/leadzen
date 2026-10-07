"""Employee setup: bounded probes, private receipts and resumable public answers.

No test sends an email, performs discovery or purchases an enrichment. Only the
AI test invokes a model. Credentials are saved encrypted after successful probes.
"""
import asyncio
import hashlib
import hmac
import json
import math
import os
from dataclasses import asdict
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pytz import country_names

from leadzen.accounts.models import LoginThrottle
from leadzen.accounts.service import access, audit, email_address, error, payload, session_user
from leadzen.config.models import OnboardingState, SiteConfig
from leadzen.configuration import EffectiveSettings, SettingsError, _fernet, effective, save_dashboard_settings, validate_public
from leadzen import workspaces
from leadzen.configuration import finder_settings
from leadzen.lead_finder import key as finder_key, label as finder_label

KINDS = {1: "ai", 2: "discovery", 4: "mailbox"}
SENIORITY = {"owner", "founder", "c_suite", "partner", "vp", "head", "director", "manager", "senior", "mid-level", "entry", "intern"}
SIZES = {"any", "1-10", "2-50", "11-50", "51-200", "201-500", "501+"}


def text(value, label, maximum, *, required=True):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise SettingsError(f"{label} is invalid or too long")
    value = value.strip()
    if required and not value:
        raise SettingsError(f"{label} is required")
    return value


def secret(value):
    result = text("" if value is None else value, "Credential", 2000, required=False)
    if any(ord(c) < 32 or ord(c) == 127 for c in result):
        raise SettingsError("Credentials cannot contain control characters")
    return result


def candidate(body, kind):
    current = effective()
    values = asdict(current)
    if kind == "ai":
        llm = body.get("llm", {})
        if not isinstance(llm, dict):
            raise SettingsError("Enter valid AI settings")
        values.update(provider=llm.get("provider", current.provider), model=llm.get("model", current.model), base_url=llm.get("base_url", current.base_url), ai_enabled=llm.get("enabled", current.ai_enabled))
        key = secret(llm.get("api_key"))
        if not isinstance(values["base_url"], str):
            raise SettingsError("AI base URL must be text")
        same = (values["provider"], values["base_url"].rstrip("/")) == (current.provider, current.base_url.rstrip("/"))
        values["llm_api_key"] = key or (current.llm_api_key if same else "")
    elif kind == "discovery":
        change = finder_settings(body, current)
        provider = change["lead_finder_provider"]
        field = f"{provider}_api_key"
        values["lead_finder_provider"] = provider
        values[field] = "" if change[f"clear_{field}"] else change[field] or getattr(current, field)
    else:
        mailbox = body.get("mailbox", {})
        if not isinstance(mailbox, dict):
            raise SettingsError("Enter valid mailbox settings")
        for submitted, stored in [("address", "mailbox_address"), ("transport", "mail_transport"), ("api_url", "mail_api_url"), ("signature", "signature"), ("smtp_host", "smtp_host"), ("smtp_port", "smtp_port"), ("smtp_username", "smtp_username"), ("imap_host", "imap_host"), ("imap_port", "imap_port")]:
            if submitted in mailbox:
                values[stored] = mailbox[submitted]
        same = (values["mailbox_address"], values["smtp_host"], values["imap_host"]) == (current.mailbox_address, current.smtp_host, current.imap_host)
        values["mailbox_password"] = secret(mailbox.get("password")) or (current.mailbox_password if same else "")
        values["imap_password"] = secret(mailbox.get("imap_password")) or (current.imap_password if same else "")
        same_api = (values["mailbox_address"], values["mail_transport"], values["mail_api_url"]) == (current.mailbox_address, current.mail_transport, current.mail_api_url)
        values["mail_api_key"] = secret(mailbox.get("api_key")) or (current.mail_api_key if same_api else "")
    public = validate_public(values)
    public["smtp_port"], public["imap_port"] = str(public["smtp_port"] or ""), str(public["imap_port"] or "")
    return EffectiveSettings(**{**values, **public})


def fingerprint(values, kind):
    fields = {
        "ai": ["ai_enabled", "provider", "model", "base_url", "llm_api_key"],
        "discovery": ["lead_finder_provider", f"{values.lead_finder_provider}_api_key"],
        "mailbox": ["mail_transport", "mail_api_url", "mail_api_key", "mailbox_address", "smtp_host", "smtp_port", "smtp_username", "mailbox_password", "imap_host", "imap_port", "imap_password", "signature"],
    }[kind]
    data = json.dumps({field: getattr(values, field) for field in fields}, sort_keys=True).encode()
    return hmac.new(os.environ["LEADZEN_SETTINGS_KEY"].encode(), data, hashlib.sha256).hexdigest()


def checked(state, values, kind):
    receipt = state.checks.get(kind, {})
    return receipt.get("expires_at", "") > timezone.now().isoformat() and hmac.compare_digest(receipt.get("fingerprint", ""), fingerprint(values, kind))


def save_candidate(values):
    return save_dashboard_settings(asdict(values), llm_api_key=values.llm_api_key, mailbox_password=values.mailbox_password, mail_api_key=values.mail_api_key, imap_password=values.imap_password, bettercontact_api_key=values.bettercontact_api_key, ai_ark_api_key=values.ai_ark_api_key)


def probe_ai(values):
    from pydantic_ai import Agent
    from pydantic_ai.usage import UsageLimits
    from leadzen.ai import build_model
    async def run():
        agent = Agent(build_model(values.provider, values.model, values.llm_api_key, values.base_url, request_timeout=5), retries=0)
        model_settings = {"max_tokens": 256}
        if values.provider == "groq" and values.model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}:
            model_settings["groq_reasoning_effort"] = "low"
        async with agent:
            result = await asyncio.wait_for(agent.run("Connection check only. Reply with the single word OK.", model_settings=model_settings, usage_limits=UsageLimits(request_limit=1)), timeout=7)
        if not isinstance(result.output, str) or not result.output.strip():
            raise SettingsError("The model did not answer")
    asyncio.run(run())
    return {"answered": True}


def probe_discovery(values):
    from leadzen.ai import pinned_request
    if values.lead_finder_provider == "ai_ark":
        from leadzen.ai_ark import credit_balance
        return {"credits": credit_balance(values)}
    status, _, raw = pinned_request("GET", "https://app.bettercontact.rocks/api/v2/account", {"X-API-Key": values.bettercontact_api_key, "Accept": "application/json", "User-Agent": "Mozilla/5.0"}, b"", "app.bettercontact.rocks", kind="BETTERCONTACT", timeout=7)
    if status != 200:
        raise SettingsError("BetterContact did not accept the connection")
    result = json.loads(raw)
    raw_credits = result.get("credits_left") if isinstance(result, dict) else None
    if isinstance(raw_credits, bool):
        raise SettingsError("Credit balance was not returned")
    credits = float(raw_credits)
    if not math.isfinite(credits) or credits < 0:
        raise SettingsError("Credit balance was not returned")
    return {"credits": int(credits)}


def probe_mailbox(values):
    from leadzen.transports import smtp_class, imap_class
    # Authenticate and read only INBOX selection metadata, not message contents.
    # The SMTP probe never calls sendmail, send_message, DATA or MAIL FROM.
    smtp = False
    if values.mail_transport == "smtp":
        with smtp_class()(values.smtp_host, int(values.smtp_port or 587), timeout=4) as client:
            client.starttls()
            client.login(values.smtp_username or values.mailbox_address, values.mailbox_password)
        smtp = True
    with imap_class()(values.imap_host, int(values.imap_port or 993), timeout=4) as client:
        client.login(values.mailbox_address, values.imap_password or values.mailbox_password)
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise SettingsError("INBOX access failed")
    return {"smtp": smtp, "imap": True}


def state_payload(state, actor):
    from leadzen.web import _settings_payload
    current = effective()
    checks = {}
    for kind in KINDS.values():
        receipt = state.checks.get(kind, {})
        checks[kind] = {key: value for key, value in receipt.items() if key not in {"fingerprint", "expires_at"}}
        checks[kind]["connected"] = checked(state, current, kind)
    config = SiteConfig.load()
    defaults = {"operator_name": actor.first_name, "operator_email": actor.email, "operator_country_code": config.operator_country_code or "US", "purpose": actor.leadzen_profile.purpose or "other", "workspace_name": actor.leadzen_profile.workspace_name, "product_name": "", "product_docs": config.product_docs, "booking_link": config.booking_link, "legacy_target": config.campaign_target, "discovery_enabled": True}
    return {"draft": {**defaults, **state.draft}, "completed_steps": state.completed_steps, "checks": checks, "connections": _settings_payload(), "countries": [{"code": code, "name": name} for code, name in sorted(country_names.items(), key=lambda row: row[1])], "onboarded": actor.leadzen_profile.onboarding_completed_at is not None}


def validate_booking_link(value):
    booking = text(value, "Booking link", 500, required=False)
    if booking:
        from urllib.parse import urlparse
        parsed = urlparse(booking)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise SettingsError("Booking link must be an HTTPS URL without credentials")
    return booking


def validate_step(step, values, state, settings):
    if step == 1:
        if settings.ai_enabled and not checked(state, settings, "ai"):
            raise PermissionError("Test this AI connection before continuing")
        return {}
    if step == 2:
        enabled = values.get("discovery_enabled", True)
        if not isinstance(enabled, bool):
            raise SettingsError("Choose whether to enable discovery")
        if enabled and not checked(state, settings, "discovery"):
            raise PermissionError("Test your selected lead provider before continuing, or choose manual contacts")
        return {"discovery_enabled": enabled}
    if step == 3:
        name = text(values.get("operator_name"), "Your name", 200)
        if "@" in name or "\n" in name:
            raise SettingsError("Name cannot look like an email address")
        country = values.get("operator_country_code")
        if not isinstance(country, str) or country not in country_names:
            raise SettingsError("Select a valid operating country")
        return {"operator_name": name, "operator_email": email_address(values.get("operator_email")), "operator_country_code": country}
    if step == 4:
        if not checked(state, settings, "mailbox"):
            raise PermissionError("Test this mailbox before continuing")
        return {}
    if step == 5:
        if not isinstance(values.get("purpose"), str) or values["purpose"] not in {"zyene_reviews", "zyene_services", "other"}:
            raise SettingsError("Choose an outreach purpose")
        booking = validate_booking_link(values.get("booking_link", ""))
        return {"purpose": values["purpose"], "workspace_name": text(values.get("workspace_name"), "Workspace name", 160), "product_name": text(values.get("product_name"), "Product name", 160), "product_docs": text(values.get("product_docs"), "Product description", 10000), "booking_link": booking}
    audience = values.get("audience")
    if not isinstance(audience, dict) or not isinstance(audience.get("country"), str) or audience["country"] not in country_names or not isinstance(audience.get("company_size"), str) or audience["company_size"] not in SIZES:
        raise SettingsError("Choose a valid audience country and company size")
    roles, seniority = audience.get("roles"), audience.get("seniority")
    if not isinstance(roles, list) or not 1 <= len(roles) <= 20 or any(not isinstance(role, str) for role in roles) or len(set(roles)) != len(roles):
        raise SettingsError("Choose at least one target role")
    roles = [text(role, "Target role", 100) for role in roles]
    if len(set(roles)) != len(roles) or any("\n" in role or "\t" in role for role in roles):
        raise SettingsError("Choose distinct, single-line target roles")
    if not isinstance(seniority, list) or not seniority or any(not isinstance(level, str) or level not in SENIORITY for level in seniority) or len(set(seniority)) != len(seniority):
        raise SettingsError("Choose valid seniority levels")
    normalized = {"industry": text(audience.get("industry"), "Industry", 300), "country": audience["country"], "company_size": audience["company_size"], "roles": roles, "seniority": seniority, "instructions": text(audience.get("instructions", ""), "Additional instructions", 5000, required=False)}
    if values.get("confirmed") is not True or values.get("accepted_legal_notice") is not True:
        raise SettingsError("Review the target preview and confirm your authorization")
    return {"audience": normalized, "confirmed": True, "accepted_legal_notice": True}


def target_preview(audience):
    size = "any company size" if audience["company_size"] == "any" else f"{audience['company_size']} employees"
    return f"Find {', '.join(audience['roles'])} working at {audience['industry']} in {country_names[audience['country']]}, {size}. Seniority: {', '.join(audience['seniority'])}. {audience['instructions']}".strip()


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@access()
def wizard(request):
    body = payload(request) if request.method == "PUT" else {}
    if request.method == "PUT" and (type(body.get("step")) is not int or body["step"] not in range(1, 7) or not isinstance(body.get("values"), dict)):
        return error("Choose a valid setup step")
    _fernet()
    workspaces.initialize_workspace(request.actor.leadzen_profile)
    with workspaces.workspace_scope(request.actor.leadzen_profile):
        state, _ = OnboardingState.objects.get_or_create(pk=1)
        if request.method == "PUT":
            step = body["step"]
            if any(previous not in state.completed_steps for previous in range(1, step)):
                return error("Complete the earlier setup steps first", 409)
            settings = candidate(body, KINDS[step]) if step in KINDS else effective()
            try:
                changes = validate_step(step, body["values"], state, settings)
            except PermissionError as exc:
                return error(str(exc), 409)
            if step == 1 and not settings.ai_enabled:
                save_candidate(settings)
            state.draft.update(changes)
            state.completed_steps = sorted(set([*state.completed_steps, step]))
            state.save()
        return JsonResponse(state_payload(state, request.actor))


@csrf_exempt
@require_http_methods(["POST"])
@access()
def test_connection(request):
    body = payload(request)
    kind = body.get("kind")
    if kind not in KINDS.values():
        return error("Choose AI, discovery or mailbox test")
    _fernet()
    workspaces.initialize_workspace(request.actor.leadzen_profile)
    with workspaces.workspace_scope(request.actor.leadzen_profile) as alias:
        baseline = asdict(effective())
        values = candidate(body, kind)
        if kind == "ai" and (not values.ai_enabled or not values.llm_api_key or not values.model):
            return error("Enter an AI provider, model and API key")
        if kind == "discovery" and not finder_key(values):
            return error(f"Enter your {finder_label(values)} API key")
        if kind == "mailbox" and (not values.mailbox_address or not values.imap_host or not (values.imap_password or values.mailbox_password) or (values.mail_transport == "smtp" and (not values.smtp_host or not values.mailbox_password)) or (values.mail_transport != "smtp" and not values.mail_api_key)):
            return error("Connect your sender and its IMAP inbox with the required credentials")
        state, _ = OnboardingState.objects.get_or_create(pk=1)
        lease_until = timezone.now() + timedelta(seconds=45)
        if OnboardingState.objects.filter(pk=1).filter(Q(testing_until__isnull=True) | Q(testing_until__lt=timezone.now())).update(testing_until=lease_until) != 1:
            return error("Another connection test is running. Try again shortly.", 409)
        try:
            # Retesting replaces, never extends, an old proof of connectivity.
            state.refresh_from_db()
            state.checks.pop(kind, None)
            state.save(update_fields=["checks", "updated_at"])
            key = hashlib.sha256(f"setup-test/{request.actor.pk}/{kind}".encode()).hexdigest()
            with transaction.atomic(using="default"):
                counter, _ = LoginThrottle.objects.using("default").get_or_create(key=key, defaults={"window_started_at": timezone.now()})
                if counter.window_started_at < timezone.now() - timedelta(minutes=15):
                    counter.attempts, counter.window_started_at = 0, timezone.now()
                    counter.save(using="default")
                if LoginThrottle.objects.using("default").filter(pk=key, attempts__lt=30).update(attempts=F("attempts") + 1) != 1:
                    return error("Too many connection tests. Try again in 15 minutes.", 429)
            result = {"ai": probe_ai, "discovery": probe_discovery, "mailbox": probe_mailbox}[kind](values)
            live_user = session_user(request)
            if live_user is None or live_user.leadzen_profile.must_change_password:
                return error("Your account access changed. Sign in again.", 401)
            with transaction.atomic(using=alias):
                state.refresh_from_db()
                if state.testing_until != lease_until or asdict(effective()) != baseline:
                    return error("Settings changed during the test. Review them and test again.", 409)
                saved = save_candidate(values)
                state.checks[kind] = {**result, "fingerprint": fingerprint(saved, kind), "expires_at": (timezone.now() + timedelta(hours=24)).isoformat(), "tested_at": timezone.now().isoformat()}
                state.save(update_fields=["checks", "updated_at"])
            return JsonResponse(state_payload(state, request.actor))
        except Exception:
            # Never echo SDK/server exception messages, credentials or mailbox data.
            return error({"ai": "AI connection failed. Check the key, model and approved endpoint.", "discovery": f"{finder_label(values)} connection failed. Check the API key and account access.", "mailbox": "Mailbox test failed. Check SMTP/IMAP, app passwords and INBOX access."}[kind])
        finally:
            OnboardingState.objects.filter(pk=1, testing_until=lease_until).update(testing_until=None)


@csrf_exempt
@require_http_methods(["POST"])
@access()
def complete(request):
    workspaces.initialize_workspace(request.actor.leadzen_profile)
    with workspaces.workspace_scope(request.actor.leadzen_profile) as alias:
        state = OnboardingState.objects.filter(pk=1).first()
        if state is None or state.completed_steps != list(range(1, 7)):
            return error("Complete all six setup steps first", 409)
        settings = effective()
        try:
            for step in range(1, 7):
                validate_step(step, state.draft, state, settings)
        except PermissionError as exc:
            return error(str(exc), 409)
        with transaction.atomic(using=alias):
            config = SiteConfig.load()
            config.product_docs = state.draft["product_name"] + "\n\n" + state.draft["product_docs"]
            config.campaign_target = target_preview(state.draft["audience"])
            config.operator_name = state.draft["operator_name"]
            config.operator_email = state.draft["operator_email"]
            config.operator_country_code = state.draft["operator_country_code"]
            config.booking_link = state.draft["booking_link"]
            config.accepted_legal_notice = True
            config.save()
        profile = request.actor.leadzen_profile
        profile.purpose, profile.workspace_name = state.draft["purpose"], state.draft["workspace_name"]
        profile.onboarding_completed_at = timezone.now()
        profile.save(using="default")
        audit(request.actor, "workspace_wizard_completed", request.actor.pk)
        return JsonResponse({"ok": True, "target_preview": config.campaign_target})
