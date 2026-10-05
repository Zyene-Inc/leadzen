import json
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tarfile

import pytest

from leadzen.operations.release import GATES, REQUIRED_FILES, ReleaseError, add_artifact, capture, checks_template, file_digest, gate, verify


def fixture_source(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    for relative in REQUIRED_FILES:
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("synthetic source\n")
    return root


def test_dirty_source_captured_deterministically_with_migrations_and_no_private_files(tmp_path):
    root = fixture_source(tmp_path)
    (root / "leadzen/config/migrations/0020_synthetic.py").write_text("untracked migration")
    (root / "leadzen/private.key").write_text("never release")
    (root / "dashboard/.env.local").write_text("private fixture")
    (root / "dashboard/.env.example").write_text("LEADZEN_API_TOKEN=\n")
    (root / "unrelated.txt").write_text("preserve")
    one = capture(root, tmp_path / "one", "linux/amd64")
    two = capture(root, tmp_path / "two", "linux/amd64")
    assert one["source_sha256"] == two["source_sha256"]
    assert one["source_archive_sha256"] == two["source_archive_sha256"]
    files = {e["path"] for e in one["files"]}
    assert "leadzen/config/migrations/0020_synthetic.py" in files
    assert "dashboard/.env.example" in files
    assert "leadzen/private.key" not in files and "dashboard/.env.local" not in files
    assert (root / "unrelated.txt").read_text() == "preserve"
    assert verify(tmp_path / "one")["approval"] == "BLOCKED"


def test_missing_application_and_symlink_sources_fail_closed(tmp_path):
    root = fixture_source(tmp_path)
    (root / "leadzen/wsgi.py").unlink()
    with pytest.raises(ReleaseError):
        capture(root, tmp_path / "one", "linux/amd64")
    (root / "leadzen/wsgi.py").symlink_to(root / "pyproject.toml")
    with pytest.raises(ReleaseError):
        capture(root, tmp_path / "two", "linux/amd64")


def test_candidate_source_and_artifact_tamper_are_detected(tmp_path):
    root = fixture_source(tmp_path)
    candidate = tmp_path / "candidate"
    capture(root, candidate, "linux/amd64")
    artifact = tmp_path / "runtime.tar"
    artifact.write_bytes(b"synthetic artifact")
    add_artifact(candidate, artifact, "container-image")
    (candidate / "artifacts/runtime.tar").write_bytes(b"changed")
    with pytest.raises(ReleaseError):
        verify(candidate)
    (candidate / "artifacts/runtime.tar").write_bytes(b"synthetic artifact")
    (candidate / "source/leadzen/wsgi.py").write_text("changed")
    with pytest.raises(ReleaseError):
        verify(candidate)


def test_unmanifested_private_build_inputs_and_symlink_directories_are_rejected(tmp_path):
    root = fixture_source(tmp_path)
    candidate = tmp_path / "candidate"
    capture(root, candidate, "linux/amd64")
    private = candidate / "source/dashboard/.env.production"
    private.write_text("private fixture")
    with pytest.raises(ReleaseError):
        verify(candidate)
    private.unlink()
    (candidate / "source/leadzen/injected").symlink_to(root / "dashboard", target_is_directory=True)
    with pytest.raises(ReleaseError):
        verify(candidate)


def test_release_gate_requires_same_candidate_every_gate_and_artifact(tmp_path):
    root = fixture_source(tmp_path)
    candidate = tmp_path / "candidate"
    manifest = capture(root, candidate, "linux/amd64")
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps({"source_sha256": manifest["source_sha256"], "gates": {}}))
    assert gate(candidate, checks)["status"] == "BLOCKED"
    for index, kind in enumerate(["container-image", "backend-wheel", "dashboard-standalone"]):
        artifact = tmp_path / f"artifact{index}.tar"
        artifact.write_bytes(str(index).encode())
        add_artifact(candidate, artifact, kind)
    evidence = completed_evidence(candidate, tmp_path)
    evidence["gates"]["actual_recovery"]["status"] = "BLOCKED"
    checks.write_text(json.dumps(evidence))
    assert gate(candidate, checks)["not_passed"] == ["actual_recovery"]
    evidence["source_sha256"] = "other candidate"
    checks.write_text(json.dumps(evidence))
    with pytest.raises(ReleaseError):
        gate(candidate, checks)


def completed_candidate(tmp_path):
    root = fixture_source(tmp_path)
    candidate = tmp_path / "candidate"
    capture(root, candidate, "linux/amd64")
    for index, kind in enumerate(("container-image", "backend-wheel", "dashboard-standalone")):
        artifact = tmp_path / f"artifact{index}.tar"
        artifact.write_bytes(f"tested artifact {index}".encode())
        add_artifact(candidate, artifact, kind)
    return candidate


def completed_evidence(candidate, evidence_root):
    evidence = checks_template(candidate)
    report = evidence_root / "report.json"
    report.write_text('{"synthetic_check":"performed"}\n')
    for result in evidence["gates"].values():
        result["status"] = "PASS"
        result["evidence"] = "Synthetic fixture only; not production certification."
        result["attestation"]["evidence_files"] = [{"path": "report.json", "sha256": file_digest(report)}]
    return evidence


def test_only_current_bound_complete_attestations_allow_gate(tmp_path):
    candidate = completed_candidate(tmp_path)
    evidence = completed_evidence(candidate, tmp_path)
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps(evidence))
    result = gate(candidate, checks)
    assert result["status"] == "PASS"
    assert result["operator_attestations_are_independent_proof"] is False
    assert all(item["status"] == "BLOCKED" for item in checks_template(candidate)["gates"].values())


def test_legacy_bare_statuses_and_untested_artifact_addition_are_blocked(tmp_path):
    candidate = completed_candidate(tmp_path)
    checks = tmp_path / "checks.json"
    manifest = verify(candidate)
    checks.write_text(json.dumps({"source_sha256": manifest["source_sha256"],
        "gates": {name: {"status": "PASS"} for name in GATES}}))
    assert gate(candidate, checks)["status"] == "BLOCKED"
    checks.write_text(json.dumps(completed_evidence(candidate, tmp_path)))
    extra = tmp_path / "untested-sbom.json"
    extra.write_text("new untested artifact")
    add_artifact(candidate, extra, "sbom")
    result = gate(candidate, checks)
    assert result["status"] == "BLOCKED"
    assert "current-artifact-bound-evidence" in result["missing"]


@pytest.mark.parametrize("field,value", [("architecture", "linux/arm64"), ("source_archive_sha256", "0" * 64), ("artifacts", [])])
def test_mismatched_release_inventory_is_blocked(tmp_path, field, value):
    candidate = completed_candidate(tmp_path)
    evidence = completed_evidence(candidate, tmp_path)
    evidence[field] = value
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps(evidence))
    assert "current-artifact-bound-evidence" in gate(candidate, checks)["missing"]


@pytest.mark.parametrize("kind", ["expired", "future", "too-long", "no-zone", "no-files", "empty-file", "changed-file", "parent-path", "symlink", "wrong-source"])
def test_invalid_attestation_is_blocked(tmp_path, kind):
    candidate = completed_candidate(tmp_path)
    evidence = completed_evidence(candidate, tmp_path)
    result = evidence["gates"]["startup"]
    attestation = result["attestation"]
    now = datetime.now(timezone.utc)
    if kind == "expired":
        attestation.update(observed_at=(now - timedelta(hours=2)).isoformat(), expires_at=(now - timedelta(hours=1)).isoformat())
    elif kind == "future":
        attestation.update(observed_at=(now + timedelta(hours=1)).isoformat(), expires_at=(now + timedelta(hours=2)).isoformat())
    elif kind == "too-long":
        attestation["expires_at"] = (now + timedelta(days=2)).isoformat()
    elif kind == "no-zone":
        attestation["observed_at"] = now.replace(tzinfo=None).isoformat()
    elif kind == "no-files":
        attestation["evidence_files"] = []
    elif kind == "empty-file":
        empty = tmp_path / "empty.json"
        empty.touch()
        attestation["evidence_files"] = [{"path": empty.name, "sha256": file_digest(empty)}]
    elif kind == "changed-file":
        # Only this gate refers to a changed evidence file.
        altered = tmp_path / "changed.json"
        altered.write_text("before")
        attestation["evidence_files"] = [{"path": altered.name, "sha256": file_digest(altered)}]
        altered.write_text("after")
    elif kind == "parent-path":
        attestation["evidence_files"][0]["path"] = "../report.json"
    elif kind == "symlink":
        (tmp_path / "link.json").symlink_to(tmp_path / "report.json")
        attestation["evidence_files"][0]["path"] = "link.json"
    else:
        result["source_sha256"] = "0" * 64
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps(evidence))
    assert gate(candidate, checks, now=now)["invalid_attestations"] == ["startup"]


def test_duplicate_deployment_artifacts_source_mismatch_and_root_symlink_are_rejected(tmp_path):
    candidate = completed_candidate(tmp_path)
    replacement = tmp_path / "replacement.tar"
    replacement.write_bytes(b"untested replacement")
    with pytest.raises(ReleaseError):
        add_artifact(candidate, replacement, "container-image")
    manifest = json.loads((candidate / "manifest.json").read_text())
    manifest["artifacts"][0]["source_sha256"] = "0" * 64
    (candidate / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ReleaseError):
        verify(candidate)
    root = tmp_path / "checkout"
    (root / "pyproject.toml").unlink()
    (root / "pyproject.toml").symlink_to(root / "leadzen/wsgi.py")
    with pytest.raises(ReleaseError):
        capture(root, tmp_path / "symlinked", "linux/amd64")


def test_operator_can_only_tighten_evidence_horizon(tmp_path):
    candidate = completed_candidate(tmp_path)
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps(completed_evidence(candidate, tmp_path)))
    with pytest.raises(ReleaseError):
        gate(candidate, checks, max_age_hours=48)
    assert gate(candidate, checks, max_age_hours=1)["status"] == "BLOCKED"


def test_archive_cannot_diverge_from_tested_tree_by_refreshing_its_checksum(tmp_path):
    candidate = completed_candidate(tmp_path)
    manifest = verify(candidate)
    with tarfile.open(candidate / "source.tar", "w") as archive:
        for entry in manifest["files"]:
            content = (candidate / "source" / entry["path"]).read_bytes()
            if entry["path"] == "leadzen/wsgi.py":
                content = b"changed untested bytes\n"
            member = tarfile.TarInfo(entry["path"])
            member.mode = 0o755 if entry["executable"] else 0o644
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    manifest["source_archive_sha256"] = file_digest(candidate / "source.tar")
    (candidate / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ReleaseError):
        verify(candidate)


def test_checks_template_cli_is_blocked_and_never_overwrites(monkeypatch, tmp_path):
    from leadzen.operations.release import main

    candidate = completed_candidate(tmp_path)
    output = tmp_path / "new-checks.json"
    monkeypatch.setattr("sys.argv", ["release", "checks-template", str(candidate), "--output", str(output)])
    assert main() == 0
    original = output.read_bytes()
    assert {row["status"] for row in json.loads(original)["gates"].values()} == {"BLOCKED"}
    assert main() == 1
    assert output.read_bytes() == original
