"""Disposable browser fixture: real Django/SQLite, no outbound provider traffic.

This test-only process never loads an existing database or inherited credentials.
Expose it only through the reviewed staging gateway; it binds loopback by default.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import sys
from urllib.parse import urlsplit
from unittest.mock import patch

from cryptography.fernet import Fernet


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--port", type=int, default=8110)
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--candidate-sha256", required=True)
    args = parser.parse_args()
    origin = urlsplit(args.public_origin)
    if origin.scheme != "https" or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username or origin.password:
        parser.error("A trusted HTTPS origin, without path or credentials, is required")
    if args.directory.is_symlink():
        parser.error("Fixture directory cannot be a symbolic link")
    args.directory = args.directory.resolve()
    if not args.directory.name.startswith("leadzen-e2e.") or not args.directory.is_dir():
        parser.error("Use a freshly created, private leadzen-e2e.* directory")
    if any(args.directory.iterdir()):
        parser.error("The fixture directory must be empty; existing data is never reused")
    if not 1024 <= args.port <= 65535 or args.port in {8000, 3001}:
        parser.error("Use a separate nonprivileged fixture port")
    if bool(args.certificate) != bool(args.private_key):
        parser.error("Supply both certificate and private key, or neither")
    if not re.fullmatch(r"[a-f0-9]{64}", args.candidate_sha256):
        parser.error("Supply the verified candidate source SHA-256")
    return args


def main():
    args = arguments()
    root = args.directory
    root.chmod(0o700)
    os.umask(0o077)
    repository = Path(__file__).resolve().parents[2]
    from candidate import candidate_sha256
    if candidate_sha256(repository) != args.candidate_sha256:
        raise RuntimeError("Candidate source changed before fixture startup")
    sys.path.insert(0, str(repository))
    for name in list(os.environ):
        if name.startswith(("LEADZEN_", "OPENOUTFIND_", "OUTSEND_")) or name.endswith(("API_KEY", "TOKEN", "PASSWORD")):
            os.environ.pop(name)
    token = secrets.token_urlsafe(48)
    settings_key = Fernet.generate_key().decode()
    os.environ.update(
        DJANGO_SETTINGS_MODULE="leadzen.settings", LEADZEN_ENV="production",
        LEADZEN_DB=str(root / "control.sqlite3"), LEADZEN_WORKSPACE_ROOT=str(root / "workspaces"),
        LEADZEN_SETTINGS_KEY=settings_key, LEADZEN_SECRET_KEY=secrets.token_urlsafe(64),
        LEADZEN_DASHBOARD_TOKEN=token, LEADZEN_ALLOWED_HOSTS="localhost,127.0.0.1",
        LEADZEN_PUBLIC_URL=args.public_origin, LEADZEN_DASHBOARD_ORIGINS=args.public_origin,
        LEADZEN_RESEND_API_KEY="synthetic-fixture-resend", LEADZEN_INVITATION_FROM="Fixture <fixture@preview.example>",
        LEADZEN_AUTOPILOT_ENABLED="0", LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED="0",
    )
    from leadzen.production import validate_environment
    validate_environment()
    import django
    django.setup()
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.http import JsonResponse
    from django.utils import timezone
    from leadzen.accounts.invitations import issue_invitation
    from leadzen.accounts.service import create_account
    from leadzen.configuration import save_dashboard_settings
    from leadzen.config.models import SiteConfig
    from leadzen.workspaces import initialize_workspace, workspace_scope
    from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
    from socketserver import ThreadingMixIn

    call_command("migrate", verbosity=0, interactive=False)
    password = "Fixture-only-" + secrets.token_urlsafe(24)
    fixture_id = secrets.token_hex(16)
    manifest = {
        "fixture_id": fixture_id, "public_origin": args.public_origin,
        "provider_disabled": True, "database_directory": str(root),
        "password": password, "accounts": {}, "schema": 1, "candidate_sha256": args.candidate_sha256,
    }
    accounts = {}
    for name, admin, change in [("admin", True, False), ("ready", False, False), ("foreign", False, False), ("password_change", False, True)]:
        email = name.replace("_", "-") + "@preview.example"
        user = create_account(email=email, name="Synthetic " + name, password=password, is_admin=admin, require_change=change)
        accounts[name] = user
        manifest["accounts"][name] = {"email": email, "id": user.pk}

    def catch_invitation(_url, _key, body, **_kwargs):
        matched = re.search(r"#token=([\w-]+)", body["text"])
        if not matched:
            raise RuntimeError("Fixture invitation omitted setup capability")
        # Local private capability, never returned by the status endpoint or logs.
        manifest["setup_token"] = matched[1]
        if (root / "manifest.json").exists():
            (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return "synthetic-fixture-invitation"

    with patch("leadzen.accounts.invitations.post_email", catch_invitation):
        pending, _ = issue_invitation(accounts["admin"], email="setup@preview.example", name="Synthetic setup employee")
    accounts["setup"] = pending
    manifest["accounts"]["setup"] = {"email": pending.email, "id": pending.pk}
    for name, user in accounts.items():
        if name == "admin":
            continue
        initialize_workspace(user.leadzen_profile)
        with workspace_scope(user.leadzen_profile) as alias:
            call_command("migrate", database=alias, verbosity=0, interactive=False)
            config = SiteConfig.load()
            config.product_docs, config.campaign_target = "Synthetic fixture product", "Synthetic fixture audience"
            config.operator_name, config.operator_email = "Synthetic employee", "sender@preview.example"
            config.operator_country_code, config.accepted_legal_notice = "US", True
            config.save()
            save_dashboard_settings({"ai_enabled": False, "mailbox_address": "sender@preview.example", "smtp_host": "smtp.zoho.com", "smtp_port": 587, "imap_host": "imap.zoho.com", "imap_port": 993, "signature": "Synthetic signature"}, mailbox_password="synthetic-fixture-mailbox")
            if name in {"ready", "foreign", "password_change"}:
                from cold_outreach.leads.models import Lead, Deal
                contact = Lead.objects.create(lead_id="fixture-" + name, first_name="Synthetic " + name, last_name="Contact", email=name + "-contact@preview.example", company="Fixture company")
                Deal.objects.create(lead=contact, reason="Synthetic private workspace fixture")
                manifest["accounts"][name]["contact_id"] = contact.pk
                profile = user.leadzen_profile
                profile.workspace_name, profile.purpose = "Synthetic " + name, "other"
                profile.onboarding_completed_at, profile.tour_completed_at = timezone.now(), timezone.now()
                profile.save()

    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "backend.env").write_text("\n".join(f"{name}={os.environ[name]}" for name in sorted(os.environ) if name.startswith("LEADZEN_")) + "\n")
    api_origin = ("https" if args.certificate else "http") + f"://127.0.0.1:{args.port}"
    (root / "dashboard.env").write_text(f"NODE_ENV=production\nLEADZEN_API_URL={api_origin}\nLEADZEN_API_TOKEN={token}\nLEADZEN_DASHBOARD_PUBLIC_URL={args.public_origin}\n")
    calls = {"blocked_external_calls": 0}

    def block_external(*_args, **_kwargs):
        calls["blocked_external_calls"] += 1
        raise RuntimeError("External providers are disabled in the browser fixture")

    def disabled_job(request, job):
        job.status, job.output, job.finished_at = "failed", "External actions are disabled in this browser fixture.", timezone.now()
        job.save()
        return JsonResponse({"error": job.output}, status=503)

    def synthetic_probe(_values):
        return {"synthetic": True, "answered": True, "smtp": True, "imap": True, "credits": 0}

    application = get_wsgi_application()

    def fixture_application(environ, start_response):
        if environ.get("PATH_INFO") == "/__e2e/status":
            status = {"schema": 1, "fixture_id": fixture_id, "candidate_sha256": args.candidate_sha256, "provider_disabled": True, "production_settings": True, **calls}
            body = json.dumps(status).encode()
            start_response("200 OK", [("Content-Type", "application/json"), ("Cache-Control", "private, no-store"), ("Content-Length", str(len(body)))])
            return [body]
        return application(environ, start_response)

    class QuietLog(WSGIRequestHandler):
        def log_message(self, _format, *_args):
            pass

    class FixtureServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    with make_server("127.0.0.1", args.port, fixture_application, handler_class=QuietLog, server_class=FixtureServer) as server:
        if args.certificate:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(args.certificate, args.private_key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        with contextlib.ExitStack() as guards:
            for path in ["socket.socket.connect", "socket.create_connection", "http.client.HTTPConnection.connect", "http.client.HTTPSConnection.connect", "smtplib.SMTP", "smtplib.SMTP_SSL", "subprocess.Popen", "leadzen.ai.build_model", "leadzen.email_api.post_email", "leadzen.transports.public_socket", "leadzen.chat.views.launch"]:
                guards.enter_context(patch(path, block_external))
            guards.enter_context(patch("leadzen.accounts.invitations.post_email", catch_invitation))
            guards.enter_context(patch("leadzen.web._launch_job", disabled_job))
            for kind in ["ai", "discovery", "mailbox"]:
                guards.enter_context(patch("leadzen.setup_wizard.probe_" + kind, synthetic_probe))
            print("Disposable browser API ready; providers, subprocess workers and external sockets are blocked.", flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()
