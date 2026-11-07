# Copyright 2026 Mindroot Ltd
# Modifications copyright 2026 Zyene
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0. Unless required by
# applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.
#
# Derived from Warmbly (https://github.com/warmbly/warmbly), commit
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1, files internal/pkg/dsn/dsn.go and
# internal/pkg/dsn/cause.go. Translated from Go to Python and modified by Zyene
# for LeadZen: the same patterns, markers and decision order, with Go-specific
# plumbing removed. See THIRD_PARTY_NOTICES.md.
"""Read delivery-status notifications (bounce messages, RFC 3464).

Conservative on purpose: callers suppress an address only on a confirmed
permanent failure that names the recipient, so a soft or transient bounce is
never treated as hard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Cause names what a refusal was about.
CAUSE_UNKNOWN = ""
CAUSE_RECIPIENT_INVALID = "recipient_invalid"
CAUSE_MAILBOX_FULL = "mailbox_full"
CAUSE_REPUTATION_BLOCK = "reputation_block"
CAUSE_TRANSIENT = "transient"

# A notice can paste a whole transcript.
REASON_LIMIT = 500

_STATUS = re.compile(r"^\s*Status:\s*([245])\.\d{1,3}\.\d{1,3}", re.I | re.M)
_STATUS_CODE = re.compile(r"^\s*Status:\s*([245]\.\d{1,3}\.\d{1,3})", re.I | re.M)
_DIAG_FIELD = re.compile(r"^[ \t]*Diagnostic-Code:[^;\r\n]*;[ \t]*(.*)$", re.I | re.M)
_FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:")
_ACTION = re.compile(r"^\s*Action:\s*(failed|delayed|delivered|relayed|expanded)", re.I | re.M)
_FINAL_RCPT = re.compile(r"^\s*(?:Final|Original)-Recipient:\s*[^;\r\n]*;\s*<?([^\s<>]+@[^\s<>]+?)>?\s*$", re.I | re.M)
_MESSAGE_ID = re.compile(r"^\s*Message-ID:\s*<([^>\s]+)>", re.I | re.M)
_DIAGNOSTIC = re.compile(r"^\s*Diagnostic-Code:\s*[^;\r\n]*;\s*([245])\d\d", re.I | re.M)
_BLANK_LINE = re.compile(r"\r?\n[ \t]*\r?\n")
_RETURNED = re.compile(r"(-{2,}\s*original message|original message headers|message/rfc822)", re.I)
_TRANSIENT = re.compile(r"\b(delay|delayed|will retry|will be retried|temporar(y|ily)|still trying)\b", re.I)

# A machine bounce source in the From line.
SENDER_MARKERS = ("mailer-daemon", "postmaster@", "mail-daemon")

# The subjects mail servers write on a failure notice.
SUBJECT_MARKERS = (
    "undeliverable", "undelivered mail", "delivery status notification",
    "returned mail", "delivery failure", "mail delivery failed", "mail delivery failure",
    "delivery has failed", "failure notice", "message not delivered", "delivery incomplete",
    "non remis", "unzustellbar",
)


@dataclass
class Report:
    is_bounce: bool = False
    # Only a 5.x.x status or an explicit permanent "Action: failed".
    permanent: bool = False
    failed_recipient: str = ""
    original_message_id: str = ""
    status: str = ""
    action: str = ""
    diagnostic: str = ""

    def reason(self, fallback: str = "") -> str:
        """The notice's own account of the failure: status and the remote reply."""
        if self.diagnostic and (not self.status or _same_status(self.diagnostic, self.status)):
            return self.diagnostic
        if self.diagnostic:
            return _bound(f"{self.status} {self.diagnostic}")
        if self.status:
            return self.status
        return _bound(fallback)

    def with_failed_recipients(self, header: str, subject: str, body: str) -> "Report":
        """Read a notice that carries only X-Failed-Recipients (Gmail, Exim).

        Permanent unless the notice says delivery is still being retried.
        """
        header = (header or "").strip()
        if not header or self.permanent or is_transient_notice(subject, body):
            return self
        self.is_bounce = self.permanent = True
        if not self.failed_recipient:
            self.failed_recipient = header.split(",")[0].strip().strip("<>")
        return self


def is_bounce_sender(sender: str) -> bool:
    lowered = (sender or "").lower()
    return any(marker in lowered for marker in SENDER_MARKERS)


def has_bounce_subject(subject: str) -> bool:
    """A prefix, so a person's "Re: <subject>" never matches."""
    lowered = (subject or "").strip().lower()
    return any(lowered.startswith(marker) for marker in SUBJECT_MARKERS)


def detect(sender: str, subject: str, content_type: str) -> bool:
    """Cheap envelope signals only; callers gate the full parse on this."""
    if is_bounce_sender(sender) or "multipart/report" in (content_type or "").lower():
        return True
    lowered = (subject or "").lower()
    return any(marker in lowered for marker in SUBJECT_MARKERS)


def parse(body: str) -> Report:
    """Permanence comes from Status / Diagnostic-Code / Action, never from prose."""
    report = Report()
    if match := _STATUS.search(body):
        report.is_bounce, report.permanent = True, match.group(1) == "5"
    if not report.permanent and (match := _DIAGNOSTIC.search(body)):
        report.is_bounce, report.permanent = True, match.group(1) == "5"
    if match := _ACTION.search(body):
        report.is_bounce = True
        # "failed" is permanent per RFC 3464, but a co-present 4.x.x status
        # (retry-then-fail) means transient: defer to the status code.
        if match.group(1).lower() == "failed" and _has_no_4xx(body):
            report.permanent = True
    if match := _FINAL_RCPT.search(body):
        report.failed_recipient = match.group(1).strip()
    # The last Message-ID in the body belongs to the returned original message.
    if ids := _MESSAGE_ID.findall(body):
        report.original_message_id = ids[-1].strip()
    group = _failed_group(body)
    if match := _FINAL_RCPT.search(group):
        report.failed_recipient = match.group(1).strip()
    if match := _ACTION.search(group):
        report.action = match.group(1).lower()
    if match := _STATUS_CODE.search(group):
        report.status = match.group(1)
    report.diagnostic = _diagnostic_text(group)
    return report


def is_transient_notice(subject: str, body: str) -> bool:
    """A 4.x.x status, or the mail system's own words about a delay."""
    if (match := _STATUS.search(body)) and match.group(1) == "4":
        return True
    return bool(_TRANSIENT.search(subject or "") or _TRANSIENT.search(_notice_text(body)))


def _has_no_4xx(body: str) -> bool:
    match = _STATUS.search(body)
    return match.group(1) != "4" if match else True


def _failed_group(body: str) -> str:
    """The first per-recipient group with a permanent status, else the first with any."""
    first = ""
    for group in _BLANK_LINE.split(body):
        match = _STATUS_CODE.search(group)
        if match and match.group(1).startswith("5"):
            return group
        if not first and (match or _DIAG_FIELD.search(group)):
            first = group
    return first


def _diagnostic_text(body: str) -> str:
    """The first Diagnostic-Code value with its folded continuation lines."""
    match = _DIAG_FIELD.search(body)
    if not match:
        return ""
    parts = [match.group(1)]
    for line in body[match.end():].split("\n")[1:]:
        line = line.rstrip("\r")
        trimmed = line.strip()
        if not trimmed or line[0] not in " \t" or _FIELD_NAME.match(trimmed):
            break
        parts.append(trimmed)
    return _bound(" ".join(parts))


def _bound(text: str) -> str:
    """Collapse whitespace, drop control characters and cap the length."""
    text = " ".join("".join(" " if ch.isspace() or ord(ch) < 32 or ord(ch) == 127 else ch for ch in text or "").split())
    return text[:REASON_LIMIT]


def _notice_text(body: str) -> str:
    """The mail system's own part; the returned original says nothing about delivery."""
    match = _RETURNED.search(body)
    return body[:match.start()] if match else body


# ── Cause ────────────────────────────────────────────────────────────

# The mailbox exists and is over quota. They win over the recipient markers
# because Postfix quota policies answer "Recipient address rejected: Mailbox full".
MAILBOX_FULL_MARKERS = (
    "mailbox full", "mailbox is full", "over quota", "quota exceeded",
    "exceeded storage", "insufficient storage", "out of storage", "quotaexceeded",
)

# The RECIPIENT is the problem, whatever the numeric code.
RECIPIENT_MARKERS = (
    "user unknown", "unknown user", "no such user", "no such recipient", "no such mailbox",
    "user not found", "recipient not found", "recipient unknown", "unknown recipient",
    "invalid recipient", "invalid mailbox", "mailbox not found", "mailbox is disabled",
    "mailbox disabled", "account has been disabled", "account is disabled",
    "unrouteable address", "unroutable address", "no mailbox here", "not a valid mailbox",
    "user doesn't have an account",
)

# Blame the recipient only when nothing blames the sender or a policy.
WEAK_RECIPIENT_MARKERS = (
    "recipient address rejected", "recipient rejected", "mailbox unavailable",
    "does not exist", "doesn't exist",
)

TRANSIENT_MARKERS = ("greylist", "grey-list", "try again", "temporarily", "rate limit", "too many")

# Scoped to the SENDER's address or domain; decide before recipient wording.
SENDER_SCOPED_MARKERS = (
    "sender address", "sender domain", "sender's domain", "domain of sender", "envelope sender",
    "sender rejected", "sender verify failed", "sender not allowed", "mail from",
)

# The SENDER's greeting, IP, authentication, reputation or a session policy.
SESSION_MARKERS = (
    "helo", "ehlo", "fully-qualified", "fully qualified", "relay access denied", "relay denied",
    "relaying denied", "not permitted to relay", "unable to relay", "client host rejected",
    "client host blocked", "authentication required", "auth required", "not authenticated",
    "not authorized", "blacklist", "blocklist", "blocked using", "listed in", "spamhaus", "spam",
    "reputation", "service unavailable", "connection refused", "policy",
)


def address_is_fine(cause: str) -> bool:
    """A refusal that names something other than the recipient's address."""
    return cause in (CAUSE_MAILBOX_FULL, CAUSE_REPUTATION_BLOCK, CAUSE_TRANSIENT)


def _parse_status(token: str):
    parts = token.split(".")
    if len(parts) != 3 or any(not p.isdigit() or len(p) > 3 for p in parts):
        return None
    numbers = tuple(int(p) for p in parts)
    return numbers if numbers[0] in (2, 4, 5) else None


def status_in(text: str):
    """The deciding enhanced status: the first 5.x.x, else the first specific one."""
    permanent = specific = first = None
    for token in re.split(r"[^\d.]+", text or ""):
        status = _parse_status(token.strip("."))
        if not status:
            continue
        first = first or status
        if status[1:] == (0, 0):
            continue
        if status[0] == 5:
            permanent = status
            break
        specific = specific or status
    return permanent or specific or first


def _same_status(text: str, status: str) -> bool:
    got, want = status_in(text), _parse_status(status)
    return bool(got and want and got == want)


def blame(text: str) -> str:
    """What a refusal was about, from its status code and wording."""
    lower = (text or "").lower()
    status = status_in(lower)
    if status and status[0] == 4:
        return CAUSE_TRANSIENT
    if any(m in lower for m in SENDER_SCOPED_MARKERS):
        return CAUSE_REPUTATION_BLOCK
    if (status and status == (5, 2, 2)) or any(m in lower for m in MAILBOX_FULL_MARKERS):
        return CAUSE_MAILBOX_FULL
    if any(m in lower for m in RECIPIENT_MARKERS):
        return CAUSE_RECIPIENT_INVALID
    if any(m in lower for m in TRANSIENT_MARKERS):
        return CAUSE_TRANSIENT
    if any(m in lower for m in SESSION_MARKERS):
        return CAUSE_REPUTATION_BLOCK
    if any(m in lower for m in WEAK_RECIPIENT_MARKERS):
        return CAUSE_RECIPIENT_INVALID
    if not status or status[0] != 5:
        return CAUSE_UNKNOWN
    subject, detail = status[1], status[2]
    if subject == 1:
        if detail in (1, 2, 3, 6, 10):  # bad mailbox, bad domain, bad syntax, moved, null MX
            return CAUSE_RECIPIENT_INVALID
        if detail in (7, 8):  # the SENDER's address
            return CAUSE_REPUTATION_BLOCK
    elif subject == 2:
        if detail == 1:  # disabled
            return CAUSE_RECIPIENT_INVALID
        if detail == 3:  # message too large
            return CAUSE_REPUTATION_BLOCK
    elif subject == 3:  # receiving mail system
        return CAUSE_TRANSIENT
    elif subject == 4:
        # Exchange answers a missing mailbox with 5.4.1 and a missing domain with
        # 5.4.4, so neither vouches for the address.
        if detail not in (1, 4):
            return CAUSE_TRANSIENT
    elif subject in (6, 7):  # content, policy
        return CAUSE_REPUTATION_BLOCK
    return CAUSE_UNKNOWN
