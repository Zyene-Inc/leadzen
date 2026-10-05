"""Bind fixture identity to the current production source, without reading secrets."""
from pathlib import Path
import hashlib


def candidate_sha256(repository: Path) -> str:
    paths = []
    for directory in ["leadzen", "cold_outreach"]:
        paths.extend(path for path in (repository / directory).rglob("*.py") if "__pycache__" not in path.parts)
    for directory in ["app", "components", "lib", "public"]:
        paths.extend(path for path in (repository / "dashboard" / directory).rglob("*") if path.is_file())
    for name in ["dashboard/proxy.ts", "dashboard/next.config.ts", "dashboard/package.json", "dashboard/package-lock.json", "pyproject.toml", "requirements-production.lock"]:
        path = repository / name
        if path.is_file():
            paths.append(path)
    result = hashlib.sha256()
    for path in sorted(set(paths)):
        result.update(str(path.relative_to(repository)).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return result.hexdigest()
