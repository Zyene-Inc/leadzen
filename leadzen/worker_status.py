"""How a background workspace pass tells its dispatcher what happened.

A pass exits 0 when it ran, BUSY_EXIT when another job held the workspace (a Chat
run, a send or a reply check) so it should simply run on the next pass, and 1 on a
real failure. On a failure it prints only the error's class name, never its message,
so the dispatcher can log where to look without exposing settings or contacts.
"""
import re
import sys

BUSY_EXIT = 75  # EX_TEMPFAIL
_MARKER = "LEADZEN_WORKER_ERROR="
_REPORTED = re.compile(r"^" + _MARKER + r"([A-Za-z_][A-Za-z0-9_]{0,79})$", re.M)


class DatabaseBusy(RuntimeError):
    """Another LeadZen job holds this workspace's send lock right now."""


def error_name(exc):
    """The class name of the deepest cause: safe to show, and it tells a reader where to look."""
    seen = set()
    while id(exc) not in seen and (exc.__cause__ or exc.__context__) is not None:
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return type(exc).__name__


def run_pass(work):
    """Run one workspace pass in its child process and exit with its status."""
    try:
        work()
    except DatabaseBusy:
        raise SystemExit(BUSY_EXIT)
    except Exception as exc:
        print(_MARKER + error_name(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)


def reported_error(stream):
    """The error class name a finished pass printed to its stderr file, or ""."""
    if stream is None:
        return ""
    try:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 4096))
        found = _REPORTED.findall(stream.read().decode("utf-8", "replace"))
    except (OSError, ValueError):
        return ""
    return found[-1] if found else ""
