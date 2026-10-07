"""Observe the pinned finder, without changing its files or parsing human logs."""
import io
import json
import re
import sys
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from unittest.mock import patch

from django.db import transaction
from django.utils import timezone

from leadzen.config.models import ChatRun, DiscoveryCandidate, DiscoveryEvent, DiscoveryLookup, DiscoverySession

_current = ContextVar("leadzen_discovery_monitor", default=None)

_CAMPAIGN_RULES = (
    "\n\nThe campaign target above is the eligibility rule for this search. Product "
    "documentation describes what is sold; it must not broaden the requested "
    "audience. Reject a profile when its industry, location, company size, or role "
    "does not satisfy an explicit campaign restriction, even if the product would "
    "help that prospect. Do not infer ownership or employee count from a job title "
    "or a small-sounding company name. If a required fact is unsupported, reject."
)

_ADMITTED_MISMATCH = (
    re.compile(r"\b(?:outside|not (?:strictly )?in)\b.{0,160}\b(?:campaign|target|requested|specified)\b", re.I | re.S),
    re.compile(r"\b(?:campaign|target|requested|specified)\b.{0,100}\b(?:mismatch|outside|does not include|doesn't include)\b", re.I | re.S),
    re.compile(r"\brather than\b.{0,130}\b(?:campaign|target)\b", re.I | re.S),
)


def _qualify_for_campaign(profile_text, product_docs, campaign_target, qualifier):
    label, reason = qualifier(profile_text, product_docs=product_docs,
                              campaign_target=campaign_target + _CAMPAIGN_RULES)
    if label == 1 and any(pattern.search(reason) for pattern in _ADMITTED_MISMATCH):
        return 0, "Campaign target mismatch acknowledged by the qualification: " + reason
    return label, reason


class DiscoveryPaused(Exception):
    """Raised only between persisted actions, never across an uncertain POST."""


def current():
    return _current.get()


@contextmanager
def observe(row):
    session = DiscoverySession.objects.filter(run_id=row.pk).first()
    token = _current.set(Monitor(session) if session else None)
    try:
        yield
    finally:
        _current.reset(token)


def safe_profile(value):
    try:
        parsed = urlsplit(value or "")
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return value[:500]
    except ValueError:
        pass
    return ""


def candidate_payload(row):
    return {"id": row.pk, "source_id": row.source_id, "outcome": row.outcome,
            "contact_id": row.contact_id, **row.data}


def counts(session):
    rows = session.candidates.all()
    return {"discovered": rows.filter(discovered=True).count(), "evaluated": rows.filter(evaluated=True).count(),
            "awaiting_evaluation": rows.filter(discovered=True, evaluated=False).count(),
            "qualified": rows.filter(outcome="qualified").count(), "rejected": rows.filter(outcome="rejected").count(),
            "with_email": sum(bool(r.data.get("email")) for r in rows.filter(outcome="qualified")),
            "produced": rows.filter(produced=True).count()}


def credits(session):
    receipts = list(session.lookups.all())
    uncertain = any(r.credits is None for r in receipts)
    used = sum((r.credits or Decimal(0) for r in receipts), Decimal(0))
    return {"used": None if uncertain else float(used), "reported": float(used),
            "pending": sum(r.state != "terminated" for r in receipts),
            "approved": session.goal if session.unit == "emails" else 0}


def selected_identity(source_ids):
    from openoutfind.crm.models import Lead, Deal as Decision
    from cold_outreach.leads.models import Deal, Suppression
    from leadzen.home import QUALIFIED
    from leadzen.config.models import ContactPreferences
    keys = [str(i) for i in source_ids]
    return {"profiles": list(Lead.objects.filter(pk__in=source_ids).order_by("pk").values("id", "profile_url", "full_name", "job_title", "company__name", "company__domain", "synthetic", "disqualified")),
            "qualified": list(Decision.objects.filter(lead_id__in=source_ids, state__in=QUALIFIED).exclude(outcome="wrong_fit").order_by("lead_id").values_list("lead_id", flat=True)),
            "stopped": list(Deal.objects.filter(lead__lead_id__in=keys, state="Completed").order_by("pk").values_list("lead__lead_id", flat=True)),
            "suppressed": list(Suppression.objects.filter(email__in=Deal.objects.filter(lead__lead_id__in=keys).exclude(lead__email="").values("lead__email")).order_by("pk").values_list("email", flat=True)),
            "deleted": list(ContactPreferences.objects.filter(lead__lead_id__in=keys, deleted_at__isnull=False).order_by("pk").values_list("lead__lead_id", flat=True))}


class Monitor:
    def __init__(self, session):
        self.session = session

    def guard(self):
        from leadzen.chat.engine import snapshot
        from leadzen.workspaces import assert_worker_access
        assert_worker_access()
        row = ChatRun.objects.get(pk=self.session.run_id)
        if row.status != "running" or row.cancel_requested or not row.deadline_at or row.deadline_at <= timezone.now():
            raise PermissionError("Discovery stopped or exceeded its deadline")
        if snapshot("find_leads", self.session.action["arguments"]) != self.session.action["snapshot"]:
            raise PermissionError("Discovery setup changed")
        if self.session.source_ids and selected_identity(self.session.source_ids) != self.session.action.get("source_identity"):
            raise PermissionError("Selected lead identity or deletion state changed")

    def boundary(self):
        self.guard()
        self.session.refresh_from_db()
        if self.session.pause_requested:
            raise DiscoveryPaused()
        DiscoverySession.objects.filter(pk=self.session.pk).update(phase="running", updated_at=timezone.now())

    def event(self, kind, data):
        from leadzen.chat.engine import redact
        # Keep a rolling bounded history. Reaching the cap must not silently
        # freeze live progress for the rest of a large discovery run.
        DiscoveryEvent.objects.create(session=self.session, kind=kind, data=redact(data))
        if self.session.events.count() > 1000:
            # Activity derives the true start time from the first saved event.
            # Preserve that anchor alongside the most recent 999 updates.
            first = self.session.events.order_by("pk").values_list("pk", flat=True).first()
            cutoff = self.session.events.order_by("-pk").values_list("pk", flat=True)[998]
            self.session.events.filter(pk__lt=cutoff).exclude(pk=first).delete()

    def candidate(self, lead):
        if lead.synthetic:
            return None
        if not self.session.candidates.filter(source_id=lead.pk).exists() and self.session.candidates.count() >= 5000:
            raise PermissionError("Candidate storage limit reached")
        from leadzen.chat.engine import redact
        row, _ = DiscoveryCandidate.objects.get_or_create(session=self.session, source_id=lead.pk)
        row.data = redact({"name": (lead.full_name or " ".join(filter(None, [lead.first_name, lead.last_name])) or "Unnamed profile")[:240],
                           "title": (lead.job_title or "")[:240], "company": ((lead.company.name or lead.company.domain or "") if lead.company else "")[:240],
                           "profile_url": safe_profile(lead.profile_url), "reason": row.data.get("reason", ""), "email": lead.email or ""})
        return row

    def discovered(self, leads):
        for lead in leads:
            row = self.candidate(lead)
            if row:
                changed = not row.discovered
                row.discovered = True
                row.save()
                if changed:
                    self.event("discovered", candidate_payload(row))

    def evaluating(self, lead=None):
        # This is an operation phase, not a verdict. An interrupted LLM call
        # must not count a candidate as evaluated or manufacture a reason.
        row = self.candidate(lead) if lead is not None else None
        if row:
            row.save()
        self.event("evaluating", candidate_payload(row) if row else {
            "message": "Reviewing a candidate against your saved target."
        })

    def verdict(self, lead):
        from openoutfind.crm.models import Deal, DealState
        from openoutfind.core.export import lead_record
        from cold_outreach.leads.ingest import ingest
        from cold_outreach.leads.models import Deal as Contact
        from leadzen.chat.engine import redact
        lead.refresh_from_db()
        row = self.candidate(lead)
        deal = Deal.objects.filter(lead=lead).first()
        if not row or not deal:
            return
        outcome = "rejected" if lead.disqualified or deal.state == DealState.FAILED else "qualified"
        changed = not row.evaluated or row.outcome != outcome
        row.evaluated, row.outcome = True, outcome
        row.data["reason"] = redact((deal.reason or "")[:2000])
        if outcome == "qualified":
            ingest(io.StringIO(json.dumps(lead_record(deal)) + "\n"))
            row.contact_id = Contact.objects.filter(lead__lead_id=str(lead.pk)).values_list("pk", flat=True).first()
        row.save()
        if changed:
            self.event(outcome, candidate_payload(row))

    def output(self, record):
        from openoutfind.crm.models import Lead
        from cold_outreach.leads.models import Deal as Contact
        from leadzen.chat.engine import redact
        lead = Lead.objects.filter(pk=record.get("lead_id"), synthetic=False).select_related("company").first()
        if not lead:
            return
        if self.session.source_ids and lead.pk not in self.session.source_ids:
            return
        row = self.candidate(lead)
        row.outcome = "qualified"
        row.produced = self.session.unit == "leads" or bool(record.get("email") and lead.email)
        row.data["email"] = record.get("email") or lead.email or ""
        row.data["reason"] = redact(str(record.get("reason") or row.data.get("reason", ""))[:2000])
        row.contact_id = Contact.objects.filter(lead__lead_id=str(lead.pk)).values_list("pk", flat=True).first()
        row.save()

    def reserve_lookup(self, body):
        from openoutfind.crm.models import Deal, DealState
        from leadzen.config.models import ContactPreferences
        if self.session.unit != "emails" or body.get("enrich_email_address") is not True or body.get("enrich_phone_number") is True:
            raise PermissionError("Email enrichment was not approved")
        data = body.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise PermissionError("Only one approved email lookup is allowed per request")
        deal = Deal.objects.filter(lead__profile_url=data[0].get("linkedin_url"), lead__synthetic=False, lead__disqualified=False,
                                   state__in=[DealState.QUALIFIED, DealState.READY_TO_FIND_EMAIL]).first()
        if not deal or (self.session.source_ids and deal.lead_id not in self.session.source_ids):
            raise PermissionError("Email lookup is outside the qualified selection")
        if ContactPreferences.objects.filter(lead__lead_id=str(deal.lead_id), deleted_at__isnull=False).exists():
            raise PermissionError("This contact was deleted")
        with transaction.atomic(using=self.session._state.db):
            rows = list(self.session.lookups.all())
            used = sum((r.credits or Decimal(0) for r in rows), Decimal(0))
            pending = sum(r.state != "terminated" or r.credits is None for r in rows)
            if used + pending + 1 > self.session.goal:
                raise PermissionError("The approved email-credit budget is reserved or exhausted")
            if any(r.source_id == deal.lead_id for r in rows):
                raise PermissionError("A lookup was already submitted; never resubmit uncertain work")
            from leadzen.autopilot import external_guard
            external_guard(reserve_credit=True)
            return DiscoveryLookup.objects.create(session=self.session, source_id=deal.lead_id)

    def submitted(self, receipt, body):
        identifier = body.get("request_id") or body.get("id")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 100:
            raise PermissionError("The provider did not return a usable lookup handle")
        receipt.request_id, receipt.state = identifier, "submitted"
        receipt.save(update_fields=["request_id", "state"])
        self.event("email_lookup", {"message": "Verified email requested for one approved lead."})

    def report_lookup(self, identifier, body):
        row = self.session.lookups.filter(request_id=identifier).first()
        if not row:
            raise PermissionError("Lookup handle is not owned by this discovery run")
        if body.get("credits_consumed") is not None:
            try:
                value = Decimal(str(body["credits_consumed"]))
                if not value.is_finite() or value < 0 or value > Decimal("999999.99") or value.as_tuple().exponent < -2 or isinstance(body["credits_consumed"], bool):
                    raise InvalidOperation()
            except InvalidOperation:
                raise PermissionError("The provider usage report is invalid") from None
            row.credits = max(value, row.credits or Decimal(0))
        if body.get("status") == "terminated":
            row.state = "terminated"
            data = body.get("data")
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                status = data[0].get("contact_email_address_status")
                if status in {"valid", "deliverable", "catch_all_safe", "not_found", "invalid"}:
                    row.email_status = status
        row.save(update_fields=["credits", "state", "email_status"])
        if credits(self.session)["reported"] > self.session.goal:
            # Preserve the provider's actual report, then forbid additional work.
            raise PermissionError("Reported usage exceeded the approved budget")

    @contextmanager
    def adapters(self, *, poll_only=False):
        from openoutfind.core import cycle, job
        from openoutfind.core.db import leads as lead_store
        from openoutfind.core.ml import qualifier as qualification
        from openoutfind.core.pipeline import discover, qualify, ready_pool
        from openoutfind.crm.models import Lead, DealState
        original_cycle, original_fetch = cycle.run_one_action, discover._fetch
        original_harvest, original_verdict = discover._harvest, qualify._save_qualification_result
        original_due, original_profiles = cycle._due, ready_pool.get_qualified_profiles
        original_create = lead_store.create_lead
        original_qualification, original_llm = qualify.run_qualification, qualification.qualify_with_llm
        original_candidates, original_unit_ids = qualify.fetch_qualification_candidates, job._unit_ids
        new_source_after = self.session.action.get("new_source_after")
        new_only = (self.session.unit == "leads" and self.session.action.get("authorization") == "autopilot"
                    and isinstance(new_source_after, int) and not isinstance(new_source_after, bool)
                    and new_source_after >= 0)
        qualification_candidates = ContextVar("leadzen_qualification_candidates", default=())

        def discovered_ids():
            return set(self.session.candidates.filter(discovered=True, source_id__gt=new_source_after)
                       .values_list("source_id", flat=True))

        def candidates():
            pool = original_candidates()
            if new_only:
                selected = discovered_ids()
                return [lead for lead in pool if lead.pk in selected]
            return pool

        def profiles():
            pool = original_profiles()
            if new_only:
                selected = discovered_ids()
                return [p for p in pool if p.get("lead_id") in selected]
            return [p for p in pool if p.get("lead_id") in self.session.source_ids]

        def unit_ids(*args, **kwargs):
            # The upstream --new goal means newly qualified, including old backlog.
            # Autopilot's promise is profiles actually discovered in today's run.
            return original_unit_ids(*args, **kwargs) & discovered_ids()

        def fresh_top_up(site_config, model):
            from openoutfind.core.pipeline import top_up as pipeline
            original_discovery = pipeline.discover
            moved = False

            def search(*args, **kwargs):
                nonlocal moved
                result = original_discovery(*args, **kwargs)
                moved = moved or bool(result)
                return result

            # Cold top_up otherwise says "idle" when a returned page contains only
            # familiar profiles. Its frontier moved; try the next bounded action.
            with patch.object(pipeline, "discover", search):
                acted = pipeline.top_up(site_config, model())
            return bool(acted or moved)

        def step(*args, **kwargs):
            self.boundary()
            return original_cycle(*args, **kwargs)

        def fetch(node, offset):
            self.boundary()
            filters = node.to_filters()
            self.event("searching", {"filters": {str(k)[:80]: str(v)[:300] for k, v in filters.items()}, "offset": offset})
            page = original_fetch(node, offset)
            if page is not None and isinstance(getattr(page, "leads", None), list):
                self.event("search_completed", {"profiles_returned": len(page.leads), "offset": offset})
            return page

        def create_profile(data, *args, **kwargs):
            self.boundary()
            result = original_create(data, *args, **kwargs)
            if result:
                lead = Lead.objects.filter(profile_url=data.get("contact_linkedin_profile_url"), synthetic=False).select_related("company").first()
                if lead:
                    self.discovered([lead])
            return result

        def harvest(*args, **kwargs):
            # Emit each actual persisted profile as it arrives, rather than
            # waiting for an entire fetched page to finish embedding.
            with patch("openoutfind.core.db.leads.create_lead", create_profile):
                return original_harvest(*args, **kwargs)

        def run_qualification(site_config, qualifier, candidates=None):
            pool = qualify.fetch_qualification_candidates() if candidates is None else candidates
            if new_only:
                selected = discovered_ids()
                pool = [lead for lead in pool if lead.pk in selected]
            token = qualification_candidates.set(pool)
            try:
                return original_qualification(site_config, qualifier, candidates=pool)
            finally:
                qualification_candidates.reset(token)

        def review(profile_text, product_docs, campaign_target):
            self.boundary()
            matches = [lead for lead in qualification_candidates.get() if lead.profile_text == profile_text]
            # Profile text is not a canonical ID. Identical firmographics can
            # belong to several people; show the phase without guessing whom.
            self.evaluating(matches[0] if len(matches) == 1 else None)
            return _qualify_for_campaign(profile_text, product_docs, campaign_target, original_llm)

        def verdict(qualifier, lead, *args, **kwargs):
            original_verdict(qualifier, lead, *args, **kwargs)
            self.verdict(lead)

        def due(state):
            rows = original_due(state)
            if self.session.source_ids:
                rows = rows.filter(lead_id__in=self.session.source_ids)
            if state == DealState.FINDING_EMAIL:
                rows = rows.filter(lookup_request_id__in=self.session.lookups.exclude(request_id="").values_list("request_id", flat=True))
            return rows

        with ExitStack() as stack:
            stack.enter_context(patch("openoutfind.core.cycle.run_one_action", step))
            stack.enter_context(patch("openoutfind.core.pipeline.discover._fetch", fetch))
            stack.enter_context(patch("openoutfind.core.pipeline.discover._harvest", harvest))
            stack.enter_context(patch("openoutfind.core.pipeline.qualify.run_qualification", run_qualification))
            # Already-loaded top_up holds a cached imported alias. If it has
            # not loaded yet, its first import picks up the patched function;
            # do not eagerly load the ML vocabulary just to observe progress.
            top_up = sys.modules.get("openoutfind.core.pipeline.top_up")
            if top_up is not None:
                stack.enter_context(patch.object(top_up, "run_qualification", run_qualification))
                if new_only:
                    stack.enter_context(patch.object(top_up, "fetch_qualification_candidates", candidates))
            stack.enter_context(patch("openoutfind.core.ml.qualifier.qualify_with_llm", review))
            stack.enter_context(patch("openoutfind.core.pipeline.qualify._save_qualification_result", verdict))
            stack.enter_context(patch("openoutfind.core.cycle._due", due))
            # Employee data is not shared with the upstream cross-operator hub.
            stack.enter_context(patch("openoutfind.contacts.service.resolve", return_value=None))
            stack.enter_context(patch("openoutfind.contacts.service.contribute", return_value=None))
            if new_only:
                # Searching/qualifying new profiles cannot poll or buy old addresses.
                stack.enter_context(patch("openoutfind.core.cycle.ROWS", (cycle.ROWS[1],
                    (cycle.ROWS[3][0], fresh_top_up, False))))
                stack.enter_context(patch("openoutfind.core.pipeline.qualify.fetch_qualification_candidates", candidates))
                stack.enter_context(patch("openoutfind.core.pipeline.ready_pool.get_qualified_profiles", profiles))
                stack.enter_context(patch("openoutfind.core.job._unit_ids", unit_ids))
            if self.session.source_ids:
                # A selected action cannot consume an unrelated lookup's slot.
                # Continuations only collect handles already owned by this session;
                # they cannot rank/discover leads or submit another paid request.
                from openoutfind.crm.models import Deal
                stack.enter_context(patch("openoutfind.core.job._on_order", lambda: Deal.objects.filter(
                    state=DealState.FINDING_EMAIL, lead_id__in=self.session.source_ids).count()))
                stack.enter_context(patch("openoutfind.core.cycle.ROWS", cycle.ROWS[:1] if poll_only else cycle.ROWS[:3]))
                stack.enter_context(patch("openoutfind.core.pipeline.ready_pool.get_qualified_profiles", profiles))
            try:
                yield
            finally:
                if top_up is None:
                    # A first import inside this context caches our patched aliases.
                    # Restore them too so later discovery cannot keep this session's
                    # candidate selection or cancellation boundary by accident.
                    loaded = sys.modules.get("openoutfind.core.pipeline.top_up")
                    if loaded is not None:
                        if getattr(loaded, "run_qualification", None) is run_qualification:
                            loaded.run_qualification = original_qualification
                        if getattr(loaded, "fetch_qualification_candidates", None) is candidates:
                            loaded.fetch_qualification_candidates = original_candidates


class ProgressOutput(io.StringIO):
    """Import each complete JSONL record now; incomplete tails cannot become leads."""
    def __init__(self, monitor):
        super().__init__()
        self.monitor, self.tail = monitor, ""

    def write(self, text):
        from cold_outreach.leads.ingest import ingest
        result = super().write(text)
        self.tail += text
        while "\n" in self.tail:
            line, self.tail = self.tail.split("\n", 1)
            if not line.strip():
                continue
            if len(line) > 262144:
                raise ValueError("Discovery record is too large")
            ingested = ingest(io.StringIO(line + "\n"))
            if ingested.stored:
                self.monitor.output(json.loads(line))
        if len(self.tail) > 262144:
            raise ValueError("Discovery record is too large")
        return result
