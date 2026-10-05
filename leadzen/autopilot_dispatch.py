"""Nonblocking fair dispatch: at most four isolated employee processes at a time."""
import subprocess
import logging
import sys
import time

_workers = {}
_cursor = 0
logger = logging.getLogger(__name__)


def tick():
    global _cursor
    successful = True
    from django.conf import settings
    from leadzen.accounts.models import AccountProfile
    from leadzen.workspaces import database_path, worker_environment
    from leadzen.web_worker import _database_lock
    with _database_lock(settings.DATABASE_PATH.parent / "scheduler" / "db.sqlite3"):
        for key, (process, started) in list(_workers.items()):
            code = process.poll()
            if code is not None:
                if code:
                    successful = False
                    logger.error("Workspace Autopilot worker failed (exit code %s). Check account access, schema and connection settings.", code)
                del _workers[key]
            elif time.monotonic() - started > 900:
                successful = False
                process.kill()
                process.wait(timeout=5)
                logger.error("Workspace Autopilot worker exceeded its execution deadline. Claimed sends and paid requests remain held for review.")
                del _workers[key]
        from leadzen.operations.maintenance import maintenance_active
        if maintenance_active(settings.DATABASE_PATH):
            return successful
        profiles = list(AccountProfile.objects.filter(user__is_active=True, deleted_at__isnull=True,
            must_change_password=False, onboarding_completed_at__isnull=False).select_related("user").order_by("pk"))
        if not profiles:
            return successful
        for offset in range(len(profiles)):
            if maintenance_active(settings.DATABASE_PATH):
                break
            if len(_workers) >= 4:
                break
            index = (_cursor + offset) % len(profiles)
            profile = profiles[index]
            if profile.pk in _workers or not database_path(profile).is_file():
                continue
            process = subprocess.Popen([sys.executable, "-m", "leadzen.autopilot_worker"],
                env=worker_environment(profile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _workers[profile.pk] = (process, time.monotonic())
        _cursor = (_cursor + max(1, offset)) % len(profiles)
    return successful
