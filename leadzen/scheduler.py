"""Opt-in service for approved follow-ups and separately authorized Daily Autopilot.

Run explicitly with LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED=1. The default is disabled.
The control process launches isolated, bounded workspace passes, not shared ORM state.
"""
import os
import logging
import subprocess
import sys
import time

logger = logging.getLogger(__name__)


def workspace_tick():
    from django.conf import settings
    from leadzen.web_worker import _database_lock
    from leadzen.workspaces import assert_worker_access, guard_worker_sends
    from leadzen.mailboxes import prepare_worker_mailbox
    from leadzen.followups import run_due
    assert_worker_access()
    with _database_lock(settings.DATABASE_PATH):
        guard_worker_sends()
        from leadzen.ai import install_engine_adapters
        from leadzen.wizard import apply_to_environment
        from leadzen.config.models import SiteConfig
        install_engine_adapters()
        prepare_worker_mailbox(require_ai=False)
        apply_to_environment(SiteConfig.load())
        return run_due()


def tick():
    successful = True
    from django.conf import settings
    from leadzen.accounts.models import AccountProfile
    from leadzen.workspaces import database_path, worker_environment
    from leadzen.web_worker import _database_lock
    # A second service cannot race the same control pass.
    with _database_lock(settings.DATABASE_PATH.parent / "scheduler" / "db.sqlite3"):
        from leadzen.operations.maintenance import maintenance_active
        if maintenance_active(settings.DATABASE_PATH):
            return
        profiles = AccountProfile.objects.filter(
            user__is_active=True, deleted_at__isnull=True, must_change_password=False,
            onboarding_completed_at__isnull=False,
        ).select_related("user")
        for profile in profiles:
            if maintenance_active(settings.DATABASE_PATH):
                break
            if not database_path(profile).is_file():
                continue
            try:
                result = subprocess.run([sys.executable, "-m", "leadzen.scheduler", "--workspace"],
                               env=worker_environment(profile), timeout=180,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if result.returncode:
                    successful = False
                    logger.error("Workspace follow-up worker failed (exit code %s). Check account access, schema and connection settings.", result.returncode)
            except subprocess.TimeoutExpired:
                successful = False
                # Interrupted claimed messages remain sending/review, never retried.
                logger.error("Workspace follow-up worker exceeded its execution deadline. Claimed sends remain held for review.")
                continue
    return successful


def main():
    if os.environ.get("LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED") != "1" and os.environ.get("LEADZEN_AUTOPILOT_ENABLED") != "1":
        raise SystemExit("Automatic follow-ups are disabled. Enable the service only after reviewing its sending scope.")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadzen.settings")
    import django
    django.setup()
    from django.conf import settings
    if sys.argv[1:] == ["--workspace"]:
        if not os.environ.get("LEADZEN_CONTROL_DB") or not os.environ.get("LEADZEN_ACTOR_ID"):
            raise SystemExit("An authorized workspace is required")
        workspace_tick()
        return
    if sys.argv[1:]:
        raise SystemExit("usage: python -m leadzen.scheduler")
    (settings.DATABASE_PATH.parent / "scheduler").mkdir(mode=0o700, exist_ok=True)
    while True:
        try:
            from leadzen.operations.monitoring import record_scheduler_pass
            from leadzen.operations.maintenance import maintenance_active
            if maintenance_active(settings.DATABASE_PATH):
                record_scheduler_pass(settings.DATABASE_PATH, status="held")
                time.sleep(30)
                continue
            record_scheduler_pass(settings.DATABASE_PATH, status="running")
            if os.environ.get("LEADZEN_AUTOPILOT_ENABLED") == "1":
                from leadzen.autopilot_dispatch import tick as dispatch
                completed = dispatch()
            else:
                completed = tick()
            record_scheduler_pass(settings.DATABASE_PATH, status="failed" if completed is False else "ok")
        except Exception:
            print("Follow-up pass held. Check workspace access, schema and service configuration.", flush=True)
            try:
                record_scheduler_pass(settings.DATABASE_PATH, status="failed")
            except Exception:
                print("Scheduler progress could not be recorded. Check private runtime storage.", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
