# Production sign-in capacity incident — October 7, 2026

## Observed failure

The dashboard displayed “Sign-in is temporarily unavailable” while the public
backend timed out. On the Google Compute Engine `leadzen-api` VM, the journal
recorded an out-of-memory kill of `leadzen.service` at 14:25:55 UTC. At the
time, the VM used `e2-micro` with about 1 GB RAM and no swap. Browser SSH and
the public API subsequently became unresponsive. This is a host-capacity
failure, not evidence that one signed-in user exhausted a user quota. The
follow-up scheduler also logged a worker exit at 14:20:57 UTC and a 180-second
timeout at 14:24:52 UTC. Their relationship to the OOM kill is plausible but
unproven because the worker output was not retained.

## Recovery performed with owner approval

The owner approved a resize, investigation, and memory monitoring, then gave
separate approval for a billable 30 GB disk snapshot. The VM was gracefully
stopped. Google Cloud snapshot `leadzen-api-pre-resize-20261007` completed in
`us-central1`; the console showed it ready for use with 3.51 GB stored. The
stopped VM was changed to `e2-small` (2 GB RAM, shared CPU) and restarted,
retaining the static public IP `35.225.8.140`. No application code, database,
or user records were intentionally changed.

The public API health route returned the expected anonymous HTTP 401 in about
1.9 seconds. The dashboard login page returned HTTP 200. A synthetic invalid
login through the dashboard proxy returned the expected HTTP 401 in about
2.5 seconds, with no gateway 503. No real login credential or email was sent
for this check. On the VM, `leadzen.service` and `leadzen-followups.service`
were active after reboot, with zero systemd restarts at inspection. At
15:05 UTC, `free -m` showed 1960 MB total and 1275 MB available; there was
still no swap. No scheduler error appeared in the checked post-restart journal
window; this does not establish that every scheduled pass succeeded.

## Monitoring work

The official Google Cloud Ops Agent v2.72.0 was installed on the VM. Its
host-metrics collector is active. The configured logging pipeline has no
receivers and agent self-log collection is disabled, so this installation is
for host metrics rather than production log ingestion. Google Cloud Monitoring
email channel `LeadZen support alerts` was created for the owner-approved
`support@zyene.com` destination. No test notification was sent.

**Pending verification:** The Ops Agent's metric export currently returns
`PermissionDenied` for `monitoring.timeSeries.create` in project
`zyene-reviews`. The VM runs as
`1013344814588-compute@developer.gserviceaccount.com` with Monitoring API
write scope, but that principal lacks the project `Monitoring Metric Writer`
role. The role grant is prepared in the Google Cloud IAM UI and awaits the
owner's separate action-time confirmation. The alert policy is also pending;
do not claim that memory notifications are active until a `state=used` memory
metric appears and the policy is created and verified. Google Cloud's generic
email channel may require recipient verification or a live event before receipt
can be confirmed; no real test email is authorized here.

## Remaining operational risks

- The old scheduler worker exit and timeout need cause analysis from future
  safe telemetry. Do not rerun a scheduler pass merely to diagnose: it can
  perform external send or paid provider work.
- Two GB provides headroom at idle but does not establish capacity under
  concurrent requests or longer scheduler jobs. The VM still has no swap.
- A host-only memory alert cannot report every application failure or a host
  outage that prevents metrics from being sent. The repository's broader
  [production monitor](production-monitoring.md) remains a separate, unverified
  installation gate.

