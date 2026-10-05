# Read-only production preflight

Implemented locally on October 4, 2026. This tool does not deploy, migrate,
checkpoint a database, change settings, contact providers, or authorize sending.
Run it against the immutable release candidate and the target host's private
configuration after writers are quiesced and WAL is explicitly checkpointed.
See [environment inventory](production-environment.md) and the
[October 4 audit](production-readiness-audit-2026-10-04.md).

The command loads no `leadzen.settings` and never calls `django.setup()` against
current data. That matters because normal settings import can upgrade historical
configuration table labels. A fresh child reads the installed migration definitions
with an in-memory settings/registry description; migration data operations and app
`ready` hooks are never executed. The current graph includes dependency migrations,
account migration `0004_accountprofile_tour_state` and configuration migration
`0019_discoverylookup_source_index`.

## Inputs

Supply canonical absolute paths to two private mode-600 environment files and a
mode-600 JSON policy. Symlinks at any path component and hardlinked files are rejected.
The policy belongs to the caller. Environment files belong to `env_owner_uid`.
The storage boundary, control database, workspace root and employee folders belong
to the dedicated non-root `service_uid`, with directories mode 700 and files mode 600.
If a privileged release operator reads root-owned configuration for a service
account, set these two owner IDs separately.

Environment files accept one `NAME=value` per line, whole-line comments and one
quoted single-line value. Do not source them in a shell. Duplicate names, command
substitution, multiline/ambiguous quoting and files over 256 KiB fail. Pulled
Vercel files may omit host-injected `NODE_ENV`; an explicit development override fails.

Example policy below uses reserved example domains and a hypothetical host/UID.
Replace metadata privately using actual deployment evidence. It contains no secrets.

```json
{
  "service_uid": 1000,
  "env_owner_uid": 0,
  "expected_hostname": "leadzen-production-host",
  "expected_machine": "x86_64",
  "storage_root": "/var/lib/leadzen",
  "persistent_storage": true,
  "dashboard_origin": "https://dashboard.example.com",
  "api_origin": "https://api.example.com",
  "private_listen_addresses": ["127.0.0.1"],
  "trusted_proxy_networks": ["127.0.0.1/32"],
  "forwarded_proxy_addresses": ["127.0.0.1"],
  "features": {
    "invitations": false,
    "mcp": false,
    "chat": false,
    "discovery": false,
    "mail": false,
    "autopilot": false,
    "automatic_followups": false
  }
}
```

Host name and architecture are compared with the executing host without printing
their values. Origin values must be exact HTTPS origins with public hosts and
default HTTPS ports. Dashboard origin must match both frontend and backend
configuration. API origin must match the frontend API URL, and its hostname must
appear in the explicit backend Host list. The dashboard CORS list must contain
exactly the policy's dashboard origin. Public/wildcard listeners, global proxy
addresses, all-network trust and proxies outside their trusted CIDRs fail.

These fields describe operator-attested topology. The tool does **not** observe
the firewall, deployed reverse-proxy rules, actual listening sockets, DNS ownership,
volume mounts or durable cloud storage. `persistent_storage: true` is an explicit
attestation, not automatic proof of persistence. Collect those host observations
separately before approving a release. A local policy must not claim a temporary
directory or container writable layer is durable production storage.

Every feature boolean is mandatory. False is recorded as `FEATURE_DISABLED` with
`scope: RELEASE_POLICY`; it excludes that feature's configuration from this release
check and **does not disable application routes or authorize a feature change**.
Actual Autopilot/follow-up environment switches must agree with the policy.
For an enabled release feature, configure it and its account settings before running
the check. Invitations require explicit provider/sender configuration; MCP requires
its exact API-origin `/mcp` endpoint. Employee Chat requires enabled AI, a supported
provider/model and protected key; discovery additionally needs BetterContact;
mail and automatic outreach require the configured mailbox/transport credential.
Compatible endpoints must be HTTPS and belong to the server-approved host list.
RuntimeSettings singleton row 1 takes precedence exactly as at runtime: an
explicit empty override clears a legacy credential/model rather than reviving it.
All enabled mail workflows need reply-inbox credentials for suppression handling,
approved public SMTP/IMAP hosts and supported TLS ports. AI endpoint selection is
checked against the provider and approved host policy. Index checks compare actual
columns, order, uniqueness and partial predicates, as well as names.
These are offline structural checks, not DNS/certificate ownership, live
billing/delivery/provider availability proof.

## Invocation and outcome

Keep input paths and reports in private operator storage. `--report` must name a
new file; it is created mode 600 and never overwrites an existing report.

```bash
.venv/bin/python -B -m leadzen.operations.preflight \
  --backend-env /private/operator/backend.env \
  --dashboard-env /private/operator/dashboard.env \
  --policy /private/operator/preflight-policy.json \
  --report /private/operator/preflight-current.json
```

The JSON output contains fixed check codes, variable names when required variables
are missing, aggregate counts and database roles. It omits secret values, origins,
absolute input/database paths, account identifiers, decrypted contents, provider
responses and exception details. Exit 0 means all implemented checks passed; exit 1
means a confirmed failed check; exit 2 means evidence/input/access was blocked.
`PASS` does not certify the unobserved host/browser/provider boundaries or approve
deployment. The `limits` field makes those boundaries explicit.

Before migration, the additive `--schema-policy allow-pending` mode can inspect
ownership/history/integrity while permitting recorded missing migrations. Its
result remains **BLOCKED**, with `SCHEMA_PENDING` and a pending count. Credential
checks for an older schema are explicitly blocked. It cannot produce a ready PASS
until the current graph and physical schema are present.

Initial focused implementation checks passed 20 tests. After mailbox compatibility,
physical schema/host/CLI regressions and configuration coverage, the focused
preflight plus production-configuration command passed **64 tests in 13.69 seconds**.
Ruff 0.15.20 reported no errors for the new module and test file. The final command
below also includes the disposable clean/prior-schema migration scenario.
That combined command passed **65 tests in 6.13 seconds** before the final canonical
origin cases. The final preflight-only suite passed **34 tests in 4.08 seconds**.
A later combined run passed 65 tests and encountered one existing request-metrics
test expecting 404 where concurrently introduced maintenance now returned 503;
the release owner's complete regression run must resolve that separate fixture.

## Database and key checks

The control database is read directly with SQLite. Workspace folders must be
canonical UUIDs present in server-owned `AccountProfile` records, including retained
inactive/deleted records. Each initialized marker and corresponding database are
validated. Foreign folders, database aliases, unexpected names and incomplete
database initialization fail or block; a server-owned empty uninitialized folder
does not claim a database has been checked. Accounts and directories are bounded
at 10,000; a larger inventory blocks rather than silently skipping data.

For every initialized database, the tool verifies migration history and dependency
ordering, current tables/columns/indexes/uniqueness/nullability/foreign-key structure,
SQLite integrity and foreign-key data consistency. Unknown migration records fail.
It does not run reverse migrations or repair records. Each SQLite connection has
a one-second connection timeout and a 30-second SQL progress deadline; ordinary
filesystem I/O is subject to the host filesystem's behavior.

SQLite `mode=ro` alone may create or update WAL shared-memory files. This tool uses
`mode=ro&immutable=1` and refuses any nonempty WAL with `DATABASE_WAL_PENDING`.
It therefore requires a quiesced, checkpointed snapshot. Stop API intake and every
worker/scheduler, take the coordinated recovery set and checkpoint through the
authorized recovery/release procedure; the preflight never does that itself.
Running it while writes continue cannot establish a consistent release snapshot.

The existing Fernet key must decrypt every nonempty runtime-settings, sender-mailbox
and invitation ciphertext into the expected string dictionary. Only checked-row counts and status
are returned. Legacy plaintext credential columns are counted, never displayed or
automatically changed; their presence fails the gate for explicit remediation.
Oversized/malformed ciphertext or more than 10,000 encrypted rows blocks or fails.
Preserve the original `LEADZEN_SETTINGS_KEY` with the matched recovery set. Generating
a replacement for an existing installation makes saved credentials unreadable.

## Synthetic verification

Tests initialize disposable databases through real migrations. They cover control
and employee checks, valid protected settings, token mismatch, wrong host identity,
foreign UUIDs, symlinks/hardlinks/permissions/owners, missing physical schema/index,
old migration history, incompatible keys, legacy plaintext counts, foreign-key
violations, outstanding WAL, enabled/disabled features and unsafe public variables.
They assert unchanged database hashes and absence of created WAL/shared-memory files.
The graph child also runs with an invalid selected database and deliberately invalid
`DJANGO_SETTINGS_MODULE` and proves neither is accessed.

```bash
.venv/bin/pytest -q tests/test_operations_preflight.py tests/test_production_config.py tests/test_production_migrations.py
.venv/bin/python -m compileall -q leadzen/operations/preflight.py tests/test_operations_preflight.py
git diff --check
```

Implemented and tested locally; actual target-host configuration, current database
state, proxy/firewall/volume observations and execution of this gate on production
remain separate evidence. No migration, customer-data mutation or provider call
was performed by this implementation.
