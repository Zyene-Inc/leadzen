"""Use the existing sender's history and threading for SMTP and HTTP providers."""
import ipaddress
import socket
import ssl
import imaplib
import smtplib
from contextlib import contextmanager
from contextvars import ContextVar
from email.utils import getaddresses

from leadzen.configuration import SettingsError, approved_host, effective
from leadzen.email_api import post_email

_delivery_guard = ContextVar("leadzen_transport_guard", default=None)


class SendingWindowClosed(PermissionError):
    """A known pre-submission deferral, never an uncertain provider attempt."""


@contextmanager
def delivery_guard_scope(guard):
    token = _delivery_guard.set(guard)
    try:
        yield
    finally:
        _delivery_guard.reset(token)


def delivery_guard():
    """Revalidate the shared service approval immediately before transport bytes."""
    guard = _delivery_guard.get()
    if guard:
        guard()
    from leadzen.mcp.guard import assert_connection_access
    assert_connection_access()
    from leadzen.autopilot import external_guard
    external_guard()


def public_addresses(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise SettingsError("Email endpoints must resolve only to public addresses")
    return addresses


def public_socket(host, port, timeout=10):
    for family, kind, protocol, _, address in public_addresses(host, port):
        sock = socket.socket(family, kind, protocol)
        sock.settimeout(timeout)
        try:
            sock.connect(address)
            return sock
        except OSError:
            sock.close()
    raise OSError("Unable to connect to email provider")


def smtp_class(base=smtplib.SMTP):
    """Share the same verified TLS/destination handling between test and send."""
    class PinnedSMTP(base):
        def sendmail(self, *args, **kwargs):
            delivery_guard()
            return super().sendmail(*args, **kwargs)

        def data(self, message):
            # The server can take time to answer MAIL, RCPT or DATA. Recheck at
            # the body write, after its 354 response, before any message bytes.
            self._leadzen_data_write = True
            try:
                return super().data(message)
            finally:
                self._leadzen_data_write = False

        def send(self, value):
            if getattr(self, "_leadzen_data_write", False):
                try:
                    delivery_guard()
                except PermissionError:
                    # Abort DATA mode without sending QUIT as message content.
                    # A known pre-submission denial must stay a safe deferral.
                    self.close()
                    raise
            return super().send(value)

        def _get_socket(self, host, port, timeout):
            approved_host(host, "MAIL")
            if port not in (465, 587, 2525):
                raise SettingsError("Use SMTP 465, 587 or 2525")
            self._implicit_tls = False
            sock = public_socket(host, port, timeout)
            if port == 465:
                try:
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                except Exception:
                    sock.close()
                    raise
                self._implicit_tls = True
            return sock

        def starttls(self, *, context=None):
            if self._implicit_tls:
                return None
            return super().starttls(context=context or ssl.create_default_context())
    return PinnedSMTP


def imap_class():
    class PinnedIMAP(imaplib.IMAP4_SSL):
        def _create_socket(self, timeout):
            approved_host(self.host, "MAIL")
            if self.port != 993:
                raise SettingsError("Use IMAP TLS port 993")
            sock = public_socket(self.host, self.port, timeout or 30)
            try:
                return ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
            except Exception:
                sock.close()
                raise
    return PinnedIMAP


def deliver_api(mailbox, message, row):
    from cold_outreach.emails.delivery_policy import record_acceptance
    from leadzen.workspaces import assert_worker_access
    from leadzen.config.models import ContactPreferences
    assert_worker_access()
    delivery_guard()
    values = effective()
    if mailbox.from_address != values.mailbox_address or not values.mail_api_key:
        raise SettingsError("Sending identity or credentials changed. Start a new run.")
    recipients = [address for _, address in getaddresses([message.get("To", ""), message.get("Bcc", "")]) if address]
    if not recipients:
        raise SettingsError("A recipient is required")
    # Enforced at the provider sink as well as the campaign creation screen.
    if values.mail_transport == "resend":
        for address in [a for _, a in getaddresses([message.get("To", "")])]:
            if not ContactPreferences.objects.filter(lead__email__iexact=address, opted_in=True).exists():
                raise SettingsError("Resend requires an explicitly opted-in recipient")
    if values.mail_transport == "zeptomail" and not getattr(row, "_leadzen_transactional", False):
        raise SettingsError("ZeptoMail supports transactional messages only")
    text = message.get_body(preferencelist=("plain",)).get_content()
    headers = {key: str(message[key]) for key in ("Message-ID", "In-Reply-To", "References", "List-Unsubscribe") if message[key]}
    payload = {"from": values.mailbox_address, "to": recipients[:1], "subject": str(message["Subject"]), "text": text, "headers": headers}
    if len(recipients) > 1:
        payload["bcc"] = recipients[1:]
    if values.mail_transport == "zeptomail":
        payload = {"from": {"address": values.mailbox_address}, "to": [{"email_address": {"address": a}} for a in recipients], "subject": str(message["Subject"]), "textbody": text, "mime_headers": headers, "client_reference": str(row.pk)}
    elif values.mail_transport == "sendgrid":
        payload = {"from": {"email": values.mailbox_address}, "personalizations": [{"to": [{"email": recipients[0]}], **({"bcc": [{"email": a} for a in recipients[1:]]} if len(recipients) > 1 else {})}], "subject": str(message["Subject"]), "content": [{"type": "text/plain", "value": text}], "headers": headers}
    identifier = post_email(values.mail_api_url, values.mail_api_key, payload, provider=values.mail_transport, operation_id=f"outreach/{row.message_id}")
    record_acceptance(row, 250, identifier.encode())


def configure_transports():
    from cold_outreach.emails import sender, sync, warmth
    if getattr(sender, "_leadzen_transport_configured", False) is True:
        return
    original = sender._deliver
    original_sync = sync._connect
    original_fetch = sync._fetch
    original_measure = warmth.measure_pool

    class PinnedClient(sync.IMAPClient):
        def _create_IMAP4(self):
            return imap_class()(self.host, self.port, timeout=self._timeout.connect)

    sync.IMAPClient = PinnedClient
    original_resume = sync._resume_from
    sync._resume_from = lambda coverage, mailbox, epoch, next_uid: 0 if not coverage.uidvalidity and message_exists(mailbox) else original_resume(coverage, mailbox, epoch, next_uid)

    def fetch_complete(client, uid, spec, key):
        part = original_fetch(client, uid, spec, key)
        if not part:
            # The library falls back to headers when a body fetch fails. That
            # could lose an opt-out permanently while claiming a complete sync.
            raise SettingsError("Reply sync is incomplete. Follow-ups are paused until the inbox can be read.")
        return part

    sync._fetch = fetch_complete

    class PinnedSMTP(smtp_class(sender._SMTP)):
        def login(self, user, password, *, initial_response_ok=True):
            values = effective()
            return super().login(values.smtp_username or user, password, initial_response_ok=initial_response_ok)

    sender._SMTP = PinnedSMTP

    def deliver(mailbox, message, row):
        delivery_guard()
        values = effective()
        if values.mail_transport == "smtp":
            if values.smtp_host == "smtp.resend.com":
                from leadzen.config.models import ContactPreferences
                if not ContactPreferences.objects.filter(lead__email__iexact=str(message["To"]), opted_in=True).exists():
                    raise SettingsError("Resend requires an explicitly opted-in recipient")
            if "zeptomail" in values.smtp_host and not getattr(row, "_leadzen_transactional", False):
                raise SettingsError("ZeptoMail supports transactional messages only")
            return original(mailbox, message, row)
        return deliver_api(mailbox, message, row)

    def connect(mailbox):
        from leadzen.workspaces import assert_worker_access
        assert_worker_access()
        from leadzen.mcp.guard import assert_connection_access
        assert_connection_access()
        from leadzen.autopilot import external_guard
        external_guard()
        values = effective()
        if not values.imap_host or not (values.imap_password or values.mailbox_password):
            raise SettingsError("Connect an IMAP inbox to read replies and run follow-ups")
        approved_host(values.imap_host, "MAIL")
        public_addresses(values.imap_host, int(values.imap_port or 993))
        mailbox.imap_host = values.imap_host
        mailbox.imap_port = int(values.imap_port or 993)
        mailbox.username = values.mailbox_address
        mailbox.password = values.imap_password or values.mailbox_password
        try:
            return original_sync(mailbox)
        except Exception:
            raise SettingsError("The reply inbox could not be read. Sending follow-ups is paused.") from None

    sender._deliver = deliver
    sync._connect = connect
    # API providers have no Sent-folder warm-up measurement. Keep the safe floor.
    # Use the same verified/pinned inbox connection for Sent-folder measurement.
    def read_history(mailbox):
        client = connect(mailbox)
        imap = client._imap
        try:
            folder = warmth._sent_folder(imap)
            return warmth._count_by_day(imap, folder) if folder else __import__("collections").Counter()
        finally:
            client.logout()
    warmth.read_sent_history = read_history
    warmth.measure_pool = lambda: original_measure() if effective().mail_transport == "smtp" else None
    sender._leadzen_transport_configured = True


def sync_replies_strict(mailbox, *, classify=True):
    from cold_outreach.emails import sync
    from cold_outreach.emails.classify import classify_pending
    from cold_outreach.emails.project import project_pending
    from cold_outreach.emails.models import FolderCoverage
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()
    started = __import__("django.utils.timezone", fromlist=["now"]).now()
    sync.mirror(mailbox)
    coverage = FolderCoverage.objects.filter(mailbox=mailbox, folder="INBOX").first()
    if coverage is None or not coverage.synced_at or coverage.synced_at < started:
        raise SettingsError("Reply sync is incomplete. Follow-ups are paused until the inbox can be read.")
    if classify:
        classify_pending()
        project_pending()
    from leadzen.outreach import honor_saved_optouts
    honor_saved_optouts(mailbox)


def message_exists(mailbox):
    from cold_outreach.emails.models import Message, Direction
    return Message.objects.filter(mailbox=mailbox, direction=Direction.OUTBOUND).exists()
