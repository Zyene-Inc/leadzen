# leadzen/config/models.py
"""Every answer this install gave, in one row — and the two vocabularies it exports into.

**This is the one place a human's answer is remembered, and this is the program with a
human in front of it.** The children are agent-first: `openoutfind` and `openoutsend` read
their configuration from `OPENOUTFIND_*` / `OUTSEND_*` on every run and persist none of
it, because an agent supplies its environment on every invocation and has nothing to
remember. Somebody who types does not want to retype, so the wizard asks once and this row
answers for them from then on.

**Exporting is not a translation layer.** That objection was real while each child *also*
had a config model — two surfaces for the strings to drift against. With the environment as
a child's only surface, `export()` writes the one interface each child has, and the child
fails loudly naming a variable if this row ever stops filling it.

The split against the children is the same rule they follow internally: **an answer
somebody gave lives here; what a pipeline produced or measured lives in the child's own
store.** So the leads, the walk, the mail log, the suppression list and the mailbox's
learned capacity are not here and never will be.
"""
from __future__ import annotations

import uuid

from django.db import models

# Where each field lands in the finder's vocabulary. A field absent from both maps is one
# only this host reads (`operator_name` is the sender's alone, and so on).
FINDER_ENV = {
    "product_docs": "OPENOUTFIND_PRODUCT_DOCS",
    "campaign_target": "OPENOUTFIND_CAMPAIGN_TARGET",
    "ai_model": "OPENOUTFIND_AI_MODEL",
    "llm_api_key": "OPENOUTFIND_LLM_API_KEY",
    "llm_api_base": "OPENOUTFIND_LLM_API_BASE",
    "bettercontact_api_key": "OPENOUTFIND_BETTERCONTACT_API_KEY",
    "apollo_api_key": "OPENOUTFIND_APOLLO_API_KEY",
    "email_finder": "OPENOUTFIND_EMAIL_FINDER",
    "operator_email": "OPENOUTFIND_OPERATOR_EMAIL",
    "operator_country_code": "OPENOUTFIND_OPERATOR_COUNTRY",
    "contacts_api_token": "OPENOUTFIND_CONTACTS_API_TOKEN",
    "accepted_legal_notice": "OPENOUTFIND_ACCEPT_LEGAL_NOTICE",
    "newsletter": "OPENOUTFIND_NEWSLETTER",
}

# And in the sender's. **The suffixes are not always the same** — `OPENOUTFIND_OPERATOR_COUNTRY`
# against `OUTSEND_OPERATOR_COUNTRY`, `OUTSEND_OPERATOR_NAME` against a finder that signs
# nothing — which is exactly why the mapping is written down once here instead of being
# guessed from a prefix.
SENDER_ENV = {
    "product_docs": "OUTSEND_PRODUCT_DOCS",
    "campaign_target": "OUTSEND_CAMPAIGN_TARGET",
    "booking_link": "OUTSEND_BOOKING_LINK",
    "ai_model": "OUTSEND_AI_MODEL",
    "llm_api_key": "OUTSEND_LLM_API_KEY",
    "llm_api_base": "OUTSEND_LLM_API_BASE",
    "operator_name": "OUTSEND_OPERATOR_NAME",
    "operator_email": "OUTSEND_OPERATOR_EMAIL",
    "operator_country_code": "OUTSEND_OPERATOR_COUNTRY",
    "mailbox_address": "OUTSEND_MAILBOX_ADDRESS",
    "mailbox_password": "OUTSEND_MAILBOX_PASSWORD",
    "smtp_host": "OUTSEND_SMTP_HOST",
    "smtp_port": "OUTSEND_SMTP_PORT",
    "imap_host": "OUTSEND_IMAP_HOST",
    "imap_port": "OUTSEND_IMAP_PORT",
    "signature": "OUTSEND_SIGNATURE",
}


class SiteConfig(models.Model):
    """The answers, as a singleton. `load()` is the only way anything reads it."""

    # ── what you sell, and to whom ────────────────────────────────
    product_docs = models.TextField(blank=True, default="")
    campaign_target = models.TextField(blank=True, default="")
    # Never required: the sender renders its whole booking block only when there is one.
    booking_link = models.CharField(max_length=500, blank=True, default="")

    # ── the model that judges and writes ──────────────────────────
    # A pydantic-ai `provider:model` id — the provider lives inside the string, so there
    # is no second field to drift out of sync.
    ai_model = models.CharField(max_length=200, blank=True, default="")
    llm_api_key = models.CharField(max_length=500, blank=True, default="")
    # Only the openai_compatible provider reads this one.
    llm_api_base = models.CharField(max_length=500, blank=True, default="")

    # ── finding people ────────────────────────────────────────────
    # BetterContact's key powers discovery (free) as well as enrichment (paid); Apollo's
    # only resolves an address, so it never stands alone.
    bettercontact_api_key = models.CharField(max_length=500, blank=True, default="")
    apollo_api_key = models.CharField(max_length=500, blank=True, default="")
    email_finder = models.CharField(max_length=32, blank=True, default="")

    # ── the operator ──────────────────────────────────────────────
    # The name signs the mail; the address is where the store keys this install and where
    # the newsletter goes. Both children turn these into the one Django `User` they share.
    operator_name = models.CharField(max_length=200, blank=True, default="")
    operator_email = models.EmailField(blank=True, default="")
    # ISO-3166 alpha-2 — the operator's *jurisdiction*, not a target market.
    operator_country_code = models.CharField(max_length=2, blank=True, default="")
    # An acceptance somebody gave is a record. It is kept because it was given, and the
    # children are told about it on every run because they keep nothing.
    accepted_legal_notice = models.BooleanField(default=False)
    # Consent, and never a default: silence is not a yes in any jurisdiction.
    newsletter = models.BooleanField(default=False)

    # ── the mailbox this install sends from ───────────────────────
    # The password is the provider's app password — a Google box rejects a login password
    # outright. Host and port stay blank unless the operator's provider needs them; the
    # sender's own model carries the Google Workspace defaults, and exporting a blank
    # would override them with nothing.
    mailbox_address = models.EmailField(blank=True, default="")
    mailbox_password = models.CharField(max_length=500, blank=True, default="")
    smtp_host = models.CharField(max_length=200, blank=True, default="")
    smtp_port = models.CharField(max_length=8, blank=True, default="")
    imap_host = models.CharField(max_length=200, blank=True, default="")
    imap_port = models.CharField(max_length=8, blank=True, default="")
    signature = models.TextField(blank=True, default="")
    # Empty preserves the existing sender/automatic-policy windows until an
    # employee explicitly saves a weekly schedule in Settings.
    sending_schedule = models.JSONField(default=dict, blank=True)

    # ── the contacts store ────────────────────────────────────────
    # Minted by the hub rather than typed, and kept so an install keeps one identity
    # across runs instead of registering itself on each one.
    contacts_api_token = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self):
        return "Site Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def export(self) -> dict[str, str]:
        """This row as the environment both children read.

        A blank field exports nothing at all rather than an empty string: to a child,
        unset means *use your default* (the sender's SMTP host, the finder's hub URL),
        while a blank value means the operator asked for nothing there. Booleans go as
        `true`/`false`, the only spellings the finder's gate accepts either way.
        """
        environment = {}
        # The two maps are walked separately, never merged: they are keyed by *field*,
        # and most fields appear in both, so merging them would silently keep one
        # child's variable and drop the other's.
        for mapping in (FINDER_ENV, SENDER_ENV):
            for field, variable in mapping.items():
                value = getattr(self, field)
                if isinstance(value, bool):
                    environment[variable] = "true" if value else "false"
                elif str(value).strip():
                    environment[variable] = str(value).strip()
        return environment


class RuntimeSettings(models.Model):
    """Dashboard-editable non-secret settings plus encrypted credential material.

    This is deliberately separate from ``SiteConfig``.  The wizard remains backwards
    compatible with the CLI, while dashboard edits do not write new mailbox or provider
    secrets into ordinary text columns.  ``encrypted_secrets`` is a Fernet token whose
    key is supplied only by the API process through ``LEADZEN_SETTINGS_KEY``.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    llm_provider = models.CharField(max_length=64, blank=True, default="")
    llm_model = models.CharField(max_length=200, blank=True, default="")
    llm_base_url = models.CharField(max_length=500, blank=True, default="")
    mailbox_address = models.EmailField(blank=True, default="")
    smtp_host = models.CharField(max_length=255, blank=True, default="")
    smtp_port = models.PositiveIntegerField(null=True, blank=True)
    imap_host = models.CharField(max_length=255, blank=True, default="")
    imap_port = models.PositiveIntegerField(null=True, blank=True)
    signature = models.TextField(blank=True, default="")
    encrypted_secrets = models.TextField(blank=True, default="")
    mail_transport = models.CharField(max_length=24, default="smtp")
    mail_api_url = models.CharField(max_length=500, blank=True, default="")
    smtp_username = models.CharField(max_length=320, blank=True, default="")
    ai_enabled = models.BooleanField(default=True)
    lead_finder_provider = models.CharField(max_length=24, default="bettercontact")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Runtime Settings"
        verbose_name_plural = "Runtime Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "RuntimeSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class OutreachJob(models.Model):
    """A dashboard-triggered worker run with durable, inspectable state."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=32, default="send")
    requested_count = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    pid = models.PositiveIntegerField(null=True, blank=True)
    output = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    campaign_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True, unique=True)
    campaign_approval = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]


class OnboardingState(models.Model):
    """Private, resumable public answers and server-issued test receipts."""
    draft = models.JSONField(default=dict)
    completed_steps = models.JSONField(default=list)
    checks = models.JSONField(default=dict)
    testing_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class ContactPreferences(models.Model):
    lead = models.OneToOneField("outsend_leads.Lead", on_delete=models.CASCADE, related_name="preferences")
    opted_in = models.BooleanField(default=False)
    consent_note = models.CharField(max_length=500, blank=True, default="")
    # Remove from the workspace without erasing conversation or opt-out history.
    deleted_at = models.DateTimeField(null=True, blank=True)


class EmailCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, default="draft")
    category = models.CharField(max_length=24, default="outreach")
    target = models.CharField(max_length=2000, blank=True, default="")
    product = models.CharField(max_length=2000, blank=True, default="")
    booking_link = models.URLField(max_length=500, blank=True, default="")
    signature = models.TextField(blank=True, default="")
    # Existing sequences retain calendar arithmetic; new UI drafts opt in.
    delay_basis = models.CharField(max_length=24, default="calendar_days")
    delay_timezone = models.CharField(max_length=64, default="America/New_York")
    steps = models.JSONField(default=list)
    from_address = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    autopilot_run = models.ForeignKey("AutopilotRun", null=True, blank=True, on_delete=models.PROTECT, related_name="campaigns")
    # Only a final send confirmation can authorize these specific follow-ups.
    followup_approval = models.JSONField(default=dict)


class CampaignRecipient(models.Model):
    campaign = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name="recipients")
    deal = models.ForeignKey("outsend_leads.Deal", on_delete=models.CASCADE)
    personal_steps = models.JSONField(default=list)
    authorization_hash = models.CharField(max_length=64, blank=True, default="")
    next_step = models.PositiveSmallIntegerField(default=0)
    next_send_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default="pending")
    message_id = models.CharField(max_length=320, blank=True, default="")
    # Never automatically retry an ambiguous provider result after a process dies.
    claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["campaign", "deal"], name="campaign_deal_unique")]


class WorkspaceContext(models.Model):
    stream_token = models.UUIDField(null=True, blank=True)
    stream_expires_at = models.DateTimeField(null=True, blank=True)
    actor_id = models.PositiveIntegerField(primary_key=True)
    references = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class ChatThread(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.PositiveIntegerField(db_index=True)
    title = models.CharField(max_length=100, default="New conversation")
    context = models.JSONField(default=dict)
    archived = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16)
    content = models.TextField(default="")
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ChatRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="runs")
    actor_id = models.PositiveIntegerField(db_index=True)
    request_id = models.UUIDField(unique=True)
    status = models.CharField(max_length=24, default="queued")
    steps = models.PositiveSmallIntegerField(default=0)
    model_requests = models.PositiveSmallIntegerField(default=0)
    deadline_at = models.DateTimeField(null=True, blank=True)
    credits_reserved = models.PositiveSmallIntegerField(default=0)
    emails_reserved = models.PositiveSmallIntegerField(default=0)
    pending = models.JSONField(default=dict)
    approval_expires_at = models.DateTimeField(null=True, blank=True)
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor_id"], condition=models.Q(status__in=["queued", "running", "awaiting_approval", "paused"]), name="one_active_chat_per_actor")]


class DiscoverySession(models.Model):
    run = models.OneToOneField(ChatRun, primary_key=True, on_delete=models.CASCADE, related_name="discovery")
    action = models.JSONField(default=dict)
    goal = models.PositiveSmallIntegerField()
    unit = models.CharField(max_length=16, default="leads")
    target = models.TextField(default="")
    source_ids = models.JSONField(default=list)
    pause_requested = models.BooleanField(default=False)
    phase = models.CharField(max_length=24, default="queued")
    provider_calls = models.PositiveSmallIntegerField(default=0)
    synthetic = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class DiscoveryCandidate(models.Model):
    session = models.ForeignKey(DiscoverySession, on_delete=models.CASCADE, related_name="candidates")
    source_id = models.PositiveIntegerField()
    discovered = models.BooleanField(default=False)
    evaluated = models.BooleanField(default=False)
    outcome = models.CharField(max_length=16, default="pending")
    produced = models.BooleanField(default=False)
    data = models.JSONField(default=dict)
    contact_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "source_id"], name="discovery_candidate_unique")]


class DiscoverySearch(models.Model):
    """Paid profile-search reservation, persisted before any network write."""
    session = models.OneToOneField(DiscoverySession, on_delete=models.CASCADE, related_name="profile_search")
    query_hash = models.CharField(max_length=64, db_index=True)
    page = models.PositiveIntegerField(default=0)
    size = models.PositiveSmallIntegerField()
    credits = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    state = models.CharField(max_length=16, default="uncertain")
    profiles = models.JSONField(default=list)


class DiscoveryEvent(models.Model):
    session = models.ForeignKey(DiscoverySession, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=24)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class DiscoveryLookup(models.Model):
    session = models.ForeignKey(DiscoverySession, on_delete=models.CASCADE, related_name="lookups")
    source_id = models.PositiveIntegerField(db_index=True)
    request_id = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=16, default="uncertain")
    credits = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    email_status = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "source_id"], name="discovery_lookup_unique")]


class EmailReview(models.Model):
    """Saved human-review boundary; generation and approval never imply sending."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.PositiveIntegerField(db_index=True)
    request_id = models.UUIDField(unique=True)
    kind = models.CharField(max_length=16, default="initial")
    status = models.CharField(max_length=16, default="generating")
    from_address = models.EmailField()
    signature = models.TextField(blank=True, default="")
    context_hash = models.CharField(max_length=64)
    requested_count = models.PositiveSmallIntegerField()
    generation_calls = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor_id"], condition=models.Q(status="generating"), name="one_generating_email_review")]


class ReviewedEmail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(EmailReview, on_delete=models.CASCADE, related_name="drafts")
    deal = models.ForeignKey("outsend_leads.Deal", on_delete=models.PROTECT)
    reply_to = models.ForeignKey("outsend_emails.Message", null=True, blank=True, on_delete=models.PROTECT, related_name="reply_drafts")
    subject = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    approved_hash = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=16, default="pending")
    message = models.OneToOneField("outsend_emails.Message", null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_draft")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["review", "deal"], name="review_deal_unique")]


class AutopilotPolicy(models.Model):
    """Immutable scope of an employee's explicit standing authorization."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.PositiveIntegerField()
    enabled = models.BooleanField(default=True)
    scope = models.JSONField(default=dict)
    setup_hash = models.CharField(max_length=64)
    authorized_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    disabled_at = models.DateTimeField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    issue = models.CharField(max_length=300, default="", blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor_id"], condition=models.Q(enabled=True), name="one_enabled_autopilot")]


class AutopilotRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(AutopilotPolicy, on_delete=models.PROTECT, related_name="runs")
    actor_id = models.PositiveIntegerField()
    workday = models.DateField()
    phase = models.CharField(max_length=24, default="scheduled")
    checkpoint = models.JSONField(default=dict)
    # Reservations count even when a provider response is lost; never release on error.
    model_requests = models.PositiveIntegerField(default=0)
    email_credits = models.PositiveIntegerField(default=0)
    issue = models.CharField(max_length=300, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deadline_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor_id", "workday"], name="one_autopilot_workday")]
