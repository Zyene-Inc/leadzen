"""Read-only home facts from the employee's routed finder and sender databases."""
import hmac

from django.db import transaction
from django.db.models import CharField, Exists, OuterRef, Q
from django.db.models.functions import Cast, Lower, Trim
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pytz import country_names

from cold_outreach.emails.models import Direction, Message
from cold_outreach.leads.models import Lead as Contact
from openoutfind.crm.models import Deal, DealState, Lead
from leadzen.accounts.service import access, audit, payload
from leadzen.config.models import OnboardingState, SiteConfig
from leadzen.configuration import effective
from leadzen.setup_wizard import fingerprint, target_preview, validate_step

QUALIFIED = (DealState.QUALIFIED, DealState.READY_TO_FIND_EMAIL, DealState.FINDING_EMAIL, DealState.RESOLVED, DealState.NO_EMAIL_FOUND)


def current_target(config, state):
    # A partially edited wizard must not masquerade as the active engine target.
    audience = state.draft.get("audience") if state else None
    try:
        if not audience or target_preview(audience) != config.campaign_target:
            audience = None
    except (KeyError, TypeError):
        audience = None
    return {"summary": config.campaign_target, "audience": audience,
            "country_name": country_names.get(audience["country"], "") if audience else ""}


def summary():
    config, values = SiteConfig.load(), effective()
    state = OnboardingState.objects.filter(pk=1).first()
    deleted = Contact.objects.filter(preferences__deleted_at__isnull=False).filter(
        Q(lead_id=Cast(OuterRef("pk"), CharField())) |
        (Q(email__iexact=OuterRef("email")) & ~Q(email="")))
    profiles = Lead.objects.filter(synthetic=False).alias(deleted=Exists(deleted)).filter(deleted=False)
    decisions = Deal.objects.filter(lead__in=profiles)
    qualified = decisions.filter(state__in=QUALIFIED, lead__disqualified=False).exclude(outcome="wrong_fit")
    accepted = Message.objects.filter(direction=Direction.OUTBOUND, delivery_events__status="accepted")
    replies = Message.objects.filter(direction=Direction.INBOUND, kind="human_reply", thread_id__in=accepted.exclude(thread_id=None).values("thread_id"))
    credits = {"configured": bool(values.bettercontact_api_key), "balance": None, "checked_at": None, "synthetic": False}
    receipt = state.checks.get("discovery", {}) if state else {}
    if values.bettercontact_api_key and receipt and hmac.compare_digest(receipt.get("fingerprint", ""), fingerprint(values, "discovery")):
        # This is a dated balance, not a claim that the connection or balance is live.
        credits.update(balance=receipt.get("credits"), checked_at=receipt.get("tested_at"), synthetic=receipt.get("synthetic", False))
    activity = []
    for decision in decisions.filter(Q(state__in=QUALIFIED) | Q(state=DealState.FAILED, outcome="wrong_fit")).select_related("lead").order_by("-creation_date", "-pk")[:8]:
        lead = decision.lead
        status = "excluded" if lead.disqualified else "rejected" if decision.state == DealState.FAILED or decision.outcome == "wrong_fit" else "qualified"
        activity.append({"id": decision.pk, "name": lead.full_name or " ".join(filter(None, [lead.first_name, lead.last_name])) or f"Profile {lead.pk}", "status": status, "reason": decision.reason, "at": decision.creation_date.isoformat()})
    return {
        "operator_name": config.operator_name,
        "metrics": {
            "found": profiles.count(),
            "qualified": qualified.count(),
            "with_email": qualified.exclude(lead__email__isnull=True).exclude(lead__email="").count(),
            "contacted": accepted.annotate(address=Lower(Trim("to_address"))).exclude(address="").values("address").distinct().count(),
            "replies": replies.annotate(address=Lower(Trim("from_address"))).exclude(address="").values("address").distinct().count(),
        },
        "credits": credits,
        "target": current_target(config, state),
        "recent_activity": activity,
    }


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@access(workspace=True)
def target(request):
    alias = SiteConfig.objects.all().db
    if request.method == "PUT":
        changes = validate_step(6, payload(request), None, None)
        with transaction.atomic(using=alias):
            config = SiteConfig.load()
            config.campaign_target = target_preview(changes["audience"])
            config.save(update_fields=["campaign_target"])
            state, _ = OnboardingState.objects.get_or_create(pk=1)
            state.draft.update(changes)
            state.save(update_fields=["draft", "updated_at"])
        audit(request.actor, "workspace_target_updated", request.actor.pk)
    config = SiteConfig.load()
    state = OnboardingState.objects.filter(pk=1).first()
    result = current_target(config, state)
    return JsonResponse({**result, "countries": [{"code": code, "name": name} for code, name in sorted(country_names.items(), key=lambda row: row[1])], "accepted_legal_notice": config.accepted_legal_notice})
