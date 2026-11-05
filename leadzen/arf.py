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
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1, files internal/pkg/arf/arf.go and
# internal/pkg/arf/mime.go. Translated from Go to Python and modified by Zyene
# for LeadZen: MIME walking uses the standard library email parser. See
# THIRD_PARTY_NOTICES.md.
"""Read Abuse Reporting Format messages (RFC 5965): a recipient pressed "spam".

A complaint never arrives synchronously; it comes back as mail. This module
only parses. Suppression hangs off the resolved send, never off an address the
report asserts.
"""
from __future__ import annotations

import email
import re
from dataclasses import dataclass
from email import policy

_FEEDBACK_TYPE = re.compile(r"^\s*Feedback-Type:\s*([a-z-]+)", re.I | re.M)
_MESSAGE_ID = re.compile(r"^\s*Message-ID:\s*<([^>\s]+)>", re.I | re.M)
# Original-Rcpt-To only. Original-Mail-From is the SENDER, and reading it as the
# complainer would suppress the employee's own address.
_ORIGINAL_RCPT = re.compile(r"^\s*Original-Rcpt-To:\s*<?([^\s<>]+@[^\s<>]+?)>?\s*$", re.I | re.M)
_USER_AGENT = re.compile(r"^\s*User-Agent:\s*(.+)$", re.I | re.M)

REPORT_MARKERS = ("message/feedback-report", "report-type=feedback-report")
SENDER_MARKERS = ("abuse@", "feedback@", "fbl@", "scomp@", "staff@hotmail.com", "complaints@", "abusedesk@")

MAX_MIME_BYTES = 1 << 20
MAX_MIME_PARTS = 64
REPORT_PARTS = frozenset({
    "message/feedback-report", "message/rfc822", "message/rfc822-headers",
    "text/rfc822-headers", "message/global", "message/global-headers",
})


@dataclass
class Report:
    # Only an abuse-type report. "not-spam" rescues mail from junk; reading it as
    # a complaint would invert the signal.
    is_complaint: bool = False
    original_message_id: str = ""
    # Advisory only: the caller suppresses the address the resolved send went to.
    complained_recipient: str = ""
    user_agent: str = ""


def detect(sender: str, subject: str, content_type: str) -> bool:
    """Cheap envelope signals only; callers gate the full parse on this."""
    lowered = (content_type or "").lower()
    if any(marker in lowered for marker in REPORT_MARKERS):
        return True
    lowered = (sender or "").lower()
    if any(marker in lowered for marker in SENDER_MARKERS):
        return True
    lowered = (subject or "").lower()
    return "abuse report" in lowered or "complaint about message" in lowered or "email feedback report" in lowered


def parse(body: str) -> Report:
    """The LAST Message-ID is the reported message, after the report's own part."""
    report = Report()
    if match := _FEEDBACK_TYPE.search(body):
        report.is_complaint = match.group(1).strip().lower() == "abuse"
    if match := _ORIGINAL_RCPT.search(body):
        report.complained_recipient = match.group(1).strip()
    if match := _USER_AGENT.search(body):
        report.user_agent = match.group(1).strip()[:120]
    if ids := _MESSAGE_ID.findall(body):
        report.original_message_id = ids[-1].strip()
    return report


def parse_mime(raw: bytes) -> Report:
    """Parse a whole raw message by its report parts only."""
    if not raw or len(raw) > MAX_MIME_BYTES:
        return Report()
    try:
        message = email.message_from_bytes(raw, policy=policy.compat32)
    except Exception:
        return Report()
    parts = []
    for count, part in enumerate(message.walk(), 1):
        if count > MAX_MIME_PARTS:
            return Report()
        if part.get_content_type() not in REPORT_PARTS:
            continue
        payload = part.get_payload()
        if isinstance(payload, list):
            # message/rfc822 parts are parsed into a nested message.
            parts.extend(str(item) for item in payload)
        else:
            decoded = part.get_payload(decode=True)
            parts.append(decoded.decode("utf-8", "replace") if isinstance(decoded, bytes) else str(payload))
    return parse("\n".join(parts))
