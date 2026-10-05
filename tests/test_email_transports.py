import io
import socket
import ssl
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from leadzen.email_api import DeliveryError, post_email
from leadzen.configuration import SettingsError
from leadzen.transports import public_addresses


class FakeSocket:
    def __init__(self, response):
        self.response = response
        self.written = b""
    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.response)
    def sendall(self, value):
        self.written += value
    def close(self):
        pass


@contextmanager
def installed_transports(monkeypatch):
    from cold_outreach.emails import sender, sync, warmth
    from leadzen.transports import configure_transports
    with monkeypatch.context() as scoped:
        for module, names in [(sender, ["_SMTP", "_deliver", "_leadzen_transport_configured"]), (sync, ["IMAPClient", "_fetch", "_connect", "_resume_from"]), (warmth, ["read_sent_history", "measure_pool"])]:
            for name in names:
                scoped.setattr(module, name, getattr(module, name, None), raising=False)
        scoped.setattr(sender, "_leadzen_transport_configured", False)
        configure_transports()
        yield sender


def test_smtp_465_encrypts_before_greeting_and_keeps_acceptance(monkeypatch):
    from email.message import EmailMessage
    # A complete synthetic SMTP exchange; no network or real credential is used.
    raw = FakeSocket(b"")
    secured = FakeSocket(b"220 ready\r\n250-server\r\n250 AUTH PLAIN\r\n235 logged in\r\n250 sender\r\n250 recipient\r\n354 data\r\n250 synthetic-queue-id\r\n221 bye\r\n")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = "sender@example.com", "person@example.com", "Synthetic"
    message.set_content("Local transport test")
    with installed_transports(monkeypatch) as sender, patch("leadzen.transports.public_socket", return_value=raw) as connect, patch.object(ssl.SSLContext, "wrap_socket", return_value=secured) as wrap, patch("leadzen.transports.effective", return_value=SimpleNamespace(smtp_username="relay-user")):
        with sender._SMTP("smtp.zoho.com", 465, timeout=10) as smtp:
            smtp.starttls()  # Legacy caller: must not renegotiate implicit TLS.
            smtp.login("sender@example.com", "synthetic-password")
            smtp.send_message(message)
            assert smtp.accepted_response == (250, b"synthetic-queue-id")
        connect.assert_called_once_with("smtp.zoho.com", 465, 10)
        wrap.assert_called_once_with(raw, server_hostname="smtp.zoho.com")
    assert raw.written == b"" and b"STARTTLS" not in secured.written
    assert b"AUTH PLAIN" in secured.written and b"data\r\n" in secured.written


@pytest.mark.parametrize("port", [587, 2525])
def test_smtp_starttls_ports_still_use_verified_context(monkeypatch, port):
    sock = FakeSocket(b"220 ready\r\n")
    with installed_transports(monkeypatch) as sender, patch("leadzen.transports.public_socket", return_value=sock), patch("smtplib.SMTP.starttls", return_value=(220, b"ready")) as start, patch.object(ssl.SSLContext, "wrap_socket") as wrap:
        smtp = sender._SMTP("smtp.zoho.com", port, timeout=10)
        smtp.starttls()
        context = start.call_args.kwargs["context"]
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        wrap.assert_not_called()
        smtp.close()


def test_smtp_465_certificate_failure_closes_socket_before_auth(monkeypatch):
    from unittest.mock import Mock
    sock = Mock()
    with installed_transports(monkeypatch) as sender, patch("leadzen.transports.public_socket", return_value=sock), patch.object(ssl.SSLContext, "wrap_socket", side_effect=ssl.SSLCertVerificationError("synthetic certificate failure")):
        with pytest.raises(ssl.SSLCertVerificationError):
            sender._SMTP("smtp.zoho.com", 465, timeout=10)
        sock.close.assert_called_once()
        sock.sendall.assert_not_called()


@pytest.mark.parametrize("provider,status,body,identifier", [("resend", 200, b'{"id":"synthetic-mail"}', "synthetic-mail"), ("zeptomail", 200, b'{"request_id":"synthetic-zoho"}', "synthetic-zoho"), ("sendgrid", 202, b"", "accepted")])
def test_actual_http_adapter_serializes_and_accepts_provider_response(provider, status, body, identifier):
    response = f"HTTP/1.1 {status} OK\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
    sock = FakeSocket(response)
    with patch("leadzen.transports.public_socket", return_value=sock), patch("ssl.create_default_context") as context:
        context.return_value.wrap_socket.return_value = sock
        assert post_email("https://api.resend.com/emails", "synthetic-key", {"from": "sender@example.com", "to": ["test@example.com"]}, provider=provider, operation_id="synthetic-operation") == identifier
    assert b"POST /emails" in sock.written
    assert (b"Zoho-enczapikey synthetic-key" if provider == "zeptomail" else b"Bearer synthetic-key") in sock.written
    if provider == "resend":
        assert b"Idempotency-Key: synthetic-operation" in sock.written


@pytest.mark.parametrize("body,status", [(b'{"secret":"do-not-expose"}', 403), (b"invalid", 200), (b'{}', 200), (b'[]', 200), (b'null', 200), (b'', 302)])
def test_provider_failure_does_not_return_raw_error_or_follow_redirects(body, status):
    sock = FakeSocket(f"HTTP/1.1 {status} ERROR\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
    with patch("leadzen.transports.public_socket", return_value=sock), patch("ssl.create_default_context") as context:
        context.return_value.wrap_socket.return_value = sock
        with pytest.raises(DeliveryError) as result:
            post_email("https://api.resend.com/emails", "synthetic-key", {})
    assert "do-not-expose" not in str(result.value) and "synthetic-key" not in str(result.value)


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.0.0.2", "::1", "fc00::1"])
def test_private_dns_is_rejected_before_socket_or_provider_call(address):
    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]), patch("socket.socket") as create:
        with pytest.raises(SettingsError):
            public_addresses("api.example.com", 443)
        create.assert_not_called()


def test_employee_worker_cannot_inherit_platform_invitation_key(monkeypatch):
    from leadzen.workspaces import worker_environment
    monkeypatch.setenv("LEADZEN_RESEND_API_KEY", "synthetic-platform-key")
    monkeypatch.setenv("LEADZEN_DASHBOARD_TOKEN", "synthetic-service-key")
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-ai-key")
    env = worker_environment()
    assert not {"LEADZEN_RESEND_API_KEY", "LEADZEN_DASHBOARD_TOKEN", "GROQ_API_KEY"} & env.keys()


def test_missing_reply_body_fails_closed_before_classification(monkeypatch):
    from cold_outreach.emails import sync, sender
    from leadzen.transports import configure_transports
    # Restore every adapter after the test; configure_transports patches modules
    # intentionally inside the short-lived worker, not the web process.
    with monkeypatch.context() as scoped:
        from cold_outreach.emails import warmth
        for module, names in [(sender, ["_SMTP", "_deliver", "_leadzen_transport_configured"]), (sync, ["IMAPClient", "_fetch", "_connect", "_resume_from"]), (warmth, ["read_sent_history", "measure_pool"])]:
            for name in names:
                scoped.setattr(module, name, getattr(module, name, None), raising=False)
        scoped.setattr(sender, "_leadzen_transport_configured", False)
        configure_transports()
        class Client:
            def fetch(self, *args):
                return {}  # Provider refused a body or header.
        with pytest.raises(SettingsError, match="Reply sync is incomplete"):
            sync._fetch(Client(), 12, "BODY.PEEK[]", "BODY[]")
