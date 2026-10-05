"""One durable chat run on the backend, never a long-running Vercel request."""
import os
import sys


def main(run_id):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadzen.settings")
    import django
    django.setup()
    from django.conf import settings
    from leadzen.chat.engine import drive, finish
    from leadzen.config.models import ChatRun
    from leadzen.web_worker import _database_lock
    try:
        with _database_lock(settings.DATABASE_PATH):
            drive(run_id)
    except Exception:
        row = ChatRun.objects.filter(pk=run_id, status="queued").first()
        if row:
            finish(row, "failed", "Another outreach worker is busy. No new chat action was started. Try again after it finishes.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
