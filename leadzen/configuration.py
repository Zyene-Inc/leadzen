"""Safe loading and application of settings edited in the private dashboard."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import OperationalError, ProgrammingError, transaction

from leadzen.config.models import RuntimeSettings, SiteConfig

ALLOWED_PROVIDERS = {"groq", "openai", "anthropic", "google", "mistral", "cohere", "openai_compatible"}
LLM_HOSTS = {"api.groq.com", "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com", "api.mistral.ai", "api.cohere.com"}
MAIL_HOSTS = {f"{protocol}.{domain}" for protocol in ("smtp", "smtppro", "imap", "imappro") for domain in ("zoho.com", "zoho.in", "zoho.eu", "zoho.com.au", "zoho.jp", "zoho.ca")}
MAIL_HOSTS |= {"smtp.gmail.com", "imap.gmail.com", "smtp.office365.com", "outlook.office365.com"}
MAIL_HOSTS |= {"smtp.resend.com", "smtp.sendgrid.net", "smtp.zeptomail.com", "smtp.zeptomail.in", "smtp.zeptomail.eu"}
EMAIL_HOSTS = {"api.resend.com", "api.sendgrid.com", "api.zeptomail.com", "api.zeptomail.in", "api.zeptomail.eu", "zeptomail.zoho.com", "cpaas.zoho.com"}


def approved_host(host: str, kind: str) -> None:
    defaults = LLM_HOSTS if kind == "LLM" else EMAIL_HOSTS if kind == "EMAIL" else MAIL_HOSTS
    extra = {item.strip().lower() for item in os.environ.get(f"LEADZEN_{kind}_HOSTS", "").split(",") if item.strip()}
    if host.lower() not in defaults | extra:
        raise SettingsError(f"This {kind.lower()} host is not approved. Contact support@zyene.com to approve the endpoint.")


class SettingsError(ValueError):
    """An operator-editable settings value is invalid or cannot be protected."""


def _fernet() -> Fernet:
    raw = os.environ.get("LEADZEN_SETTINGS_KEY", "").strip()
    if not raw:
        raise SettingsError("LEADZEN_SETTINGS_KEY is not configured on the API")
    try:
        return Fernet(raw.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise SettingsError("LEADZEN_SETTINGS_KEY is not a valid Fernet key") from exc


def _encode(secrets: dict[str, str]) -> str:
    # Keep empty values too: a dashboard "clear" must override any legacy value
    # that may still exist in SiteConfig, rather than silently resurrecting it.
    payload = json.dumps({key: value for key, value in secrets.items()}, separators=(",", ":"))
    return _fernet().encrypt(payload.encode("utf-8")).decode("ascii")


def _decode(token: str) -> dict[str, str]:
    if not token:
        return {}
    try:
        value = _fernet().decrypt(token.encode("ascii"))
        result = json.loads(value.decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingsError("Stored runtime credentials cannot be decrypted") from exc
    if not isinstance(result, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in result.items()):
        raise SettingsError("Stored runtime credentials are malformed")
    return result


@dataclass(frozen=True)
class EffectiveSettings:
    provider: str
    model: str
    base_url: str
    mailbox_address: str
    smtp_host: str
    smtp_port: str
    imap_host: str
    imap_port: str
    signature: str
    llm_api_key: str
    mailbox_password: str
    mail_transport: str = "smtp"
    mail_api_url: str = ""
    smtp_username: str = ""
    mail_api_key: str = ""
    imap_password: str = ""
    ai_enabled: bool = True
    bettercontact_api_key: str = ""
    ai_ark_api_key: str = ""
    lead_finder_provider: str = "bettercontact"


def _legacy_values(config: SiteConfig) -> dict[str, str]:
    provider, separator, model = config.ai_model.partition(":")
    if not separator:
        provider, model = "", config.ai_model
    return {
        "provider": provider,
        "model": model,
        "base_url": config.llm_api_base,
        "mailbox_address": config.mailbox_address,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "signature": config.signature,
        "llm_api_key": config.llm_api_key,
        "mailbox_password": config.mailbox_password,
        "bettercontact_api_key": config.bettercontact_api_key,
    }


def effective() -> EffectiveSettings:
    """Return dashboard values, falling back to the existing CLI wizard values."""
    config = SiteConfig.load()
    values = _legacy_values(config)
    try:
        runtime = RuntimeSettings.objects.filter(pk=1).first()
    except (OperationalError, ProgrammingError):
        runtime = None
    if runtime:
        for field, key in (
            ("llm_provider", "provider"), ("llm_model", "model"), ("llm_base_url", "base_url"),
            ("mailbox_address", "mailbox_address"), ("smtp_host", "smtp_host"),
            ("smtp_port", "smtp_port"), ("imap_host", "imap_host"), ("imap_port", "imap_port"),
            ("signature", "signature"),
            ("mail_transport", "mail_transport"), ("mail_api_url", "mail_api_url"),
            ("smtp_username", "smtp_username"),
            ("lead_finder_provider", "lead_finder_provider"),
        ):
            value = getattr(runtime, field)
            values[key] = "" if value is None else str(value)
        values["ai_enabled"] = runtime.ai_enabled
        if runtime.encrypted_secrets:
            values.update(_decode(runtime.encrypted_secrets))
    return EffectiveSettings(**values)


def _valid_url(value: str, field: str, kind="LLM") -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise SettingsError(f"{field} must be an HTTPS URL without embedded credentials, query or fragment")
    try:
        if parsed.port not in (None, 443):
            raise SettingsError("AI endpoint must use HTTPS port 443")
    except ValueError as exc:
        raise SettingsError("Invalid endpoint port") from exc
    approved_host(parsed.hostname, kind)
    return value.rstrip("/")


def validate_public(data: dict) -> dict[str, str | int | None]:
    if not isinstance(data, dict):
        raise SettingsError("settings must be an object")
    if any(not isinstance(data.get(key, ""), str) for key in ("provider", "model", "base_url", "mailbox_address", "smtp_host", "imap_host", "signature", "mail_transport", "mail_api_url", "smtp_username")):
        raise SettingsError("Connection fields must be text")
    provider = str(data.get("provider", "")).strip().lower()
    model = str(data.get("model", "")).strip()
    base_url = _valid_url(str(data.get("base_url", "")), "base_url")
    address = str(data.get("mailbox_address", "")).strip().lower()
    smtp_host = str(data.get("smtp_host", "")).strip()
    imap_host = str(data.get("imap_host", "")).strip()
    signature = str(data.get("signature", "")).strip()
    transport = data.get("mail_transport", "smtp")
    if transport not in {"smtp", "resend", "zeptomail", "sendgrid", "compatible"}:
        raise SettingsError("Choose a supported email transport")
    api_url = _valid_url(data.get("mail_api_url", ""), "Email API URL", "EMAIL")
    expected = {"resend": "https://api.resend.com/emails", "sendgrid": "https://api.sendgrid.com/v3/mail/send"}
    if transport in expected:
        if api_url and api_url != expected[transport]:
            raise SettingsError("Use the selected provider's official email endpoint")
        api_url = expected[transport]
    if transport == "zeptomail":
        api_url = api_url or "https://api.zeptomail.com/v1.1/email"
        if urlparse(api_url).hostname not in EMAIL_HOSTS - {"api.resend.com", "api.sendgrid.com"}:
            raise SettingsError("Use a Zoho ZeptoMail endpoint")
    if transport == "compatible" and not api_url:
        raise SettingsError("An approved Resend-compatible endpoint is required")
    ai_enabled = data.get("ai_enabled", True)
    if not isinstance(ai_enabled, bool):
        raise SettingsError("AI enabled must be a boolean")
    username = data.get("smtp_username", "").strip()
    if len(username) > 320 or any(ord(c) < 32 for c in username):
        raise SettingsError("SMTP username is invalid")
    if provider and provider not in ALLOWED_PROVIDERS:
        raise SettingsError("Unsupported provider")
    if len(model) > 200 or any(ord(char) < 32 for char in model):
        raise SettingsError("model is invalid")
    if address:
        try:
            validate_email(address)
        except ValidationError as exc:
            raise SettingsError("mailbox_address must be a valid email address") from exc
    if len(smtp_host) > 255 or len(imap_host) > 255 or len(signature) > 10000:
        raise SettingsError("mailbox settings are too long")
    for host in (smtp_host, imap_host):
        if host:
            approved_host(host, "MAIL")

    def port(name: str, default: int | None) -> int | None:
        value = data.get(name, default)
        if value in (None, ""):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError(f"{name} must be a port number") from exc
        if not 1 <= parsed <= 65535:
            raise SettingsError(f"{name} must be between 1 and 65535")
        return parsed

    if provider == "openai_compatible" and not base_url:
        raise SettingsError("base_url is required for openai_compatible")
    smtp_port, imap_port = port("smtp_port", None), port("imap_port", None)
    if smtp_port not in (None, 465, 587, 2525) or imap_port not in (None, 993):
        raise SettingsError("Use SMTP TLS port 465 or STARTTLS port 587/2525, and IMAP TLS port 993")
    return {
        "provider": provider, "model": model, "base_url": base_url, "mailbox_address": address,
        "smtp_host": smtp_host, "smtp_port": smtp_port, "imap_host": imap_host,
        "imap_port": imap_port, "signature": signature,
        "mail_transport": transport, "mail_api_url": api_url, "smtp_username": username,
        "ai_enabled": ai_enabled,
    }


def validate_bettercontact_key(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 2000:
        raise SettingsError("Lead provider API key must be text, at most 2000 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SettingsError("Lead provider API key cannot contain control characters")
    return value.strip()


def lead_finder_credentials(data: dict) -> tuple[str | None, bool]:
    """Validate before either setup path creates or updates a workspace."""
    finder = data.get("lead_finder", {})
    if not isinstance(finder, dict):
        raise SettingsError("lead_finder must be an object")
    validate_finder_provider(finder.get("provider", "bettercontact"))
    clear = finder.get("clear_api_key", False)
    if not isinstance(clear, bool):
        raise SettingsError("Lead finder clear_api_key must be a boolean")
    return validate_bettercontact_key(finder.get("api_key")), clear


def validate_finder_provider(value):
    if not isinstance(value, str) or value not in {"bettercontact", "ai_ark"}:
        raise SettingsError("Choose BetterContact or AI Ark for lead finding")
    return value


def finder_settings(body, current):
    key, clear = lead_finder_credentials(body)
    provider = validate_finder_provider(body.get("lead_finder", {}).get("provider", current.lead_finder_provider))
    return {"lead_finder_provider": provider, f"{provider}_api_key": key, f"clear_{provider}_api_key": clear}


def save_dashboard_settings(public: dict, *, llm_api_key: str | None = None, mailbox_password: str | None = None,
                            mail_api_key: str | None = None, imap_password: str | None = None,
                            bettercontact_api_key: str | None = None,
                            ai_ark_api_key: str | None = None, lead_finder_provider: str | None = None,
                            clear_llm_api_key: bool = False, clear_mailbox_password: bool = False,
                            clear_mail_api_key: bool = False, clear_imap_password: bool = False,
                            clear_bettercontact_api_key: bool = False, clear_ai_ark_api_key: bool = False) -> EffectiveSettings:
    normalized = validate_public(public)
    bettercontact_api_key = validate_bettercontact_key(bettercontact_api_key)
    ai_ark_api_key = validate_bettercontact_key(ai_ark_api_key)
    for value in (llm_api_key, mailbox_password, mail_api_key, imap_password):
        if value is not None and (not isinstance(value, str) or len(value) > 2000):
            raise SettingsError("Credentials must be text, at most 2000 characters")
        if value is not None and any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise SettingsError("Credentials cannot contain control characters")
    runtime = RuntimeSettings.load()
    current = effective()
    secrets = {"llm_api_key": current.llm_api_key, "mailbox_password": current.mailbox_password,
               "mail_api_key": current.mail_api_key, "imap_password": current.imap_password,
               "bettercontact_api_key": current.bettercontact_api_key, "ai_ark_api_key": current.ai_ark_api_key}
    runtime.lead_finder_provider = validate_finder_provider(lead_finder_provider or public.get("lead_finder_provider", current.lead_finder_provider))
    if (normalized["provider"], normalized["base_url"]) != (current.provider, current.base_url):
        secrets["llm_api_key"] = ""
    if (normalized["mailbox_address"], normalized["smtp_host"], normalized["imap_host"]) != (current.mailbox_address, current.smtp_host, current.imap_host):
        secrets["mailbox_password"] = ""
        secrets["imap_password"] = ""
    if (normalized["mail_transport"], normalized["mail_api_url"], normalized["mailbox_address"]) != (current.mail_transport, current.mail_api_url, current.mailbox_address):
        secrets["mail_api_key"] = ""
    if clear_llm_api_key:
        secrets["llm_api_key"] = ""
    elif llm_api_key:
        secrets["llm_api_key"] = llm_api_key.strip()
    if clear_mailbox_password:
        secrets["mailbox_password"] = ""
    elif mailbox_password:
        secrets["mailbox_password"] = mailbox_password.strip()
    for name, value, clear in (("mail_api_key", mail_api_key, clear_mail_api_key), ("imap_password", imap_password, clear_imap_password)):
        if clear:
            secrets[name] = ""
        elif value:
            secrets[name] = value.strip()
    if clear_bettercontact_api_key:
        secrets["bettercontact_api_key"] = ""
    elif bettercontact_api_key:
        secrets["bettercontact_api_key"] = bettercontact_api_key
    if clear_ai_ark_api_key:
        secrets["ai_ark_api_key"] = ""
    elif ai_ark_api_key:
        secrets["ai_ark_api_key"] = ai_ark_api_key
    if any(len(value) > 2000 for value in secrets.values()):
        raise SettingsError("credential is too long")
    runtime.llm_provider = str(normalized["provider"])
    runtime.llm_model = str(normalized["model"])
    runtime.llm_base_url = str(normalized["base_url"])
    runtime.mailbox_address = str(normalized["mailbox_address"])
    runtime.smtp_host = str(normalized["smtp_host"])
    runtime.smtp_port = normalized["smtp_port"]
    runtime.imap_host = str(normalized["imap_host"])
    runtime.imap_port = normalized["imap_port"]
    runtime.signature = str(normalized["signature"])
    runtime.mail_transport = normalized["mail_transport"]
    runtime.mail_api_url = normalized["mail_api_url"]
    runtime.smtp_username = normalized["smtp_username"]
    runtime.ai_enabled = normalized["ai_enabled"]
    runtime.encrypted_secrets = _encode(secrets)
    with transaction.atomic(using=runtime._state.db):
        runtime.save()
        # These legacy CLI credentials are now held in encrypted storage. Do not
        # retain plaintext copies or resurrect a cleared dashboard connection.
        SiteConfig.objects.filter(pk=1).update(bettercontact_api_key="", llm_api_key="", mailbox_password="")
    from leadzen.mailboxes import sync_dashboard_mailbox
    sync_dashboard_mailbox()
    return effective()


def apply_dashboard_overrides() -> None:
    """Override wizard exports with dashboard settings for this process/run."""
    try:
        values = effective()
        runtime = RuntimeSettings.objects.filter(pk=1).first()
    except (OperationalError, ProgrammingError):
        return
    model = f"{values.provider}:{values.model}" if values.provider and values.model else ""
    overrides = {
        "OPENOUTFIND_AI_MODEL": model,
        "OUTSEND_AI_MODEL": model,
        "OPENOUTFIND_LLM_API_KEY": values.llm_api_key,
        "OUTSEND_LLM_API_KEY": values.llm_api_key,
        "OPENOUTFIND_LLM_API_BASE": values.base_url,
        "OUTSEND_LLM_API_BASE": values.base_url,
        "OUTSEND_MAILBOX_ADDRESS": values.mailbox_address,
        "OUTSEND_MAILBOX_PASSWORD": values.mailbox_password,
        "OUTSEND_SMTP_HOST": values.smtp_host,
        "OUTSEND_SMTP_PORT": str(values.smtp_port or ""),
        "OUTSEND_IMAP_HOST": values.imap_host,
        "OUTSEND_IMAP_PORT": str(values.imap_port or ""),
        "OUTSEND_SIGNATURE": values.signature,
    }
    for variable, value in overrides.items():
        if value:
            os.environ[variable] = value
        elif runtime:
            # An explicit dashboard clear overrides both wizard exports and
            # ambient values from an earlier run in this process.
            os.environ.pop(variable, None)
    if runtime and "bettercontact_api_key" in _decode(runtime.encrypted_secrets):
        if values.bettercontact_api_key and values.lead_finder_provider == "bettercontact":
            os.environ["OPENOUTFIND_BETTERCONTACT_API_KEY"] = values.bettercontact_api_key
            os.environ["OPENOUTFIND_EMAIL_FINDER"] = "bettercontact"
        else:
            os.environ.pop("OPENOUTFIND_BETTERCONTACT_API_KEY", None)
    # An explicit choice must never fall back to an ambient upstream provider.
    if runtime:
        os.environ["OPENOUTFIND_EMAIL_FINDER"] = values.lead_finder_provider
    if values.lead_finder_provider != "bettercontact":
        os.environ.pop("OPENOUTFIND_BETTERCONTACT_API_KEY", None)
