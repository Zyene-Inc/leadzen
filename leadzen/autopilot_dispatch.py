"""Nonblocking fair dispatch: at most four isolated employee processes at a time."""
import subprocess
import logging
import sys
import tempfile
import time

from leadzen.worker_status import BUSY_EXIT, reported_error

_workers = {}
_errors = {}  # each running worker's stderr file, read only for its error type
_busy = {}  # consecutive passes a workspace was busy
_cursor = 0
# About 15 minutes of 30-second passes: longer than any Chat run, so a lock this old is stuck.
BUSY_ALERT = 30
logger = logging.getLogger(__name__)


def _finished(key, code):
    """Log one finished worker. Returns False when the pass should count as failed."""
    errors = _errors.pop(key, None)
    try:
        label = str(key)[:8]
        if code == BUSY_EXIT:
            # A Chat run, send or reply check held the workspace; it runs on the next pass.
            _busy[key] = _busy.get(key, 0) + 1
            if _busy[key] < BUSY_ALERT:
                return True
            if _busy[key] == BUSY_ALERT:
                logger.warning("Workspace %s has been busy for about 15 minutes; follow-ups and Autopilot wait until its running job ends.", label)
            return False
        _busy.pop(key, None)
        if code:
            name = reported_error(errors)
            logger.error("Workspace Autopilot worker failed for workspace %s (exit code %s%s). Check account access, schema and connection settings.",
                         label, code, f", {name}" if name else "")
            return False
        return True
    finally:
        if errors is not None:
            errors.close()


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
                if not _finished(key, code):
                    successful = False
                del _workers[key]
            elif time.monotonic() - started > 900:
                successful = False
                process.kill()
                process.wait(timeout=5)
                logger.error("Workspace Autopilot worker exceeded its execution deadline. Claimed sends and paid requests remain held for review.")
                del _workers[key]
                errors = _errors.pop(key, None)
                if errors is not None:
                    errors.close()
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
            errors = tempfile.TemporaryFile()
            try:
                process = subprocess.Popen([sys.executable, "-m", "leadzen.autopilot_worker"],
                    env=worker_environment(profile), stdout=subprocess.DEVNULL, stderr=errors)
            except BaseException:
                errors.close()
                raise
            _workers[profile.pk] = (process, time.monotonic())
            _errors[profile.pk] = errors
        _cursor = (_cursor + max(1, offset)) % len(profiles)
    return successful
