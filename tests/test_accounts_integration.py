"""Real files and router, in a separate process so pytest's DB blocker isn't bypassed."""
import os
from pathlib import Path
import subprocess
import sys


def test_two_employee_workspaces_and_worker_revocation(tmp_path):
    root = Path(__file__).resolve().parent.parent
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OUTSEND_", "OPENOUTFIND_", "LEADZEN_"))}
    env.update(LEADZEN_DB=str(tmp_path / "control.sqlite3"), LEADZEN_WORKSPACE_ROOT=str(tmp_path / "workspaces"), LEADZEN_ALLOWED_HOSTS="testserver,localhost,127.0.0.1,[::1]", PYTHONPATH=str(root), DJANGO_SETTINGS_MODULE="leadzen.settings")
    result = subprocess.run([sys.executable, str(root / "tests/scenarios/accounts.py")], env=env, cwd=root, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-6000:]
    assert "isolation and revocation verified" in result.stdout
