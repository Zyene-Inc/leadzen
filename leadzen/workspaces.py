"""Keep each employee's library-managed leads, mail, and credentials isolated."""
from __future__ import annotations

import copy
import fcntl
import os
import subprocess
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from django.conf import settings
from django.db import connections

_active_database = ContextVar("leadzen_workspace_database", default=None)


class WorkspaceRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label != "leadzen_accounts":
            return _active_database.get()
        return "default"

    db_for_write = db_for_read

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._state.db and obj2._state.db:
            return obj1._state.db == obj2._state.db
        return None


def database_path(profile) -> Path:
    root = Path(os.environ.get("LEADZEN_WORKSPACE_ROOT") or settings.DATABASE_PATH.parent / "workspaces")
    return root / str(profile.id) / "db.sqlite3"


def worker_environment(profile=None) -> dict[str, str]:
    # Never inherit another employee's provider/mailbox exports from the web process.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("OUTSEND_", "OPENOUTFIND_")) and key not in {
               "OPENAI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
               "MISTRAL_API_KEY", "COHERE_API_KEY", "LEADZEN_DASHBOARD_TOKEN",
               "LEADZEN_RESEND_API_KEY",
           }}
    env["DJANGO_SETTINGS_MODULE"] = "leadzen.settings"
    if profile is not None:
        path = database_path(profile)
        env["LEADZEN_DB"] = str(path)
        env["OUTSEND_HOME"] = str(path.parent)
        env["LEADZEN_CONTROL_DB"] = str(settings.DATABASE_PATH)
        env["LEADZEN_ACTOR_ID"] = str(profile.user_id)
        env["LEADZEN_WORKSPACE_ID"] = str(profile.id)
    return env


def initialize_workspace(profile) -> None:
    path = database_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (path.parent / "initialize.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (path.parent / "initialized").exists():
            subprocess.run([sys.executable, "-m", "leadzen", "migrate", "--noinput"],
                           env=worker_environment(profile), check=True, capture_output=True, timeout=120)
            path.chmod(0o600)
            (path.parent / "initialized").touch(mode=0o600)


@contextmanager
def workspace_scope(profile):
    path = database_path(profile)
    if not path.is_file():
        raise RuntimeError("Your workspace has not been initialized")
    alias = "workspace_" + profile.id.hex
    if alias not in connections.databases:
        config = copy.deepcopy(connections.databases["default"])
        config["NAME"] = str(path)
        config["TEST"] = {**config.get("TEST", {}), "MIRROR": None}
        connections.databases[alias] = config
    token = _active_database.set(alias)
    try:
        yield alias
    finally:
        _active_database.reset(token)
        connections[alias].close()


def assert_worker_access() -> None:
    """Revalidate account ownership at execution time, including before SMTP."""
    control_path = os.environ.get("LEADZEN_CONTROL_DB")
    if not control_path:
        if os.environ.get("LEADZEN_ACTOR_ID"):
            raise PermissionError("Worker authorization is unavailable")
        return  # Deliberate local CLI mode, not a dashboard-triggered account job.
    from django.contrib.auth import get_user_model
    from leadzen.accounts.models import AccountProfile

    if "control" not in connections.databases:
        config = copy.deepcopy(connections.databases["default"])
        config["NAME"] = control_path
        connections.databases["control"] = config
    user_id = os.environ.get("LEADZEN_ACTOR_ID")
    workspace_id = os.environ.get("LEADZEN_WORKSPACE_ID")
    valid = AccountProfile.objects.using("control").filter(
        pk=workspace_id, user_id=user_id, user__is_active=True, deleted_at__isnull=True,
        must_change_password=False, onboarding_completed_at__isnull=False,
    ).exists()
    if not valid:
        raise PermissionError("This account no longer has permission to run outreach")
    get_user_model().objects.using("control").get(pk=user_id, is_active=True)


def guard_worker_sends() -> None:
    from cold_outreach.emails import sender

    original = sender._deliver
    if getattr(original, "_leadzen_guarded", False) is True:
        return

    def guarded(*args, **kwargs):
        assert_worker_access()
        from email.utils import getaddresses
        from leadzen.config.models import RuntimeSettings, ContactPreferences
        from leadzen.configuration import effective
        mailbox = args[0] if args else kwargs.get("mailbox")
        message = args[1] if len(args) > 1 else kwargs.get("email_message")
        if message is not None:
            for _, address in getaddresses(message.get_all("To", [])):
                if ContactPreferences.objects.filter(lead__email__iexact=address, deleted_at__isnull=False).exists():
                    raise PermissionError("This contact was deleted. Queued outreach is stopped.")
        if mailbox is not None and RuntimeSettings.objects.filter(pk=1).exists():
            values = effective()
            credential = values.mailbox_password if values.mail_transport == "smtp" else values.mail_api_key
            if mailbox.from_address != values.mailbox_address or not credential:
                raise PermissionError("The sending mailbox changed. Start a new run with your current settings.")
            mailbox.password = values.mailbox_password
        return original(*args, **kwargs)

    guarded._leadzen_guarded = True
    sender._deliver = guarded
