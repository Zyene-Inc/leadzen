from datetime import date, datetime, timedelta, timezone
import json

import pytest

from leadzen.operations.advisories import assess

IMAGE_ID = "sha256:" + "1" * 64
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def scanner_report(vulnerabilities):
    return {"SchemaVersion": 2, "ArtifactType": "container_image", "CreatedAt": NOW.isoformat(),
        "Metadata": {"ImageID": IMAGE_ID, "ImageConfig": {"architecture": "amd64", "os": "linux"},
                     "OS": {"Family": "debian", "Name": "13"}},
        "Results": [{"Class": "os-pkgs", "Type": "debian", "Packages": [{"Name": "synthetic", "Version": "1"}],
                     "Vulnerabilities": vulnerabilities}]}


def test_unfixed_and_fixable_high_are_both_visible_and_gate_release():
    report = scanner_report([
        {"VulnerabilityID": "CVE-synthetic-one", "PkgName": "sqlite", "InstalledVersion": "1", "Severity": "HIGH"},
        {"VulnerabilityID": "CVE-synthetic-two", "PkgName": "zlib", "InstalledVersion": "2", "Severity": "CRITICAL", "FixedVersion": "3"},
    ])
    result = assess(report, {"decisions": []}, "linux/amd64", image_id=IMAGE_ID, now=NOW)
    assert result["status"] == "FAIL" and len(result["unresolved"]) == 2
    assert result["counts"] == {"HIGH": 1, "CRITICAL": 1}


def test_risk_decisions_match_exact_package_version_architecture_and_expiry():
    report = scanner_report([
        {"VulnerabilityID": "CVE-synthetic", "PkgName": "pkg", "InstalledVersion": "1", "Severity": "HIGH"}])
    decision = {"id": "CVE-synthetic", "package": "pkg", "version": "1", "architecture": "linux/amd64",
        "expires": "2026-11-01", "disposition": "not-affected", "reviewer": "operator", "evidence": "primary advisory", "reason": "specific path absent"}
    assert assess(report, {"decisions": [decision]}, "linux/amd64", date(2026, 10, 4), image_id=IMAGE_ID, now=NOW)["status"] == "PASS"
    # A risk decision for another architecture cannot waive this image.
    decision["architecture"] = "linux/arm64"
    assert assess(report, {"decisions": [decision]}, "linux/amd64", date(2026, 10, 4), image_id=IMAGE_ID, now=NOW)["status"] == "FAIL"
    decision["architecture"] = "linux/amd64"
    assert assess(report, {"decisions": [decision]}, "linux/amd64", date(2026, 12, 4), image_id=IMAGE_ID, now=NOW)["status"] == "FAIL"


@pytest.mark.parametrize("kind", ["empty-results", "empty-metadata", "wrong-image", "wrong-architecture", "no-packages", "malformed-package", "malformed-result", "stale", "future", "no-zone", "wrong-artifact"])
def test_incomplete_mismatched_or_stale_scan_cannot_pass(kind):
    report = scanner_report([])
    if kind == "empty-results":
        report["Results"] = []
    elif kind == "empty-metadata":
        report["Metadata"] = {"arbitrary": True}
    elif kind == "wrong-image":
        report["Metadata"]["ImageID"] = "sha256:" + "2" * 64
    elif kind == "wrong-architecture":
        report["Metadata"]["ImageConfig"]["architecture"] = "arm64"
    elif kind == "no-packages":
        report["Results"][0]["Packages"] = []
    elif kind == "malformed-package":
        report["Results"][0]["Packages"] = [{}]
    elif kind == "malformed-result":
        report["Results"] = [None]
    elif kind == "stale":
        report["CreatedAt"] = (NOW - timedelta(hours=25)).isoformat()
    elif kind == "future":
        report["CreatedAt"] = (NOW + timedelta(hours=1)).isoformat()
    elif kind == "no-zone":
        report["CreatedAt"] = NOW.replace(tzinfo=None).isoformat()
    else:
        report["ArtifactType"] = "filesystem"
    with pytest.raises((ValueError, KeyError)):
        assess(report, {"decisions": []}, "linux/amd64", image_id=IMAGE_ID, now=NOW)


def test_complete_clean_image_report_can_pass_and_carries_binding():
    result = assess(scanner_report([]), {"decisions": []}, "linux/amd64", image_id=IMAGE_ID, now=NOW)
    assert result["status"] == "PASS"
    assert result["image_id"] == IMAGE_ID and result["architecture"] == "linux/amd64"
    assert result["scan_created_at"] == NOW.isoformat()


def test_blank_risk_review_is_not_an_acceptance():
    report = scanner_report([{"VulnerabilityID": "CVE-synthetic", "PkgName": "pkg", "InstalledVersion": "1", "Severity": "HIGH"}])
    decision = {"id": "CVE-synthetic", "package": "pkg", "version": "1", "architecture": "linux/amd64",
        "expires": "2026-11-01", "disposition": "accepted-risk", "reviewer": " ", "evidence": "primary advisory", "reason": "reviewed path"}
    assert assess(report, {"decisions": [decision]}, "linux/amd64", image_id=IMAGE_ID, now=NOW)["status"] == "FAIL"


def test_cli_rejects_empty_report_and_preserves_prior_evidence(monkeypatch, tmp_path, capsys):
    from leadzen.operations.advisories import main

    report = tmp_path / "incomplete.json"
    report.write_text(json.dumps({"Results": [], "Metadata": {"arbitrary": True}}))
    decisions = tmp_path / "decisions.json"
    decisions.write_text('{"decisions":[]}')
    output = tmp_path / "result.json"
    output.write_text("previous evidence")
    monkeypatch.setattr("sys.argv", ["advisories", str(report), "--architecture", "linux/amd64",
        "--image-id", IMAGE_ID, "--decisions", str(decisions), "--output", str(output)])
    assert main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
    assert output.read_text() == "previous evidence"
