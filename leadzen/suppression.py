"""Terminal, employee-scoped address blocking shared by the two manual controls."""
from django.db import transaction

from cold_outreach.leads.models import Deal, DealState, Outcome, Suppression
from leadzen.accounts.service import email_address
from leadzen.config.models import CampaignRecipient


def record_payload(record):
    return {"id": record.pk, "email": record.email, "reason": record.reason, "suppressed_at": record.suppressed_at.isoformat()}


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
