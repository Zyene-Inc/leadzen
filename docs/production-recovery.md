# Full-server recovery and isolated restore

The recovery commands are local preparation. No timer is installed, no service is
stopped, and no production database is modified by this repository change.
Installation, maintenance, a real current backup, independent storage and service
resumption require the reviewed release authorization.

The recovery set includes the control database and **every initialized employee
database**, including inactive/deleted employees; the exact private backend
environment/key; service-unit bytes; a verified deployed release's source archive
and all source-matched runtime/build artifacts. A Workspace export cannot replace
this set. The release manifest must describe the **currently deployed** source and
runtime, not only a newer candidate. Preparing an older deployed-release capture
is a separate release task if no matched manifest exists.

Use repeated `--protected-file` arguments for the matching dashboard environment,
deployed reverse-proxy configuration and other reviewed private release settings.
The tool requires owned mode-600 regular files, rejects hardlinks, duplicate paths,
more than 32 inputs and inputs larger than 1 MiB, and aborts if their bytes change
during backup. It keeps their basenames/mapping only in the protected index and
restores the exact bytes under `private/protected-NNN.bin`; it never executes or
installs them. Stage a private owned copy of public/root-owned proxy configuration
before the authorized backup. Verify that these are current deployed settings,
rather than a candidate or a stale environment export.

The recovery command reads the backend environment as its runtime owner. Use an
owned mode-600 private copy matching the current deployed environment at
`/srv/private/leadzen-runtime.env` in these examples. If systemd loads a root-owned
`/etc/leadzen.env`, preparing and privately verifying that runtime-owned copy is
an authorized operator step; do not weaken the root-owned file's permissions.

Ordinary manifests contain generated names, counts, byte sizes and checksums.
Account/workspace relationships, environment values, actual service configuration
and release material are inside the protected `private/` bundle. Directories are
0700 and files 0600 under the runtime owner. Storage encryption, remote custody,
access auditing and key escrow remain operator responsibilities. Never upload a
snapshot or paste its private bundle into an issue/chat.

## Safe backup sequence

1. Verify a private production environment, a complete deployed-release manifest
   and required runtime artifacts. Preserve both stable keys:
   `LEADZEN_SETTINGS_KEY` and `LEADZEN_SECRET_KEY`. The former must decrypt saved
   RuntimeSettings, invitation and mailbox records. Plaintext/nested mailbox
   credentials block a current verified snapshot; disposition requires a separate
   approved remediation, never automatic rewriting.
2. Close public intake and MCP with the maintenance hold. Pause scheduler dispatch
   and drain existing workers. Never kill a provider operation or replay an
   ambiguous send/purchase to make a backup succeed.
3. Only after drain proof, stop the fixed API and scheduler units. The existing
   API unit contains MCP. Include every additional installed writer in the
   reviewed deployment inventory. Unmanaged writers and another independently
   deployed host are outside this single-host systemd contract and are a blocker.
4. Run the backup as the runtime owner with private matched metadata:

```sh
python -m leadzen.operations.maintenance hold --control-db /opt/leadzen/data/db.sqlite3
python -m leadzen.operations.maintenance drain --control-db /opt/leadzen/data/db.sqlite3 --timeout 3600
# Stop only after the drain command succeeds; this is an authorized operator step.
sudo systemctl stop leadzen-followups.service leadzen.service
python -m leadzen.operations.recovery backup \
  --env-file /srv/private/leadzen-runtime.env \
  --release-manifest /opt/leadzen-deployed-release/manifest.json \
  --protected-file /srv/private/dashboard-production.env \
  --protected-file /srv/private/Caddyfile.deployed \
  --service-unit-file /etc/systemd/system/leadzen.service \
  --service-unit-file /etc/systemd/system/leadzen-followups.service \
  --writer-unit leadzen.service --writer-unit leadzen-followups.service \
  --destination /srv/leadzen-backups \
  --independent-destination /mnt/leadzen-independent-backups
```

The tool requires loaded units to be inactive/dead with PID zero and no remaining
cgroup children, takes existing control/scheduler/workspace send and initialization
locks, and keeps source SQLite connections open. It checks source data versions,
the initialized namespace and metadata again after the expensive release copies
and after the independent mirror copy, immediately before local publication. A
write, changed key/environment/unit/protected file or lost quiescence aborts the
backup. An already complete independent mirror is retained with pending local
evidence; this outcome is a failed backup, never reported as a local success.
Maintenance hold creation/removal also fsyncs the containing directory so the
hold survives a crash under the filesystem's durability guarantees.
SQLite's backup API includes committed WAL state;
copied databases undergo integrity, foreign-key, key and ownership checks.

The second destination must be private and on a **different filesystem device**.
The explicit filesystem adapter verifies and fsyncs a full second copy before the
local snapshot is atomically published. There is no CLI same-volume bypass. A
second directory on the same disk is rejected. Different-device checks do not
prove off-host custody or object-store encryption: configure a protected remote
mount and test host-loss recovery before claiming independent disaster recovery.
No cloud bucket, paid resource or remote upload was provisioned here.

5. Verify both copies and run a new isolated restore/drill before recording a
   recovery gate as PASS. A failed backup leaves incomplete private staging,
   keeps intake held and requires an alert/operator response.
6. Review held external effects, verify the intended release/health, and resume
   only through the authorized release runbook. Neither backup nor restore removes
   the hold or restarts automatic outreach.

`compose/leadzen/backup/` contains uninstalled systemd service/timer and private
environment templates. The root wrapper performs only fixed-unit maintenance;
database operations run as the configured runtime owner. Its default intentionally
leaves the service stopped/intake held after success. A daily timer therefore
requires a staffed maintenance/resumption procedure before installation. Review
paths, owners, drain coverage, private mount availability and alerting first.

## Restore without touching production paths

```sh
python -m leadzen.operations.recovery verify /srv/leadzen-backups/SNAPSHOT
python -m leadzen.operations.recovery restore /srv/leadzen-backups/SNAPSHOT \
  --target /srv/leadzen-drills/NEW_ABSENT_DIRECTORY
python -m leadzen.operations.recovery drill /srv/leadzen-drills/NEW_ABSENT_DIRECTORY
```

The target must be a **new absent directory** under an owned private parent. No
command supports overwriting a production database or restoring in place. A
separate drill environment rewrites database paths only to that isolated target,
disables both automatic services and drops external provider/email exports. The
controlled child denies socket connections, DNS, listeners and subprocess launch
before Django loads. It migrates only the isolated copies, uses canonical account
services for a new synthetic actor, verifies login/logout/session revocation,
checks restored workspace routes and creates two empty synthetic employee
workspaces to prove sentinel isolation. Before synthetic actors are created, the
drill checks every pre-existing business record's original columns and values
privately across the isolated upgrade, then rechecks integrity, foreign keys and
actual matching-key decryption in every restored database. Only reviewed legacy
renames and the pending 0018 timezone conversion are normalized. Aggregate
`original_records_checked`, `encrypted_records_checked` and
`validated_database_count` accompany the measured booleans; record values or
private fingerprints never enter the ordinary result. It never resets a real employee password.
This controlled Python guard is not a general sandbox for arbitrary executable
archive contents. For production operator drills, also use a network-disabled
container or OS service with `PrivateNetwork=yes`, `IPAddressDeny=any`, and
`RestrictAddressFamilies=AF_UNIX`; do not run restored historical executables.

Protected `drill-result.json` contains only booleans/counts. A successful drill
does not send mail, check provider billing or prove a current deployed release.

## Retention and failure recovery

```sh
python -m leadzen.operations.recovery retain /srv/leadzen-backups \
  --independent-root /mnt/leadzen-independent-backups --keep 7
```

At least two complete snapshots must be retained. Local retention deletes only
old tool-owned **native** snapshots that still verify and have an identical
verified independent copy. Foreign directories, corrupt snapshots, historical
imports and incomplete staging are preserved. Independent copies are never
deleted by this command; their retention/immutability policy is reviewed
separately. Production databases are outside retention's namespace.

If a deployment fails, keep intake and automatic services held, verify the
pre-release recovery set, restore into a new directory, run the isolated drill,
and reconcile post-backup external effects before the operator chooses a
coordinated data/runtime rollback. Never blindly replace live databases with an
older copy: legitimate later writes and accepted sends may exist. Migration 0018
has irreversible wall-clock metadata normalization; a migration reverse alone
does not restore earlier metadata.

## Evidence and remaining gates

On October 4, the user-authorized **October 3 historical** archive was inspected
without blanket extraction. Only selected regular env/database/unit members were
staged; archive links were excluded. Its matching key decrypted one settings
record and one mailbox; zero plaintext/nested mailbox rows were present. The
control plus one initialized employee database passed integrity/FK/mapping checks.
An isolated copy upgraded to current schemas and passed authentication, session
revocation, existing workspace routing and two synthetic workspace isolation
checks with networking blocked. The original archive/databases were untouched.
Safe aggregate evidence:
[`production-historical-recovery-validation-2026-10-04.json`](production-historical-recovery-validation-2026-10-04.json).

That archive lacks `LEADZEN_SECRET_KEY` and cannot prove today’s release,
current full employee inventory, live backup schedule, independent copy or host-loss
restore. Those gates remain **BLOCKED/UNVERIFIED** until a fresh authorized
current recovery set, matched source/runtime/keys and independent storage drill
pass. Do not substitute the historical proof for the current production gate.
