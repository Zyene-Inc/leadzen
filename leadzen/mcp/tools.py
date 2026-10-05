"""Strict employee capabilities over LeadZen's canonical Workspace services.

OAuth grants access to records; it does not approve spending, inbox access, or
sending. External actions become one durable Chat approval and one bounded worker.
"""
import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Literal

from django.db import IntegrityError, transaction
from django.utils import timezone
from pydantic import Field, StrictInt, create_model, field_validator

from leadzen.chat import tools as chat_tools
from leadzen.chat.tools import Arguments, Empty, Lead, Leads, List, Draft, Edit, Regenerate, Thread, Reply, Suppress, Target, Find
from leadzen.config.models import ChatRun, ChatThread, EmailCampaign

ACTIVE = ["queued", "running", "awaiting_approval", "paused"]


class Request(Arguments):
    requestId: str = Field(pattern=r"^[0-9a-fA-F-]{36}$", description="New UUID for this action. Reuse only to retrieve the identical action, never to retry uncertain work.")

    @field_validator("requestId")
    @classmethod
    def canonical_request(cls, value):
        return str(uuid.UUID(value))


class Operation(Arguments):
    operationId: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")

    @field_validator("operationId")
    @classmethod
    def canonical_operation(cls, value):
        return str(uuid.UUID(value))


class Contact(Arguments):
    email: str = Field(max_length=254)
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    company: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=500)
    profile_text: str = Field(default="", max_length=10000)
    opted_in: Literal[False] = False
    consent_note: Literal[""] = ""


class AddContact(Arguments):
    contact: Contact


class ImportContacts(Arguments):
    contacts: list[Contact] = Field(min_length=1, max_length=25)


class UpdateContact(Lead):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    profile_text: str | None = Field(default=None, max_length=10000)


class SendDrafts(Arguments):
    draftIds: list[str] = Field(min_length=1, max_length=25)

    @field_validator("draftIds")
    @classmethod
    def canonical_drafts(cls, values):
        values = [str(uuid.UUID(value)) for value in values]
        if len(set(values)) != len(values):
            raise ValueError("Choose distinct draft IDs")
        return values


class Campaign(Arguments):
    campaignId: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")

    @field_validator("campaignId")
    @classmethod
    def canonical_campaign(cls, value):
        return str(uuid.UUID(value))


class SendCampaign(Campaign):
    count: StrictInt = Field(default=25, ge=1, le=25)


class SequenceStep(Arguments):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    delay_days: StrictInt = Field(ge=0, le=90)


class CreateCampaign(Arguments):
    name: str = Field(min_length=1, max_length=160)
    leadIds: list[StrictInt] = Field(min_length=1, max_length=25)
    steps: list[SequenceStep] = Field(min_length=1, max_length=3)
    category: Literal["outreach", "opted_in", "transactional"] = "outreach"
    target: str = Field(default="", max_length=2000)
    product: str = Field(default="", max_length=2000)
    signature: str = Field(default="", max_length=2000)
    booking_link: str = Field(default="", max_length=500)
    delay_basis: Literal["working_days", "calendar_days"] = "working_days"

    @field_validator("leadIds")
    @classmethod
    def distinct_leads(cls, ids):
        return Leads(leadIds=ids).leadIds


class Schedule(Arguments):
    timezone: Literal["America/New_York"] = "America/New_York"
    days: list[StrictInt] = Field(min_length=1, max_length=7)
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class Identity(Arguments):
    operator_name: str = Field(min_length=1, max_length=160)
    operator_email: str = Field(max_length=254)
    operator_country_code: str = Field(pattern=r"^[A-Z]{2}$")


class Product(Arguments):
    product_name: str = Field(default="", max_length=160)
    product_docs: str = Field(min_length=1, max_length=10000)


class SettingChanges(Arguments):
    identity: Identity | None = None
    product: Product | None = None
    booking_link: str | None = Field(default=None, max_length=500)
    sending_schedule: Schedule | None = None


class UpdateSettings(Arguments):
    changes: SettingChanges


class StopDiscovery(Arguments):
    runId: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")


# Entries are static and never select a handler, module, URL or SQL from input.
# mutation=True requires an idempotency UUID; external=True always needs portal
# approval, including free discovery's AI/model requests.
ENTRIES = {
    "get_workspace_status": (Empty, "Workspace status and tasks needing attention.", False, False),
    "get_workspace_context": (Empty, "Saved employee offer, target and canonical references.", False, False),
    "list_leads": (List, "Search up to 25 saved employee leads by bounded filters.", False, False),
    "get_lead": (Lead, "Read a canonical saved lead, history and outreach state.", False, False),
    "create_lead": (AddContact, "Add one real contact. Does not invent or grant opt-in consent.", True, False),
    "update_lead": (UpdateContact, "Edit contact details, preserving email identity and consent.", True, False),
    "delete_lead": (Lead, "Remove a contact from the employee list and stop pending outreach.", True, False),
    "import_leads": (ImportContacts, "Import up to 25 contacts atomically, with no email sending.", True, False),
    "find_leads": (Find, "Prepare free-profile discovery (no email purchases); portal approval covers model/provider use.", True, True),
    "find_work_emails": (Leads, "Prepare paid verified-email lookup for selected saved profiles; requires portal approval.", True, True),
    "stop_discovery": (StopDiscovery, "Stop a canonical employee discovery run; retain saved results.", True, False),
    "get_credit_usage": (Empty, "Read saved credit usage and uncertain lookups without a provider request.", False, False),
    "create_drafts": (chat_tools.Drafts, "Prepare personal drafts for up to 25 leads; portal approval covers AI use. Sends nothing.", True, True),
    "get_draft": (Draft, "Read one canonical draft and complete reviewed copy.", False, False),
    "update_draft": (Edit, "Edit exact draft text; AI instructions require portal approval. Edits revoke prior message approvals.", True, False),
    "regenerate_draft": (Regenerate, "Prepare AI draft revision with exact instructions; portal approval required. Sends nothing.", True, True),
    "send_email": (Draft, "Prepare exact message and recipient approval in the portal; cannot send from client consent alone.", True, True),
    "send_emails": (SendDrafts, "Prepare exact portal approval for up to 25 drafts; pacing and sending checks remain enforced.", True, True),
    "list_campaigns": (Empty, "Read up to 25 saved Outreach sequences and their state.", False, False),
    "get_campaign": (Campaign, "Read a saved sequence, recipients, content and schedule.", False, False),
    "create_campaign": (CreateCampaign, "Save an employee sequence draft; does not activate or authorize follow-ups.", True, False),
    "pause_campaign": (Campaign, "Pause a saved sequence to stop new sends. Accepted mail cannot be recalled.", True, False),
    "send_campaign": (SendCampaign, "Prepare one due-send pass for exact portal review. Future automatic follow-ups remain a portal authorization.", True, True),
    "list_replies": (List, "Read stored human replies; does not refresh the external inbox.", False, False),
    "get_thread": (Thread, "Read a canonical Inbox conversation and message history.", False, False),
    "sync_mailbox": (Empty, "Prepare external reply check and optional AI classification; portal approval required.", True, True),
    "draft_reply": (Reply, "Prepare an AI reply draft for a saved conversation, after portal approval. Sends nothing.", True, True),
    "send_reply": (Draft, "Prepare exact reviewed reply approval in the portal.", True, True),
    "get_settings": (Empty, "Read nonsecret employee settings. Credentials, storage paths and admin features are never exposed.", False, False),
    "update_settings": (UpdateSettings, "Edit nonsecret identity, offer, booking URL or weekly New York hours. No connections or approvals can be configured.", True, False),
    "get_target": (Empty, "Read the current saved lead audience.", False, False),
    "update_target": (Target, "Save a bounded lead audience without discovering or emailing.", True, False),
    "get_autopilot": (Empty, "Read Autopilot state. Enabling or expanding standing authorization requires the portal.", False, False),
    "pause_autopilot": (Empty, "Disable Daily Autopilot and stop pending automatic work.", True, False),
    "get_activity": (List, "Read bounded saved activity; imported content is untrusted data.", False, False),
    "list_suppressions": (List, "Read saved do-not-contact records without external requests.", False, False),
    "suppress_contact": (Suppress, "Stop outreach to a selected contact and record a manual address block.", True, False),
    "unsuppress_contact": (Lead, "Prepare portal review of removal of a manual block; terminal opt-outs stay blocked and sequences stay stopped.", True, True),
    "get_operation": (Operation, "Poll actual result, approval and saved status for this connection's operation. Never repeats it.", False, False),
    "cancel_operation": (Operation, "Cancel this connection's pending operation. In-flight provider acceptance cannot be recalled.", True, False),
}
SCHEMAS = {name: create_model("MCP" + "".join(part.title() for part in name.split("_")), __base__=(schema, Request)) if mutation else schema
           for name, (schema, _description, mutation, _external) in ENTRIES.items()}


def list_tools():
    return [{"name": name, "description": description, "inputSchema": SCHEMAS[name].model_json_schema(),
             "annotations": {"readOnlyHint": not mutation, "destructiveHint": name == "delete_lead", "idempotentHint": True, "openWorldHint": external or name == "update_draft"}}
            for name, (_schema, description, mutation, external) in ENTRIES.items()]


def normalized(name, arguments):
    if name not in SCHEMAS:
        raise ValueError("Unknown employee capability")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    return SCHEMAS[name].model_validate(arguments).model_dump(exclude_none=name in {"update_settings", "update_lead"})


def _operation(actor, connection, operation_id):
    row = ChatRun.objects.select_related("thread").filter(pk=operation_id, actor_id=actor.pk, thread__actor_id=actor.pk).first()
    if not row or row.thread.context.get("mcpConnectionId") != str(connection.pk):
        raise ValueError("Operation not found for this connection")
    return row


def operation_payload(row):
    from leadzen.chat.engine import redact
    from leadzen.chat.views import run_payload
    result = row.thread.messages.filter(role="tool", data__mcpOperationId=str(row.pk)).order_by("-created_at", "-pk").first()
    if not result:
        result = row.thread.messages.filter(role="tool").order_by("-created_at", "-pk").first()
    path = f"/chat/{row.thread_id}"
    from leadzen.mcp.auth import configuration
    origin = configuration()[2].rstrip("/")
    return _portal_links(redact({"operationId": str(row.pk), "status": row.status, "operation": run_payload(row),
                   "result": result.data.get("result") if result else None, "portalUrl": origin + path,
                   "note": "Open the portal to review and approve the exact action. No external action has started." if row.status == "awaiting_approval"
                   else "Open the saved discovery in LeadZen to resume only the remaining approved goal. Polling does not resume work." if row.status == "paused"
                   else "This is saved operation state. Polling does not restart, approve or repeat work."}))


def _portal_links(value):
    """Only server-generated Workspace navigation keys get the trusted origin."""
    from leadzen.mcp.auth import configuration
    origin = configuration()[2].rstrip("/")
    if isinstance(value, list):
        return [_portal_links(item) for item in value]
    if isinstance(value, dict):
        return {key: origin + item if key in {"workspaceUrl", "portalUrl", "authorizationUrl"} and isinstance(item, str) and item.startswith("/") and not item.startswith("//")
                else _portal_links(item) if isinstance(item, (dict, list)) else item for key, item in value.items()}
    return value


def _settings(actor):
    from leadzen.web import _settings_payload
    from leadzen.workspace_settings import settings_payload
    payload = settings_payload(actor)["workspace"]
    return {"workspace": {key: payload[key] for key in ("identity", "product", "booking_link", "sending_schedule", "target", "checks")},
            "connections": _public_connections(_settings_payload()), "workspaceUrl": "/settings",
            "note": "Credentials, connection changes, provider tests, backups and standing authorizations are managed only in the portal."}


def _invoke(actor, view, body=None, method="GET", **parameters):
    return chat_tools.invoke(SimpleNamespace(actor_id=actor.pk), view, body, method, **parameters)


def _canonical_tool(name, args):
    if name in chat_tools.SEND_TOOLS:
        return name, {**args, "approvalToken": None}
    if name in {"pause_campaign", "send_campaign"}:
        return name, {"campaign_id": args["campaignId"], **({"count": args["count"]} if name == "send_campaign" else {})}
    if name == "create_campaign":
        return "draft_campaign", {"contact_ids": args["leadIds"], **{key: value for key, value in args.items() if key != "leadIds"}}
    return name, args


def _generation_preview(actor, name, args):
    from leadzen.crm import contact_payload
    row = SimpleNamespace(actor_id=actor.pk)
    if name == "create_drafts":
        leads = chat_tools.lead_rows(args["leadIds"])
        recipients = [contact_payload(lead) for lead in leads]
    elif name == "draft_reply":
        from leadzen.outreach import conversation
        conversation_data = _invoke(actor, conversation, thread_id=args["threadId"])
        recipients = [conversation_data]
    else:
        draft = chat_tools.draft_rows(row, [args["draftId"]])[0]
        from leadzen.outreach import review_payload
        recipients = [item for item in review_payload(draft.review)["drafts"] if item["id"] == str(draft.pk)]
    return {"recipients": recipients, "instructions": args.get("instructions", ""),
            "note": "Uses your saved AI provider and may incur provider charges. Creates or revises only these drafts; this approval sends no emails."}


def _execute_local(actor, connection, name, args):
    from leadzen.chat.engine import execute
    from leadzen import campaigns, outreach
    row = SimpleNamespace(actor_id=actor.pk, thread=SimpleNamespace(context={}))
    if name == "get_operation":
        return operation_payload(_operation(actor, connection, args["operationId"]))
    if name == "get_workspace_context":
        from leadzen.chat.context import structured
        return structured(actor.pk)
    if name == "get_lead":
        return _invoke(actor, campaigns.contact, deal_id=args["leadId"])
    if name == "get_draft":
        draft = chat_tools.draft_rows(row, [args["draftId"]])[0]
        return {**outreach.review_payload(draft.review), "drafts": [item for item in outreach.review_payload(draft.review)["drafts"] if item["id"] == str(draft.pk)], "workspaceUrl": f"/outreach?review={draft.review_id}"}
    if name == "get_thread":
        return _invoke(actor, outreach.conversation, thread_id=args["threadId"])
    if name == "get_settings":
        return _settings(actor)
    if name == "get_autopilot":
        from leadzen.autopilot import state
        return {**state(actor.pk), "workspaceUrl": "/outreach", "authorizationUrl": "/outreach"}
    if name == "pause_autopilot":
        from leadzen.autopilot import settings
        return _invoke(actor, settings, {"enabled": False}, "POST")
    if name == "get_campaign":
        campaign = EmailCampaign.objects.filter(pk=args["campaignId"]).first()
        if not campaign:
            raise ValueError("Sequence not found in your Workspace")
        return {**campaigns.campaign_payload(campaign), "workspaceUrl": f"/outreach?campaign={campaign.pk}"}
    if name == "list_campaigns":
        return {"items": [campaigns.campaign_payload(c) for c in EmailCampaign.objects.order_by("-created_at")[:25]], "workspaceUrl": "/outreach"}
    if name == "list_suppressions":
        from cold_outreach.leads.models import Suppression
        from leadzen.suppression import record_payload
        records = Suppression.objects.order_by("-suppressed_at", "-pk")
        filters = args["filters"]
        if filters["query"]:
            from django.db.models import Q
            records = records.filter(Q(email__icontains=filters["query"]) | Q(reason__icontains=filters["query"]))
        if filters.get("since"):
            records = records.filter(suppressed_at__gte=filters["since"])
        return {"items": [record_payload(record) for record in records[:filters["limit"]]], "workspaceUrl": "/suppression"}
    if name in {"create_lead", "import_leads"}:
        return _invoke(actor, campaigns.add_contacts, args["contact"] if name == "create_lead" else args, "POST")
    if name == "update_lead":
        from leadzen.crm import owned_contact
        from leadzen.config.models import ContactPreferences
        deal = owned_contact(args["leadId"])
        if not deal:
            raise ValueError("Lead not found in your Workspace")
        preferences = ContactPreferences.objects.filter(lead=deal.lead).first()
        body = {key: getattr(deal.lead, key) or "" for key in ("email", *campaigns.FIELDS)}
        body.update({key: value for key, value in args.items() if key != "leadId"})
        body.update(opted_in=bool(preferences and preferences.opted_in), consent_note=preferences.consent_note if preferences else "")
        return _invoke(actor, campaigns.contact, body, "PUT", deal_id=deal.pk)
    if name == "delete_lead":
        return _invoke(actor, campaigns.contact, method="DELETE", deal_id=args["leadId"])
    if name == "update_settings":
        from leadzen.web import runtime_settings
        return _safe_settings_result(_invoke(actor, runtime_settings, {"workspace_updates": args["changes"]}, "PUT"))
    if name == "cancel_operation":
        target = _operation(actor, connection, args["operationId"])
        ChatRun.objects.filter(pk=target.pk, status__in=ACTIVE).update(cancel_requested=True)
        ChatRun.objects.filter(pk=target.pk, status__in=["queued", "awaiting_approval", "paused"]).update(status="cancelled", pending={}, finished_at=timezone.now())
        target.refresh_from_db()
        return operation_payload(target)
    canonical, canonical_args = _canonical_tool(name, args)
    return execute(canonical, canonical_args, row)


def _safe_settings_result(result):
    result = dict(result)
    result["workspace"] = {key: result["workspace"][key] for key in ("identity", "product", "booking_link", "sending_schedule", "target", "checks")}
    return {"workspace": result["workspace"], "connections": _public_connections(result), "workspaceUrl": "/settings"}


def _public_connections(payload):
    return {"ai": {key: payload["llm"][key] for key in ("enabled", "provider", "model", "api_key_configured")},
            "mailbox": {key: payload["mailbox"][key] for key in ("transport", "address", "signature", "api_key_configured", "password_configured", "imap_password_configured")},
            "lead_finder": payload["lead_finder"]}


def call_tool(actor, connection, name, arguments):
    from leadzen.chat.engine import event, finish, prepare, redact
    from leadzen.mcp.auth import connection_live
    live = connection_live(connection.pk, actor.pk)
    args = normalized(name, arguments)
    _schema, _description, mutation, external = ENTRIES[name]
    required_scope = "leadzen:write" if mutation else "leadzen:read"
    if required_scope not in live.scopes:
        raise PermissionError("This connection does not grant this capability")
    if not mutation:
        return _portal_links(redact(_execute_local(actor, connection, name, args)))
    request_id = args.pop("requestId")
    action = {"name": name, "arguments": args}
    existing = ChatRun.objects.select_related("thread").filter(request_id=request_id).first()
    if existing:
        if existing.actor_id != actor.pk or existing.thread.context.get("mcpConnectionId") != str(connection.pk) or existing.thread.context.get("mcpAction") != action:
            raise ValueError("Request ID already used for a different action")
        return operation_payload(existing)
    # Cancellation is allowed while its own target is active. Execute it first
    # inside the same transaction; other changes share Chat's per-actor task lock.
    alias = ChatRun.objects.all().db
    from leadzen.chat.views import recover_stale
    recover_stale(actor.pk)
    try:
        with transaction.atomic(using=alias):
            stopping = name in {"cancel_operation", "stop_discovery", "suppress_contact", "pause_campaign", "pause_autopilot"}
            if not stopping and ChatRun.objects.filter(actor_id=actor.pk, status__in=ACTIVE).exists():
                raise ValueError("Finish or cancel your active task in LeadZen before starting another action")
            if ChatRun.objects.filter(actor_id=actor.pk, created_at__gt=timezone.now() - timedelta(minutes=10)).count() >= 30:
                raise ValueError("Operation limit reached. Try again in a few minutes")
            if ChatThread.objects.filter(actor_id=actor.pk, archived=False, deleted_at__isnull=True).count() >= 100:
                raise ValueError("Archive an old conversation in LeadZen before starting another operation")
            local_result = _execute_local(actor, connection, name, args) if name == "cancel_operation" else None
            thread = ChatThread.objects.create(actor_id=actor.pk, title=f"Connected assistant: {name.replace('_', ' ')}"[:100],
                context={"mcpConnectionId": str(connection.pk), "mcpAction": action})
            row = ChatRun.objects.create(actor_id=actor.pk, thread=thread, request_id=request_id, status="succeeded" if stopping else "running", deadline_at=timezone.now() + timedelta(minutes=10))
            # Send intent is canonical capability selection, never imported data.
            event(row, "user", f"Request {name.replace('_', ' ')} from my connected assistant.", {"source": "mcp", "arguments": args})
            needs_external = external or (name == "update_draft" and bool(args.get("instructions")))
            if needs_external:
                canonical, canonical_args = _canonical_tool(name, args)
                preview = _generation_preview(actor, name, args) if name in {"create_drafts", "draft_reply", "regenerate_draft", "update_draft"} else None
                prepare(row, canonical, chat_tools.engine_find_args(canonical_args) if canonical == "find_leads" else canonical_args)
                row.refresh_from_db()
                if canonical == "find_leads":
                    row.pending = {**row.pending, "arguments": canonical_args}
                    row.save(update_fields=["pending", "updated_at"])
                if preview is not None:
                    summary = {"create_drafts": "Create personal email drafts?", "draft_reply": "Draft a conversation reply?", "regenerate_draft": "Regenerate this email draft?", "update_draft": "Revise this draft with AI?"}[name]
                    row.pending = {**row.pending, "summary": summary, "preview": redact(preview)}
                    row.save(update_fields=["pending", "updated_at"])
                return operation_payload(row)
            if name != "cancel_operation":
                # Typed update_draft requires a persisted row for shared context.
                local_result = chat_tools.execute(row, name, args) if name in {"update_draft", "suppress_contact", "unsuppress_contact"} else _execute_local(actor, connection, name, args)
            event(row, "tool", "Saved employee operation", {"tool": name, "mcpOperationId": str(row.pk), "result": local_result})
            finish(row, "succeeded", "Saved. No external provider action was started.")
            row.refresh_from_db()
            return operation_payload(row)
    except IntegrityError:
        raise ValueError("Another task started in your Workspace. Review it before retrying") from None
