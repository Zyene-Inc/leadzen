"""Employee-scoped provider selection; never silently switch billing accounts."""
from leadzen.configuration import effective

LABELS = {"bettercontact": "BetterContact", "ai_ark": "AI Ark"}


def key(values=None):
    values = values or effective()
    return getattr(values, f"{values.lead_finder_provider}_api_key")


def label(values=None):
    return LABELS[(values or effective()).lead_finder_provider]


def public(values=None):
    values = values or effective()
    return {"provider": values.lead_finder_provider, "name": label(values),
            "api_key_configured": bool(key(values)),
            "configured_providers": {p: bool(getattr(values, f"{p}_api_key")) for p in LABELS}}


def budget(count, emails=False, *, selected=False, values=None):
    # At most two raw AI Ark profiles per requested qualified contact. Rejected
    # and duplicate profiles are billable too; a full result set isn't promised.
    values = values or effective()
    return (count if values.lead_finder_provider == "ai_ark" and not selected else 0) + (count if emails else 0)
