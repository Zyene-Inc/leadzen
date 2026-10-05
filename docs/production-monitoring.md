# Operational monitoring and bounded alerts

The repository prepares private checks and templates; no production timer,
notification destination or external test delivery was installed/contacted.
Copy/review `compose/leadzen/monitor/monitor.json.example` into an owned 0600
private configuration before authorized installation. The monitor state directory
must be owned 0700; safe state/heartbeat files are 0600. Never put sink tokens or
backend credentials into release manifests or public dashboard variables.

The monitor reads its backend environment file as the configured service user;
the file must be owned by that user with mode 600, under an accessible private
parent. A root-owned `/etc/leadzen.env` loaded by systemd for the API cannot be
read directly by an unprivileged monitor. The template therefore names
`/srv/private/leadzen-runtime.env`: prepare an authorized exact private copy of
the current deployed environment, verify the matching bytes/keys privately, and
review ownership and update synchronization before installation. Do not loosen
the live file's permissions or assume a dated export is current.

```sh
python -m leadzen.operations.monitoring --config /etc/leadzen-monitor.json
```

Each check reports safe categories/counts and a nonzero exit for actionable
failures. It checks authenticated private `/api/health` and `/api/ready`, request
latency, API/scheduler systemd state, disk capacity, Linux available memory,
control/employee namespace, SQLite integrity/FKs, failed/stale saved jobs,
writer-lock age, actual scheduler pass progress and freshness of a verified
full native backup plus identical independent copy. Flags enabling outreach are
not health evidence. Scheduler heartbeat includes only pass status and timestamps;
the maintenance hold prevents a new pass and records the hold explicitly.
Employee child startup errors, nonzero exits and timeouts propagate a failed pass
to the scheduler heartbeat even if no job record was created. The existing
`SCHEDULER_PASS_FAILED` alert exposes these failures without leaking child output.
The durable heartbeat also retains `last_failed_at` through subsequent healthy
passes. `SCHEDULER_RECENT_PASS_FAILED` reports failures within the configured
`failure_window_seconds` (default 3600), so a 60-second monitor does not miss a
failed pass overwritten by the next 30-second success. The signal expires after
that reviewed window; it never retries or cancels the failed operation.
Namespace-index scratch copies use the same concurrent-change stamp validation
as the employee database probes; inconsistent live bytes are UNVERIFIED.

The production template enables bounded journal aggregation of application
requests over five minutes. It alerts on server-error counts, slow-request counts
and authentication failures, independently of the health probes. The runtime
owner needs read access to the API unit's journal. Missing evidence, unreadable
journals or a saturated 5,000-line window remain visible as UNVERIFIED alarms;
raw journal text, route identifiers and personal data never enter the report.
Tune the explicit thresholds using target-host load and normal traffic evidence.

Live database files are not opened by SQLite during monitor checks. DB/WAL bytes
are copied into scratch storage, source file stamps are checked for concurrent
changes, and SQLite queries run on the scratch copies. Busy/changing sources are
reported UNVERIFIED rather than corruption; readiness separately exercises the
live database. Corrupt files, namespace uncertainty and inaccessible files remain
visible. Checks never log account IDs, recipients, DB values, tokens or raw HTTP,
process, provider or exception text.

The configured thresholds need actual-host tuning and load evidence. A scheduler
pass can take several bounded employee child passes; choose the progress deadline
for the real employee count rather than hiding stale progress with an unlimited
timeout. Worker and lock deadlines expose held work; the monitor never retries a
send/purchase, cancels a job or kills a process. A maintenance backup defaults to
holding intake/services until explicit operator reconciliation, which monitoring
will expose. Incomplete backup staging is visible and is not a fresh backup.

## Notification authorization and test delivery

The default configuration has `alert.approved=false` and the default service
omits `--deliver-alert`. Changed failure/recovery categories are saved locally as
`BLOCKED_AUTHORIZATION_REQUIRED`. Identical state does not repeatedly notify.
Delivery failures persist as `DELIVERY_FAILED`, cause a nonzero command result,
and retry at a bounded interval (default one hour, minimum one minute). Safe error
categories remain visible even when the notification provider is down.

After fresh approval of the exact private destination and one bounded synthetic
test, the operator can set `alert.approved=true` in the private configuration and
enable `--deliver-alert` in the reviewed unit. The adapter accepts only verified
HTTPS on port 443, rejects redirects/credentials/query fragments and private DNS
addresses, pins the public socket and limits request/response size. One child
process gets an eight-second hard deadline covering DNS/TLS/headers/body; there
are no implicit provider retries. Payloads contain only source, PASS/FAIL and safe
issue code/severity pairs. Use a destination adapter that accepts this JSON shape.

The exact prepared external test command is:

```sh
python -m leadzen.operations.monitoring --config /etc/leadzen-monitor.json --deliver-alert
```

It remains **BLOCKED** until the sink URL/token, recipient/on-call ownership,
private approved configuration and current user authorization are established.
Do not claim external incident delivery from a local fixture test.

The synthetic regression explicitly delivered one safe JSON alarm to a temporary
`127.0.0.1` HTTP fixture with `allow_local_test=True`. This flag requires the
literal loopback HTTP fixture and cannot authorize an external destination. It is
not in production timer templates. Repeating the same failure produced no second
notification; timeout/failure tests preserved secret/PII omission.

## Installation and operator response

1. Review exact paths, runtime owner, private env/config/state permissions,
   thresholds, Linux/systemd assumptions and independent backup mount.
2. Run local checks and an authorized current isolated restore; inspect safe
   statuses. Missing host evidence is BLOCKED/UNVERIFIED, not a PASS.
3. Authorize/configure/test the exact notification sink and confirm on-call receipt.
4. Only then install/enable the reviewed monitor service/timer. No automatic
   deployment, external messaging or paid resource provisioning occurs here.
5. Alert on missed monitor runs as well as monitor failures using a separate
   host/service supervisor. If the host dies, its local monitor cannot deliver an
   alarm; independent external uptime/missed-heartbeat monitoring remains an
   installation gate.
6. For stale/failed jobs or locks, inspect conservative saved state and external
   acceptance/usage evidence before any retry. For stale backups, keep release
   promotion blocked and create/verify a fresh full recovery set.

Central aggregation, external monitor-of-monitor coverage, notification receipt,
current-host capacity and real provider/inbox/billing checks remain **UNVERIFIED**
until separately authorized operational verification. This implementation provides
actionable local evidence without declaring those external gates completed.
