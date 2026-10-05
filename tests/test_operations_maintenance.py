import pytest

from leadzen.operations.maintenance import WORKER, clear_hold, drain, maintenance_active, requests_running, set_hold, track_request


def test_hold_blocks_api_and_mcp_keeps_private_health_and_preserves_headers(client, tmp_path, monkeypatch):
    database = tmp_path / "control.sqlite3"
    monkeypatch.setenv("LEADZEN_CONTROL_DB", str(database))
    set_hold(database)
    for path in ["/api/auth/login", "/api/contacts", "/mcp", "/oauth/token"]:
        response = client.post(path)
        assert response.status_code == 503
        assert response["Retry-After"] == "30" and "no-store" in response["Cache-Control"]
        assert response["X-Frame-Options"] == "DENY" and response["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/health").status_code == 401
    with pytest.raises(ValueError):
        clear_hold(database, False)
    assert maintenance_active(database)
    clear_hold(database, True)
    assert not maintenance_active(database)


def test_worker_drain_requires_hold_and_never_kills_workers(tmp_path, monkeypatch):
    database = tmp_path / "control.sqlite3"
    with pytest.raises(ValueError):
        drain(database, 1)
    set_hold(database)
    monkeypatch.setattr("leadzen.operations.maintenance.workers_running", lambda: 1)
    assert not drain(database, 1)
    assert maintenance_active(database)
    monkeypatch.setattr("leadzen.operations.maintenance.workers_running", lambda: 0)
    assert drain(database, 1)


def test_hold_refuses_symlink_private_directory(tmp_path):
    (tmp_path / "operations").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        set_hold(tmp_path / "control.sqlite3")


def test_hold_creation_and_release_fsync_directory_entries(tmp_path, monkeypatch):
    import os
    import stat
    synced = []
    actual_fsync = os.fsync
    def observe(descriptor):
        synced.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
        actual_fsync(descriptor)
    monkeypatch.setattr(os, "fsync", observe)
    database = tmp_path / "control.sqlite3"
    set_hold(database)
    assert synced[-2:] == ["file", "directory"]
    clear_hold(database, True)
    assert synced[-1] == "directory" and synced.count("directory") >= 2


def test_inflight_requests_are_visible_and_exception_cleanup_preserves_drain(tmp_path, monkeypatch):
    database = tmp_path / "control.sqlite3"
    monkeypatch.setenv("LEADZEN_CONTROL_DB", str(database))
    with pytest.raises(RuntimeError):
        with track_request():
            assert requests_running(database) == 1
            with track_request():
                assert requests_running(database) == 2
            assert requests_running(database) == 1
            raise RuntimeError("synthetic internal failure")
    assert requests_running(database) == 0
    assert WORKER.search("123 python -m leadzen.scheduler --workspace fixture")
    assert WORKER.search("123 python -m leadzen.scheduler --workspace")
    assert not WORKER.search("123 python -m leadzen.scheduler --loop")


def test_request_racing_hold_is_rejected_after_publishing_counter(tmp_path, monkeypatch):
    from django.http import JsonResponse
    from django.test import RequestFactory
    from leadzen.operations.maintenance import MaintenanceIntake
    database = tmp_path / "control.sqlite3"
    monkeypatch.setenv("LEADZEN_CONTROL_DB", str(database))
    monkeypatch.setenv("LEADZEN_ENV", "production")
    checks = iter([False, True])
    monkeypatch.setattr("leadzen.operations.maintenance.maintenance_active", lambda *_: next(checks))
    handled = []
    middleware = MaintenanceIntake(lambda _: handled.append(True) or JsonResponse({"unexpected": True}))
    response = middleware(RequestFactory().post("/api/contacts"))
    assert response.status_code == 503 and handled == []
    assert response["Retry-After"] == "30" and "no-store" in response["Cache-Control"]
    assert requests_running(database) == 0


def test_scheduler_pass_lock_blocks_drain_between_employee_children(tmp_path, monkeypatch):
    import fcntl
    from leadzen.operations.maintenance import scheduler_running
    database = tmp_path / "control.sqlite3"
    set_hold(database)
    monkeypatch.setattr("leadzen.operations.maintenance.workers_running", lambda: 0)
    folder = tmp_path / "scheduler"
    folder.mkdir(mode=0o700)
    lock = folder / "send.lock"
    with lock.open("w") as owner:
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert scheduler_running(database)
        assert not drain(database, 1)
        assert maintenance_active(database)
    assert not scheduler_running(database)
    assert drain(database, 1)


@pytest.mark.django_db
def test_streaming_request_keeps_drain_hold_until_complete_or_closed(tmp_path, monkeypatch):
    from django.http import StreamingHttpResponse
    from django.test import RequestFactory
    from leadzen.operations.maintenance import MaintenanceIntake
    database = tmp_path / "control.sqlite3"
    monkeypatch.setenv("LEADZEN_CONTROL_DB", str(database))
    monkeypatch.setenv("LEADZEN_ENV", "production")
    middleware = MaintenanceIntake(lambda _: StreamingHttpResponse(iter([b"one", b"two"])))
    response = middleware(RequestFactory().get("/api/chat/stream"))
    assert requests_running(database) == 1
    assert list(response.streaming_content) == [b"one", b"two"]
    assert requests_running(database) == 0
    response.close()
    assert requests_running(database) == 0
    response = middleware(RequestFactory().get("/api/chat/stream"))
    assert requests_running(database) == 1
    response.close()
    assert requests_running(database) == 0
