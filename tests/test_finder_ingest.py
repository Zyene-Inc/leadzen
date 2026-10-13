"""Finder records never undo an employee's edits; they fill blanks and add the bought email."""
import json
from unittest.mock import patch

from tests.test_ai_ark import ark_client, person, discovery_client, chat_client  # noqa
from tests.test_chat import post


def test_work_email_lookup_reverts_employee_edits(ark_client):
    from tests.test_lead_crm import prospect, lookup_body
    from leadzen.chat.engine import drive
    from leadzen.config.models import ChatRun
    deal, profile = prospect()
    profile.profile_url = person()["link"]["linkedin"]
    profile.save()
    edit = {"email": "", "first_name": "Bruce", "last_name": "Corrected", "company": "Corrected Practice", "title": "Practice Owner",
            "website": "https://example.com", "linkedin_url": profile.profile_url, "profile_text": "", "opted_in": False, "consent_note": ""}
    r = ark_client.put(f"/api/contacts/{deal.pk}", json.dumps(edit), content_type="application/json")
    assert r.status_code == 200, r.content
    deal.lead.refresh_from_db()
    assert deal.lead.title == "Practice Owner"
    with patch("leadzen.chat.views.launch"):
        response = post(ark_client, f"/api/contacts/{deal.pk}/email", lookup_body(ark_client, deal))
    assert response.status_code == 202, response.content
    row = ChatRun.objects.get(pk=response.json()["run"]["id"])
    enriched = {**person(), "email": {"state": "DONE", "output": [{"address": "bruce@example.com", "found": True, "status": "VALID", "domainType": "SMTP", "free": False, "generic": False}]}}
    with patch("leadzen.ai.pinned_request", return_value=(200, {}, json.dumps(enriched).encode())):
        drive(row.pk)
    deal.lead.refresh_from_db()

    assert deal.lead.email == "bruce@example.com"
    assert deal.lead.title == "Practice Owner", deal.lead.title


def test_finder_ingest_fills_blanks_keeps_edits_and_adds_email(db):
    import io
    from cold_outreach.leads.models import Lead
    from leadzen.finder_ingest import ingest
    Lead.objects.create(lead_id="901", first_name="Ada", title="Owner (edited)", company="")
    record = {"lead_id": 901, "first_name": "Adeline", "title": "Founder", "company": "Finder Co", "email": "ada@example.com", "reason": "fit"}
    assert ingest(io.StringIO(json.dumps(record) + "\n")).stored == 1
    lead = Lead.objects.get(lead_id="901")
    assert (lead.first_name, lead.title, lead.company, lead.email) == ("Ada", "Owner (edited)", "Finder Co", "ada@example.com")
