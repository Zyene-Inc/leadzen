"""Which background work may run together, and the locks that keep it safe.

A ChatRun belongs to one lane, and each employee has at most one active run per
lane (database constraint ``one_active_run_per_lane``):

- ``chat``: conversations. They may send, so the worker holds ``send.lock``.
- ``inbox``: reply checks. Syncing must not overlap sending: ``send.lock``.
- ``provider``: lead search and work-email lookups. They spend provider credits and
  move lead records, so they never overlap each other (``provider.lock``), but they
  no longer block reply checks or Chat. Chat's own lead-search steps take the same
  lock. A server-wide slot cap keeps these heavy jobs within a 2 GB VM.
"""
import fcntl
import os
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

CHAT, PROVIDER, INBOX = "chat", "provider", "inbox"
PROVIDER_SLOTS = 2
_held = set()


class LaneBusy(RuntimeError):
    """Work could not start because a conflicting job holds the lock. Nothing ran."""


@contextmanager
def _exclusive(path, message):
    key = str(path)
    if key in _held:  # Re-entrant inside one process (a job's own lead-search step).
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LaneBusy(message) from None
        _held.add(key)
        try:
            yield
        finally:
            _held.discard(key)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _server_slot(database_path, wait):
    root = Path(os.environ.get("LEADZEN_WORKSPACE_ROOT") or Path(database_path).parent) / ".provider-slots"
    deadline = time.monotonic() + wait
    with ExitStack() as stack:
        # Acquire first; the job body runs outside this retry loop, so a failure
        # inside the job can never be mistaken for a busy slot and re-run.
        while True:
            acquired = False
            for index in range(PROVIDER_SLOTS):
                try:
                    stack.enter_context(_exclusive(root / f"slot-{index}.lock", ""))
                    acquired = True
                    break
                except LaneBusy:
                    continue
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise LaneBusy("The server is running other lead searches. Try again in a few minutes. Nothing was charged.")
            time.sleep(1)
        yield


@contextmanager
def provider_work(database_path, *, wait=30):
    """Hold this workspace's provider lane and one server-wide slot."""
    with _exclusive(Path(database_path).parent / "provider.lock",
                    "Another lead search or email lookup is still running. Try again when it finishes. Nothing was charged."):
        with _server_slot(database_path, wait):
            yield
