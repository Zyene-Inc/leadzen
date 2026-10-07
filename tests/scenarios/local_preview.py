"""Local-only mail catcher and disposable accounts for reviewing the complete UI.

No production credentials are read, and every network email send is replaced.
Run with LEADZEN_PREVIEW_DIR pointing at a mktemp leadzen-preview.* directory.
"""
import json
import os
import pathlib
import sys
import threading
import time
from unittest.mock import patch

from cryptography.fernet import Fernet

root = pathlib.Path(os.environ["LEADZEN_PREVIEW_DIR"])
if not root.name.startswith("leadzen-preview.") or not root.is_dir():
    raise SystemExit("A disposable preview directory is required")
root.chmod(0o700)
fixture_key = root / "fixture-encryption-key"
if not fixture_key.exists():
    fixture_key.write_bytes(Fernet.generate_key())
    fixture_key.chmod(0o600)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
for key in list(os.environ):
    if key.startswith(("OUTSEND_", "OPENOUTFIND_", "LEADZEN_")) or key.endswith("API_KEY"):
        if key != "LEADZEN_PREVIEW_DIR":
            os.environ.pop(key)
os.environ.update(DJANGO_SETTINGS_MODULE="leadzen.settings", LEADZEN_DB=str(root / "control.sqlite3"), LEADZEN_WORKSPACE_ROOT=str(root / "workspaces"), LEADZEN_SETTINGS_KEY=fixture_key.read_text(), LEADZEN_DASHBOARD_TOKEN="synthetic-local-dashboard-token", LEADZEN_RESEND_API_KEY="synthetic-local-resend-key", LEADZEN_PUBLIC_URL="http://localhost:3001", LEADZEN_ALLOWED_HOSTS="localhost,127.0.0.1", PYTHONPATH=str(pathlib.Path(__file__).resolve().parents[2]))

import django
django.setup()
from django.core.management import call_command
from django.utils import timezone
from django.core.wsgi import get_wsgi_application
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
from socketserver import ThreadingMixIn

class PreviewServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
from leadzen.accounts.service import create_account
from leadzen.workspaces import initialize_workspace, workspace_scope
from leadzen.configuration import save_dashboard_settings
from leadzen.config.models import SiteConfig

call_command("migrate", verbosity=0, interactive=False)
password = "LeadZen-preview-only-3487!"
if not (root / "seeded").exists():
    create_account(email="admin@preview.example", name="Preview administrator", password=password, is_admin=True, require_change=False)
    create_account(email="employee@preview.example", name="Preview employee", password=password, require_change=False)
    user = create_account(email="ready@preview.example", name="Ready employee", password=password, require_change=False)
    initialize_workspace(user.leadzen_profile)
    with workspace_scope(user.leadzen_profile):
        config = SiteConfig.load()
        config.product_docs, config.campaign_target = "Synthetic preview product", "Synthetic preview audience"
        config.operator_name, config.operator_email = "Ready employee", "sender@preview.example"
        config.operator_country_code, config.accepted_legal_notice = "US", True
        config.save()
        save_dashboard_settings({"ai_enabled": False, "mailbox_address": "sender@preview.example", "smtp_host": "smtp.zoho.com", "smtp_port": 587, "imap_host": "imap.zoho.com", "imap_port": 993}, mailbox_password="synthetic-preview-password")
    profile = user.leadzen_profile
    profile.workspace_name, profile.purpose = "Preview outreach", "zyene_reviews"
    profile.onboarding_completed_at, profile.tour_completed_at = timezone.now(), timezone.now()
    profile.save()
    (root / "seeded").touch()

def catch_mail(url, key, body, **kwargs):
    path = root / "last-invitation.json"
    path.write_text(json.dumps(body))
    path.chmod(0o600)
    return "synthetic-preview-message"

class QuietLog(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass  # Never log setup links, bodies, or user credentials.


def disabled_job(request, job):
    from django.http import JsonResponse
    job.status, job.output, job.finished_at = "failed", "Sending is disabled in this local UI preview.", timezone.now()
    job.save()
    return JsonResponse({"error": job.output}, status=503)


def seed_activity_preview(profile):
    """Saved synthetic records only, created once without running any provider."""
    import uuid
    from datetime import timedelta
    from leadzen.config.models import ChatThread, ChatRun, DiscoverySession, DiscoveryCandidate, DiscoveryEvent, OutreachJob
    thread, created = ChatThread.objects.get_or_create(actor_id=profile.user_id, title="Synthetic Activity preview")
    if not created:
        return
    start = timezone.now() - timedelta(minutes=4)
    run = ChatRun.objects.create(thread=thread, actor_id=profile.user_id, request_id=uuid.uuid4(), status="succeeded", finished_at=start + timedelta(minutes=3, seconds=30))
    ChatRun.objects.filter(pk=run.pk).update(created_at=start)
    session = DiscoverySession.objects.create(run=run, goal=3, phase="succeeded", synthetic=True, target="Synthetic local Activity preview")
    for index, (kind, name) in enumerate([("rejected", "Christopher Gomez (sample)"), ("qualified", "Bruce Lish (sample)")]):
        DiscoveryCandidate.objects.create(session=session, source_id=900000 + index, discovered=True, evaluated=True, outcome=kind, produced=kind == "qualified", data={"name": name})
        event = DiscoveryEvent.objects.create(session=session, kind=kind, data={"name": name})
        DiscoveryEvent.objects.filter(pk=event.pk).update(created_at=start + timedelta(minutes=index + 2))
    searching = DiscoveryEvent.objects.create(session=session, kind="searching", data={"filters": {"job_title": "Synthetic preview owner"}})
    DiscoveryEvent.objects.filter(pk=searching.pk).update(created_at=start)
    completed = DiscoveryEvent.objects.create(session=session, kind="search_completed", data={"profiles_returned": 2})
    DiscoveryEvent.objects.filter(pk=completed.pk).update(created_at=start + timedelta(minutes=1))
    job = OutreachJob.objects.create(requested_count=1, status="failed", finished_at=start - timedelta(minutes=1), output="[INF] Synthetic local preview, no real email sent\n[DEBUG] SMTP connection test simulated\n[DEBUG] IMAP inbox check simulated")
    OutreachJob.objects.filter(pk=job.pk).update(created_at=job.finished_at)


# An explicitly synthetic model, not a substitute for the real production agent.
# It drives the SAME persistence, ownership and approval loop without provider calls.
from leadzen.accounts.models import AccountProfile
for profile in AccountProfile.objects.using("default").select_related("user").all():
    initialize_workspace(profile)
    with workspace_scope(profile) as alias:
        call_command("migrate", database=alias, verbosity=0, interactive=False)
        if profile.user.email == "ready@preview.example":
            seed_activity_preview(profile)
            save_dashboard_settings({"provider": "openai", "model": "LOCAL PREVIEW — no external calls", "mailbox_address": "sender@preview.example", "signature": "Ready employee\nZyene", "smtp_host": "smtp.zoho.com", "smtp_port": 587, "imap_host": "imap.zoho.com", "imap_port": 993}, llm_api_key="synthetic-preview-ai", bettercontact_api_key="synthetic-preview-finder")
            from cold_outreach.leads.models import Deal, Lead
            from cold_outreach.emails.models import Message, Thread, DeliveryEvent
            from leadzen.mailboxes import active_mailboxes
            for slug, name in [("bruce", "Bruce Lish"), ("sarah", "Sarah Smith"), ("david", "David Jones")]:
                lead, _ = Lead.objects.get_or_create(lead_id=f"review-fixture-{slug}", defaults={"first_name": name.split()[0], "last_name": name.split()[1], "email": f"{slug}@preview.example", "company": "Synthetic Dental Practice", "title": "Practice owner"})
                Deal.objects.get_or_create(lead=lead, defaults={"reason": "Synthetic local fixture, not a real discovered prospect"})
            # Saved timeline facts only. Campaign sending remains disabled below.
            from leadzen.config.models import CampaignRecipient, EmailCampaign
            from leadzen.campaigns import next_send_time
            timeline_lead, _ = Lead.objects.get_or_create(lead_id="timeline-fixture-bruce", defaults={"first_name": "Bruce", "last_name": "Lane (timeline sample)", "email": "timeline-bruce@preview.example", "company": "Synthetic Dental Practice", "title": "Practice owner"})
            timeline_deal, created = Deal.objects.get_or_create(lead=timeline_lead, defaults={"reason": "Synthetic timeline fixture. No real email or provider call occurred."})
            if created:
                box = active_mailboxes().first()
                thread = Thread.objects.create(mailbox=box)
                out = Message.objects.create(mailbox=box, thread=thread, direction="out", kind="outbound", message_id="timeline-fixture-initial", from_address=box.from_address, to_address=timeline_lead.email, subject="Synthetic: patient review engagement", sent_at=timezone.now())
                DeliveryEvent.objects.create(message=out, status="accepted", queue_id="synthetic-timeline-acceptance")
                timeline_deal.state, timeline_deal.thread, timeline_deal.email_sent_at = "Emailed", thread, out.sent_at
                timeline_deal.save()
                campaign = EmailCampaign.objects.create(name="Synthetic timeline preview", status="active", from_address=box.from_address, delay_basis="working_days", delay_timezone="America/New_York", steps=[{"subject": out.subject, "body": "Synthetic initial", "delay_days": 0}, {"subject": "Synthetic follow-up", "body": "Synthetic follow-up", "delay_days": 3}, {"subject": "Synthetic final follow-up", "body": "Synthetic final", "delay_days": 5}])
                CampaignRecipient.objects.create(campaign=campaign, deal=timeline_deal, next_step=1, message_id=out.message_id, next_send_at=next_send_time(campaign, out.sent_at, 3))
            reply_lead, _ = Lead.objects.get_or_create(lead_id="review-fixture-reply", defaults={"first_name": "Bruce", "last_name": "Lish (sample reply)", "email": "bruce-reply@preview.example", "company": "Synthetic Dental Practice"})
            reply_deal, _ = Deal.objects.get_or_create(lead=reply_lead)
            if not reply_deal.thread_id:
                box = active_mailboxes().first()
                thread = Thread.objects.create(mailbox=box)
                out = Message.objects.create(mailbox=box, thread=thread, direction="out", kind="outbound", message_id="review-fixture-out", from_address=box.from_address, to_address=reply_lead.email, subject="Synthetic patient reviews", body_text="Hi Bruce, would a review management demo help?", sent_at=timezone.now())
                DeliveryEvent.objects.create(message=out, status="accepted")
                Message.objects.create(mailbox=box, thread=thread, direction="in", kind="human_reply", message_id="review-fixture-in", from_address=reply_lead.email, to_address=box.from_address, subject="Re: Synthetic patient reviews", body_text="Thanks. Can you send pricing?", received_at=timezone.now())
                reply_deal.state, reply_deal.thread, reply_deal.mailbox = "Emailed", thread, box
                reply_deal.save()
        if profile.user.email == "employee@preview.example" and profile.onboarding_completed_at:
            from openoutfind.crm.models import Lead as FoundLead, Deal as FoundDeal
            # Disposable dashboard fixtures only. These are not provider results.
            for slug, name, qualified in [("bruce", "Bruce Lish (synthetic)", True), ("emily", "Emily Waters (synthetic)", False), ("christopher", "Christopher Gomez (synthetic)", False), ("sarah", "Sarah Smith (synthetic)", True)]:
                found, created = FoundLead.objects.get_or_create(profile_url=f"https://example.com/leadzen-preview/{slug}", defaults={"full_name": name, "email": "bruce@preview.example" if slug == "bruce" else None})
                if created:
                    FoundDeal.objects.create(lead=found, state="Qualified" if qualified else "Failed", outcome="" if qualified else "wrong_fit", reason="Synthetic fixture: practice decision-maker." if qualified else "Synthetic fixture: outside the selected roles.")
            from cold_outreach.emails.models import Mailbox, Message, Thread, DeliveryEvent
            box, _ = Mailbox.objects.get_or_create(from_address="fixture@preview.example", defaults={"host": "smtp.zoho.com", "username": "fixture@preview.example"})
            if not Message.objects.filter(message_id="leadzen-home-synthetic-out").exists():
                thread = Thread.objects.create(mailbox=box)
                outbound = Message.objects.create(mailbox=box, thread=thread, direction="out", kind="outbound", message_id="leadzen-home-synthetic-out", to_address="bruce@preview.example", from_address=box.from_address, sent_at=timezone.now(), subject="Synthetic preview only")
                DeliveryEvent.objects.create(message=outbound, status="accepted")
                Message.objects.create(mailbox=box, thread=thread, direction="in", kind="human_reply", message_id="leadzen-home-synthetic-in", from_address="bruce@preview.example", to_address=box.from_address, received_at=timezone.now(), subject="Synthetic preview reply")


def synthetic_probe(values, kind):
    from leadzen.lead_finder import key
    keys = {"ai": values.llm_api_key, "discovery": key(values), "mailbox": values.imap_password or values.mailbox_password}
    if not keys[kind].startswith("synthetic-"):
        raise ValueError("Only synthetic test credentials are accepted in this disposable preview")
    return {"synthetic": True, **{"ai": {"answered": True}, "discovery": {"credits": 40}, "mailbox": {"smtp": values.mail_transport == "smtp", "imap": True}}[kind]}


from leadzen.chat.engine import decide as sdk_decide

def synthetic_decision(run):
    from leadzen.chat.engine import Decision
    from leadzen.chat.context import structured
    from pydantic_ai.models.test import TestModel
    prompt = run.thread.messages.filter(role="user").order_by("-created_at", "-pk").first().content.lower()
    context = structured(run.actor_id, run.thread.context)
    if run.steps == 0:
        choice = Decision(tool="get_workspace_context", text="Reading the current synthetic Workspace context")
    elif run.steps == 1:
        ids = context.get("selectedLeadIds") or ([context["currentLeadId"]] if context.get("currentLeadId") else [])
        draft = context.get("currentDraftId")
        if "draft_campaign" in prompt and ids:
            choice = Decision(tool="draft_campaign", arguments={"name": "Synthetic outreach draft", "category": "outreach", "contact_ids": ids[:25], "steps": [{"subject": "A question for {{company}}", "body": "Hi {{first_name}}, would a short introduction to our synthetic preview product be useful?", "delay_days": 0}], "delay_basis": "working_days"})
        elif "get emails" in prompt and ids:
            choice = Decision(tool="find_work_emails", arguments={"leadIds": ids[:25]})
        elif "find" in prompt:
            choice = Decision(tool="find_leads", text="I'll find 5 qualified sample practice owners without purchasing work-email addresses.", arguments={"count": 5, "includeEmails": False})
        elif "send" in prompt and "do not send" not in prompt and draft:
            from leadzen.config.models import ReviewedEmail
            reply = ReviewedEmail.objects.get(pk=draft).review.kind == "reply"
            choice = Decision(tool="send_reply" if reply else "send_email", arguments={"draftId": draft})
        elif "shorter" in prompt and draft:
            choice = Decision(tool="regenerate_draft", arguments={"draftId": draft, "instructions": "Make it shorter. Don't mention AI."})
        elif "draft" in prompt and context.get("currentThreadId"):
            choice = Decision(tool="draft_reply", arguments={"threadId": context["currentThreadId"]})
        elif "draft" in prompt and ids:
            choice = Decision(tool="create_drafts", arguments={"leadIds": ids[:25]})
        elif "reply" in prompt or "replied" in prompt:
            choice = Decision(tool="list_replies", arguments={"filters": {}})
        elif "why" in prompt and context.get("currentLeadId"):
            choice = Decision(tool="get_lead", arguments={"leadId": context["currentLeadId"]})
        elif "stop contacting" in prompt and context.get("currentLeadId"):
            choice = Decision(tool="suppress_contact", arguments={"leadId": context["currentLeadId"]})
        else:
            choice = Decision(tool="list_leads", arguments={"filters": {}})
    else:
        choice = Decision(tool="answer", text="## Workspace updated\n\nThe cards above show the **actual saved local results**.\n\n- Review each person and their qualification reason.\n- Open the same records in Workspace.\n- Ask me to draft outreach when you are ready.\n\nNo external AI, BetterContact credits, or real email were used in this synthetic preview.")
    # Exercise the actual SDK streaming/persistence path with a synthetic model.
    with patch("leadzen.ai.build_model", return_value=TestModel(custom_output_args=choice.model_dump())):
        return sdk_decide(run)


def synthetic_find(args):
    from leadzen.discovery_progress import current, DiscoveryPaused, ProgressOutput
    from openoutfind.crm.models import Lead, Deal
    from openoutfind.core.export import lead_record
    monitor = current()
    if not monitor:
        return {"stored": 0, "partial": False, "note": "Synthetic preview only. No external calls."}
    monitor.session.synthetic = True
    monitor.session.save(update_fields=["synthetic"])
    writer = ProgressOutput(monitor)
    stored = 0
    try:
        monitor.boundary()
        if not monitor.session.source_ids:
            monitor.event("searching", {"filters": {"job_title": "founder", "country": "United States"}})
        time.sleep(4)
        for index in range(args["count"]):
            monitor.boundary()
            if monitor.session.source_ids:
                lead = Lead.objects.filter(pk__in=monitor.session.source_ids).exclude(pk__in=monitor.session.candidates.filter(produced=True).values_list("source_id", flat=True)).first()
                if not lead:
                    break
                receipt = monitor.reserve_lookup({"data": [{"linkedin_url": lead.profile_url}], "enrich_email_address": True})
                monitor.submitted(receipt, {"id": f"synthetic-{lead.pk}"})
                monitor.report_lookup(receipt.request_id, {"status": "terminated", "credits_consumed": 1, "data": [{"contact_email_address_status": "valid"}]})
                lead.email = f"sample-{lead.pk}@preview.example"
                lead.save(update_fields=["email"])
                deal = Deal.objects.get(lead=lead)
            else:
                serial = monitor.session.candidates.count()
                for accepted in [False, True]:
                    name = ("Bruce Lish" if serial == 0 else "Sarah Smith" if index == 1 else "Alex Morgan") if accepted else ("Emily Waters" if index == 0 else "Christopher Gomez")
                    lead = Lead.objects.create(profile_url=f"https://example.com/leadzen-preview/{monitor.session.pk}/{serial}/{accepted}", full_name=name + " (sample)", job_title="Director of Dentistry" if accepted else "Dental Core Trainee", profile_text="Synthetic fixture only")
                    monitor.discovered([lead])
                    monitor.evaluating(lead)
                    time.sleep(0.6)  # Simulated review latency, only in this disposable preview.
                    deal = Deal.objects.create(lead=lead, state="Qualified" if accepted else "Failed", outcome="" if accepted else "wrong_fit", reason="Sample: director-level US dental practice decision-maker." if accepted else "Sample: trainee rather than the requested decision-maker.")
                    monitor.verdict(lead)
            if args["emails"] and not lead.email:
                receipt = monitor.reserve_lookup({"data": [{"linkedin_url": lead.profile_url}], "enrich_email_address": True})
                monitor.submitted(receipt, {"id": f"synthetic-{lead.pk}"})
                monitor.report_lookup(receipt.request_id, {"status": "terminated", "credits_consumed": 1, "data": [{"contact_email_address_status": "valid"}]})
                lead.email = f"sample-{lead.pk}@preview.example"
                lead.save(update_fields=["email"])
            writer.write(json.dumps(lead_record(deal)) + "\n")
            stored += 1
            time.sleep(3)
        return {"stored": stored, "partial": False, "note": "Synthetic local preview completed. No external calls or real credits spent."}
    except DiscoveryPaused:
        return {"stored": stored, "partial": False, "paused": True}


def preview_launch(request, run):
    from leadzen.chat.engine import drive
    if run.thread.context.get("mcpConnectionId"):
        from leadzen.mcp.worker import drive
    from django.db import connections
    def work():
        try:
            with workspace_scope(request.actor.leadzen_profile):
                drive(run.pk)
        finally:
            connections.close_all()
    threading.Thread(target=work, daemon=True).start()


def synthetic_email_drafts(review, drafts):
    from leadzen.crm import contact_name
    return [{"id": str(d.pk), "subject": "Synthetic: patient review engagement", "body": f"Hi {d.deal.lead.first_name or contact_name(d.deal)},\n\n" + ("Would a quick demo be useful?" if "shorter" in d.instructions.lower() else "I can walk you through the product and discuss pricing on a demo. What time works for you?" if review.kind == "reply" else "How do you currently collect and respond to patient reviews? Would a short demo be useful?") + "\n\nSynthetic local preview only. No external AI or email provider is called."} for d in drafts]


def synthetic_send(box, message, record):
    from cold_outreach.emails.models import DeliveryEvent
    if not str(message["To"]).endswith("@preview.example"):
        raise RuntimeError("Preview accepts synthetic fixture recipients only")
    DeliveryEvent.objects.create(message=record, status="accepted", queue_id="synthetic-preview-acceptance")


def synthetic_space_out(box, now):
    from datetime import timedelta
    box.next_send_at = now + timedelta(seconds=2)
    box.save(update_fields=["next_send_at"])


def reviewed_preview_launch(request, job):
    if job.kind != "reviewed":
        return disabled_job(request, job)
    from django.http import JsonResponse
    from django.db import connections
    from leadzen.config.models import OutreachJob, EmailReview
    from leadzen.outreach import run_review
    profile = request.actor.leadzen_profile
    def work():
        try:
            with workspace_scope(profile):
                current = OutreachJob.objects.get(pk=job.pk)
                if OutreachJob.objects.filter(pk=current.pk, status="queued").update(status="running", started_at=timezone.now()) != 1:
                    return
                current.refresh_from_db()
                run_review(current, wait=True)
                OutreachJob.objects.filter(pk=current.pk, status="running").update(status="succeeded", finished_at=timezone.now(), output="Synthetic preview only; no real email sent")
        except Exception:
            with workspace_scope(profile):
                OutreachJob.objects.filter(pk=job.pk, status="running").update(status="failed", finished_at=timezone.now(), output="Synthetic preview failed; no real provider called")
                EmailReview.objects.filter(pk=job.campaign_approval.get("review_id"), status__in=["running", "queued"]).update(status="failed")
        finally:
            connections.close_all()
    threading.Thread(target=work, daemon=True).start()
    return JsonResponse({"job": {"id": str(job.pk)}}, status=202)

with patch("leadzen.accounts.invitations.post_email", catch_mail), patch("smtplib.SMTP", side_effect=RuntimeError("External sending disabled in local preview")), patch("smtplib.SMTP_SSL", side_effect=RuntimeError("External sending disabled in local preview")), patch("leadzen.web._launch_job", reviewed_preview_launch), patch("leadzen.outreach.generate", synthetic_email_drafts), patch("leadzen.outreach.sync_replies_strict"), patch("leadzen.outreach.within_sending_window", return_value=True), patch("cold_outreach.emails.sender._deliver", synthetic_send), patch("cold_outreach.emails.steps.send.space_out", synthetic_space_out), patch("leadzen.chat.views.launch", preview_launch), patch("leadzen.chat.engine.decide", synthetic_decision), patch("leadzen.chat.engine.find_leads", synthetic_find), patch("leadzen.ai.build_model", side_effect=RuntimeError("External models disabled in preview")), patch("leadzen.email_api.post_email", side_effect=RuntimeError("External email disabled in preview")), patch("leadzen.transports.public_socket", side_effect=RuntimeError("External mailbox access disabled in preview")), patch("leadzen.setup_wizard.probe_ai", lambda values: synthetic_probe(values, "ai")), patch("leadzen.setup_wizard.probe_discovery", lambda values: synthetic_probe(values, "discovery")), patch("leadzen.setup_wizard.probe_mailbox", lambda values: synthetic_probe(values, "mailbox")):
    print("Local API ready at http://127.0.0.1:8000. Invitations are caught locally; reviewed outreach uses synthetic acceptance only. All external providers and campaign sends are disabled.", flush=True)
    with make_server("127.0.0.1", 8000, get_wsgi_application(), handler_class=QuietLog, server_class=PreviewServer) as server:
        server.serve_forever()
