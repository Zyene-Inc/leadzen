# Production image risk decision — October 5, 2026

The `security / image` job for commit
[`bfb387bffb36fe723612eaa351f93a067146ef8c`](https://github.com/Zyene-Inc/leadzen/commit/bfb387bffb36fe723612eaa351f93a067146ef8c)
scanned Linux amd64 image
`sha256:0aa62bd38e2deef4654406af6b61ee21e167b7942d888b93741c210578a37d63`.
The complete Trivy report is retained in
[Actions run 37333568237](https://github.com/Zyene-Inc/leadzen/actions/runs/37333568237);
its SHA-256 is
`b38789c93b3c8556d22df149ad96a1dbf0490db19e5d54274e0b676f0604e1ae`.

The scan found 44 HIGH package/CVE matches across eight distinct CVEs, with no
CRITICAL findings. It also reported 61 MEDIUM, 60 LOW, and 2 UNKNOWN matches.
The 44 HIGH matches are recorded individually by vulnerability ID, package,
installed version, and architecture in
[`production-image-risk-decisions.json`](production-image-risk-decisions.json).
The decisions expire **November 4, 2026**. GitHub Actions continues to retain and
publish the complete scan; the risk gate reports reviewed matches and does not
hide findings.

The accepted matches concern ncurses, systemd/libudev, ACL, util-linux, and Perl:

- [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720)
- [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742)
- [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369)
- [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642)
- [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408)
- [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409)
- [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410)
- [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538)

The image already uses the current official Python 3.12.15 slim Trixie digest.
The cited Debian tracker entries did not offer a compatible Trixie fix for these
installed versions at review time. The decision is an explicit, time-limited
acceptance of residual risk, not a claim that the packages are unaffected or
that the scanner findings are false positives. The authenticated GitHub reviewer
`dikondaashish` recorded the decision following explicit user approval on
October 5, 2026.

Reassess before expiry and sooner if compatible Trixie fixes become available.
Update the image and remove each resolved decision; do not renew an entry without
a fresh review. Unknown-severity findings remain visible for review but are not
covered by this HIGH/CRITICAL release-gate decision.
