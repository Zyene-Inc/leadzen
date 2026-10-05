"""Small provider adapters. No redirects, raw provider errors, or credential logs."""
import http.client
import json
import time
from urllib.parse import urlsplit

from leadzen.configuration import _valid_url


class DeliveryError(ValueError):
    pass


def post_email(url, key, payload, *, provider="resend", operation_id=None):
    # Recheck the allowlist at the external sink, even if a stored legacy value
    # or a future caller bypasses the Settings form.
    url = _valid_url(url, "Email API URL", "EMAIL")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise DeliveryError("An approved HTTPS email API is required")
    headers = {"Content-Type": "application/json", "Authorization":
               f"Zoho-enczapikey {key}" if provider == "zeptomail" else f"Bearer {key}"}
    if operation_id and provider in {"resend", "compatible"}:
        headers["Idempotency-Key"] = str(operation_id)
    from leadzen.transports import public_socket
    import ssl

    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            sock = public_socket(self.host, self.port, self.timeout)
            try:
                self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
                # Off, a reply or competing outreach may arrive while connecting.
                from leadzen.transports import delivery_guard
                delivery_guard()
            except Exception:
                (self.sock if self.sock is not None else sock).close()
                raise

    content = json.dumps(payload).encode()
    if len(content) > 262144:
        raise DeliveryError("Email request exceeded the limit")
    connection = PinnedHTTPS(parsed.hostname, timeout=10)
    deadline = time.monotonic() + 10
    try:
        connection.request("POST", parsed.path or "/", content, headers)
        response = connection.getresponse()
        from leadzen.provider_io import read_response
        raw = read_response(connection, response, limit=65536, deadline=deadline, description="Email provider")
        if not 200 <= response.status < 300:
            raise DeliveryError("Email provider did not confirm acceptance. Check the sender domain and credentials.")
        if provider == "sendgrid" and response.status == 202:
            return str(response.getheader("X-Message-Id", "accepted"))[:200]
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise DeliveryError("Email provider returned an unrecognized response")
        identifier = result.get("request_id" if provider == "zeptomail" else "id")
        if not isinstance(identifier, str) or not identifier:
            raise DeliveryError("Email provider returned an unrecognized response")
        return identifier[:200]
    except PermissionError:
        raise
    except (OSError, http.client.HTTPException, ValueError) as exc:
        if isinstance(exc, DeliveryError):
            raise
        raise DeliveryError("Email delivery could not be confirmed. Check the provider before retrying.") from None
    finally:
        connection.close()
