# Portions copyright 2026 Mindroot Ltd, licensed under the Apache License,
# Version 2.0 (http://www.apache.org/licenses/LICENSE-2.0). Modifications
# copyright 2026 Zyene.
#
# The bounce and complaint decisions follow Warmbly
# (https://github.com/warmbly/warmbly), commit
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1: internal/app/worker/wmail/bounce.go
# (which reports become events), internal/app/advanced/inbound_bounce.go (resolve
# the report to our own send; never guess a recipient) and the bounce branch of
# internal/app/advanced/service.go (suppress unless the cause clears the
# address). Translated from Go to Python and adapted by Zyene to LeadZen's saved
# mail log and Do not contact list. See THIRD_PARTY_NOTICES.md.
"""Turn stored bounce and spam-complaint reports into Do not contact entries.

Runs after each mailbox check, over messages the sender library already saved.
A hard bounce (permanent failure that names the recipient) and a spam complaint
block the address with the reason and date; a soft bounce (temporary failure,
full mailbox, or a refusal aimed at the sending mailbox) is recorded only.
Each report is read once.
"""
from __future__ import annotations

import email
import logging
from email import policy

from cold_outreach.emails.models import Direction, Message
from leadzen import arf, dsn

logger = logging.getLogger(__name__)

HARD_BOUNCE, SOFT_BOUNCE, COMPLAINT, NONE = "hard_bounce", "soft_bounce", "complaint", "none"
# Kinds a report can carry after the sender library's classifier has read it.
SCANNED_KINDS = ("", "bounce", "auto_reply", "unrelated")


def keep_reports(original):
    """Wrap the sync rule about whose mail is stored so complaint reports are kept.

    A feedback-loop report arrives from the provider's abuse address and often
    carries no threading headers, so the library would skip it as unrelated mail.
    """
    if getattr(original, "_leadzen_keeps_reports", False):
        return original

    def is_our_conversation(mailbox, msg):
        if original(mailbox, msg):
            return True
        from cold_outreach.emails import parsing
        return arf.detect(parsing.sender_address(msg), msg.get("Subject") or "", msg.get("Content-Type") or "")

    is_our_conversation._leadzen_keeps_reports = True
    return is_our_conversation


def _report_text(msg) -> str:
    """Every text and report part, decoded, as one body for the line parsers."""
    parts = []
    for count, part in enumerate(msg.walk(), 1):
        if count > arf.MAX_MIME_PARTS:
            break
        if part.get_content_maintype() == "multipart":
            continue
        payload = part.get_payload()
        if isinstance(payload, list):
            # message/delivery-status holds its field groups, message/rfc822 the
            # returned original; both are parsed into nested header blocks.
            parts.append("\n".join(item.as_string() if hasattr(item, "as_string") else str(item) for item in payload))
            continue
        if not part.get_content_type().startswith(("text/", "message/")):
            continue
        decoded = part.get_payload(decode=True)
        parts.append(decoded.decode(part.get_content_charset() or "utf-8", "replace") if isinstance(decoded, bytes) else str(payload))
    return "\n".join(parts)


def _our_send(mailbox, report_message, message_id):
    """The outbound message a report is about, sent from this mailbox, or None."""
    outbound = Message.objects.filter(mailbox=mailbox, direction=Direction.OUTBOUND)
    message_id = (message_id or "").strip().strip("<>")
    if message_id:
        found = outbound.filter(message_id=message_id).order_by("-sent_at").first()
        if found:
            return found
    from cold_outreach.emails.project import _bounced_send
    return _bounced_send(report_message)


def _reason(text, limit=200):
    clean = " ".join("".join(ch if ch.isprintable() else " " for ch in text or "").split())
    return clean[:limit]


def read_report(mailbox, message):
    """Decide what one stored message means. Returns ``(kind, address, cause, reason)``."""
    raw = bytes(message.raw or b"")
    if not raw:
        return NONE, "", "", ""
    msg = email.message_from_bytes(raw[:arf.MAX_MIME_BYTES], policy=policy.compat32)
    sender, subject, content_type = message.from_address, message.subject or msg.get("Subject") or "", msg.get("Content-Type") or ""
    body = _report_text(msg)

    if arf.detect(sender, subject, content_type):
        report = arf.parse(body)
        if not report.is_complaint or not report.original_message_id:
            report = arf.parse_mime(raw)
        if report.is_complaint and report.original_message_id:
            send = _our_send(mailbox, message, report.original_message_id)
            if send is None:
                return NONE, "", "", ""
            via = f" reported by {report.user_agent}" if report.user_agent else ""
            return COMPLAINT, send.to_address, "complaint", _reason(f"Spam complaint{via}")
        if report.is_complaint:
            return NONE, "", "", ""

    if not dsn.detect(sender, subject, content_type):
        return NONE, "", "", ""
    report = dsn.parse(body).with_failed_recipients(msg.get("X-Failed-Recipients") or "", subject, body)
    if not report.is_bounce:
        return NONE, "", "", ""
    send = _our_send(mailbox, message, report.original_message_id or message.in_reply_to)
    if send is None:
        return NONE, "", "", ""  # Nothing to attribute it to: give up rather than guess.
    address = send.to_address
    if report.failed_recipient and report.failed_recipient.lower() != address.lower():
        return NONE, "", "", ""  # The report names someone this send was not for.
    reason = report.reason(subject)
    if not report.permanent:
        return SOFT_BOUNCE, address, dsn.CAUSE_TRANSIENT, _reason(reason)
    cause = dsn.blame(reason)
    if dsn.address_is_fine(cause):
        return SOFT_BOUNCE, address, cause, _reason(reason)
    return HARD_BOUNCE, address, cause or dsn.CAUSE_UNKNOWN, _reason(reason)


def apply_mail_signals(mailbox) -> int:
    """Read every unread report in this mailbox once. Returns addresses blocked."""
    from leadzen.config.models import MailSignal
    from leadzen.suppression import block_address
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()
    seen = MailSignal.objects.values("message_pk")
    pending = (Message.objects.filter(mailbox=mailbox, direction=Direction.INBOUND, kind__in=SCANNED_KINDS)
               .exclude(pk__in=seen).order_by("pk"))
    blocked = 0
    for message in pending.iterator(chunk_size=100):
        try:
            kind, address, cause, reason = read_report(mailbox, message)
        except Exception:
            logger.exception("mail signals: could not read message %s", message.pk)
            continue
        suppressed = False
        if kind in (HARD_BOUNCE, COMPLAINT) and address:
            label = "Spam complaint" if kind == COMPLAINT else "Hard bounce"
            text = reason if kind == COMPLAINT else f"{label}: {reason}" if reason else label
            try:
                block_address(address, _reason(text))
                suppressed = True
                blocked += 1
            except ValueError:
                logger.warning("mail signals: %s could not be blocked", address)
        MailSignal.objects.get_or_create(message_pk=message.pk, defaults={
            "kind": kind, "address": address[:320], "cause": cause[:24], "reason": reason, "suppressed": suppressed})
        if kind != NONE:
            logger.info("mail signals: %s for %s (%s)", kind, address, cause or "no cause")
    return blocked
