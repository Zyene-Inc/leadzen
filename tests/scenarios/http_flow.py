"""Exercise Next.js → API → real disposable SQLite with the local mail catcher."""
import http.cookiejar
import json
import pathlib
import re
import ssl
import sys
import uuid
import urllib.error
import urllib.request

base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:3001"
assert base in {"http://localhost:3001", "https://localhost:3443"}
root = pathlib.Path(sys.argv[1])
assert root.name.startswith("leadzen-preview.")
password = "LeadZen-preview-only-3487!"
employee_email = f"flow-{uuid.uuid4().hex[:8]}@preview.example"


class BrowserClient:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.jar)]
        if base.startswith("https:"):
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=sys.argv[3])))
        self.opener = urllib.request.build_opener(*handlers)

    def call(self, path, method="GET", body=None, origin=base):
        headers = {"Content-Type": "application/json", "Origin": origin}
        request = urllib.request.Request(base + path, data=json.dumps(body or {}).encode() if method != "GET" else None, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            return response.code, json.loads(response.read())


admin, employee, foreign = BrowserClient(), BrowserClient(), BrowserClient()
assert admin.call("/api/auth/login", "POST", {"email": "admin@preview.example", "password": password}, origin="https://foreign.example")[0] == 403
status, data = admin.call("/api/auth/login", "POST", {"email": "admin@preview.example", "password": password})
assert status == 200 and data["next"] == "/admin"
cookie = next(iter(admin.jar))
assert cookie.has_nonstandard_attr("HttpOnly") and cookie.get_nonstandard_attr("SameSite").lower() == "lax"
assert cookie.secure is base.startswith("https:")
status, created = admin.call("/api/proxy/admin/users", "POST", {"name": "Full flow employee", "email": employee_email})
assert status == 201 and created["invitation_status"] == "sent"
token = re.search(r"#token=([\w-]+)", json.loads((root / "last-invitation.json").read_text())["text"])[1]
assert token not in json.dumps(created)
assert employee.call("/api/auth/setup", "POST", {"token": token})[0] == 200
assert employee.call("/api/auth/setup", "POST", {"token": token, "password": "short"})[0] == 400
assert employee.call("/api/auth/setup", "POST", {"token": token, "password": password})[0] == 200
assert employee.call("/api/auth/setup", "POST", {"token": token, "password": password})[0] == 400
status, login = employee.call("/api/auth/login", "POST", {"email": employee_email, "password": password})
assert status == 200 and login["next"] == "/onboarding"
assert employee.call("/api/proxy/admin/users")[0] == 403
assert employee.call("/api/proxy/overview")[0] == 403
setup = {"purpose": "zyene_reviews", "workspace_name": "Full local flow", "product_docs": "Synthetic product description", "campaign_target": "Synthetic audience", "operator_country_code": "US", "accepted_legal_notice": True, "llm": {"enabled": False}, "mailbox": {"transport": "resend", "address": "sender@preview.example", "api_key": "synthetic-api-key", "imap_host": "imap.zoho.com", "imap_port": 993, "imap_password": "synthetic-inbox-password"}}
status, setup_result = employee.call("/api/proxy/onboarding", "PUT", setup)
assert status == 200, setup_result.get("error", "Workspace setup failed")
status, settings = employee.call("/api/proxy/settings")
assert status == 200 and settings["mailbox"]["api_key_configured"] and not settings["llm"]["enabled"]
assert "synthetic-api-key" not in json.dumps(settings) and "synthetic-inbox-password" not in json.dumps(settings)
assert employee.call("/api/proxy/tour", "POST")[0] == 200
status, lead = employee.call("/api/proxy/contacts", "POST", {"email": "prospect@example.com", "first_name": "Ada", "company": "Synthetic company", "opted_in": True, "consent_note": "Synthetic test signup"})
assert status == 201
status, campaign = employee.call("/api/proxy/campaigns", "POST", {"name": "Local consented sequence", "category": "opted_in", "contact_ids": lead["ids"], "steps": [{"subject": "Hi {{first_name}}", "body": "Hello {{company}}", "delay_days": 0}, {"subject": "Following up", "body": "A quick follow-up", "delay_days": 3}]})
assert status == 201
identifier = campaign["id"]
assert employee.call(f"/api/proxy/campaigns/{identifier}", "PUT", {"status": "active"})[0] == 200
status, send_review = employee.call(f"/api/proxy/campaigns/{identifier}/preview?count=1")
assert status == 200 and "Ada" in send_review["recipients"][0]["subject"]
assert employee.call(f"/api/proxy/campaigns/{identifier}/run", "POST", {"count": 1, "revision": send_review["revision"], "request_id": str(uuid.uuid4())})[0] == 503  # No external sends in this preview.
assert employee.call("/api/proxy/jobs")[1]["items"][0]["status"] == "failed"
assert foreign.call("/api/auth/login", "POST", {"email": "ready@preview.example", "password": password})[0] == 200
assert foreign.call(f"/api/proxy/campaigns/{identifier}", "PUT", {"status": "paused"})[0] == 404
assert all(row["email"] != "prospect@example.com" for row in foreign.call("/api/proxy/leads")[1]["items"])
assert employee.call(f"/api/proxy/contacts/{lead['ids'][0]}", "PUT", {"suppress": True})[0] == 200
assert employee.call(f"/api/proxy/campaigns/{identifier}", "DELETE")[0] == 200
assert admin.call(f"/api/proxy/admin/users/{created['user']['id']}", "PUT", {"is_active": False})[0] == 200
assert employee.call("/api/proxy/overview")[0] == 401
assert admin.call(f"/api/proxy/admin/users/{created['user']['id']}", "PUT", {"is_active": True})[0] == 200
assert employee.call("/api/auth/login", "POST", {"email": employee_email, "password": password})[0] == 200
assert employee.call("/api/auth/logout", "POST")[0] == 200
assert not list(employee.jar)
print("Full local HTTP flow passed: invitation, password, onboarding, tour, contacts, campaign, isolation, disable/re-enable, logout. No live emails sent.")
