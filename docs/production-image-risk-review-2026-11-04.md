# Production image risk decision — November 4, 2026

The `security / image` job for pull request 23 (commit `d94a944`) scanned Linux amd64 image
`sha256:3b557ab349de8e2619048a0f7e159abd7d71911b0ae49742f4d34701fa6c481b`,
built from `python:3.12.16-slim-trixie` (Debian 13.7). Actions keeps the complete Trivy report in
[run 41936231349](https://github.com/Zyene-Inc/leadzen/actions/runs/41936231349).
Its SHA-256 is `60c04b32f114811cd21e63d24c9555684e714a2de606b128c62bbac95edbe12e`.

The scan found 45 HIGH and 0 CRITICAL package/CVE matches. It also reported
73 MEDIUM, 62 LOW and 8 UNKNOWN. None of the HIGH matches has a Debian fix.
The CRITICAL findings and the Python package findings from the November 4 failure
(Pillow, pyasn1, certifi, filelock) are resolved by patching, not by this decision.

## Renewed matches (44)

These are the same CVE, package and installed version as the October 7 review. The decisions
expired on October 21, 2026. The base-image refresh did not change these package versions.

- [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) — ncurses (4 packages)
- [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) — libsystemd0, libudev1
- [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) — libacl1
- [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642),
  [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408),
  [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409),
  [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) — util-linux family (9 packages each)
- [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) — perl-base

The runtime facts behind the earlier reasons still hold at `d94a944`:

- The entrypoint drops to uid 1000 through `gosu`.
- LeadZen starts subprocesses only through `sys.executable -m leadzen.*`. It never invokes mount, nsenter, infocmp or Perl.
- Archives are read with Python's `tarfile`, not Perl's Archive::Tar.

## New match (1)

[CVE-2026-119373](https://security-tracker.debian.org/tracker/CVE-2026-119373) in
`libsqlite3-0` 3.46.1-7+deb13u2 is a heap overflow in FTS5 `fts5MergeRowidLists()`.
It was published October 30, 2026, and SQLite fixed it in 3.54.0. Debian lists trixie as affected, with no fix.
This library matters to LeadZen more than the others do, because Python's `sqlite3` module links it
and every workspace database uses it. The exploit needs an attacker to populate a `detail=none` FTS5
table and then run a prefix `MATCH` query. LeadZen, Django and openoutfind create no FTS5 tables.
LeadZen's raw SQL is limited to fixed PRAGMA, schema and migration statements, and there is no
arbitrary-SQL path. Recovery opens only backups the operator supplies.

## Decision

All 45 matches are recorded individually by vulnerability ID, package, installed version and
architecture in [`production-image-risk-decisions.json`](production-image-risk-decisions.json).
The decisions expire **November 18, 2026**, the same 14-day window as the last review. Each one is
an explicit, time-limited acceptance of residual risk. It does not claim the packages are
unaffected or that the findings are false positives. GitHub Actions continues to retain and
publish the complete scan, and the risk gate reports the reviewed matches without hiding them.

Ashish Dikonda approved these decisions as owner on November 4, 2026.

Reassess before expiry, and sooner if compatible Trixie fixes become available. Update the image
and remove each resolved decision, and do not renew an entry without a fresh review.

## Addendum — November 5, 2026

The `security / image` scan for commit `ed51da1`
([run 42091259169](https://github.com/Zyene-Inc/leadzen/actions/runs/42091259169), report SHA-256
`60c43a028ef22650d14a21a006e5556dfc267da4a1fd043061ae6614675a5959`) reported three new HIGH matches:

- [CVE-2026-109518](https://security-tracker.debian.org/tracker/CVE-2026-109518) in `apt` and
  `libapt-pkg7.0` 3.0.3. **Fixed by patching, not accepted.** Commit `6fe78c6` moves the base image to
  the November 5 rebuild of `python:3.12.16-slim-trixie`
  (`sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54`), which ships apt 3.0.4.
- [CVE-2026-76844](https://security-tracker.debian.org/tracker/CVE-2026-76844) in `zlib1g`
  1:1.3.dfsg+really1.3.1-1+b1 is a heap overflow in zlib's `gz_write()` that follows a failed `write()`.
  Debian lists trixie as affected, with no fix. Trivy's title for this entry wrongly names
  webpack-dev-middleware, but its description and package are zlib's.
  Within the image, only `dpkg-deb` and `libapt-pkg` import the `gzwrite`/`gzputs`/`gzprintf` family.
  LeadZen never runs package tooling, and its uid 1000 runtime cannot install packages. CPython's
  `zlib` and `gzip` modules use the deflate stream API rather than gzFile. No native extension in
  `/opt/venv` imports the affected functions.

The CVE-2026-76844 decision expires November 18, 2026, together with the batch above.
Ashish Dikonda approved it as owner on November 5, 2026.
