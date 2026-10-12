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


def search_scope(args, values=None):
    """What the provider search uses, versus what only AI qualification checks."""
    from leadzen.config.models import OnboardingState, SiteConfig
    from leadzen.geo import place
    from leadzen.home import current_target
    values = values or effective()
    location = args.get("location") or {}
    if values.lead_finder_provider == "ai_ark":
        from leadzen.ai_ark import describe
        saved = current_target(SiteConfig.load(), OnboardingState.objects.filter(pk=1).first())["audience"]
        return {"changes_search": False,
                "search": "AI Ark searches your saved Target only: " + (describe(saved) if saved else "save a structured Target first") + ". A Chat request cannot change an AI Ark search; update Target to change it.",
                "qualification": "AI then checks each returned profile against your saved Target. Rejected profiles are still charged."}
    if args.get("audience"):
        where = f" restricted to {place(location)}" if location.get("country") else "; no location filter was given, so location is only checked by AI qualification"
        return {"changes_search": True,
                "search": f"This request changes the BetterContact search: it builds a separate search for this audience{where}. Your saved Target's search is kept and restored next time.",
                "qualification": "AI then checks each returned profile against this request's audience."}
    from leadzen.search_plan import spec
    value = spec({})
    filters = [f"location {value['place']}" if value["place"] else "",
               (f"{value['headcount'][0]}+ employees" if value["headcount"][1] >= 1_000_000 else f"{value['headcount'][0]}-{value['headcount'][1]} employees") if value["headcount"] else "",
               "seniority " + ", ".join(value["seniority"]) if value["seniority"] else ""]
    return {"changes_search": False,
            "search": "BetterContact searches your saved Target: job-title keywords come from the Target" + "".join(f"; {f}" for f in filters if f) + ".",
            "qualification": "AI then checks each returned profile against your saved Target."}
