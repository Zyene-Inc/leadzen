"""Terminal, employee-scoped address blocking shared by the two manual controls."""
from django.db import transaction

from cold_outreach.leads.models import Deal, DealState, Outcome, Suppression
from leadzen.accounts.service import email_address
from leadzen.config.models import CampaignRecipient


def record_payload(record):
    return {"id": record.pk, "email": record.email, "reason": record.reason, "suppressed_at": record.suppressed_at.isoformat()}


def opt_out_evidence(address):
    """A suppression keeps its first reason, so check what later arrived as well."""
    from cold_outreach.emails.delivery_policy import address_is_dead
    from cold_outreach.emails.models import DeliveryEvent, Direction, Kind, Message
    from leadzen.outreach import EXACT_STOP
    inbound = Message.objects.filter(direction=Direction.INBOUND, from_address__iexact=address)
    if inbound.filter(kind=Kind.OPT_OUT).exists() or inbound.filter(to_address__icontains="+unsub@").exists():
        return True
    if any(EXACT_STOP.fullmatch(body or "") for body in inbound.values_list("body_text", flat=True).iterator()):
        return True
    bounces = DeliveryEvent.objects.filter(message__to_address__iexact=address, status=DeliveryEvent.Status.BOUNCED)
    return any(address_is_dead(status) for status in bounces.values_list("enhanced_status", flat=True))


def block_address(address, reason="Manually suppressed"):
    email = email_address(address)
    if not isinstance(reason, str) or len(reason) > 200 or any(ord(c) < 32 for c in reason):
        raise ValueError("Enter a reason of up to 200 characters without control characters")
    with transaction.atomic(using=Suppression.objects.all().db):
        # Preserve the first reason/date, including historical mixed-case records.
        record = Suppression.objects.filter(email=email).first() or Suppression.objects.filter(email__iexact=email).order_by("suppressed_at", "pk").first()
        created = record is None
        if created:
            record, created = Suppression.objects.get_or_create(email=email, defaults={"reason": reason.strip() or "Manually suppressed"})
        elif record.email != email:
            # The upstream import gate queries the canonical address exactly.
            # Retain the original ID, reason and timestamp while making it usable.
            record.email = email
            record.save(update_fields=["email"])
        deals = Deal.objects.filter(lead__email__iexact=email)
        deals.exclude(state=DealState.COMPLETED).update(state=DealState.COMPLETED, outcome=Outcome.UNSUBSCRIBED)
        CampaignRecipient.objects.filter(deal__in=deals).exclude(status="completed").update(status="stopped")
    return record, created


def removal_blocker(email):
    """Why this address's block cannot be lifted, or "" when it can.

    Only blocks an employee added ("Manually suppressed") can be removed, and only
    while no later opt-out, unsubscribe, exact STOP or dead-address bounce exists.
    """
    records = Suppression.objects.filter(email__iexact=email)
    if not records.exists():
        return "This address is not on the do-not-contact list."
    if records.exclude(reason__startswith="Manually suppressed").exists() or opt_out_evidence(email):
        return "This is an opt-out or a delivery block. It cannot be removed."
    return ""


def unsuppress(email):
    """Lift a manual block. Stopped sequences stay stopped; nothing is sent."""
    blocker = removal_blocker(email)
    if blocker:
        raise ValueError(blocker)
    with transaction.atomic(using=Suppression.objects.all().db):
        return Suppression.objects.filter(email__iexact=email).delete()[0]
