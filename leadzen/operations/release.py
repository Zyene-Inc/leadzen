"""Capture the intended working tree without Git resets or private runtime files.

This command prepares local artifacts only. It neither deploys nor promotes.
The source digest covers relative names, executable bits and every included byte.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

ROOT_FILES = {
    "README.md", "LICENCE.md", "THIRD_PARTY_NOTICES.md",
    "LEGAL_NOTICE.md", "PRIVACY_NOTICE.md", "pyproject.toml", "requirements-production.lock",
    "requirements-build.in", "requirements-build.lock",
    "pytest.ini", "manage.py", "Makefile", "local.yml", ".dockerignore", ".gitignore",
}
SOURCE_DIRS = {"leadzen", "dashboard", "compose", "tests", "skills", ".github", ".claude-plugin"}
DOC_FILES = {"production-preflight.md", "production-recovery.md", "production-monitoring.md",
             "production-release.md", "production-environment.md", "production-secrets.md",
             "production-browser-verification.md", "production-image-risk-decisions.json"}
DOC_FILES.update({"production-capacity.md", "production-integrations.md"})
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", ".next", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".cache", ".vercel", "coverage", "htmlcov", "dist",
    "build", "data", "media", "backups", "test-results", "playwright-report",
}
PRIVATE_SUFFIXES = (".db", ".db-wal", ".db-shm", ".key", ".pem", ".p12", ".log", ".bak", ".backup")
REQUIRED_FILES = {
    "pyproject.toml", "requirements-production.lock", "requirements-build.lock", "leadzen/wsgi.py",
    "leadzen/config/migrations/__init__.py", "leadzen/accounts/migrations/__init__.py",
    "dashboard/package.json", "dashboard/package-lock.json", "compose/leadzen/Dockerfile",
}
GATES = {
    "preflight", "secret_current", "credential_disposition", "backend_tests", "frontend_tests",
    "typecheck", "dependency_audit", "image_advisories", "production_build", "migrations",
    "startup", "browser", "actual_recovery", "alert_delivery", "target_capacity",
    "enabled_integrations", "external_release_controls",
}
DEPLOYMENT_KINDS = {"backend-wheel", "dashboard-standalone", "container-image"}
MAX_EVIDENCE_HOURS = 24


class ReleaseError(ValueError):
    """Messages intentionally exclude file contents and exception details."""


def _private(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".env.example") or name == ".env.example":
        return False
    return (name.startswith(".env") or ".env." in name or name.endswith((".env", *PRIVATE_SUFFIXES))
            or ".sqlite" in name or name.endswith((".pyc", ".pyo", ".tsbuildinfo"))
            or name.startswith(".coverage") or name == ".ds_store" or ".egg-info" in name
            or name in {"admin-login.txt", "credentials.json", "service-account.json"})


def inputs(root: Path) -> list[Path]:
    result = []
    for path in root.iterdir():
        if path.name in ROOT_FILES and path.is_file():
            if path.is_symlink():
                raise ReleaseError("Symlink root source file refused")
            result.append(path)
        elif path.name in SOURCE_DIRS or path.name == "docs":
            if path.is_symlink():
                raise ReleaseError("Symlink source directory refused")
            for directory, dirs, files in os.walk(path, followlinks=False):
                for name in dirs:
                    if (Path(directory) / name).is_symlink() and name not in SKIP_DIRS:
                        raise ReleaseError("Symlink source directory refused")
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info"))
                for name in sorted(files):
                    candidate = Path(directory) / name
                    if _private(candidate):
                        continue
                    relative = candidate.relative_to(root)
                    # Historical evidence, screenshots and machine-local locators do not deploy.
                    if path.name == "docs" and name not in DOC_FILES:
                        continue
                    if str(relative).startswith("tests/fixtures/pages/"):
                        continue
                    if candidate.is_symlink() or not candidate.is_file():
                        raise ReleaseError("Nonregular source file refused")
                    result.append(candidate)
    result = sorted(set(result), key=lambda p: p.relative_to(root).as_posix())
    if not REQUIRED_FILES.issubset({p.relative_to(root).as_posix() for p in result}):
        raise ReleaseError("Required application, migration, or dependency inputs missing")
    return result


def digest_entries(entries: list[dict]) -> str:
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(path: Path, root: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "sha256": file_digest(path),
            "bytes": path.stat().st_size, "executable": bool(path.stat().st_mode & stat.S_IXUSR)}


def capture(root: Path, output: Path, architecture: str) -> dict:
    root = root.resolve()
    output = output.resolve()
    if output.exists() or output.is_relative_to(root) or output.parent.is_symlink():
        raise ReleaseError("Use a new output directory outside the checkout")
    if architecture not in {"linux/amd64", "linux/arm64"}:
        raise ReleaseError("Explicit supported target architecture required")
    selected = inputs(root)
    before = [_entry(p, root) for p in selected]
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".leadzen-capture-", dir=output.parent))
    staging.chmod(0o700)
    try:
        tree = staging / "source"
        tree.mkdir(mode=0o700)
        for source in selected:
            destination = tree / source.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination, follow_symlinks=False)
            destination.chmod(0o755 if source.stat().st_mode & stat.S_IXUSR else 0o644)
        copied = [_entry(tree / item["path"], tree) for item in before]
        after_inputs = inputs(root)
        if before != copied or before != [_entry(p, root) for p in after_inputs]:
            raise ReleaseError("Source changed during capture; retry after edits finish")
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True)
        tracked_names = set(tracked.stdout.decode().split("\0")) if tracked.returncode == 0 else set()
        manifest = {"schema_version": 1, "source_sha256": digest_entries(copied), "architecture": architecture,
                    "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
                    "git_revision_is_complete_release": False,
                    "included_untracked_files": sum(e["path"] not in tracked_names for e in copied),
                    "files": copied, "locks": {e["path"]: e["sha256"] for e in copied
                    if e["path"] in {"requirements-production.lock", "requirements-build.lock", "dashboard/package-lock.json"}},
                    "artifacts": [], "approval": "BLOCKED"}
        archive = staging / "source.tar"
        with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as tar:
            for entry in copied:
                file = tree / entry["path"]
                info = tar.gettarinfo(str(file), arcname=entry["path"])
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                with file.open("rb") as stream:
                    tar.addfile(info, stream)
        manifest["source_archive_sha256"] = file_digest(archive)
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        os.rename(staging, output)
        return manifest
    except BaseException:
        shutil.rmtree(staging)
        raise


def verify(candidate: Path) -> dict:
    manifest = json.loads((candidate / "manifest.json").read_text())
    if manifest.get("architecture") not in {"linux/amd64", "linux/arm64"}:
        raise ReleaseError("Unsupported candidate architecture")
    tree = candidate / "source"
    # Builds may add caches and dependency directories, but cannot add source or
    # private environment inputs after the tested snapshot was captured.
    expected = {e["path"] for e in manifest["files"]}
    if len(expected) != len(manifest["files"]) or not REQUIRED_FILES.issubset(expected):
        raise ReleaseError("Incomplete or duplicate candidate source inventory")
    for directory, dirs, files in os.walk(tree, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).is_symlink() and name not in SKIP_DIRS:
                raise ReleaseError("Candidate contains a symlink directory")
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.endswith(".egg-info")]
        for name in files:
            path = Path(directory) / name
            if name.endswith((".pyc", ".pyo", ".tsbuildinfo")) or name.startswith(".coverage"):
                continue
            if path.relative_to(tree).as_posix() not in expected:
                raise ReleaseError("Candidate contains unmanifested source or private input")
    entries = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        file = tree / relative
        if relative.is_absolute() or ".." in relative.parts or file.is_symlink() or not file.is_file():
            raise ReleaseError("Unsafe or missing candidate file")
        entries.append(_entry(file, tree))
    if entries != manifest["files"] or digest_entries(entries) != manifest["source_sha256"]:
        raise ReleaseError("Candidate source checksum mismatch")
    if file_digest(candidate / "source.tar") != manifest["source_archive_sha256"]:
        raise ReleaseError("Candidate archive checksum mismatch")
    # The tree is tested while operators may transport the archive. Verify their
    # contents correspond, even if an archive hash was accidentally refreshed.
    with tarfile.open(candidate / "source.tar", "r") as archive:
        members = archive.getmembers()
        if len(members) != len(entries) or [member.name for member in members] != [item["path"] for item in entries]:
            raise ReleaseError("Candidate archive source inventory mismatch")
        for member, entry in zip(members, entries):
            if not member.isfile() or member.size != entry["bytes"] or bool(member.mode & stat.S_IXUSR) != entry["executable"]:
                raise ReleaseError("Unsafe or inconsistent candidate archive member")
            digest = hashlib.sha256()
            with archive.extractfile(member) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ReleaseError("Candidate archive bytes differ from tested source")
    kinds = set()
    for artifact in manifest["artifacts"]:
        kind = artifact["kind"]
        if artifact.get("source_sha256") != manifest["source_sha256"]:
            raise ReleaseError("Artifact belongs to a different source candidate")
        if kind in DEPLOYMENT_KINDS and kind in kinds:
            raise ReleaseError("Ambiguous deployment artifact kind")
        kinds.add(kind)
        file = candidate / "artifacts" / artifact["name"]
        if Path(artifact["name"]).name != artifact["name"] or file.is_symlink() or not file.is_file():
            raise ReleaseError("Unsafe or missing build artifact")
        if file.stat().st_size != artifact["bytes"] or file_digest(file) != artifact["sha256"]:
            raise ReleaseError("Build artifact checksum mismatch")
    return manifest


def add_artifact(candidate: Path, artifact: Path, kind: str) -> dict:
    manifest = verify(candidate)
    if kind in DEPLOYMENT_KINDS and any(item["kind"] == kind for item in manifest["artifacts"]):
        raise ReleaseError("Deployment artifact already fixed; capture a new candidate")
    destination = candidate / "artifacts" / artifact.name
    if destination.exists() or artifact.is_symlink() or not artifact.is_file() or _private(artifact):
        raise ReleaseError("Use a new regular nonprivate build artifact")
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    shutil.copyfile(artifact, destination)
    destination.chmod(0o600)
    manifest["artifacts"].append({"name": artifact.name, "kind": kind, "bytes": destination.stat().st_size,
        "sha256": file_digest(destination), "source_sha256": manifest["source_sha256"]})
    manifest["approval"] = "BLOCKED"
    (candidate / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamp required")
    return parsed


def _attestation_valid(value: dict, source: str, root: Path, now: datetime,
                       max_age_hours: float) -> bool:
    """Check operator attestations without treating them as independent proof."""
    try:
        if value.get("source_sha256") != source or not isinstance(value.get("evidence"), str) or not value["evidence"].strip():
            return False
        attestation = value["attestation"]
        observed = _utc_timestamp(attestation["observed_at"])
        expires = _utc_timestamp(attestation["expires_at"])
        if not observed <= now < expires or not timedelta(0) < expires - observed <= timedelta(hours=max_age_hours):
            return False
        files = attestation["evidence_files"]
        if not isinstance(files, list) or not 1 <= len(files) <= 64:
            return False
        seen = set()
        for item in files:
            relative = Path(item["path"])
            if relative.is_absolute() or not relative.parts or ".." in relative.parts or item["path"] in seen:
                return False
            seen.add(item["path"])
            path = root / relative
            # resolve() alone would permit a symlink back into this root.
            for parent in (path, *path.parents):
                if parent == root:
                    break
                if parent.is_symlink():
                    return False
            if (not path.is_file() or path.stat().st_size == 0 or not path.resolve().is_relative_to(root)
                    or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
                return False
            if file_digest(path) != item["sha256"]:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def checks_template(candidate: Path, hours: float = MAX_EVIDENCE_HOURS) -> dict:
    if not 0 < hours <= MAX_EVIDENCE_HOURS:
        raise ReleaseError("Evidence validity must be positive and at most 24 hours")
    manifest = verify(candidate)
    now = datetime.now(timezone.utc)
    return {"schema_version": 2, "source_sha256": manifest["source_sha256"],
            "source_archive_sha256": manifest["source_archive_sha256"],
            "architecture": manifest["architecture"], "artifacts": manifest["artifacts"],
            "gates": {name: {"status": "BLOCKED", "source_sha256": manifest["source_sha256"],
                "evidence": "Replace with the observed check and its limitations; never infer PASS.",
                "attestation": {"observed_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=hours)).isoformat(), "evidence_files": []}}
                for name in sorted(GATES)}}


def gate(candidate: Path, checks: Path, *, now: datetime | None = None,
         max_age_hours: float = MAX_EVIDENCE_HOURS) -> dict:
    manifest = verify(candidate)
    if not 0 < max_age_hours <= MAX_EVIDENCE_HOURS:
        raise ReleaseError("Evidence horizon may only tighten the 24-hour limit")
    now = now or datetime.now(timezone.utc)
    if checks.is_symlink() or not checks.is_file():
        raise ReleaseError("Regular release evidence file required")
    evidence = json.loads(checks.read_text())
    if evidence.get("source_sha256") != manifest["source_sha256"]:
        raise ReleaseError("Check evidence belongs to a different source candidate")
    results = evidence.get("gates", {})
    if not isinstance(results, dict) or any(not isinstance(value, dict) or value.get("status") not in {"PASS", "FAIL", "BLOCKED"} for value in results.values()):
        raise ReleaseError("Unknown check status")
    missing = sorted(GATES - results.keys())
    failed = sorted(k for k in GATES & results.keys() if results[k]["status"] != "PASS")
    binding_valid = (evidence.get("schema_version") == 2
        and evidence.get("source_archive_sha256") == manifest["source_archive_sha256"]
        and evidence.get("architecture") == manifest["architecture"]
        and evidence.get("artifacts") == manifest["artifacts"])
    if not binding_valid:
        missing.append("current-artifact-bound-evidence")
    invalid = sorted(k for k in GATES & results.keys() if results[k]["status"] == "PASS"
        and not _attestation_valid(results[k], manifest["source_sha256"], checks.parent.resolve(), now, max_age_hours))
    failed = sorted(set(failed) | set(invalid))
    if not DEPLOYMENT_KINDS.issubset({a["kind"] for a in manifest["artifacts"]}):
        missing.append("deployment-artifacts")
    return {"status": "PASS" if not missing and not failed else "BLOCKED", "missing": missing,
            "not_passed": failed, "invalid_attestations": invalid,
            "source_sha256": manifest["source_sha256"],
            "operator_attestations_are_independent_proof": False,
            "automatic_deployment": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("capture")
    create.add_argument("--source", type=Path, default=Path.cwd())
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--architecture", required=True)
    for name in ("verify", "artifact", "gate", "checks-template"):
        item = commands.add_parser(name)
        item.add_argument("candidate", type=Path)
        if name == "artifact":
            item.add_argument("file", type=Path)
            item.add_argument("--kind", required=True)
        if name == "gate":
            item.add_argument("--checks", type=Path, required=True)
            item.add_argument("--max-age-hours", type=float, default=MAX_EVIDENCE_HOURS)
        if name == "checks-template":
            item.add_argument("--output", type=Path, required=True)
            item.add_argument("--valid-hours", type=float, default=MAX_EVIDENCE_HOURS)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            result = capture(args.source, args.output, args.architecture)
        elif args.command == "artifact":
            result = add_artifact(args.candidate, args.file, args.kind)
        elif args.command == "gate":
            result = gate(args.candidate, args.checks, max_age_hours=args.max_age_hours)
        elif args.command == "checks-template":
            result = checks_template(args.candidate, args.valid_hours)
            # Never overwrite completed or historical release evidence.
            with args.output.open("x") as stream:
                stream.write(json.dumps(result, indent=2) + "\n")
        else:
            result = verify(args.candidate)
        print(json.dumps({k: result[k] for k in ("status", "source_sha256", "architecture", "missing", "not_passed") if k in result}))
        return 0 if result.get("status", "PASS") == "PASS" else 2
    except (ReleaseError, OSError, ValueError, KeyError, TypeError, AttributeError, tarfile.TarError):
        print(json.dumps({"status": "FAIL", "reason": "Candidate validation failed; inspect source completeness, paths, and checksums privately"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
