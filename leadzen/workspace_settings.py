"""Canonical employee settings and consistent backups of the combined workspace."""
import hmac
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from urllib.parse import quote

from django.http import FileResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pytz import country_names

from leadzen.accounts.service import access, payload
from leadzen.config.models import OnboardingState, SiteConfig
from leadzen.configuration import effective, SettingsError
from leadzen.home import current_target
from leadzen.setup_wizard import fingerprint, text, validate_step, validate_booking_link
from leadzen.sending_schedule import get_schedule, normalize_schedule
from leadzen.workspaces import database_path


def settings_payload(actor):
    config, values = SiteConfig.load(), effective()
    state = OnboardingState.objects.filter(pk=1).first()
    checks = {}
    for kind in ("ai", "discovery", "mailbox"):
        receipt = (state.checks.get(kind) or {}) if state else {}
        matches = bool(os.environ.get("LEADZEN_SETTINGS_KEY")) and hmac.compare_digest(receipt.get("fingerprint", ""), fingerprint(values, kind))
        checks[kind] = {key: receipt[key] for key in ("tested_at", "synthetic", "answered", "credits", "smtp", "imap") if matches and key in receipt}
        checks[kind]["connected"] = bool(matches and receipt.get("expires_at", "") > timezone.now().isoformat())
    draft = state.draft if state else {}
    name, description = draft.get("product_name", ""), draft.get("product_docs", "")
    if config.product_docs != (name + "\n\n" + description if name else description):
        name, description = "", config.product_docs
    path = database_path(actor.leadzen_profile)
    try:
        size = path.stat().st_size
    except OSError:
        size = None
    return {"workspace": {
        "identity": {"operator_name": config.operator_name, "operator_email": config.operator_email,
                     "operator_country_code": config.operator_country_code, "country_name": country_names.get(config.operator_country_code, "")},
        "product": {"product_name": name, "product_docs": description}, "booking_link": config.booking_link,
        "sending_schedule": get_schedule(config),
        "target": {**current_target(config, state), "accepted_legal_notice": config.accepted_legal_notice},
        "checks": checks, "countries": [{"code": code, "name": name} for code, name in sorted(country_names.items(), key=lambda row: row[1])],
        "data": {"engine": "SQLite", "path": str(path), "size_bytes": size, "combined": True},
    }}


def validate_changes(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - {"identity", "product", "booking_link", "target", "sending_schedule"}:
        raise SettingsError("Choose valid workspace settings")
    changes = {}
    if "identity" in value:
        if not isinstance(value["identity"], dict):
            raise SettingsError("Identity must be an object")
        changes.update(validate_step(3, value["identity"], None, None))
    if "product" in value:
        product = value["product"]
        if not isinstance(product, dict):
            raise SettingsError("Product must be an object")
        changes.update(product_name=text(product.get("product_name", ""), "Product name", 160, required=False),
                       product_docs=text(product.get("product_docs"), "Product description", 10000))
    if "booking_link" in value:
        changes["booking_link"] = validate_booking_link(value["booking_link"])
    if "sending_schedule" in value:
        changes["sending_schedule"] = normalize_schedule(value["sending_schedule"])
    if "target" in value:
        if not isinstance(value["target"], dict):
            raise SettingsError("Target must be an object")
        changes.update(validate_step(6, value["target"], None, None))
    return changes


def apply_changes(changes):
    if not changes:
        return
    config = SiteConfig.load()
    for key in ("operator_name", "operator_email", "operator_country_code", "booking_link", "accepted_legal_notice", "sending_schedule"):
        if key in changes:
            setattr(config, key, changes[key])
    if "product_docs" in changes:
        config.product_docs = (changes["product_name"] + "\n\n" if changes["product_name"] else "") + changes["product_docs"]
    if "audience" in changes:
        from leadzen.setup_wizard import target_preview
        config.campaign_target = target_preview(changes["audience"])
    config.save()
    state, _ = OnboardingState.objects.get_or_create(pk=1)
    state.draft.update(changes)
    state.save(update_fields=["draft", "updated_at"])


@csrf_exempt
@require_http_methods(["POST"])
@access(workspace=True)
def backup(request):
    if payload(request).get("confirmed") is not True:
        raise SettingsError("Confirm the workspace database backup")
    path = database_path(request.actor.leadzen_profile)
    # SQLite's backup API includes committed WAL data and yields a consistent
    # snapshot while discovery and sending keep using the original database.
    snapshot = tempfile.TemporaryFile(mode="w+b")
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 512 * 1024 * 1024:
            raise SettingsError("This workspace cannot be backed up through the browser. Contact your administrator.")
        deadline = time.monotonic() + 10
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise SettingsError("The database is busy. Try the backup again shortly.")
            if total * page_size > 512 * 1024 * 1024:
                raise SettingsError("This workspace is too large for a browser backup.")
        with tempfile.TemporaryDirectory(prefix="leadzen-backup-") as directory:
            copy_path = os.path.join(directory, "workspace.sqlite3")
            with closing(sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=5)) as source, closing(sqlite3.connect(copy_path)) as destination:
                page_size = source.execute("PRAGMA page_size").fetchone()[0]
                source.backup(destination, pages=128, progress=progress, sleep=0.05)
                # Export one self-contained file, including for WAL workspaces.
                # Viewing the download must not require creating WAL sidecars.
                destination.execute("PRAGMA journal_mode=DELETE")
            os.chmod(copy_path, 0o600)
            with open(copy_path, "rb") as stored:
                while chunk := stored.read(65536):
                    snapshot.write(chunk)
        snapshot.seek(0)
        filename = f"leadzen-workspace-{timezone.now().strftime('%Y-%m-%d-%H%M%S')}.sqlite3"
        return FileResponse(snapshot, as_attachment=True, filename=filename, content_type="application/vnd.sqlite3")
    except (OSError, sqlite3.Error, SettingsError):
        snapshot.close()
        return JsonResponse({"error": "The workspace backup could not be created. Try again or contact your administrator."}, status=503)
