# Controlled release and rollback

The release candidate is captured from the complete intended working tree, not
from `HEAD`. `leadzen.operations.release` rejects symlinks, private files,
databases, logs, dependency directories and untracked source omissions. It
records the Git revision as provenance only, a deterministic source hash, target
architecture, dependency lock hashes, source archive hash and checksums for the
wheel, standalone dashboard and scanned container image.

Capture and verify it outside the checkout:

```sh
candidate=/srv/private/leadzen-candidates/$(date -u +%Y%m%dT%H%M%SZ)
umask 077
.venv/bin/python -m leadzen.operations.release capture \
  --source "$PWD" --output "$candidate" --architecture linux/amd64
.venv/bin/python -m leadzen.operations.release verify "$candidate"
```

Build the Python wheel and dashboard standalone output from `candidate/source`,
then add each artifact only after it has been tested. The container build must
use the exact target architecture and the pinned base image in
`compose/leadzen/Dockerfile`; the image scan must be saved alongside its digest
and complete advisory JSON. The candidate source hash in every browser, build,
test and artifact record must match `manifest.json`.

Use `uv build --build-constraints requirements-build.lock --require-hashes` for
the wheel. The hash-locked builder and Python backend are separate from the
runtime dependency lock. The historical `compose/leadzen/deploy-accounts.sh`
now validates `CANDIDATE_DIRECTORY CHECKS_JSON` and fails before touching services
or data when a gate is incomplete. Its old in-place extraction, key/environment
override and unvalidated workspace migration path have been retired for safety.

The release gate requires PASS evidence for preflight, current secret scan,
credential disposition, backend/frontend tests, type checks, dependency and image
advisories, production build/startup, current migrations, trusted browser,
actual current recovery, alert delivery, target-host capacity, enabled
integrations and external promotion controls. Missing evidence is BLOCKED. The
repository workflow files do not prove that GitHub branch protection or Vercel
promotion controls are enabled; verify those controls in the owning accounts.

Create a fresh checks document **after the complete artifact inventory is frozen**:

```sh
python -m leadzen.operations.release checks-template "$candidate" \
  --output "$candidate/release-checks.v2.json" --valid-hours 24
```

Every gate initially remains BLOCKED. A PASS requires a nonempty explanation,
the matching source SHA-256, and an `attestation` containing UTC `observed_at`,
`expires_at` and `evidence_files`. Each evidence entry has a `path` relative to
the checks document's directory and its exact `sha256`; absolute paths, traversal,
symlinks, empty files and changed bytes are rejected. Copy the necessary protected
evidence under that directory first. For example:

```json
{
  "status": "PASS",
  "source_sha256": "MATCHING_64_CHARACTER_SOURCE_SHA256",
  "evidence": "Describe the actual command, result and tested scope.",
  "attestation": {
    "observed_at": "2026-10-04T12:00:00+00:00",
    "expires_at": "2026-10-05T12:00:00+00:00",
    "evidence_files": [{"path": "evidence/check.json", "sha256": "MATCHING_64_CHARACTER_FILE_SHA256"}]
  }
}
```

The top-level schema version 2, architecture, source archive hash and complete
artifact descriptors must remain identical to the generated template. Artifact
changes require new checks and applicable verification. The gate rejects legacy
bare PASS records and stale evidence; validity cannot exceed 24 hours, and
`--max-age-hours 1` can tighten that window. These are explicit operator
attestations bound to retained bytes, not independent certification or signatures.
Do not set current production gates to PASS using a synthetic or historical test.

Assess a complete current Trivy report using the immutable inspected image ID:

```sh
python -m leadzen.operations.advisories image-advisories.json \
  --image-id "$RECORDED_DOCKER_IMAGE_ID" --architecture linux/amd64 \
  --decisions docs/production-image-risk-decisions.json --output image-risk-result.json
```

The scan must contain a real OS/package inventory, matching image identity and
architecture, and fresh metadata. An empty report cannot establish a clean image.

## Deployment order

1. Freeze the candidate hash and record the tested wheel, standalone dashboard,
   image digest, lock hashes, target architecture and release manifest.
2. Run `leadzen.operations.preflight` against the current private environment,
   policy, control database and every initialized employee database. Preserve the
   existing Fernet settings key and signing key.
3. Place the maintenance hold, stop new API/MCP intake, pause scheduler dispatch,
   and wait for the bounded drain. If a worker or request remains active, leave
   the hold and stop. Never kill an ambiguous provider operation.
   Drain also checks the scheduler's pass lock between employee children; both
   schedulers recheck the hold before dispatching each next employee. A child
   whose command ends in `--workspace` remains visible to the process check.
4. After drain succeeds, stop only the reviewed API and scheduler units. Before
   copying, backup requires `SystemdQuiescence` to prove inactive/dead, PID zero
   and an empty cgroup. Create and verify the matched
   control-plus-workspaces recovery set and its independent protected copy.
5. Stage the exact candidate runtime and dashboard artifact beside the current
   release. Run `leadzen.operations.migrations` in plan mode; apply only with
   `--execute`, the verified candidate, matched recovery set, complete writer-unit
  list and the hold still active. A historical/imported snapshot cannot authorize
  an actual migration; use a complete native matched recovery set. It migrates the control database and every
   server-derived employee database, then rechecks integrity, schema and keys.
6. Start the API and dashboard candidate. Verify authenticated health/readiness,
   anonymous 401s, headers/cookies, login/setup/password/onboarding, CRUD,
   settings, logout, employee isolation and the exact candidate hash.
7. Promote traffic only after all release gates pass. Keep intake held while
   reconciling uncertain external operations. Resume only explicitly authorized
   scheduling; neither recovery nor migration resumes it.
8. Observe API failures/latency, locks, disk/memory, authentication spikes,
   worker failures, scheduler heartbeat and backup freshness for the approved
   observation window. Record evidence before closing the release.

## Prepared operator commands

These commands are prepared for an authorized single-host release. They must not
be run merely because this document exists. Resolve the target's actual service
owner, paths, unit inventory and deployed-release manifest first. Run Python/uv
commands as that dedicated runtime owner; use sudo only for the reviewed units
and immutable runtime pointer. Keep private configuration outside the source.

```sh
candidate=/srv/private/leadzen-candidates/REVIEWED_SOURCE_HASH
checks=/srv/private/leadzen-release-checks.json
python=/srv/private/leadzen-release-tools/bin/python
backend_env=/srv/private/leadzen-runtime.env
dashboard_env=/srv/private/dashboard-production.env
policy=/srv/private/leadzen-release-policy.json
control=/opt/leadzen/data/db.sqlite3
deployed=/opt/leadzen-deployed-release/manifest.json

"$python" -m leadzen.operations.release verify "$candidate"
"$python" -m leadzen.operations.preflight --backend-env "$backend_env" \
  --dashboard-env "$dashboard_env" --policy "$policy" --schema-policy allow-pending
# Pending schema yields BLOCKED; record it and resolve it only through the
# verified matched-recovery migration sequence, never by ignoring the check.
# A nonempty residual WAL also yields BLOCKED for immutable plan/preflight reads.
# Do not checkpoint a live source to make this check pass. First hold/drain/stop
# writers and verify the complete SQLite-safe matched recovery set below.
"$python" -m leadzen.operations.maintenance hold --control-db "$control"
"$python" -m leadzen.operations.maintenance drain --control-db "$control" --timeout 3600
sudo systemctl stop leadzen-followups.service leadzen.service
"$python" -m leadzen.operations.recovery backup --env-file "$backend_env" \
  --release-manifest "$deployed" \
  --protected-file "$dashboard_env" \
  --protected-file /srv/private/Caddyfile.deployed \
  --service-unit-file /etc/systemd/system/leadzen.service \
  --service-unit-file /etc/systemd/system/leadzen-followups.service \
  --writer-unit leadzen.service --writer-unit leadzen-followups.service \
  --destination /srv/leadzen-backups \
  --independent-destination /mnt/leadzen-independent-backups
# Select the exact newly returned complete snapshot; do not choose an older one.
snapshot=/srv/leadzen-backups/EXACT_RETURNED_SNAPSHOT
"$python" -m leadzen.operations.recovery verify "$snapshot"
"$python" -m leadzen.operations.recovery verify "/mnt/leadzen-independent-backups/$(basename "$snapshot")"
drill=/srv/leadzen-drills/NEW_ABSENT_DIRECTORY
"$python" -m leadzen.operations.recovery restore "$snapshot" --target "$drill"
# Also enforce OS/container network denial for an actual operator drill.
"$python" -m leadzen.operations.recovery drill "$drill"
"$python" -m leadzen.operations.migrations --backend-env "$backend_env" --policy "$policy"
# Preserve a BLOCKED pending-schema/WAL plan as evidence. The explicit execution
# path verifies the native matched backup first, then handles checkpointing only
# under the required stopped-writer/lock contract; it revalidates after migration.
"$python" -m leadzen.operations.migrations --backend-env "$backend_env" --policy "$policy" \
  --candidate "$candidate" --recovery-set "$snapshot" \
  --writer-unit leadzen.service --writer-unit leadzen-followups.service --execute
"$python" -m leadzen.operations.preflight --backend-env "$backend_env" \
  --dashboard-env "$dashboard_env" --policy "$policy"
```

Stage a **new** runtime directory rather than installing over the running venv.
Use reviewed `uv==0.11.15`, the hashed runtime lock and the tested wheel with
`--no-deps`. Keep the previous complete runtime. A network-disabled candidate
image can instead be loaded from the tested image archive and selected by its
recorded ID; rebuilding produces a different artifact and requires revalidation.

The current platform uses Vercel for the dashboard. Read-only October 4 metadata
reports Node 24.x for the project and its latest production deployment. CI now
checks both Node 22 and 24 and runs the browser job on 24. Its production
environment, prebuilt Vercel artifact and promotion checks must be reconciled and
tested before preparing `vercel deploy --prebuilt --prod`. The locally tested
standalone artifact is preserved for verification; it does not establish that a
Vercel build is byte-identical or that its production controls are enabled.
Do not promote an untested fresh build in place of the tested candidate.

With every gate's same-source evidence complete, run:

```sh
"$python" -m leadzen.operations.release gate "$candidate" --checks "$checks"
# Start only the reviewed candidate API/unit, verify health/auth/isolation and
# promote the tested dashboard through the approved platform procedure.
sudo systemctl start leadzen.service
"$python" -m leadzen.operations.monitoring --config /etc/leadzen-monitor.json
# Release intake only after verification and uncertain-operation reconciliation.
"$python" -m leadzen.operations.maintenance release --control-db "$control" --reconciled
# Restart scheduling only with its separately confirmed authorization.
```

The runtime/unit cutover and Vercel promotion commands remain target-specific
and BLOCKED until the actual host and owning platform controls are available.
The commands above intentionally do not claim an unobserved runtime cutover.
While intake is held, ordinary authentication/CRUD returns maintenance 503. Run
the browser journeys against the exact isolated provider-disabled candidate;
held production checks exercise private health/readiness only. Do not label a
503-blocked production journey passed or remove the hold merely to test it.
The protected dashboard environment and proxy copy must come from the current
deployed release, remain owned mode 600, and be verified against that deployment
before backup. A candidate environment does not replace previous-release recovery
configuration. Their exact bytes are retained in the private recovery bundle.
The example backend environment is a runtime-owner mode-600 verified copy of the
current systemd environment. Set preflight's `env_owner_uid` to its actual owner;
the backup/migration/monitor processes must be able to read it under their
reviewed identity. A root-owned API EnvironmentFile is not automatically readable
by those services. Keep any approved copy synchronized and privately byte-verified.

## Rollback order

Keep intake and all automatic workers held. Preserve logs and a fresh consistent
incident snapshot. Reconcile accepted/unknown external sends, purchases and AI
usage before retrying anything. For a frontend-only issue, return to the previous
immutable dashboard artifact without restoring databases. For a backend issue,
return to the previous runtime only when it is compatible with the forward schema.

If data restoration is necessary, restore the complete matched control-plus-all-
employee recovery set into a new isolated path, verify keys/integrity/FKs,
authentication and routing, and reconcile legitimate post-backup writes before
an operator chooses a coordinated service/database cutover. Never run destructive
reverse migrations, restore one database without the other, or overwrite a live
database in place. Keep the failed candidate and recovery set for incident
analysis. Reopen intake only after readiness and isolation checks pass, and resume
scheduling only after uncertain-operation reconciliation.

For a data-recovery rollback, keep services held/stopped and use the same
`recovery verify`, `restore --target NEW_ABSENT_DIRECTORY` and `drill` commands
above against the **complete** matched pre-release set. Do not copy individual
SQLite files into live storage. A backend-code rollback uses the recorded previous
runtime only after schema compatibility is proven; a frontend rollback promotes
the recorded previous immutable Vercel deployment only after its API contract
is checked. Exact runtime-pointer/platform rollback commands require the current
host/deployment inventory and remain BLOCKED rather than being guessed here.

No deployment, production migration, provider call, credential rotation or
external alert delivery was performed while preparing this release.
