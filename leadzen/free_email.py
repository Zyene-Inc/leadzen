"""Free LinkedIn work-email lookup, tried before any paid BetterContact credit is offered.

The lookup is ApplyBolt's LinkedIn email finder (used under Zyene's written agreement with
ApplyBolt). LeadZen sends only the normalized public profile URL, from the server, over
the same pinned HTTPS transport as the other providers. Nothing is sent to anyone.

A found address is saved only when ApplyBolt marks it valid and it belongs to the
lead's company. It is then saved exactly like a purchased one: the finder profile gets
the email and is marked resolved, and the record goes through the sender's ingest, which
applies the suppression checks. The lead becomes ready to draft. Outreach still needs the
usual review or an approved Autopilot policy. A miss or an unverified answer saves no
address, and the existing approval-gated BetterContact purchase stays the fallback.
"""
import io
import json
import os
import re
import unicodedata
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from leadzen.config.models import ContactPreferences, FreeEmailLookup

HOST = "api.applybolt.app"
URL = f"https://{HOST}/public/findEmailByLinkedIn"
LABEL = "Free lookup"
TIMEOUT = 45
RUNNING_STALE = timedelta(minutes=3)
PROFILE_HOSTS = {"linkedin.com", "www.linkedin.com", "m.linkedin.com"}


class Busy(Exception):
    """A lookup for this profile is already running."""


def enabled():
    return os.environ.get("LEADZEN_FREE_EMAIL_LOOKUP", "on").strip().lower() not in {"off", "0", "false", "no"}


def hourly_limit():
    try:
        return max(0, min(int(os.environ.get("LEADZEN_FREE_EMAIL_HOURLY_LIMIT", "60")), 1000))
    except ValueError:
        return 60


def normalize_profile(value):
    """The canonical https://www.linkedin.com/in/<slug> URL, or None for anything else."""
    try:
        raw = value if re.match(r"^https?://", value or "", re.I) else f"https://{value or ''}"
        url = urlsplit(raw)
        if (url.hostname or "").lower() not in PROFILE_HOSTS or url.scheme not in {"http", "https"} or url.username or url.password or url.port:
            return None
    except ValueError:
        return None
    match = re.fullmatch(r"/in/([A-Za-z0-9._-]{2,100})/?", url.path)
    return f"https://www.linkedin.com/in/{match.group(1)}" if match else None


def key(value):
    text = unicodedata.normalize("NFKD", (value or "").lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:120]


def words(value):
    return [word for word in key(value).split("-") if len(word) > 2]


def company_matches(expected, actual):
    a, b = key(expected), key(actual)
    if not a or not b:
        return False
    return a == b or a.startswith(f"{b}-") or b.startswith(f"{a}-") or bool(words(expected)) and all(w in words(actual) for w in words(expected))


def domain_matches(email, domain):
    domain = (domain or "").lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
    host = email.rsplit("@", 1)[-1].lower()
    return bool(domain) and (host == domain or host.endswith(f".{domain}"))


def parse(payload, *, company, domain):
    """(status, email, verdict) from one provider answer. Only a verified company address is found."""
    if not isinstance(payload, dict) or payload.get("found") not in (True, False):
        return "error", "", ""
    if payload["found"] is False:
        return "not_found", "", ""
    email = payload.get("email")
    if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,63}", email):
        return "error", "", ""
    verdict = str(payload.get("validation") or "")[:32]
    provider_company = payload.get("company") if isinstance(payload.get("company"), str) else ""
    belongs = company_matches(company, provider_company) or domain_matches(email, domain)
    if verdict == "valid" and belongs:
        return "found", email.strip().lower(), verdict
    return "unverified", "", verdict


def request(profile_url, *, preauthorized=False):
    """One provider call. Returns the parsed JSON body; raises on an unusable response."""
    from leadzen.ai import pinned_request
    status, _, raw = pinned_request("POST", URL, {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "LeadZen"},
                                    json.dumps({"linkedinUrl": profile_url}).encode(), HOST, kind="APPLYBOLT", timeout=TIMEOUT,
                                    preauthorized=preauthorized)
    if status == 429:
        raise RateLimited()
    if status != 200:
        raise ValueError(f"HTTP {status}")
    return json.loads(raw)


class RateLimited(Exception):
    pass


def facts(source):
    """Decision, company name and domain for a finder profile."""
    from openoutfind.crm.models import Deal as Decision
    decision = Decision.objects.filter(lead=source).first()
    company = source.company.name if source.company else ""
    domain = source.company.domain if source.company else ""
    return decision, company or "", domain or ""


def ineligible(source, decision):
    """Why this profile cannot get a free lookup, or '' when it can."""
    from leadzen.home import QUALIFIED
    from openoutfind.crm.models import DealState
    if not enabled():
        return "The free email lookup is turned off."
    if source.synthetic or source.disqualified:
        return "This profile cannot be looked up."
    if source.email:
        return "An email address is already saved."
    if not normalize_profile(source.profile_url):
        return "The free lookup needs a linkedin.com/in/ profile."
    if not decision or decision.state not in QUALIFIED or decision.outcome == "wrong_fit":
        return "Only qualified leads are looked up."
    if decision.state == DealState.FINDING_EMAIL:
        return "A paid lookup is already running for this lead."
    if ContactPreferences.objects.filter(lead__lead_id=str(source.pk), deleted_at__isnull=False).exists():
        return "This lead was deleted."
    return ""


def within_limit():
    return FreeEmailLookup.objects.filter(checked_at__gte=timezone.now() - timedelta(hours=1)).count() < hourly_limit()


def claim(source, *, retry):
    """Reserve this profile for one lookup. Returns the row, or None when already settled."""
    now = timezone.now()
    with transaction.atomic(using=FreeEmailLookup.objects.all().db):
        row = FreeEmailLookup.objects.select_for_update().filter(source_id=source.pk).first()
        if row:
            if row.status == "running" and row.checked_at > now - RUNNING_STALE:
                raise Busy()
            if row.status not in {"error", "running"} or (row.status == "error" and not retry):
                return None
            row.status, row.attempts, row.checked_at = "running", row.attempts + 1, now
            row.save(update_fields=["status", "attempts", "checked_at"])
            return row
        return FreeEmailLookup.objects.create(source_id=source.pk, status="running", attempts=1, checked_at=now)


def save_found(source, decision, email):
    """Store the address on the finder profile and the sender lead, like a purchased one."""
    from openoutfind.core.export import lead_record
    from openoutfind.crm.models import DealState
    from leadzen.finder_ingest import ingest
    source.email = email
    source.save(update_fields=["email"])
    decision.state, decision.not_before, decision.lookup_request_id = DealState.RESOLVED, None, ""
    decision.save(update_fields=["state", "not_before", "lookup_request_id"])
    ingest(io.StringIO(json.dumps(lead_record(decision)) + "\n"))


def settle(row, source, decision, answer, monitor=None):
    """Save one finished lookup (in the caller's thread). answer is (status, email, verdict)."""
    status, email, verdict = answer
    if status == "found":
        source.refresh_from_db()
        decision.refresh_from_db()
        if source.email or ineligible(source, decision):
            status, email = "unverified", ""
        else:
            save_found(source, decision, email)
    row.status, row.email, row.verdict, row.checked_at = status, email, verdict, timezone.now()
    row.save(update_fields=["status", "email", "verdict", "checked_at"])
    if monitor:
        monitor.free_email_settled(source, status, email)
    return status


def release(row):
    """The task stopped before the call: nothing was learned about this person."""
    if row.attempts <= 1:
        row.delete()
    else:
        FreeEmailLookup.objects.filter(pk=row.pk).update(status="error")


def lookup(source, *, retry=False, monitor=None):
    """Run the free lookup for one finder profile and wait for it. Returns the saved status,
    or '' when skipped. Raises Busy, RateLimited and PermissionError (a stopped task)."""
    decision, company, domain = facts(source)
    if ineligible(source, decision):
        return ""
    row = claim(source, retry=retry)
    if row is None:
        return FreeEmailLookup.objects.get(source_id=source.pk).status
    try:
        answer = parse(request(normalize_profile(source.profile_url)), company=company, domain=domain)
    except RateLimited:
        row.status = "error"
        row.save(update_fields=["status"])
        raise
    except PermissionError:
        release(row)
        raise
    except Exception:
        answer = ("error", "", "")
    return settle(row, source, decision, answer, monitor)


class Pipeline:
    """Free lookups started the moment each lead qualifies, while discovery keeps going.

    Only the HTTPS call runs in a worker thread. Claiming, the stop/budget check right
    before each call (assert_action_access), and every database write happen in the
    discovery thread, so SQLite and the workspace routing never see a second writer.
    """
    WORKERS = 4

    def __init__(self, monitor=None, limit=100):
        from concurrent.futures import ThreadPoolExecutor
        self.monitor, self.limit = monitor, limit
        self.executor = ThreadPoolExecutor(max_workers=self.WORKERS, thread_name_prefix="free-email")
        self.pending = {}
        self.summary = {"checked": 0, "found": 0, "not_found": 0, "errors": 0, "stopped": ""}

    def start(self, source):
        """Queue one profile. Returns False when it was not started."""
        if self.summary["stopped"] or self.summary["checked"] + len(self.pending) >= self.limit:
            return False
        decision, company, domain = facts(source)
        if ineligible(source, decision):
            return False
        if not within_limit():
            self.summary["stopped"] = "hourly_limit"
            return False
        while len(self.pending) >= self.WORKERS:
            self.collect(wait=True)
        try:
            row = claim(source, retry=False)
        except Busy:
            return False
        if row is None:
            return False
        from leadzen.chat.engine import assert_action_access
        try:
            assert_action_access()
        except PermissionError:
            release(row)
            self.summary["stopped"] = "stopped"
            return False
        future = self.executor.submit(request, normalize_profile(source.profile_url), preauthorized=True)
        self.pending[future] = (row, source, decision, company, domain)
        return True

    def collect(self, *, wait=False):
        """Save every finished lookup; with wait, block until at least one finishes."""
        from concurrent.futures import FIRST_COMPLETED, wait as wait_for
        if not self.pending:
            return
        if wait:
            wait_for(list(self.pending), timeout=TIMEOUT + 15, return_when=FIRST_COMPLETED)
        for future in [f for f in self.pending if f.done()]:
            row, source, decision, company, domain = self.pending.pop(future)
            try:
                answer = parse(future.result(), company=company, domain=domain)
            except RateLimited:
                answer = ("error", "", "")
                self.summary["stopped"] = "rate_limited"
            except Exception:
                answer = ("error", "", "")
            try:
                status = settle(row, source, decision, answer, self.monitor)
            except Exception:
                status = "error"
            self.summary["checked"] += 1
            key = {"found": "found", "error": "errors"}.get(status, "not_found")
            self.summary[key] += 1

    def finish(self):
        """Wait for every started lookup (each has its own timeout) and save the results."""
        deadline = TIMEOUT + 30
        from concurrent.futures import wait as wait_for
        if self.pending:
            wait_for(list(self.pending), timeout=deadline)
        self.collect()
        for future, (row, *_rest) in list(self.pending.items()):
            # A worker that outlived its own timeout: record it as retryable, never as a miss.
            future.cancel()
            FreeEmailLookup.objects.filter(pk=row.pk).update(status="error")
            self.pending.pop(future)
            self.summary["errors"] += 1
        self.executor.shutdown(wait=False, cancel_futures=True)
        return self.summary


def candidates(limit):
    """Qualified profiles without an email or a free lookup yet, newest first."""
    from leadzen.home import QUALIFIED
    from openoutfind.crm.models import Deal as Decision, DealState
    tried = FreeEmailLookup.objects.values_list("source_id", flat=True)
    rows = (Decision.objects.filter(state__in=[s for s in QUALIFIED if s != DealState.FINDING_EMAIL], lead__synthetic=False, lead__disqualified=False)
            .exclude(outcome="wrong_fit").filter(Q(lead__email__isnull=True) | Q(lead__email="")).exclude(lead_id__in=list(tried))
            .select_related("lead", "lead__company").order_by("-creation_date", "-pk"))
    picked = []
    for decision in rows[: limit * 4]:
        if len(picked) >= limit:
            break
        if normalize_profile(decision.lead.profile_url):
            picked.append(decision.lead)
    return picked


def after_discovery(limit, monitor=None):
    """Try the free lookup for newly qualified profiles. Never raises into discovery."""
    summary = {"checked": 0, "found": 0, "not_found": 0, "errors": 0, "stopped": ""}
    if not enabled() or limit < 1:
        return summary
    for source in candidates(min(limit, 100)):
        if not within_limit():
            summary["stopped"] = "hourly_limit"
            break
        try:
            status = lookup(source, monitor=monitor)
        except RateLimited:
            summary["stopped"] = "rate_limited"
            break
        except (Busy, PermissionError):
            break
        except Exception:
            summary["errors"] += 1
            continue
        if not status:
            continue
        summary["checked"] += 1
        if status == "found":
            summary["found"] += 1
        elif status == "error":
            summary["errors"] += 1
        else:
            summary["not_found"] += 1
    return summary


def row_payload(status, email, checked_at):
    # "email" is for server-side comparison only; the CRM strips it before responding.
    if status == "running" and checked_at <= timezone.now() - RUNNING_STALE:
        status = "error"  # an interrupted lookup can be retried
    return {"status": status, "email": email, "checked_at": checked_at.isoformat(), "label": LABEL, "retry": status == "error"}


def _payload(row):
    return row_payload(row.status, row.email, row.checked_at)


def payload(source_id):
    """The saved free-lookup result for one profile, for the lead screens."""
    row = FreeEmailLookup.objects.filter(source_id=source_id).first() if source_id else None
    return _payload(row) if row else None

