"""Finder records update saved contacts without undoing an employee's edits.

The sender library's ingest writes every non-empty finder value ("latest wins").
That is right for a new contact and for the work email it buys, but a later
lookup or re-discovery must not silently revert a corrected name, company or
title. Saved non-empty details are kept; the finder only fills blanks. Email and
suppression still go through the library's own checks.
"""
import io
import json

from cold_outreach.leads.ingest import LEAD_FIELDS, ingest as library_ingest
from cold_outreach.leads.models import Lead

KEPT = tuple(field for field in LEAD_FIELDS if field != "email")


def ingest(stream):
    text = stream.read()
    ids = set()
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("lead_id") is not None:
            ids.add(str(record["lead_id"]).strip())
    saved = {lead.lead_id: {field: getattr(lead, field) for field in KEPT if getattr(lead, field)}
             for lead in Lead.objects.filter(lead_id__in=ids)} if ids else {}
    result = library_ingest(io.StringIO(text))
    for lead in Lead.objects.filter(lead_id__in=list(saved)):
        changed = [field for field, value in saved[lead.lead_id].items() if getattr(lead, field) != value]
        for field in changed:
            setattr(lead, field, saved[lead.lead_id][field])
        if changed:
            lead.save(update_fields=changed)
    return result
