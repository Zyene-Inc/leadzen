"""Adapter for encrypted dashboard mailboxes and one active sending identity.

The pinned sender expects plaintext in memory. Its password field is encrypted on
database writes and decrypted on database reads only inside authorized workers.
Switching a mailbox preserves the old row/history but excludes it from new runs.
"""
from leadzen.configuration import SettingsError, _encode, _decode, effective, validate_public


def configure_mailbox_clock():
    """Keep the shared mailbox ledger on the employee's selected calendar day."""
    from cold_outreach.emails.models import mailbox
    if getattr(mailbox._local_midnight, "_leadzen_schedule", False):
        return
    def local_midnight():
        from datetime import timezone as utc
        from django.utils import timezone
        from leadzen.timezone import NEW_YORK as zone
        midnight = timezone.now().astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0, fold=0)
        # Normalize a skipped midnight to its real instant after the clock jump.
        return midnight.astimezone(utc.utc).astimezone(zone)

    local_midnight._leadzen_schedule = True
    mailbox._local_midnight = local_midnight


def active_mailboxes():
    from cold_outreach.emails.models import Mailbox
    from leadzen.config.models import RuntimeSettings
    rows = Mailbox.objects.all()
    runtime = RuntimeSettings.objects.filter(pk=1).first()
    return rows.filter(from_address=runtime.mailbox_address) if runtime else rows


def sync_dashboard_mailbox():
    from cold_outreach.emails.models import Mailbox
    values = effective()
    if not values.mailbox_address or not (values.mailbox_password if values.mail_transport == "smtp" else values.mail_api_key):
        return
    password = values.mailbox_password or values.imap_password
    if not getattr(Mailbox._meta.get_field("password"), "_leadzen_encrypted", False):
        password = _encode({"mailbox_password": password})
    # Authorized workers encrypt raw values in the field adapter. Encoding here
    # as well would store a nested token and break a later single decryption.
    defaults = {"from_address": values.mailbox_address, "signature": values.signature,
                "password": password}
    for field, value in (("host", values.smtp_host), ("port", values.smtp_port), ("imap_host", values.imap_host), ("imap_port", values.imap_port)):
        if value:
            defaults[field] = int(value) if field.endswith("port") else value
    Mailbox.objects.update_or_create(username=values.mailbox_address, defaults=defaults)


def prepare_worker_mailbox(require_ai=True):
    """Prepare connections without changing which canonical contacts are visible.

    ``require_ai`` validates classification credentials for reply checks. It does
    not select a sender or authorize follow-ups; approved campaign/reviewed
    services own recipient eligibility, and workers reject legacy sender jobs.
    """
    from cold_outreach.emails.models import Mailbox
    from leadzen.config.models import RuntimeSettings
    runtime = RuntimeSettings.objects.filter(pk=1).first()
    if runtime is None:
        return  # Existing deliberate local CLI mode uses the sender unchanged.
    values = effective()
    if (require_ai and (not values.ai_enabled or not values.llm_api_key)) or not (values.mailbox_password if values.mail_transport == "smtp" else values.mail_api_key):
        raise SettingsError("Required connection credentials are missing. Complete your connection settings.")
    validate_public({"provider": values.provider, "model": values.model, "base_url": values.base_url,
                     "mailbox_address": values.mailbox_address, "smtp_host": values.smtp_host,
                     "imap_host": values.imap_host, "smtp_port": values.smtp_port, "imap_port": values.imap_port,
                     "mail_transport": values.mail_transport, "mail_api_url": values.mail_api_url,
                     "smtp_username": values.smtp_username, "ai_enabled": values.ai_enabled})
    field = Mailbox._meta.get_field("password")
    if not getattr(field, "_leadzen_encrypted", False):
        field.get_prep_value = lambda raw: _encode({"mailbox_password": raw})
        field.from_db_value = lambda raw, expression, connection: _decode(raw).get("mailbox_password", "")
        field._leadzen_encrypted = True
    manager_type = type(Mailbox.objects)
    if not getattr(manager_type, "_leadzen_scoped", False):
        original = manager_type.get_queryset
        def workspace_mailboxes(self):
            rows = original(self)
            # The adapter is process-wide; preserve deliberately configured CLI
            # mailboxes when the current routed database has no dashboard config.
            return rows.filter(from_address=effective().mailbox_address) if self.model is Mailbox and RuntimeSettings.objects.filter(pk=1).exists() else rows
        manager_type.get_queryset = workspace_mailboxes
        manager_type._leadzen_scoped = True
    from leadzen.transports import configure_transports
    configure_transports()
