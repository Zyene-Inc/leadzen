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
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1: internal/pkg/dnsauth/dnsauth.go
# (record rules, DKIM selector hints, DMARC inheritance, special-use domains)
# and internal/app/advisor/detect_deliverability.go (the fix steps and record
# values). Translated from Go to Python and modified by Zyene for LeadZen: uses
# dnspython, walks parent domains for DMARC instead of a public-suffix list,
# adds an MX result, and writes plain-language results for Settings. See
# THIRD_PARTY_NOTICES.md.
"""Check a sending domain's SPF, DKIM, DMARC and MX records.

Read-only DNS lookups, run only when an employee asks. A DKIM key lives at a
selector its owner chose and DNS cannot list selectors, so a DKIM probe that
finds nothing is "not verified", never "missing".
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import dns.exception
import dns.resolver

LOOKUP_TIMEOUT = 5.0
MAX_SELECTOR_PROBES = 32
SELECTOR_BATCH = 8

# Generic selectors probed when the domain's own records name none.
DEFAULT_SELECTORS = (
    "google", "selector1", "selector2", "default", "dkim", "mail", "email",
    "k1", "k2", "s1", "s2", "key1", "key2", "smtp", "x", "zoho", "fm1",
    "protonmail", "pm", "sig1", "mandrill",
)

# A fragment of a provider's host, as it appears in MX or SPF, to the selectors
# that provider publishes. Amazon SES, SparkPost and HubSpot use per-account tokens.
PROVIDER_SELECTORS = (
    ("google.com", ("google",)), ("googlemail.com", ("google",)),
    ("outlook.com", ("selector1", "selector2")), ("microsoft.com", ("selector1", "selector2")),
    ("zoho", ("zoho", "zmail")),
    ("messagingengine.com", ("fm1", "fm2", "fm3", "mesmtp")), ("fastmail.com", ("fm1", "fm2", "fm3")),
    ("protonmail.ch", ("protonmail", "protonmail2", "protonmail3")), ("proton.me", ("protonmail", "protonmail2", "protonmail3")),
    ("yandex", ("mail",)), ("mailgun.org", ("mailo", "smtp", "k1", "mg", "pic")),
    ("sendgrid.net", ("s1", "s2", "smtpapi")), ("mcsv.net", ("k1", "k2", "k3")),
    ("mandrillapp.com", ("mandrill",)), ("mailjet.com", ("mailjet",)),
    ("mtasv.net", ("pm",)), ("postmarkapp.com", ("pm",)), ("icloud.com", ("sig1",)),
    ("migadu.com", ("key1", "key2", "key3")), ("mxroute", ("x",)), ("mxrouting.net", ("x",)),
    ("titan.email", ("titan1", "titan2")), ("secureserver.net", ("default", "dkim")),
    ("zendesk.com", ("zendesk1", "zendesk2")), ("freshemail.io", ("fd1", "fd2")),
    ("klaviyomail.com", ("kl", "kl2")), ("mlsend.com", ("ml",)), ("createsend.com", ("cm",)),
    ("elasticemail.com", ("api",)), ("resend.com", ("resend",)), ("brevo.com", ("mail",)),
    ("sendinblue.com", ("mail",)), ("mailbox.org", ("mbo0001",)), ("ionos", ("ionos1",)),
    ("hostinger", ("hostingermail-a", "hostingermail-b", "hostingermail1", "hostingermail2")),
)

# Special-use names that never resolve (RFC 2606, 6761, 6762, 8375).
RESERVED_SUFFIXES = ("test", "example", "invalid", "localhost", "local", "home.arpa")

# SPF include per provider. An unrecognised provider gets no guess: a wrong
# include looks finished and is worse than an obvious blank.
SPF_INCLUDES = (
    (("google.com", "googlemail.com"), "include:_spf.google.com"),
    (("outlook.com", "microsoft.com"), "include:spf.protection.outlook.com"),
)


class Lookups:
    """The resolver the check runs against; injected in tests."""

    def __init__(self):
        self.resolver = dns.resolver.Resolver()
        self.resolver.lifetime = LOOKUP_TIMEOUT

    def txt(self, name):
        """``(records, transient)``. NXDOMAIN/no answer is authoritative absence."""
        try:
            answer = self.resolver.resolve(name, "TXT", raise_on_no_answer=False)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return [], False
        except (dns.exception.DNSException, OSError):
            return [], True
        return [b"".join(r.strings).decode("utf-8", "replace") for r in answer], False

    def mx(self, name):
        try:
            answer = self.resolver.resolve(name, "MX", raise_on_no_answer=False)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return [], False
        except (dns.exception.DNSException, OSError):
            return [], True
        return [str(r.exchange).rstrip(".").lower() for r in sorted(answer, key=lambda r: r.preference)], False


def is_spf(txt):
    return txt.strip().lower().startswith("v=spf1")


def is_dmarc(txt):
    return "v=dmarc1" in txt.lower()


def dkim_key(txt):
    """A DKIM key that can sign: a non-empty p= (an empty p= is a revoked key)."""
    version = key_type = public = None
    for part in txt.split(";"):
        name, sep, value = part.strip().partition("=")
        if not sep:
            continue
        name = name.strip().lower()
        if name == "v":
            version = value.strip().lower()
        elif name == "k":
            key_type = value.strip()
        elif name == "p":
            public = value.strip()
    if version and version != "dkim1":
        return False
    if not version and not key_type:
        return False
    return bool(public)


def dmarc_tag(record, tag):
    for part in record.split(";"):
        part = part.strip().lower()
        if part.startswith(tag + "="):
            return part[len(tag) + 1:].strip()
    return ""


def reserved(domain):
    return any(domain == s or domain.endswith("." + s) for s in RESERVED_SUFFIXES)


def selector_hints(spf_record, mx_hosts):
    out = []
    for host in spf_record.lower().split() + list(mx_hosts):
        for fragment, selectors in PROVIDER_SELECTORS:
            if fragment in host.lower():
                out.extend(selectors)
    return out


def dedupe(items):
    seen, out = set(), []
    for item in items:
        item = item.strip().lower()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _lookup_dmarc(domain, lookups):
    """``(record, found_at, transient)``.

    A subdomain with no record of its own is covered by its parent's policy,
    where sp= applies when present. Warmbly reads the organizational domain from
    the public-suffix list; this walks parent names, as DMARCbis does.
    """
    labels = domain.split(".")
    for index in range(len(labels) - 1):
        name = ".".join(labels[index:])
        txts, transient = lookups.txt("_dmarc." + name)
        if transient:
            return "", "", True
        record = next((t for t in txts if is_dmarc(t)), "")
        if record:
            return record, name, False
    return "", "", False


def _probe_selectors(domain, candidates, lookups):
    """Probe in bounded batches; stop at the first batch that finds a key."""
    found = []
    with ThreadPoolExecutor(max_workers=SELECTOR_BATCH) as pool:
        for start in range(0, len(candidates), SELECTOR_BATCH):
            batch = candidates[start:start + SELECTOR_BATCH]
            results = pool.map(lambda s: any(dkim_key(t) for t in lookups.txt(f"{s}._domainkey.{domain}")[0]), batch)
            found = [s for s, hit in zip(batch, results) if hit]
            if found:
                break
    return found


def spf_include(hosts):
    for host in hosts:
        # Zoho publishes one include per data centre: mx.zoho.eu → include:zoho.eu.
        for word in host.split():
            if ".zoho." in "." + word:
                return "include:zoho." + word.split("zoho.", 1)[1].split()[0].strip(".")
    for fragments, include in SPF_INCLUDES:
        if any(fragment in host for host in hosts for fragment in fragments):
            return include
    return ""


def check(domain, lookups=None):
    """Check one sending domain and return results with plain-language fixes."""
    lookups = lookups or Lookups()
    domain = (domain or "").strip().rstrip(".").lower()
    result = {"domain": domain, "state": "unknown", "summary": "", "checks": []}
    if not domain:
        result["summary"] = "There is no sending domain to check yet."
        return result
    if reserved(domain):
        result["summary"] = "This is a test domain that can never receive mail, so it cannot be checked."
        return result
    try:
        name = domain.encode("idna").decode("ascii")
    except UnicodeError:
        name = domain

    spf_txts, spf_error = lookups.txt(name)
    spf_records = [t.strip() for t in spf_txts if is_spf(t)]
    spf = spf_records[0] if spf_records else ""
    dmarc, dmarc_at, dmarc_error = _lookup_dmarc(name, lookups)
    mx_hosts, mx_error = lookups.mx(name)
    selectors = dedupe(selector_hints(spf, mx_hosts) + list(DEFAULT_SELECTORS))[:MAX_SELECTOR_PROBES]
    dkim = _probe_selectors(name, selectors, lookups)
    include = spf_include([spf.lower()] + mx_hosts)
    checks = result["checks"]

    # SPF does not inherit from a parent, so it must sit on the exact domain.
    if spf_error:
        checks.append(_row("spf", "SPF", "unknown", "Could not be checked because DNS did not answer. Try again in a few minutes."))
    elif len(spf_records) > 1:
        checks.append(_row("spf", "SPF", "fail", "This domain has more than one SPF record. Two SPF records count as a failure, not a backup.",
                           ["Merge them into one TXT record at the root of the domain, then delete the extra one."], record=spf))
    elif spf:
        checks.append(_row("spf", "SPF", "pass", "Found. Receiving servers can see which services may send as this domain.", record=spf))
    else:
        value = f"v=spf1 {include or 'include:YOUR-PROVIDER-SPF-HOST'} ~all"
        checks.append(_row("spf", "SPF", "fail", "Missing. Without it, receiving servers cannot tell your mail is really from you.", [
            "Open the DNS settings for this domain where you bought it or host it.",
            "Add a TXT record at the root of the domain (written as @ or left blank, depending on your DNS provider).",
            "If an SPF record already exists, edit that one instead of adding a second." + ("" if include else " Replace the include with the SPF host your email provider publishes."),
        ], fix={"type": "TXT", "host": domain, "value": value}))

    if dkim:
        checks.append(_row("dkim", "DKIM", "pass", f"Found a signing key (selector “{dkim[0]}”). Your emails can carry a signature receivers can check."))
    else:
        host, where = _dkim_host(mx_hosts + [spf.lower()], domain)
        checks.append(_row("dkim", "DKIM", "unknown", "Not verified. A DKIM key sits at a name only your email provider knows, so we could not find it. It may still be set up.", [
            f"In your email provider's admin console, generate a DKIM key and publish the record it gives you. {where}",
            "Then turn signing on. Publishing the key and turning signing on are two separate switches, and missing the second is the usual cause.",
        ], fix={"type": "TXT", "host": host, "value": "The value your email provider generates"}))

    if dmarc_error:
        checks.append(_row("dmarc", "DMARC", "unknown", "Could not be checked because DNS did not answer. Try again in a few minutes."))
    elif dmarc:
        policy = dmarc_tag(dmarc, "sp") if dmarc_at != name and dmarc_tag(dmarc, "sp") else dmarc_tag(dmarc, "p")
        inherited = f" It comes from {dmarc_at}." if dmarc_at != name else ""
        detail = {"reject": "rejects", "quarantine": "sends to spam"}.get(policy, "only monitors")
        checks.append(_row("dmarc", "DMARC", "pass", f"Found (policy: {policy or 'none'}). Mail that fails the checks {detail}.{inherited}", record=dmarc))
    else:
        checks.append(_row("dmarc", "DMARC", "fail", "Missing. Google and Yahoo expect bulk senders to publish one, so cold mail is more likely to land in spam.", [
            "Add a TXT record at the _dmarc host shown below.",
            "It starts at p=none, which only monitors and does not change delivery. Tighten it to quarantine once a few weeks of reports look clean.",
        ], fix={"type": "TXT", "host": "_dmarc." + domain, "value": f"v=DMARC1; p=none; rua=mailto:dmarc@{domain}; adkim=r; aspf=r; pct=100"}))

    if mx_error:
        checks.append(_row("mx", "MX", "unknown", "Could not be checked because DNS did not answer. Try again in a few minutes."))
    elif mx_hosts:
        checks.append(_row("mx", "MX", "pass", f"Found. Replies to this domain are delivered to {mx_hosts[0]}."))
    else:
        checks.append(_row("mx", "MX", "fail", "Missing. Replies and bounces to this domain cannot be delivered, and many receivers distrust a domain that cannot receive mail.", [
            "Add the MX records your email provider lists in its setup guide, then check again.",
        ]))

    states = {c["key"]: c["status"] for c in checks}
    if spf_error or dmarc_error:
        result["state"], result["summary"] = "unknown", "Some records could not be checked because DNS did not answer."
    elif states["spf"] == "pass" and states["dmarc"] == "pass" and states["mx"] != "fail":
        result["state"] = "passing"
        result["summary"] = "SPF, DMARC and MX are in place." + (" DKIM is set up too." if dkim else " DKIM could not be verified.")
    else:
        missing = [c["label"] for c in checks if c["status"] == "fail"]
        result["state"] = "failing"
        result["summary"] = "Needs attention: " + _join(missing) + "."
    return result


def _dkim_host(hosts, domain):
    text = " ".join(hosts)
    if "google" in text:
        return f"google._domainkey.{domain}", "In Google Admin: Apps > Google Workspace > Gmail > Authenticate email."
    if "outlook" in text or "microsoft" in text:
        return f"selector1._domainkey.{domain}", "In Microsoft 365 Defender: Policies > DKIM gives you two CNAME records."
    if "zoho" in text:
        return f"zoho._domainkey.{domain}", "In Zoho Mail Admin: Domains > Email configuration > DKIM."
    return f"yourselector._domainkey.{domain}", "Your provider chooses both the selector name and the value."


def _row(key, label, status, message, steps=None, fix=None, record=""):
    return {"key": key, "label": label, "status": status, "message": message,
            "steps": steps or [], "fix": fix, "record": record[:500]}


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1] if parts else "nothing"
