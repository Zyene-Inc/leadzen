import os
from pathlib import Path
import subprocess
import sys


def test_clean_and_previous_release_migrations_preserve_data(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "tests/scenarios/production_migrations.py"), str(tmp_path / "disposable")],
        env={**os.environ, "PYTHONPATH": str(root)}, cwd=root,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "data preservation" in result.stdout and "Clean database migrations" in result.stdout
