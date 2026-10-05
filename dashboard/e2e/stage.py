"""Launch a fresh provider-disabled HTTPS candidate; --test runs the CI browser gate.

This command intentionally publishes disposable synthetic data to a temporary free
Quick Tunnel. Explicit authorization is required before invoking it. No DNS,
system certificate trust, cloud project or production database is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

from candidate import candidate_sha256

VERSION = "2026.9.3"
DOWNLOADS = {
    ("Linux", "x86_64"): ("cloudflared-linux-amd64", "77e26d8d900e0b8469f416239d14b5f296525fdf79fee6f511ef55609e3fbac2"),
    ("Darwin", "arm64"): ("cloudflared-darwin-arm64.tgz", "587c2cfb1c230fe36c7fa7727da78be459dae028cabe8c001291999350f07095"),
    ("Darwin", "x86_64"): ("cloudflared-darwin-amd64.tgz", "d1155d0837487f261183b15c1eab6c4ebcad9dc49b94675f1524c3564cea3977"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-public-synthetic-fixture", action="store_true", required=True)
    parser.add_argument("--test", action="store_true", help="Run Playwright in CI/user-controlled runner; otherwise leave the candidate available for browser inspection")
    parser.add_argument("--standalone", type=Path, help="Use an already verified standalone artifact (assets included); default builds current dashboard")
    args = parser.parse_args()
    os.umask(0o077)
    repository = Path(__file__).resolve().parents[2]
    dashboard = repository / "dashboard"
    stage = Path(tempfile.mkdtemp(prefix="leadzen-browser.")).resolve()
    stage.chmod(0o700)
    processes: list[subprocess.Popen] = []
    logs = []
    clean = os.environ.copy()
    for key in list(clean):
        if key.startswith(("LEADZEN_", "OPENOUTFIND_", "OUTSEND_")) or key.endswith(("API_KEY", "TOKEN", "PASSWORD")):
            clean.pop(key)
    clean.pop("NODE_TLS_REJECT_UNAUTHORIZED", None)

    def start(command, filename, env=None):
        output = open(stage / filename, "w")
        logs.append(output)
        process = subprocess.Popen(command, cwd=repository, env=env or clean, stdout=output, stderr=subprocess.STDOUT)
        processes.append(process)
        return process

    def available_port():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    try:
        name, checksum = DOWNLOADS[(platform.system(), platform.machine())]
        download = stage / name
        with urllib.request.urlopen(f"https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/{name}", timeout=30) as response:
            download.write_bytes(response.read())
        if hashlib.sha256(download.read_bytes()).hexdigest() != checksum:
            raise RuntimeError("Official cloudflared release checksum mismatch")
        binary = stage / "cloudflared"
        if name.endswith(".tgz"):
            with tarfile.open(download) as archive:
                member = archive.getmember("cloudflared")
                if not member.isfile():
                    raise RuntimeError("Release archive did not contain a regular binary")
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError("Release binary is unreadable")
                binary.write_bytes(source.read())
        else:
            binary = download
        binary.chmod(0o700)
        config = stage / "openssl.cnf"
        config.write_text("[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=LeadZen disposable fixture CA\n[ext]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyCertSign\nsubjectAltName=IP:127.0.0.1,DNS:localhost\n")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-keyout", str(stage / "fixture.key"), "-out", str(stage / "fixture.crt"), "-config", str(config)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ports = {key: available_port() for key in ["gateway", "dashboard", "backend"]}
        gateway_env = {**clean, "LEADZEN_E2E_ORIGIN_FILE": str(stage / "origin"), "LEADZEN_E2E_CA_FILE": str(stage / "fixture.crt"), **{f"LEADZEN_E2E_{key.upper()}_PORT": str(value) for key, value in ports.items()}}
        start(["node", str(dashboard / "e2e/gateway.mjs")], "gateway.log", gateway_env)
        tunnel = start([str(binary), "tunnel", "--url", f"http://127.0.0.1:{ports['gateway']}", "--no-autoupdate"], "tunnel.log")
        deadline = time.monotonic() + 90
        origin = None
        while time.monotonic() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError("The temporary HTTPS tunnel could not start; private logs retained")
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", (stage / "tunnel.log").read_text())
            if match:
                origin = match[0]
                break
            time.sleep(0.2)
        if not origin:
            raise RuntimeError("Trusted HTTPS tunnel did not become available; release gate failed")
        (stage / "origin").write_text(origin + "\n")
        source_hash = candidate_sha256(repository)
        fixture = Path(tempfile.mkdtemp(prefix="leadzen-e2e.", dir=stage)).resolve()
        start([sys.executable, str(dashboard / "e2e/fixture_server.py"), "--directory", str(fixture), "--public-origin", origin, "--port", str(ports["backend"]), "--certificate", str(stage / "fixture.crt"), "--private-key", str(stage / "fixture.key"), "--candidate-sha256", source_hash], "backend.log")
        deadline = time.monotonic() + 120
        while not (fixture / "dashboard.env").exists():
            if time.monotonic() >= deadline or processes[-1].poll() is not None:
                raise RuntimeError("Disposable production API fixture failed; private logs retained")
            time.sleep(0.2)
        node_env = {**clean, **dict(line.split("=", 1) for line in (fixture / "dashboard.env").read_text().splitlines()), "NODE_EXTRA_CA_CERTS": str(stage / "fixture.crt"), "HOSTNAME": "127.0.0.1", "PORT": str(ports["dashboard"])}
        artifact = args.standalone.absolute() if args.standalone else dashboard / ".next/standalone"
        if not args.standalone:
            subprocess.run(["npm", "run", "build"], cwd=dashboard, env=node_env, check=True)
            shutil.copytree(dashboard / "public", artifact / "public", dirs_exist_ok=True)
            shutil.copytree(dashboard / ".next/static", artifact / ".next/static", dirs_exist_ok=True)
        if source_hash != candidate_sha256(repository):
            raise RuntimeError("Candidate source changed while building; start a fresh fixture")
        if args.standalone:
            if not (artifact / "candidate-source.sha256").is_file() or (artifact / "candidate-source.sha256").read_text().strip() != source_hash:
                raise RuntimeError("Supplied standalone artifact is not bound to this candidate source SHA-256")
        else:
            (artifact / "candidate-source.sha256").write_text(source_hash + "\n")
        if not (artifact / "server.js").is_file() or not (artifact / "public").is_dir() or not (artifact / ".next/static").is_dir():
            raise RuntimeError("Standalone artifact must include its public and static assets")
        start(["node", str(artifact / "server.js")], "dashboard.log", node_env)
        deadline = time.monotonic() + 90
        verified = False
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(origin + "/__e2e/status", timeout=5) as response:
                    status = json.load(response)
                with urllib.request.urlopen(origin + "/login", timeout=5) as response:
                    login_status = response.status
                if status.get("candidate_sha256") == source_hash and status.get("provider_disabled") is True and login_status == 200:
                    verified = True
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.3)
        if not verified:
            raise RuntimeError("Synthetic trusted HTTPS candidate failed its readiness gate")
        (stage / "candidate.json").write_text(json.dumps({"origin": origin, "candidate_sha256": source_hash, "manifest": str(fixture / "manifest.json"), "ports": ports}, indent=2) + "\n")
        print(f"Synthetic HTTPS candidate: {origin}\nCandidate source SHA-256: {source_hash}\nPrivate staging directory: {stage}", flush=True)
        if args.test:
            test_env = {**clean, "LEADZEN_E2E_BASE_URL": origin, "LEADZEN_E2E_FIXTURE_FILE": str(fixture / "manifest.json"), "LEADZEN_E2E_RESULTS_DIR": str(stage / "results")}
            return subprocess.run(["npm", "run", "test:e2e"], cwd=dashboard, env=test_env).returncode
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("A disposable staging process exited unexpectedly")
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"Browser staging failed: {type(error).__name__}. Private logs: {stage}", file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        for output in logs:
            output.close()
        # Preserve only private diagnostic files for the owner; never upload
        # manifests, env files, databases, passwords or setup capabilities.


if __name__ == "__main__":
    raise SystemExit(main())
