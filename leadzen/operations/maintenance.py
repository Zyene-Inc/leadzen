"""Pause intake and scheduler dispatch while existing bounded workers drain."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from contextlib import contextmanager
import secrets

_request_lock = threading.Lock()
_request_count = 0
_process_nonce = secrets.token_hex(8)


def hold_path(control_db: Path | None = None) -> Path:
    database = control_db or Path(os.environ.get("LEADZEN_CONTROL_DB") or os.environ.get("LEADZEN_DB", ""))
    if not database.is_absolute():
        raise ValueError("Explicit absolute control database required")
    return database.parent / "operations" / "intake.hold"


def maintenance_active(control_db: Path | None = None) -> bool:
    try:
        path = hold_path(control_db)
        # Permission/symlink uncertainty fails closed; never follow a hold link.
        return path.is_symlink() or path.exists()
    except (ValueError, OSError):
        return os.environ.get("LEADZEN_ENV") == "production"


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def set_hold(control_db: Path) -> None:
    path = hold_path(control_db)
    if path.parent.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("Canonical nonsymlink storage required")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    info = path.parent.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Private runtime-owned operations directory required")
    # If this is the first hold, persist the newly created operations directory
    # as well as the hold entry; file fsync alone does not persist directory names.
    _sync_directory(path.parent.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write('{"schema_version":1,"intake":"held"}\n')
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def clear_hold(control_db: Path, reconciled: bool) -> None:
    if not reconciled:
        raise ValueError("Reconciliation confirmation required")
    path = hold_path(control_db)
    if path.is_symlink() or path.parent.is_symlink() or path.stat().st_uid != os.getuid():
        raise ValueError("Private runtime-owned regular hold required")
    path.unlink()
    _sync_directory(path.parent)


WORKER = re.compile(r"(?:\s|/)(?:leadzen\.(?:web_worker|chat_worker|autopilot_worker|mcp\.worker))(?:\s|$)|(?:-m\s+leadzen|/leadzen)\s+(?:run|find|send)(?:\s|$)|leadzen\.scheduler\s+[^\n]*--workspace(?:\s|=|$)")


def workers_running() -> int:
    result = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, text=True, timeout=5, check=True)
    # Raw process commands can contain credentials. Only the aggregate leaves this function.
    return sum(bool(WORKER.search(line)) for line in result.stdout.splitlines())


def scheduler_running(control_db: Path) -> bool:
    # A scheduler pass can be between employee children. Its advisory lock
    # closes that gap; draining must not stop its unit mid-pass.
    path = control_db.parent / "scheduler" / "send.lock"
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Canonical scheduler lock required")
    if not path.exists():
        return False
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return False
    finally:
        os.close(descriptor)


def requests_running(control_db: Path) -> int:
    directory = hold_path(control_db).parent / "requests"
    if directory.is_symlink():
        raise ValueError("Unexpected request counter path")
    if not directory.exists():
        return 0
    info = directory.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Private request counters required")
    total = 0
    for file in directory.iterdir():
        if not re.fullmatch(r"request-[0-9]+-[0-9a-f]{16}\.json", file.name) or file.is_symlink():
            raise ValueError("Unexpected request counter")
        info = file.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 1024:
            raise ValueError("Invalid request counter")
        data = json.loads(file.read_text())
        count = data.get("in_flight")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("Invalid request counter")
        # A crashed process leaves evidence. Do not silently erase potentially
        # ambiguous external work merely because its PID is no longer alive.
        total += count
    return total


def _publish_request_count():
    operations = hold_path().parent
    directory = operations / "requests"
    if any(p.is_symlink() for p in [directory, *directory.parents]):
        raise ValueError("Canonical runtime request counter directory required")
    operations.mkdir(mode=0o700, parents=True, exist_ok=True)
    if operations.stat().st_uid != os.getuid() or operations.stat().st_mode & 0o077:
        raise ValueError("Private runtime operations directory required")
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise ValueError("Private runtime request counter directory required")
    path = directory / f"request-{os.getpid()}-{_process_nonce}.json"
    if _request_count == 0:
        path.unlink(missing_ok=True)
    else:
        temporary = directory / (".pending-" + _process_nonce)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"in_flight": _request_count}, stream)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def track_request():
    global _request_count
    with _request_lock:
        _request_count += 1
        try:
            _publish_request_count()
        except BaseException:
            _request_count -= 1
            raise
    try:
        yield
    finally:
        with _request_lock:
            _request_count -= 1
            _publish_request_count()


def drain(control_db: Path, timeout: int = 120) -> bool:
    if not maintenance_active(control_db) or not 1 <= timeout <= 3600:
        raise ValueError("Hold and bounded drain timeout required")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if workers_running() == 0 and requests_running(control_db) == 0 and not scheduler_running(control_db):
            time.sleep(0.5)
            if workers_running() == 0 and requests_running(control_db) == 0 and not scheduler_running(control_db):
                return True
        time.sleep(0.5)
    return False


class MaintenanceIntake:
    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def held_response():
        from django.http import JsonResponse
        response = JsonResponse({"error": "Maintenance is in progress. Please try again shortly."}, status=503)
        response["Retry-After"] = "30"
        response["Cache-Control"] = "private, no-store, max-age=0"
        return response

    def __call__(self, request):
        if request.path not in {"/api/health", "/api/ready"} and maintenance_active():
            return self.held_response()
        if os.environ.get("LEADZEN_ENV") != "production" or request.path in {"/api/health", "/api/ready"}:
            return self.get_response(request)
        tracker = track_request()
        opened = False

        def finish():
            nonlocal opened
            if opened:
                opened = False
                tracker.__exit__(None, None, None)

        try:
            tracker.__enter__()
            opened = True
            # Publishing first makes accepted requests visible to drain; this
            # second check rejects a request paused across the initial hold check.
            if maintenance_active():
                finish()
                return self.held_response()
            response = self.get_response(request)
            if getattr(response, "streaming", False):
                content = response.streaming_content
                if response.is_async:
                    async def stream():
                        try:
                            async for chunk in content:
                                yield chunk
                        finally:
                            finish()
                else:
                    def stream():
                        try:
                            yield from content
                        finally:
                            finish()
                response.streaming_content = stream()
                response._resource_closers.append(finish)
            else:
                finish()
            return response
        except (OSError, ValueError):
            finish()
            from django.http import JsonResponse
            response = JsonResponse({"error": "Service readiness cannot be verified. Please try again shortly."}, status=503)
            response["Cache-Control"] = "private, no-store, max-age=0"
            response["Retry-After"] = "30"
            return response
        except BaseException:
            finish()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["hold", "drain", "release"])
    parser.add_argument("--control-db", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--reconciled", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "hold":
            if not maintenance_active(args.control_db):
                set_hold(args.control_db)
        elif args.command == "release":
            clear_hold(args.control_db, args.reconciled)
        elif not drain(args.control_db, args.timeout):
            print('{"status":"BLOCKED","reason":"Workers still active; intake remains held. Do not kill or replay ambiguous external work."}')
            return 2
        print(json.dumps({"status": "PASS", "intake_held": maintenance_active(args.control_db)}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print('{"status":"FAIL","reason":"Maintenance state cannot be safely verified; no worker was killed."}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
