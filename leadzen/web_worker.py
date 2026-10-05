"""Background worker invoked by the internal dashboard API."""
from __future__ import annotations

import fcntl
import os
import sys
from contextlib import contextmanager

import django
from django.utils import timezone


@contextmanager
def _database_lock(path):
    lock_path = path.parent / "send.lock"
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another LeadZen by Zyene job already owns the database")
        yield
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def main(job_id: str, count: int) -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadzen.settings")
    django.setup()

    from leadzen.config.models import OutreachJob, SiteConfig
    from leadzen.wizard import apply_to_environment

    job = OutreachJob.objects.get(pk=job_id)
    # A replayed launch cannot resurrect a completed/failed/claimed job.
    if OutreachJob.objects.filter(pk=job.pk, status=OutreachJob.Status.QUEUED).update(status=OutreachJob.Status.RUNNING, started_at=timezone.now()) != 1:
        return 0
    job.refresh_from_db()

    try:
        from leadzen.workspaces import assert_worker_access, guard_worker_sends
        assert_worker_access()
        guard_worker_sends()
        from leadzen.ai import install_engine_adapters
        install_engine_adapters()
        from django.conf import settings

        with _database_lock(settings.DATABASE_PATH):
            from leadzen.mailboxes import prepare_worker_mailbox
            if job.kind not in {"campaign", "reviewed"}:
                raise PermissionError("Legacy autonomous dashboard jobs require a new message review")
            prepare_worker_mailbox(require_ai=False)
            apply_to_environment(SiteConfig.load())

            try:
                if job.kind == "campaign":
                    from leadzen.campaigns import run_campaign, approved_job_guard
                    approved_job_guard(job)
                    sent = run_campaign(job.campaign_id, job.requested_count,
                                        recipient_ids=job.campaign_approval["recipient_ids"], before_send=lambda: approved_job_guard(job))
                    job.output = f"{sent} email(s) accepted. Remaining messages wait for pacing, the sending window, or their follow-up date."
                else:
                    from leadzen.outreach import run_review
                    sent = run_review(job, wait=True)
                    job.output = f"{sent} reviewed email(s) accepted by the provider. Open the review for saved progress; deferred messages require new approval."
                code = 0
            except SystemExit as error:
                code = int(error.code or 0)
            job.refresh_from_db(fields=["status"])
            if job.status == "cancelled":
                return 0
            job.status = OutreachJob.Status.SUCCEEDED if code == 0 else OutreachJob.Status.FAILED
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "output", "finished_at"])
            return code
    except Exception as error:  # noqa: BLE001 - persist the failure for the dashboard.
        job.refresh_from_db(fields=["status"])
        if job.status == "cancelled":
            return 0
        if job.kind == "reviewed":
            from leadzen.config.models import EmailReview
            EmailReview.objects.filter(pk=job.campaign_approval.get("review_id"), status__in=["queued", "running"]).update(status="failed")
        job.status = OutreachJob.Status.FAILED
        # Provider exceptions can contain URLs, prompts or secrets; never expose
        # those exception strings in dashboard job payloads.
        job.output = "Worker failed. Check connections and account access; contact support@zyene.com if the problem continues."
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "output", "finished_at"])
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m leadzen.web_worker JOB_ID COUNT")
    raise SystemExit(main(sys.argv[1], int(sys.argv[2])))
