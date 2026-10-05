"""Measure bounded CRM/eligibility queries using only disposable synthetic data."""
import io
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
import django
django.setup()

from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from cold_outreach.leads.models import Lead, Deal
from openoutfind.crm.models import Lead as Profile, Deal as Decision
from leadzen.crm import contacts_query, contact_payload, contact_payloads
from leadzen.outreach import eligible

call_command("migrate", verbosity=0, stdout=io.StringIO())
profiles = Profile.objects.bulk_create([Profile(full_name=f"Synthetic {i}",
    profile_url=f"https://example.com/profile/{i}") for i in range(100)])
Decision.objects.bulk_create([Decision(lead=p, state="Qualified", reason="Synthetic fixture") for p in profiles])
contacts = Lead.objects.bulk_create([Lead(lead_id=str(p.pk), email=f"person-{p.pk}@example.com") for p in profiles])
Deal.objects.bulk_create([Deal(lead=c) for c in contacts])

results = []
for count in [1, 10, 100]:
    for name, serialize in [("individual contact serializers", lambda rows: [contact_payload(d) for d in rows]),
                            ("production CRM page serializer", contact_payloads)]:
        started = time.monotonic()
        with CaptureQueriesContext(connection) as queries:
            serialize(list(contacts_query()[:count]))
        results.append({"operation": name, "contacts": count, "queries": len(queries),
            "seconds": round(time.monotonic() - started, 4)})
with CaptureQueriesContext(connection) as queries:
    total, selected = eligible().count(), list(eligible()[:25])
results.append({"operation": "production outreach eligibility", "contacts": 100,
    "queries": len(queries), "total": total, "selected": len(selected)})
print(json.dumps(results, indent=2))
