"""Restart-safe checkpoints around the existing finder, composer and campaign sender."""
import os
import time
import uuid

# The scheduler launches this module in a fresh isolated process.
if __name__ == "__main__":
    if os.environ.get("LEADZEN_AUTOPILOT_ENABLED") != "1" or not os.environ.get("LEADZEN_ACTOR_ID") or not os.environ.get("LEADZEN_CONTROL_DB"):
        raise SystemExit("Autopilot requires an enabled service and an authorized employee workspace")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadzen.settings")
    import django
    django.setup()
from datetime import timedelta
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from leadzen.config.models import (AutopilotPolicy, AutopilotRun, CampaignRecipient, ChatRun,
    ChatThread, DiscoverySession, EmailCampaign)
from leadzen.autopilot import (ContactStopped, check_policy, execution, external_guard,
    local_now, recipient_hash, sending_schedule, within_delivery_window, within_start_window)
from leadzen.transports import SendingWindowClosed

BUSY_ISSUE = "Finish or stop your active Chat or Find Leads task so Autopilot can start."


def checkpoint(run, phase, **data):
    # A user stop wins over a worker's stale object.
    changed = AutopilotRun.objects.filter(pk=run.pk).exclude(phase="stopped").update(
        phase=phase, checkpoint={**run.checkpoint, **data}, updated_at=timezone.now())
    run.refresh_from_db()
    if not changed:
        raise PermissionError("Autopilot stopped")


def discover(run, *, emails=False, source_ids=None, new_source_after=None):
    from leadzen.chat.engine import find_leads, snapshot
    from leadzen.discovery_progress import observe, selected_identity
    source_ids = source_ids or []
    args = {"count": len(source_ids) if emails else run.checkpoint["contact_limit"], "emails": emails, "audience": ""}
    with transaction.atomic(using=run._state.db):
        thread = ChatThread.objects.create(actor_id=run.actor_id, title=f"Autopilot · {run.workday} · {'emails' if emails else 'leads'}")
        row = ChatRun.objects.create(thread=thread, actor_id=run.actor_id, request_id=uuid.uuid4(),
            status="running", deadline_at=run.deadline_at)
        action = {"arguments": args, "snapshot": snapshot("find_leads", args),
                  "authorization": "autopilot", "policy_id": str(run.policy_id)}
        if source_ids:
            action["source_identity"] = selected_identity(source_ids)
        if not emails:
            from openoutfind.crm.models import Lead as Source
            action["new_source_after"] = (new_source_after if new_source_after is not None else
                Source.objects.order_by("-pk").values_list("pk", flat=True).first() or 0)
        session = DiscoverySession.objects.create(run=row, action=action, goal=args["count"],
            unit="emails" if emails else "leads", target=run.policy.scope["target"], source_ids=source_ids)
        checkpoint(run, "enriching" if emails else "finding", **{"enrichment_id" if emails else "discovery_id": str(row.pk)})
    try:
        with observe(row):
            result = find_leads(args)
            if emails:
                result = collect_enrichment(run, row, session, args, result)
        row.refresh_from_db()
        if row.cancel_requested or row.status != "running" or result.get("paused"):
            raise PermissionError("Discovery was stopped or paused; today's automatic preparation is held")
        if result.get("partial"):
            checkpoint(run, run.phase, partial_discovery=True)
            AutopilotRun.objects.filter(pk=run.pk).update(issue="Discovery returned partial results. Only completed, verified contacts can continue.")
        return session
    finally:
        succeeded = 'result' in locals() and not result.get("partial") and not result.get("paused") and not row.cancel_requested
        ChatRun.objects.filter(pk=row.pk, status="running").update(status="succeeded" if succeeded else "failed", finished_at=timezone.now())


def collect_enrichment(run, row, session, args, result):
    """Wait for our submitted handles without repeating discovery or paid submits."""
    from openoutfind.crm.models import Deal, DealState
    from leadzen.chat.engine import find_leads
    from leadzen.discovery_progress import current
    while True:
        row.refresh_from_db()
        if row.cancel_requested or row.status != "running" or result.get("paused"):
            raise PermissionError("Discovery was stopped or paused")
        handles = session.lookups.exclude(state="terminated").exclude(request_id="").values_list("request_id", flat=True)
        owned = Deal.objects.filter(state=DealState.FINDING_EMAIL, lead_id__in=session.source_ids,
                                    lookup_request_id__in=handles).order_by("pk")
        pending = list(owned.values("pk", "lookup_attempt", "not_before"))
        if not pending:
            # An unresolved reservation without a handle remains partial/held.
            # Terminal misses are safe to skip; they never become recipients.
            settled = session.lookups.filter(state="terminated", credits__isnull=False).count()
            if settled == len(session.source_ids):
                result = {**result, "partial": False}
            return result
        external_guard()
        current().boundary()
        session.refresh_from_db()
        if session.provider_calls >= 200:
            return {**result, "partial": True}
        next_due = min(p["not_before"] or timezone.now() for p in pending)
        delay = (next_due - timezone.now()).total_seconds()
        if delay > 0:
            # Stops, expiry and the preparation deadline are checked between waits.
            time.sleep(min(delay, 2))
            continue
        result = find_leads(args, poll_only=True)
        if list(owned.values("pk", "lookup_attempt", "not_before")) == pending:
            # A refusal/uncertain poll that did not advance a handle is held.
            # Do not spin or repeat the purchase to make the job reach its goal.
            return {**result, "partial": True}


def compose_sequence(run, deal):
    """No human-review rows/flags: save generated copy directly on its recipient."""
    from leadzen.outreach import generate, validated_copy
    from leadzen.chat.engine import redact
    delays = [0, *run.policy.scope["followup_days"]]
    drafts = [SimpleNamespace(pk=uuid.uuid4(), deal=deal, reply_to=None, subject="", body="",
        instructions=f'{run.policy.scope["tone"]}. Write message {index + 1} of {len(delays)} for this contact. '
                     + (f'Follow-up {days} working days after the preceding message. Do not claim they replied or that we met.' if index else 'This is our first contact.'))
        for index, days in enumerate(delays)]
    external_guard()
    result = redact(generate(SimpleNamespace(kind="initial"), drafts))
    external_guard()
    if not isinstance(result, list) or len(result) != len(drafts) or {r.get("id") for r in result if isinstance(r, dict)} != {str(d.pk) for d in drafts}:
        raise ValueError("Generation did not return exactly this recipient's sequence")
    by_id = {r["id"]: validated_copy(r.get("subject"), r.get("body")) for r in result}
    return [{"subject": by_id[str(d.pk)][0], "body": by_id[str(d.pk)][1], "delay_days": days} for d, days in zip(drafts, delays)]


def prepare(run):
    from cold_outreach.leads.models import Deal, DealState, Suppression
    from openoutfind.crm.models import Lead as Source
    from leadzen.config.models import DiscoveryLookup, ReviewedEmail
    from leadzen.outreach import blocked
    from leadzen.mailboxes import active_mailboxes
    from leadzen.transports import sync_replies_strict
    external_guard()
    sync_replies_strict(active_mailboxes().get(), classify=False)
    baseline = Source.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
    session = discover(run, new_source_after=baseline)
    ids = list(session.candidates.filter(produced=True, outcome="qualified", discovered=True, source_id__gt=baseline)
               .order_by("pk").values_list("source_id", flat=True)[:run.checkpoint["contact_limit"]])
    checkpoint(run, "enriching", source_ids=ids)
    ids = [i for i in ids if not DiscoveryLookup.objects.filter(source_id=i).exists()][:run.policy.scope["daily_credits"]]
    if not ids:
        checkpoint(run, "needs_attention" if run.checkpoint.get("partial_discovery") else "completed", contacts=0)
        return
    session = discover(run, emails=True, source_ids=ids)
    verified = session.lookups.filter(state="terminated", email_status__in=["valid", "deliverable"], credits__isnull=False).values_list("source_id", flat=True)
    produced = {str(c.source_id): c.data.get("email", "").lower() for c in session.candidates.filter(produced=True, outcome="qualified")}
    deals = list(Deal.objects.filter(lead__lead_id__in=[str(i) for i in verified], state=DealState.READY,
                                   lead__preferences__deleted_at__isnull=True).exclude(lead__email="")
                 .exclude(lead__email__in=Suppression.objects.values("email"))
                 .exclude(pk__in=CampaignRecipient.objects.values("deal_id"))
                 .exclude(pk__in=ReviewedEmail.objects.filter(state__in=["pending", "sending", "accepted", "review", "sent"]).values("deal_id")).select_related("lead"))
    # Case-insensitive email dedup across all existing outreach and today's results.
    seen = {s.lower() for s in CampaignRecipient.objects.values_list("deal__lead__email", flat=True)}
    seen.update(s.lower() for s in ReviewedEmail.objects.filter(state__in=["pending", "sending", "accepted", "review", "sent"])
                .values_list("deal__lead__email", flat=True))
    unique = []
    for deal in deals:
        address = deal.lead.email.lower()
        if (address not in seen and produced.get(deal.lead.lead_id) == address
                and not blocked(deal, "initial") and not Suppression.objects.filter(email__iexact=address).exists()):
            unique.append(deal)
            seen.add(address)
    checkpoint(run, "drafting", contacts=len(unique))
    scope = run.policy.scope
    campaign = EmailCampaign.objects.create(name=f"Autopilot · {run.workday}", autopilot_run=run,
        from_address=scope["sender"], target=scope["target"], product=scope["product"],
        signature=scope["signature"], booking_link=scope["booking_link"], delay_basis="working_days",
        delay_timezone=scope["timezone"], steps=[])
    failures = 0
    for deal in unique:
        external_guard()
        recipient = CampaignRecipient.objects.create(campaign=campaign, deal=deal, status="review")
        try:
            steps = compose_sequence(run, deal)
            recipient.personal_steps = steps
            recipient.authorization_hash = recipient_hash(campaign, recipient)
            recipient.status = "pending"
            recipient.save()
        except Exception:
            failures += 1
    checkpoint(run, "validating", draft_failures=failures)
    external_guard()
    with transaction.atomic(using=run._state.db):
        campaign.status = "active"
        campaign.save(update_fields=["status"])
        checkpoint(run, "sending" if unique else "completed", delivery_authorized=True)


def deliver_due(policy):
    """Follow-ups first, sharing the mailbox cap and five-minute pacing with manual mail."""
    from django.db.models import Q
    from leadzen.campaigns import run_campaign
    check_policy(policy)
    now = local_now(policy)
    if not within_delivery_window(policy, now):
        return
    recipients = CampaignRecipient.objects.filter(campaign__autopilot_run__policy=policy,
        campaign__status="active", status="pending").filter(Q(next_send_at__isnull=True) | Q(next_send_at__lte=timezone.now()))
    # No backlog of new cold emails from previous workdays.
    recipients.filter(next_step=0, campaign__autopilot_run__workday__lt=now.date()).update(status="stopped")
    progress = held = False
    for recipient in recipients.select_related("campaign").order_by("-next_step", "next_send_at", "pk")[:50]:
        try:
            progress = run_campaign(recipient.campaign_id, 1, recipient_ids=[recipient.pk], automatic=True) > 0 or progress
        except ContactStopped:
            progress = True
            continue
        except SendingWindowClosed:
            break  # Ordinary schedule closure is deferred, not a service failure.
        except Exception:
            held = True
            AutopilotPolicy.objects.filter(pk=policy.pk).update(issue="Some messages are held. Check Inbox, connections and recipient status in Outreach.")
            recipient.refresh_from_db()
            if recipient.status == "pending":
                break  # An unavailable inbox or policy holds the remaining batch.
    if progress and not held and not CampaignRecipient.objects.filter(campaign__autopilot_run__policy=policy,
            status__in=["review", "sending"]).exists():
        AutopilotPolicy.objects.filter(pk=policy.pk).update(issue="")
    for run in policy.runs.filter(phase="sending"):
        pending = CampaignRecipient.objects.filter(campaign__autopilot_run=run, next_step=0, status="pending").exists()
        if not pending:
            uncertain = CampaignRecipient.objects.filter(campaign__autopilot_run=run, status__in=["review", "sending"]).exists()
            checkpoint(run, "needs_attention" if uncertain else "completed")


def workspace_tick():
    from django.conf import settings
    from leadzen.web_worker import _database_lock
    from leadzen.workspaces import assert_worker_access, guard_worker_sends
    from leadzen.mailboxes import prepare_worker_mailbox
    from leadzen.ai import install_engine_adapters
    from leadzen.wizard import apply_to_environment
    from leadzen.config.models import SiteConfig
    assert_worker_access()
    with _database_lock(settings.DATABASE_PATH):
        guard_worker_sends()
        install_engine_adapters()
        prepare_worker_mailbox(require_ai=False)
        apply_to_environment(SiteConfig.load())
        if os.environ.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") == "1":
            from leadzen.followups import run_due
            run_due()
        for policy in AutopilotPolicy.objects.filter(enabled=True):
            AutopilotPolicy.objects.filter(pk=policy.pk).update(heartbeat_at=timezone.now())
            try:
                check_policy(policy)
                # Owning the shared workspace lock proves an old preparation worker is gone.
                for interrupted in policy.runs.filter(phase__in=["finding", "enriching", "drafting", "validating"]):
                    checkpoint(interrupted, "needs_attention")
                    AutopilotRun.objects.filter(pk=interrupted.pk).update(issue="Interrupted preparation held; saved results are available for review.")
                    ids = [interrupted.checkpoint.get(k) for k in ("discovery_id", "enrichment_id") if interrupted.checkpoint.get(k)]
                    ChatRun.objects.filter(pk__in=ids, status="running").update(status="failed", finished_at=timezone.now())
                deliver_due(policy)
                now = local_now(policy)
                busy = ChatRun.objects.filter(status__in=["queued", "running", "awaiting_approval", "paused"]).exists()
                if not busy:
                    AutopilotPolicy.objects.filter(pk=policy.pk, issue=BUSY_ISSUE).update(issue="")
                if not within_start_window(policy, now):
                    continue  # bounded same-day catch-up, no historical replay
                if busy:
                    AutopilotPolicy.objects.filter(pk=policy.pk, issue__in=["", BUSY_ISSUE]).update(issue=BUSY_ISSUE)
                    continue
                run, created = AutopilotRun.objects.get_or_create(actor_id=policy.actor_id, workday=now.date(), defaults={"policy": policy})
                if not created and run.phase != "scheduled":
                    continue
                monthly = sum(r.checkpoint.get("contact_limit", 0) for r in AutopilotRun.objects.filter(
                    actor_id=policy.actor_id, workday__year=now.year, workday__month=now.month).exclude(pk=run.pk))
                limit = min(policy.scope["daily_contacts"], max(0, policy.scope["monthly_contacts"] - monthly))
                if not limit:
                    checkpoint(run, "needs_attention")
                    AutopilotRun.objects.filter(pk=run.pk).update(issue="Monthly new-contact limit reached.")
                    continue
                schedule = sending_schedule(policy, initial=True)
                from leadzen.sending_schedule import UTC, window_close
                run.deadline_at = min(timezone.now().astimezone(UTC) + timedelta(minutes=12), window_close(now, schedule))
                run.save(update_fields=["deadline_at"])
                checkpoint(run, "scheduled", contact_limit=limit)
                try:
                    with execution(run):
                        prepare(run)
                    deliver_due(policy)
                except Exception:
                    AutopilotRun.objects.filter(pk=run.pk).exclude(phase="stopped").update(phase="needs_attention",
                        issue="Preparation held. Check saved discovery, provider limits and connections. Uncertain paid requests are never repeated.", updated_at=timezone.now())
            except Exception:
                AutopilotPolicy.objects.filter(pk=policy.pk).update(issue="Autopilot is held. Check authorization, setup and connections before enabling again.")


if __name__ == "__main__":
    workspace_tick()
