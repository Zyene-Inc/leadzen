"""Readable workspace history, with private diagnostics fetched separately."""
import os
import re
import stat

from django.db.models import CharField, Exists, Min, OuterRef, Q, Subquery
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from cold_outreach.emails.models import DeliveryEvent, Mailbox, Message
from cold_outreach.leads.models import Lead as Contact, Suppression
from openoutfind.crm.models import Deal, DealState, Lead
from leadzen.accounts.service import access
from leadzen.config.models import DiscoveryCandidate, DiscoveryEvent, DiscoverySession, OutreachJob
from leadzen.home import QUALIFIED

LIMIT = 100


def item(identifier, title, detail, at, kind="info", href=None):
    return {"id": identifier, "title": title, "detail": str(detail or "")[:240],
            "at": at.isoformat(), "kind": kind, "href": href}


def discovery_items(actor_id):
    result = []
    # Detailed candidate arrivals/review phases belong in the live run. Select
    # summary events before limiting so they cannot crowd real verdicts out of
    # the Workspace Activity feed.
    rows = DiscoveryEvent.objects.filter(session__run__actor_id=actor_id,
        kind__in=["qualified", "rejected", "search_completed", "searching", "email_lookup"]
    ).select_related("session").order_by("-created_at", "-pk")[:LIMIT]
    for row in rows:
        data = row.data if isinstance(row.data, dict) else {}
        href = f"/find-leads/{row.session_id}"
        if row.kind in {"qualified", "rejected"}:
            result.append(item(f"discovery-{row.pk}", f"Lead {row.kind}", data.get("name") or "Unnamed profile", row.created_at, "success" if row.kind == "qualified" else "rejected", href))
        elif row.kind == "search_completed":
            count = data.get("profiles_returned")
            if type(count) is int and count >= 0:
                result.append(item(f"discovery-{row.pk}", "BetterContact search completed", f"{count:,} profile{'s' if count != 1 else ''} returned", row.created_at, href=href))
        elif row.kind == "searching":
            result.append(item(f"discovery-{row.pk}", "BetterContact search started", "Searching the selected audience", row.created_at, href=href))
        elif row.kind == "email_lookup":
            result.append(item(f"discovery-{row.pk}", "Email lookup requested", "One approved lead", row.created_at, href=href))
    sessions = DiscoverySession.objects.filter(run__actor_id=actor_id).select_related("run").annotate(first_event_at=Min("events__created_at")).order_by("-run__created_at")[:LIMIT]
    for session in sessions:
        href = f"/find-leads/{session.pk}"
        started = session.first_event_at
        result.append(item(f"discovery-start-{session.pk}", "Discovery started" if started else "Discovery queued", f"Goal: {session.goal} {'leads with email' if session.unit == 'emails' else 'leads'}", started or session.run.created_at, href=href))
        if session.run.finished_at:
            titles = {"succeeded": "Discovery completed", "failed": "Discovery failed", "cancelled": "Discovery stopped"}
            title = titles.get(session.run.status)
            if title:
                result.append(item(f"discovery-finish-{session.pk}", title, "Open the run for saved results", session.run.finished_at, "warning" if session.run.status == "failed" else "info", href))
    return result


def legacy_decisions(actor_id):
    # Monitored verdicts carry their real decision time. Older decisions retain
    # the only timestamp available, without duplicating the same profile.
    monitored = DiscoveryCandidate.objects.filter(session__run__actor_id=actor_id, evaluated=True, source_id=OuterRef("lead_id"))
    deleted = Contact.objects.filter(preferences__deleted_at__isnull=False).filter(
        Q(lead_id=Cast(OuterRef("pk"), CharField())) | (Q(email__iexact=OuterRef("email")) & ~Q(email="")))
    profiles = Lead.objects.filter(synthetic=False).alias(deleted=Exists(deleted)).filter(deleted=False)
    rows = Deal.objects.filter(lead__in=profiles).alias(monitored=Exists(monitored)).filter(monitored=False).filter(
        Q(state__in=QUALIFIED) | Q(state=DealState.FAILED, outcome="wrong_fit")).select_related("lead").order_by("-creation_date", "-pk")[:LIMIT]
    result = []
    for row in rows:
        rejected = row.lead.disqualified or row.state == DealState.FAILED or row.outcome == "wrong_fit"
        name = row.lead.full_name or " ".join(filter(None, [row.lead.first_name, row.lead.last_name])) or "Unnamed profile"
        result.append(item(f"decision-{row.pk}", "Lead rejected" if rejected else "Lead qualified", name, row.creation_date, "rejected" if rejected else "success", "/contacts"))
    return result


def mail_items():
    accepted = DeliveryEvent.objects.filter(message_id=OuterRef("pk"), status="accepted").order_by("occurred_at", "pk")
    rows = Message.objects.annotate(accepted_at=Subquery(accepted.values("occurred_at")[:1])).order_by("-recorded_at", "-pk")[:LIMIT]
    incoming = {"human_reply": "Reply received", "auto_reply": "Automatic reply received", "opt_out": "Opt-out received", "bounce": "Bounce received"}
    result = []
    for row in rows:
        if row.direction == "in":
            result.append(item(f"message-{row.pk}", incoming.get(row.kind, "Incoming email received"), row.from_address, row.received_at or row.recorded_at, "warning" if row.kind in {"bounce", "opt_out"} else "info", "/inbox"))
        else:
            result.append(item(f"message-{row.pk}", "Email accepted by provider" if row.accepted_at else "Email attempt recorded", row.to_address, row.accepted_at or row.sent_at or row.recorded_at, "success" if row.accepted_at else "warning", "/sending"))
    return result


@require_http_methods(["GET", "OPTIONS"])
@access(workspace=True)
def feed(request):
    # This path never reads runtime credentials, raw logs, or contacts providers.
    rows = discovery_items(request.actor.pk) + legacy_decisions(request.actor.pk) + mail_items()
    statuses = {"queued": "queued", "running": "started", "succeeded": "completed", "failed": "failed", "cancelled": "stopped"}
    for job in OutreachJob.objects.only("id", "kind", "requested_count", "status", "created_at", "started_at", "finished_at").order_by("-created_at")[:LIMIT]:
        name = "Campaign" if job.kind == "campaign" else "Outreach"
        title = f"{name} {statuses.get(job.status, 'updated')}"
        rows.append(item(f"job-{job.pk}", title, f"Requested: {job.requested_count} email{'s' if job.requested_count != 1 else ''}", job.finished_at or job.started_at or job.created_at, "warning" if job.status == "failed" else "info", "/sending"))
    for row in Suppression.objects.order_by("-suppressed_at", "-pk")[:LIMIT]:
        rows.append(item(f"suppression-{row.pk}", "Added to Do Not Contact", row.email, row.suppressed_at, "info", "/suppression"))
    rows.sort(key=lambda row: (row["at"], row["id"]), reverse=True)
    return JsonResponse({"items": rows[:LIMIT], "limit": LIMIT})


def log_tail(profile, job_id):
    """Only a server-owned job file in this actor's workspace; bounded regular IO."""
    from leadzen.workspaces import database_path
    try:
        directory = os.open(database_path(profile).parent / "jobs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            descriptor = os.open(f"{job_id}.log", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                return "", False, True
            truncated = metadata.st_size > 12000
            stream.seek(max(0, metadata.st_size - 12000))
            content = stream.read(12000)
            if truncated:
                # Do not return a partial authentication line or partial secret.
                content = content.partition(b"\n")[2]
            return content.decode("utf-8", errors="replace"), truncated, False
    except FileNotFoundError:
        return "", False, False
    except OSError:
        return "", False, True


def clean_diagnostics(text, mailbox_secrets):
    from leadzen.chat.engine import redact
    text = redact(text)
    for secret in mailbox_secrets:
        if secret:
            text = text.replace(secret, "[credential removed]")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[credential removed]@", text)
    lines = []
    for line in text.splitlines():
        if re.search(r"\b(?:password|passwd|authorization|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|AUTH(?:ENTICATE)?|LOGIN)\b", line, re.I) or re.search(r"send:.*b['\"][A-Za-z0-9+/=]{16,}", line, re.I):
            lines.append("[authentication details removed]")
        else:
            lines.append(line)
    return "\n".join(lines)


@require_http_methods(["GET", "OPTIONS"])
@access(workspace=True)
def developer_logs(request):
    # Diagnostics are separate from the default feed and never accept a path or
    # employee identifier. Known credentials and protocol AUTH lines are removed.
    from leadzen.configuration import SettingsError
    jobs = list(OutreachJob.objects.order_by("-created_at")[:10])
    secrets = list(Mailbox.objects.exclude(password="").values_list("password", flat=True)) if jobs else []
    rows = []
    try:
        for job in jobs:
            text, truncated, unavailable = log_tail(request.actor.leadzen_profile, job.pk)
            output = clean_diagnostics(job.output + ("\n\n" + text if text else ""), secrets)
            rows.append({"id": str(job.pk), "label": "Campaign worker" if job.kind == "campaign" else "Outreach worker",
                         "at": (job.finished_at or job.started_at or job.created_at).isoformat(),
                         "output": output[-16000:], "truncated": truncated or len(output) > 16000, "unavailable": unavailable})
    except SettingsError:
        return JsonResponse({"error": "Developer logs are unavailable until workspace credentials can be safely redacted."}, status=503)
    return JsonResponse({"items": rows, "limit": 10})
