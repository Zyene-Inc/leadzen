"""Small, private HTTP boundary for the internal LeadZen by Zyene dashboard.

The browser never receives mailbox, LLM, or lead-provider credentials. The dashboard
calls this API with a bearer token, and the API starts the normal sender as a separate
worker process under the same database lock and pacing rules.
"""
from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
from datetime import datetime

from django.db import connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Q
from django.http import JsonResponse, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from cold_outreach.emails.models import Direction, Message, Mailbox
from cold_outreach.leads.models import Deal, DealState, Suppression
from leadzen.config.models import OutreachJob, SiteConfig
from leadzen.configuration import SettingsError, effective, finder_settings, lead_finder_credentials, save_dashboard_settings
from leadzen.branding import PRODUCT_TITLE, display_text
from leadzen.accounts.service import access
from leadzen.accounts.service import payload
from leadzen.mailboxes import active_mailboxes


def _json_error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _token_is_valid(request) -> bool:
    expected = os.environ.get("LEADZEN_DASHBOARD_TOKEN", "").strip()
    if not expected:
        return False
    authorization = request.headers.get("Authorization", "")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not supplied:
        supplied = request.headers.get("X-Dashboard-Token", "").strip()
    return bool(supplied) and hmac.compare_digest(supplied.encode(), expected.encode())


def _cors(response: JsonResponse, request):
    origin = request.headers.get("Origin", "")
    allowed = {
        value.strip().rstrip("/")
        for value in os.environ.get("LEADZEN_DASHBOARD_ORIGINS", "").split(",")
        if value.strip()
    }
    if origin and origin.rstrip("/") in allowed:
        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
        response["Vary"] = "Origin"
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _protected(view):
    def wrapped(request, *args, **kwargs):
        if request.method == "OPTIONS":
            return _cors(JsonResponse({}, status=204), request)
        if not _token_is_valid(request):
            return _cors(_json_error("Unauthorized", 401), request)
        return _cors(view(request, *args, **kwargs), request)

    return wrapped


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _message_payload(message: Message) -> dict:
    return {
        "id": message.pk,
        "direction": message.direction,
        "kind": message.kind,
        "from": message.from_address,
        "to": message.to_address,
        "subject": message.subject,
        "sent_at": _iso(message.sent_at or message.received_at or message.recorded_at),
        "thread_id": message.thread_id,
        "accepted": message.direction == Direction.OUTBOUND and (
            message.crm_accepted if hasattr(message, "crm_accepted") else message.delivery_events.filter(status="accepted").exists()
        ),
    }


def _mailbox_payload(mailbox: Mailbox) -> dict:
    sent = mailbox.sent_today()
    return {
        "address": mailbox.from_address,
        "daily_limit": mailbox.daily_limit,
        "sent_today": sent,
        "remaining_today": mailbox.headroom_today(),
        "next_send_at": _iso(mailbox.next_send_at),
        "paused_today": mailbox.paused_today(),
    }


def _settings_payload() -> dict:
    values = effective()
    from leadzen.lead_finder import public
    return {
        "llm": {
            "enabled": values.ai_enabled,
            "provider": values.provider,
            "model": values.model,
            "base_url": values.base_url,
            "api_key_configured": bool(values.llm_api_key),
        },
        "mailbox": {
            "transport": values.mail_transport,
            "api_url": values.mail_api_url,
            "smtp_username": values.smtp_username,
            "api_key_configured": bool(values.mail_api_key),
            "imap_password_configured": bool(values.imap_password),
            "address": values.mailbox_address,
            "smtp_host": values.smtp_host,
            "smtp_port": values.smtp_port,
            "imap_host": values.imap_host,
            "imap_port": values.imap_port,
            "signature": values.signature,
            "password_configured": bool(values.mailbox_password),
        },
        "lead_finder": {
            **public(values),
        },
        "settings_key_configured": bool(os.environ.get("LEADZEN_SETTINGS_KEY", "").strip()),
    }


@require_http_methods(["GET", "HEAD"])
def dashboard_entry(request):
    from urllib.parse import urlsplit
    origin = os.environ.get("LEADZEN_PUBLIC_URL", "").rstrip("/")
    if not origin and urlsplit(request.build_absolute_uri()).hostname in {"localhost", "127.0.0.1", "::1"}:
        origin = "http://localhost:3000"
    try:
        parsed = urlsplit(origin)
        parsed.port  # Reject malformed ports before constructing a redirect.
    except ValueError:
        return _json_error("Configure the dashboard URL to open LeadZen.", 503)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path or (parsed.scheme != "https" and not (local and parsed.scheme == "http")) or origin == request.build_absolute_uri("/").rstrip("/"):
        return _json_error("Configure the dashboard URL to open LeadZen.", 503)
    response = HttpResponseRedirect(origin)
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["GET", "OPTIONS"])
@_protected
def health(request):
    return JsonResponse({"ok": True, "service": "leadzen-api", "product": PRODUCT_TITLE})


@require_http_methods(["GET", "OPTIONS"])
@_protected
def ready(request):
    """Read-only control database/schema readiness, separate from liveness."""
    connection = connections["default"]
    previous_timeout = None
    try:
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                previous_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()[0]
                cursor.execute("PRAGMA busy_timeout=1000")
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("Database probe failed")
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            return _json_error("Required database migrations have not been applied", 503)
        return JsonResponse({"ok": True, "service": "leadzen-api", "checks": {"database": True, "migrations": True}})
    except Exception:
        # Paths, SQL and database/provider exception strings stay server-side.
        return _json_error("The API database is unavailable or its schema is not ready", 503)
    finally:
        if previous_timeout is not None:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"PRAGMA busy_timeout={int(previous_timeout)}")
            except Exception:
                connection.close()


@csrf_exempt
@require_http_methods(["GET", "PUT", "OPTIONS"])
@access(workspace=True)
def runtime_settings(request):
    from leadzen.workspace_settings import settings_payload, validate_changes, apply_changes
    if request.method == "GET":
        try:
            return JsonResponse({**_settings_payload(), **settings_payload(request.actor)})
        except SettingsError as error:
            return _json_error(str(error), 503)
    try:
        body = payload(request)
        # Keep the returned workspace summary read-only. Older connection clients
        # round-trip GET responses, including server-derived metadata.
        changes = validate_changes(body.get("workspace_updates"))
        alias = SiteConfig.objects.all().db
        llm = body.get("llm", {})
        mailbox = body.get("mailbox", {})
        if not isinstance(llm, dict) or not isinstance(mailbox, dict):
            raise SettingsError("llm and mailbox must be objects")
        for section, flag in ((llm, "clear_api_key"), (mailbox, "clear_password"), (mailbox, "clear_api_key"), (mailbox, "clear_imap_password")):
            if flag in section and type(section[flag]) is not bool:
                raise SettingsError("Credential removal must be a boolean")
        lead_finder_credentials(body)
        with transaction.atomic(using=alias):
            if not any(key in body for key in ("llm", "mailbox", "lead_finder")):
                apply_changes(changes)
                return JsonResponse({**_settings_payload(), **settings_payload(request.actor)})
            # Each editor submits only its changed section. Load canonical
            # defaults while holding the workspace write lock so an AI edit
            # cannot erase mailbox credentials or another tab's signature.
            current = effective()
            save_dashboard_settings(
                {
                    "provider": llm.get("provider", current.provider),
                    "model": llm.get("model", current.model),
                    "base_url": llm.get("base_url", current.base_url),
                    "mailbox_address": mailbox.get("address", current.mailbox_address),
                    "smtp_host": mailbox.get("smtp_host", current.smtp_host),
                    "smtp_port": mailbox.get("smtp_port", current.smtp_port),
                    "imap_host": mailbox.get("imap_host", current.imap_host),
                    "imap_port": mailbox.get("imap_port", current.imap_port),
                    "signature": mailbox.get("signature", current.signature),
                    "mail_transport": mailbox.get("transport", current.mail_transport),
                    "mail_api_url": mailbox.get("api_url", current.mail_api_url),
                    "smtp_username": mailbox.get("smtp_username", current.smtp_username),
                    "ai_enabled": llm.get("enabled", current.ai_enabled),
                },
                llm_api_key=llm.get("api_key"),
                mailbox_password=mailbox.get("password"),
                mail_api_key=mailbox.get("api_key"), imap_password=mailbox.get("imap_password"),
                clear_llm_api_key=llm.get("clear_api_key") is True,
                clear_mailbox_password=mailbox.get("clear_password") is True,
                clear_mail_api_key=mailbox.get("clear_api_key") is True,
                clear_imap_password=mailbox.get("clear_imap_password") is True,
                **finder_settings(body, current),
            )
            apply_changes(changes)
        return JsonResponse({**_settings_payload(), **settings_payload(request.actor)})
    except (json.JSONDecodeError, TypeError):
        return _json_error("settings must be valid JSON", 400)
    except SettingsError as error:
        status = 503 if "LEADZEN_SETTINGS_KEY" in str(error) else 400
        return _json_error(str(error), status)


@require_http_methods(["GET", "OPTIONS"])
@access(workspace=True)
def overview(request):
    from leadzen.home import summary
    today = timezone.localdate()
    contacts = Deal.objects.filter(lead__preferences__deleted_at__isnull=True)
    sent_today = Message.objects.filter(direction=Direction.OUTBOUND, sent_at__date=today, delivery_events__status="accepted").distinct().count()
    inbound_today = Message.objects.filter(direction=Direction.INBOUND, received_at__date=today).count()
    jobs = list(OutreachJob.objects.all()[:5])
    return JsonResponse({
        "home": summary(),
        "leads": {
            "total": contacts.count(),
            "ready": contacts.filter(state=DealState.READY).count(),
            "emailed": contacts.filter(state=DealState.EMAILED).count(),
            "completed": contacts.filter(state=DealState.COMPLETED).count(),
            "suppressed": Suppression.objects.count(),
        },
        "today": {"sent": sent_today, "inbound": inbound_today},
        "ai_ready": bool(effective().ai_enabled and effective().llm_api_key),
        "transport": effective().mail_transport,
        "mailboxes": [_mailbox_payload(box) for box in active_mailboxes()],
        "jobs": [_job_payload(job) for job in jobs],
        "activity": [_message_payload(message) for message in Message.objects.order_by("-recorded_at")[:8]],
    })


@require_http_methods(["GET", "OPTIONS"])
@access(workspace=True)
def leads(request):
    from leadzen.crm import list_contacts
    return list_contacts(request)


def _workspace_page(request):
    """Bound stored-data views; never interpret client workspace identifiers."""
    limit = int(request.GET.get("limit", "25"))
    offset = int(request.GET.get("offset", "0"))
    query = request.GET.get("q", "").strip()
    if limit < 1 or not 0 <= offset <= 2147483647 or len(query) > 200:
        raise ValueError("Use a positive limit, non-negative offset and a search up to 200 characters.")
    return min(limit, 100), offset, query


@require_http_methods(["GET", "OPTIONS"])
@access(workspace=True)
def inbox(request):
    try:
        limit, offset, query = _workspace_page(request)
    except ValueError:
        return _json_error("Invalid pagination or search. Use limit 1–100, a non-negative offset and search up to 200 characters.", 400)
    kind = request.GET.get("kind", "all")
    if kind not in {"all", "human_reply", "auto_reply", "bounce", "opt_out", "unrelated", ""}:
        return _json_error("Unknown inbox classification", 400)
    messages = Message.objects.filter(direction=Direction.INBOUND).order_by("-recorded_at", "-pk")
    if kind != "all":
        messages = messages.filter(kind=kind)
    if query:
        messages = messages.filter(Q(from_address__icontains=query) | Q(subject__icontains=query) | Q(body_text__icontains=query))
    return JsonResponse({
        "items": [{**_message_payload(message), "body": message.body_text[:12000], "body_truncated": len(message.body_text) > 12000} for message in messages[offset:offset + limit]],
        "total": messages.count(), "limit": limit, "offset": offset,
    })


@csrf_exempt
@require_http_methods(["GET", "POST", "OPTIONS"])
@access(workspace=True)
def suppression(request):
    if request.method == "POST":
        from leadzen.suppression import block_address, record_payload
        body = payload(request)
        record, created = block_address(body.get("email"), body.get("reason", "Manually suppressed"))
        return JsonResponse({"record": record_payload(record), "created": created}, status=201 if created else 200)
    try:
        limit, offset, query = _workspace_page(request)
    except ValueError:
        return _json_error("Invalid pagination or search. Use limit 1–100, a non-negative offset and search up to 200 characters.", 400)
    records = Suppression.objects.order_by("-suppressed_at", "-pk")
    if query:
        records = records.filter(Q(email__icontains=query) | Q(reason__icontains=query))
    return JsonResponse({
        "items": [{"id": row.pk, "email": row.email, "reason": row.reason, "suppressed_at": _iso(row.suppressed_at)} for row in records[offset:offset + limit]],
        "total": records.count(), "limit": limit, "offset": offset,
    })


def _job_payload(job: OutreachJob) -> dict:
    from leadzen.chat.engine import redact
    return {
        "id": str(job.id),
        "kind": job.kind,
        "requested_count": job.requested_count,
        "status": job.status,
        "pid": job.pid,
        "output": display_text(redact(job.output)[-2000:]),
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
    }


def recover_expired_jobs():
    """Expired send capabilities cannot run again; retain ambiguous attempts."""
    from datetime import timedelta
    from leadzen.config.models import EmailReview, ReviewedEmail, CampaignRecipient
    cutoff = timezone.now() - timedelta(minutes=20)
    with transaction.atomic(using=OutreachJob.objects.all().db):
        for job in OutreachJob.objects.filter(status__in=["queued", "running"], created_at__lt=cutoff):
            if OutreachJob.objects.filter(pk=job.pk, status=job.status).update(
                    status="failed", finished_at=timezone.now(),
                    output="The send worker expired. Review saved delivery attempts before starting a new review.") != 1:
                continue
            if job.kind == "reviewed":
                review_id = job.campaign_approval.get("review_id")
                EmailReview.objects.filter(pk=review_id, status__in=["queued", "running"]).update(status="failed")
                ReviewedEmail.objects.filter(review_id=review_id, state="sending").update(state="review")
            elif job.kind == "campaign":
                CampaignRecipient.objects.filter(campaign_id=job.campaign_id, status="sending",
                    pk__in=job.campaign_approval.get("recipient_ids", [])).update(status="review")


@require_http_methods(["GET", "OPTIONS"])
@access(workspace=True)
def jobs(request):
    return JsonResponse({"items": [_job_payload(job) for job in OutreachJob.objects.all()[:20]]})


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
@access(workspace=True)
def start_send(request):
    from leadzen.outreach import start
    return start(request)


@csrf_exempt
@require_http_methods(["POST"])
@access(workspace=True)
def start_campaign(request, campaign_id):
    from leadzen.config.models import EmailCampaign
    from leadzen.campaigns import sending_preview
    from leadzen.chat.engine import snapshot
    import uuid
    from datetime import timedelta
    recover_expired_jobs()
    campaign = EmailCampaign.objects.filter(pk=campaign_id, status__in=["draft", "active", "paused"]).first()
    if not campaign:
        return _json_error("Choose an available outreach draft in your workspace", 404)
    if campaign.autopilot_run_id:
        return _json_error("This sequence is controlled by Daily Autopilot. Monitor, pause or stop it in Outreach.", 409)
    body = payload(request)
    count = body.get("count")
    if type(count) is not int or not 1 <= count <= 25:
        return _json_error("Enter a count from 1 to 25", 400)
    try:
        request_id = uuid.UUID(str(body.get("request_id", "")))
    except ValueError:
        return _json_error("A unique request ID is required", 400)
    automatic = body.get("automatic_followups", False)
    if not isinstance(automatic, bool):
        return _json_error("Automatic follow-up approval must be a boolean", 400)
    if automatic and os.environ.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") != "1":
        return _json_error("The automatic follow-up service is not enabled", 409)
    selection = {"revision": body.get("revision"), "count": count, "automatic_followups": automatic}
    existing = OutreachJob.objects.filter(request_id=request_id).first()
    if existing:
        if existing.campaign_id != campaign.pk or existing.campaign_approval.get("selection") != selection:
            return _json_error("Request ID already used", 409)
        return JsonResponse({"job": _job_payload(existing)}, status=202)
    alias = OutreachJob.objects.all().db
    with transaction.atomic(using=alias):
        if OutreachJob.objects.filter(status__in=["queued", "running"]).exists():
            return _json_error("An outreach job is already running", 409)
        campaign = EmailCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status == "archived":
            return _json_error("This outreach was archived. Refresh before continuing.", 409)
        review = sending_preview(campaign, count)
        if review["revision"] != body.get("revision"):
            return _json_error("The campaign or recipients changed. Refresh and review before sending.", 409)
        if not review["recipient_ids"]:
            return _json_error("No eligible emails are due yet", 409)
        # Activation belongs to the exact final send approval, never draft/review.
        # Revoking an older sequence prevents resume from silently restarting it.
        if campaign.status != "active":
            campaign.status = "active"
            campaign.followup_approval = {}
            campaign.save(update_fields=["status", "followup_approval"])
        args = {"campaign_id": str(campaign.pk), "recipient_ids": review["recipient_ids"]}
        job = OutreachJob.objects.create(kind="campaign", campaign_id=campaign.pk, requested_count=count, request_id=request_id,
            campaign_approval={"selection": selection, "recipient_ids": review["recipient_ids"], "snapshot": snapshot("send_campaign", args, execution=True), "expires_at": (timezone.now() + timedelta(minutes=15)).isoformat()})
        if automatic:
            from leadzen.followups import authorize
            authorize(campaign, review["recipient_ids"], request.actor.pk)
    return _launch_job(request, job)


def _launch_job(request, job):
    from leadzen.workspaces import database_path, worker_environment
    env = worker_environment(request.actor.leadzen_profile)
    log_dir = database_path(request.actor.leadzen_profile).parent / "jobs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{job.id}.log"
    try:
        with log_file.open("ab") as output:
            log_file.chmod(0o600)
            process = subprocess.Popen(
                [sys.executable, "-m", "leadzen.web_worker", str(job.id), str(job.requested_count)],
                cwd=str(log_dir.parent), env=env, stdout=output,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
    except OSError:
        job.status = OutreachJob.Status.FAILED
        job.output = "Worker could not start. Contact support@zyene.com."
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "output", "finished_at"])
        if job.kind == "reviewed":
            from leadzen.config.models import EmailReview
            EmailReview.objects.filter(pk=job.campaign_approval.get("review_id"), status="queued").update(status="failed")
        return _json_error(job.output, 503)
    job.pid = process.pid
    job.save(update_fields=["pid"])
    return JsonResponse({"job": _job_payload(job)}, status=202)
