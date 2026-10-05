"""Isolate Django startup before pytest-django creates its actual test database.

The production registry can upgrade legacy tables while importing settings. Even
an inherited --db/environment path must never select user data during tests.
"""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

_test_registry = TemporaryDirectory(prefix="leadzen-pytest-")
_test_root = Path(_test_registry.name).resolve()
os.environ["LEADZEN_DB"] = str(_test_root / "registry.sqlite3")
os.environ["LEADZEN_WORKSPACE_ROOT"] = str(_test_root / "workspaces")
os.environ.pop("LEADZEN_CONTROL_DB", None)
os.environ["LEADZEN_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1,[::1]"

from leadzen.settings import *  # noqa: E402,F403 — same application, private startup paths

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1", "[::1]"]
