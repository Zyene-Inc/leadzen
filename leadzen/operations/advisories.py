"""Keep full image findings visible and gate HIGH/CRITICAL risk decisions."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re


def _validate_report(report: dict, architecture: str, image_id: str,
                     now: datetime, max_age_hours: float) -> None:
    if not 0 < max_age_hours <= 24 or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Invalid advisory binding or evidence horizon")
    metadata = report["Metadata"]
    actual_arch = metadata["ImageConfig"]["architecture"]
    created = datetime.fromisoformat(report["CreatedAt"].replace("Z", "+00:00"))
    if (report.get("SchemaVersion") != 2 or report.get("ArtifactType") != "container_image"
            or metadata["ImageID"] != image_id or architecture != f"linux/{actual_arch}"
            or metadata["ImageConfig"].get("os") != "linux"
            or created.tzinfo is None or created.utcoffset() != timedelta(0)
            or not timedelta(0) <= now - created <= timedelta(hours=max_age_hours)):
        raise ValueError("Wrong or stale image advisory evidence")
    os_family = metadata["OS"]["Family"]
    if not os_family or not metadata["OS"]["Name"] or not isinstance(report["Results"], list):
        raise ValueError("Incomplete image advisory evidence")
    if any(not isinstance(item, dict) for item in report["Results"]):
        raise ValueError("Invalid scan result")
    os_scans = [item for item in report["Results"]
                if item.get("Class") == "os-pkgs" and item.get("Type") == os_family]
    if not os_scans or any(not isinstance(item.get("Packages"), list) or not item["Packages"] for item in os_scans):
        raise ValueError("OS package scanning evidence missing")
    if any(not isinstance(package, dict)
           or any(not isinstance(package.get(field), str) or not package[field] for field in ("Name", "Version"))
           for result in os_scans for package in result["Packages"]):
        raise ValueError("Invalid scanned package inventory")
    for result in report["Results"]:
        if not isinstance(result, dict) or not isinstance(result.get("Vulnerabilities", []) or [], list):
            raise ValueError("Invalid vulnerability evidence")
        for item in result.get("Vulnerabilities", []) or []:
            if (not isinstance(item, dict)
                    or any(not isinstance(item.get(name), str) or not item[name] for name in ("VulnerabilityID", "PkgName", "InstalledVersion"))
                    or item.get("Severity") not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}):
                raise ValueError("Invalid vulnerability evidence")


def assess(report: dict, decisions: dict, architecture: str, today: date | None = None,
           *, image_id: str, now: datetime | None = None, max_age_hours: float = 24) -> dict:
    now = now or datetime.now(timezone.utc)
    _validate_report(report, architecture, image_id, now, max_age_hours)
    if not isinstance(decisions, dict) or not isinstance(decisions.get("decisions"), list):
        raise ValueError("Invalid risk-decision evidence")
    today = today or now.date()
    unresolved, accepted, totals = [], [], {}
    for result in report.get("Results", []):
        for item in result.get("Vulnerabilities", []) or []:
            severity = item.get("Severity", "UNKNOWN")
            totals[severity] = totals.get(severity, 0) + 1
            if severity not in {"HIGH", "CRITICAL"}:
                continue
            key = {"id": item["VulnerabilityID"], "package": item["PkgName"],
                   "version": item["InstalledVersion"], "architecture": architecture}
            matches = [d for d in decisions["decisions"] if isinstance(d, dict) and all(d.get(k) == v for k, v in key.items())]
            valid = False
            for decision in matches:
                try:
                    valid = (date.fromisoformat(decision["expires"]) >= today
                        and decision.get("disposition") in {"not-affected", "accepted-risk"}
                        and all(isinstance(decision.get(field), str) and bool(decision[field].strip())
                                for field in ("reason", "evidence", "reviewer")))
                except (ValueError, KeyError, TypeError):
                    valid = False
                if valid:
                    break
            (accepted if valid else unresolved).append({**key, "severity": severity,
                "fixed_version_available": bool(item.get("FixedVersion"))})
    return {"status": "PASS" if not unresolved else "FAIL", "counts": totals,
            "unresolved": unresolved, "reviewed": accepted, "findings_hidden": False,
            "image_id": image_id, "architecture": architecture,
            "scan_created_at": report["CreatedAt"], "maximum_evidence_age_hours": max_age_hours,
            "scanner_is_exploitability_proof": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--architecture", choices=["linux/amd64", "linux/arm64"], required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--max-age-hours", type=float, default=24)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text())
        result = assess(report, json.loads(args.decisions.read_text()), args.architecture,
                        image_id=args.image_id, max_age_hours=args.max_age_hours)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "counts": result["counts"], "unresolved": len(result["unresolved"])}))
        return 0 if result["status"] == "PASS" else 1
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        print('{"status":"FAIL","reason":"Incomplete advisory evidence or invalid decision file"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
