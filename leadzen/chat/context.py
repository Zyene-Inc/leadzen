"""Canonical UI references, validated against the routed Workspace database."""
from django.db import transaction
from leadzen.config.models import WorkspaceContext, ChatThread, ChatRun, ReviewedEmail, EmailCampaign, SiteConfig
from leadzen.crm import owned_contact, contact_payload

FIELDS = {"selectedLeadIds", "currentLeadId", "currentDraftId", "currentThreadId", "currentRunId", "currentCampaignId", "workspacePath", "lastChatId"}


def validate(actor_id, changes):
    from cold_outreach.emails.models import Thread
    if not isinstance(changes, dict) or set(changes) - FIELDS:
        raise ValueError("Choose supported Workspace context references")
    result = dict(changes)
    for key in ("currentLeadId", "currentThreadId"):
        value = result.get(key)
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError("Choose a canonical Workspace object ID")
    ids = result.get("selectedLeadIds", [])
    if not isinstance(ids, list) or len(ids) > 100 or any(type(i) is not int or i < 1 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Choose distinct Workspace leads")
    if any(not owned_contact(i) for i in ids + ([result["currentLeadId"]] if result.get("currentLeadId") else [])):
        raise ValueError("A selected lead is no longer available in this Workspace")
    if result.get("currentThreadId") and not Thread.objects.filter(pk=result["currentThreadId"]).exists():
        raise ValueError("Conversation not found")
    for key, model, lookup in (("currentDraftId", ReviewedEmail, {"review__actor_id": actor_id}), ("currentRunId", ChatRun, {"actor_id": actor_id}), ("lastChatId", ChatThread, {"actor_id": actor_id, "archived": False, "deleted_at__isnull": True}), ("currentCampaignId", EmailCampaign, {})):
        if result.get(key):
            import uuid
            try:
                result[key] = str(uuid.UUID(str(result[key])))
            except ValueError:
                raise ValueError("Choose a canonical Workspace object ID") from None
            if not model.objects.filter(pk=result[key], **lookup).exists():
                raise ValueError("Workspace object not found")
    if "workspacePath" in result:
        path = result["workspacePath"]
        import re
        if not isinstance(path, str) or not re.fullmatch(r"(?:/inbox\?thread=\d{1,12}&review=[0-9a-f-]{36}|/(?:contacts(?:/\d+)?|campaigns|outreach|sending|inbox|find-leads(?:/[0-9a-f-]{36})?|settings|suppression|activity)?(?:\?(?:review|thread|campaign)=[0-9a-f-]+)?)", path):
            raise ValueError("Choose a Workspace page")
    return result


def save(actor_id, changes):
    changes = validate(actor_id, changes)
    with transaction.atomic(using=WorkspaceContext.objects.all().db):
        row, _ = WorkspaceContext.objects.get_or_create(actor_id=actor_id)
        row.references = {**row.references, **changes}
        row.save()
    return row.references


def structured(actor_id, references=None):
    from leadzen.home import current_target
    from leadzen.config.models import OnboardingState
    config = SiteConfig.load()
    row = WorkspaceContext.objects.filter(actor_id=actor_id).first()
    refs = dict(references if references is not None else row.references if row else {})
    # Remove deleted/stale references rather than letting conversational memory repair them.
    for key in list(refs):
        try:
            validate(actor_id, {key: refs[key]})
        except ValueError:
            refs[key] = [] if key == "selectedLeadIds" else None
    leads = {i for i in refs.get("selectedLeadIds", [])}
    if refs.get("currentLeadId"):
        leads.add(refs["currentLeadId"])
    from leadzen.accounts.models import AccountProfile
    import os
    profile = AccountProfile.objects.using("control" if os.environ.get("LEADZEN_CONTROL_DB") else "default").filter(user_id=actor_id).first()
    state = OnboardingState.objects.filter(pk=1).first()
    return {"workspaceId": str(profile.pk) if profile else str(actor_id), "workspaceName": (profile.workspace_name if profile else "") or (state.draft.get("workspace_name") if state else "") or config.operator_name or "Your Workspace", "product": config.product_docs[:5000],
            "target": current_target(config, OnboardingState.objects.filter(pk=1).first()),
            "selectedLeadIds": [], "currentLeadId": None, "currentDraftId": None, "currentThreadId": None, "currentRunId": None,
            **refs, "referencedLeads": [contact_payload(owned_contact(i)) for i in sorted(leads)[:25]]}


def remember(row, **references):
    refs = save(row.actor_id, references)
    row.thread.context = {**row.thread.context, **refs}
    row.thread.save(update_fields=["context", "updated_at"])
