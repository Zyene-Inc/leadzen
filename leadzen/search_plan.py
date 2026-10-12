"""Keep BetterContact's provider search tied to the target actually requested.

The pinned finder seeds one global search frontier from the campaign target the
first time it runs and never reseeds it. A later Target, or a one-off Chat
audience, then only changed which returned profiles were rejected. LeadZen now
fingerprints each target; on a change it archives the finder's learned search
state (keywords, query pages and invented ideal profiles; never real leads),
starts a fresh plan or restores the archived plan for that target, and constrains
every Lead Finder request to the target's location, size and seniority.
"""
import base64
import hashlib
import json
import re
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from django.db import transaction
from django.utils import timezone

KEEP_ARCHIVES = 20
HEADCOUNT = {"1-10": (1, 10), "2-50": (2, 50), "11-50": (11, 50), "51-200": (51, 200),
             "201-500": (201, 500), "501+": (501, 1_000_000)}


def normalized(text):
    """Case, spacing and trailing punctuation never make a target meaningfully new."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip(" .,;:!")


def spec(args):
    """The provider-facing target for one run: text plus enforced filters."""
    from leadzen.config.models import OnboardingState, SiteConfig
    from leadzen.geo import place
    from leadzen.home import current_target
    location = args.get("location") or {}
    if args.get("audience"):
        # A Chat audience builds its own search. Only filters the employee gave in
        # that request are enforced; the saved Target's filters do not leak into it.
        return {"target": normalized(args["audience"]), "place": place(location) if location.get("country") else "",
                "headcount": None, "seniority": []}
    config = SiteConfig.load()
    audience = current_target(config, OnboardingState.objects.filter(pk=1).first())["audience"]
    if not audience:
        return {"target": normalized(config.campaign_target), "place": "", "headcount": None, "seniority": []}
    return {"target": normalized(config.campaign_target), "place": place(audience),
            "headcount": HEADCOUNT.get(audience["company_size"]), "seniority": sorted(audience.get("seniority") or [])}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def export_state():
    from openoutfind.core.models import Keyword, QueryNode
    from openoutfind.crm.models import Lead
    nodes = [{"key": n.token_key, "pairs": n.pairs, "parent": n.parent.token_key if n.parent_id else None,
              "next_offset": n.next_offset, "state": n.state, "leads_found": n.leads_found,
              "headcount": [n.headcount_min, n.headcount_max], "country_code": n.country_code}
             for n in QueryNode.objects.select_related("parent").prefetch_related("keywords").order_by("pk")]
    anchors = [{"profile_text": a.profile_text, "source_fields": a.source_fields, "country_code": a.country_code,
                "embedding": base64.b64encode(bytes(a.embedding)).decode() if a.embedding is not None else None}
               for a in Lead.objects.filter(synthetic=True, deal__isnull=True).order_by("pk")]
    return {"keywords": sorted(Keyword.objects.values_list("field", "token")), "nodes": nodes, "anchors": anchors}


def clear_state():
    from openoutfind.core.models import Keyword, QueryNode
    from openoutfind.crm.models import Lead
    from openoutfind.core.pipeline import vocabulary
    from openoutfind.core.ml import qualifier
    QueryNode.objects.all().delete()
    Keyword.objects.all().delete()
    # Invented ideal profiles only; a synthetic row with a decision is never removed.
    Lead.objects.filter(synthetic=True, deal__isnull=True).delete()
    vocabulary._refreshed_at = None
    qualifier._FITTED = None


def import_state(state):
    from openoutfind.core.models import Keyword, QueryNode
    from openoutfind.crm.models import Lead
    Keyword.rows_for([tuple(pair) for pair in state.get("keywords", [])])
    created = {}
    for row in state.get("nodes", []):
        node = QueryNode.objects.create(token_key=row["key"], next_offset=row["next_offset"], state=row["state"],
                                        leads_found=row["leads_found"], headcount_min=row["headcount"][0],
                                        headcount_max=row["headcount"][1], country_code=row["country_code"])
        node.keywords.set(Keyword.rows_for([tuple(pair) for pair in row["pairs"]]))
        created[row["key"]] = node
    for row in state.get("nodes", []):
        if row["parent"] in created:
            QueryNode.objects.filter(pk=created[row["key"]].pk).update(parent=created[row["parent"]])
    for row in state.get("anchors", []):
        Lead.objects.create(synthetic=True, profile_text=row["profile_text"], source_fields=row["source_fields"],
                            country_code=row["country_code"],
                            embedding=base64.b64decode(row["embedding"]) if row["embedding"] else None)


def activate(value):
    """Make `value` the finder's active plan. Returns (plan, reset_happened)."""
    from leadzen.config.models import SearchPlan
    from openoutfind.core.models import QueryNode
    from openoutfind.crm.models import Lead
    key = fingerprint(value)
    with transaction.atomic(using=QueryNode.objects.all().db):
        current = SearchPlan.objects.select_for_update().filter(active=True).first()
        if current and current.fingerprint == key:
            return current, False
        reset = False
        if current or QueryNode.objects.exists() or Lead.objects.filter(synthetic=True, deal__isnull=True).exists():
            # Back up first. State that predates target tracking is kept as "legacy".
            now = timezone.now()
            archived = current or SearchPlan(fingerprint=f"legacy-{now:%Y%m%dT%H%M%S%f}",
                                             target="Search plan saved before target tracking")
            archived.state, archived.active, archived.archived_at = export_state(), False, now
            archived.save()
            clear_state()
            reset = True
        plan = SearchPlan.objects.filter(fingerprint=key).first() or SearchPlan(fingerprint=key)
        if plan.state:
            import_state(plan.state)
        plan.target, plan.spec, plan.state = value["target"], value, {}
        plan.active, plan.activated_at, plan.archived_at = True, timezone.now(), None
        plan.save()
        stale = SearchPlan.objects.filter(active=False).order_by("-archived_at", "-pk").values_list("pk", flat=True)[KEEP_ARCHIVES:]
        SearchPlan.objects.filter(pk__in=list(stale)).delete()
    return plan, reset


def enforce(filters, value):
    """Constrain one Lead Finder query to the target's location, size and seniority."""
    from openoutfind.discovery import as_place
    filters = dict(filters)
    if value.get("place"):
        filters["lead_location"] = {"include": [as_place(value["place"])]}
    if value.get("headcount"):
        filters["company_headcount_min"], filters["company_headcount_max"] = value["headcount"]
    if value.get("seniority"):
        chosen = [s for s in (filters.get("lead_seniority") or {}).get("include", []) if s in value["seniority"]]
        filters["lead_seniority"] = {"include": chosen or list(value["seniority"])}
    return filters


@contextmanager
def scope(plan):
    """Run the finder against this plan only, without editing installed files."""
    from openoutfind.core.models import Keyword, QueryNode
    from openoutfind.core.pipeline import icp, qualify, vocabulary
    from openoutfind.crm.models import Deal, DealState, Lead, Outcome
    from openoutfind.discovery import as_place
    value, since = plan.spec, plan.activated_at
    original_seed, original_candidates = icp.generate_seed, qualify.fetch_qualification_candidates
    original_admitted, original_filters = vocabulary.admitted_keywords, QueryNode.to_filters

    def accepted():
        return Deal.objects.filter(lead_id__isnull=False, creation_date__gte=since).exclude(state=DealState.FAILED, outcome=Outcome.WRONG_FIT)

    def accepted_count():
        return accepted().count()

    def qualified_fields():
        # Earlier targets' accepted profiles must not grow this target's vocabulary.
        return [f for f in Lead.objects.filter(pk__in=accepted().values("lead_id")).values_list("source_fields", flat=True) if f]

    def candidates():
        # Unjudged profiles found for an earlier target are not this search's pool.
        return [lead for lead in original_candidates() if lead.creation_date >= since]

    def admitted():
        keep = []
        for field, token in original_admitted():
            if field == "lead_seniority" and value.get("seniority") and token not in value["seniority"]:
                continue
            if field == "lead_location" and value.get("place") and token != as_place(value["place"]):
                continue
            keep.append((field, token))
        return keep

    def seed(site_config):
        result = original_seed(site_config)
        keywords = [k for k in result.keywords
                    if not (k[0] == "lead_location" and value.get("place"))
                    and not (k[0] == "lead_seniority" and value.get("seniority") and k[1] not in value["seniority"])]
        if value.get("place"):
            keywords.append(("lead_location", as_place(value["place"])))
        keywords += [("lead_seniority", s) for s in value.get("seniority", []) if ("lead_seniority", s) not in keywords]
        Keyword.rows_for(keywords)
        try:
            # The finder only invents ideal profiles before its first acceptance; a
            # reset plan needs its own so ranking follows the new target.
            icp.ensure_anchors(site_config)
        except Exception:
            pass
        return result._replace(keywords=sorted(set(keywords)), headcount=tuple(value["headcount"]) if value.get("headcount") else result.headcount)

    def to_filters(node):
        return enforce(original_filters(node), value)

    with ExitStack() as stack:
        stack.enter_context(patch.object(icp, "generate_seed", seed))
        stack.enter_context(patch.object(vocabulary, "_accepted_count", accepted_count))
        stack.enter_context(patch.object(vocabulary, "_qualified_source_fields", qualified_fields))
        stack.enter_context(patch.object(vocabulary, "admitted_keywords", admitted))
        stack.enter_context(patch.object(qualify, "fetch_qualification_candidates", candidates))
        stack.enter_context(patch.object(QueryNode, "to_filters", to_filters))
        from openoutfind.core.pipeline import top_up
        stack.enter_context(patch.object(top_up, "fetch_qualification_candidates", candidates))
        yield
