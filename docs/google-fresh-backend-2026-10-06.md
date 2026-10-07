# Fresh Google backend installation — October 6, 2026

The owner explicitly requested that the existing Google VM run today's GitHub
`main` code with a new database, with no migration of old records. This report
records what was observed on the existing `leadzen-api` VM in project
`zyene-reviews`, zone `us-central1-a`. It does not authorize future deployments.

## Live release

- Source: Zyene-Inc/leadzen `main` commit
  `f1d8cfe314ba84dd7b9e59592fba0b721e63e0d4`, captured source SHA-256
  `2754d2cdddca10e3bed26b822a343f1a20dc1895a3274d6119a11d81cb4cf892`.
  The exact source archive and manifest were verified on the VM.
- Python 3.12.3 runtime: wheel built from that staged source with the hashed
  build lock, dependencies installed from `requirements-production.lock` with
  hash enforcement, in `/opt/leadzen-f1d8cfe-20261006`.
- Fresh control database and future employee workspaces:
  `/opt/leadzen-f1d8cfe-20261006/data/`. All current migrations applied.
  `support@zyene.com` was created as administrator through the private
  `bootstrap_admin` password prompt. The owner entered the generated password;
  it is kept only in the owner-only TXT file outside the repository.
- The existing `leadzen.service` now points to this runtime and the root-owned,
  mode-600 `/etc/leadzen-f1d8cfe.env`. It is active. The old service token and
  settings encryption key were carried into the new configuration to match
  Vercel; a new stable Django signing key was generated. Following the owner's
  October 6 request, `LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED=1` and
  `leadzen-followups.service` is active and enabled. Its scheduler heartbeat
  reported `status: ok` at 19:07 UTC with zero service restarts.
- An isolated candidate first returned authenticated HTTP 200 for health and
  readiness. After cutover, public
  `https://leadzen-api.zyene.com/api/health` and `/api/ready` each returned
  authenticated HTTP 200, while anonymous health returned 401. The Vercel
  dashboard login page returned HTTP 200. A direct production admin login with
  the new credential returned HTTP 200, identified `support@zyene.com`, and
  routed to `/admin`; the verification session was then signed out (HTTP 200).
  No real email or paid provider operation was run as part of this installation.
- A recovery copy of the **new** database, configuration, service units,
  source archive, manifest, and wheel is at the root-only
  `/srv/private/leadzen-current-backup-20261006`. After enabling follow-ups,
  a second root-only copy at
  `/srv/private/leadzen-current-backup-followups-20261006` captured the current
  configuration and database. Its SQLite quick check was `ok`. A matching
  owner-only copy is stored outside the repository at
  `/Users/ashishdikonda/.codex/private/leadzen/leadzen-current-backup-followups-20261006.tar.gz`;
  its SHA-256 matched the VM archive, and its extracted database also passed
  SQLite quick check.

## Old data disposition

The old `/opt/leadzen` installation held a control database with two users, two
account profiles, and one invitation. Its one employee workspace held 103 finder
leads, 20 chat messages, two reviewed emails, two sender leads, and two outreach
job records. None was migrated into the fresh database. Following the owner's
October 6 deletion instruction, a guarded cleanup removed all 24 enumerated
old VM paths, including that runtime and database, old backups, and the obsolete
token TXT file. A repeat inventory reported `SUPERSEDED_PATHS 0`. Obsolete
local backups and the old administrator password TXT were also removed; the
current administrator TXT and current installation backup were preserved.
After the purge, the API and follow-up services remained active, the scheduler
remained enabled, and authenticated public `/api/ready` returned HTTP 200.

Health, schema readiness, the admin login/logout path, and the scheduler
heartbeat are verified. The fresh database has no employee workspace, so
activation sent no outreach. Invitation delivery, paid provider calls, and an
actual follow-up send were not part of this check.
