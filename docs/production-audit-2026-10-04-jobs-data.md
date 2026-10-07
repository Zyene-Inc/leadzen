# Domain, database, background jobs and provider audit — October 4, 2026

This report covers the assigned domain source, not an independent approval of the full release. The companion [per-file inventory](production-audit-2026-10-04-jobs-data.json) records **48 inspected source paths / 5,750 source lines**, hashes, and review notes. Accounts, MCP, Chat orchestration, primary web/settings/CLI and frontend are reviewed by the other audit tracks. No live provider request, send, paid lookup, production write or deployment was performed.

## Confirmed findings and fixes

| Severity | Finding | Smallest implemented fix and evidence |
| --- | --- | --- |
| HIGH | `honor_saved_optouts` inspected only the first 500 EMAILED contacts. Later exact STOP replies were omitted during classification-free automatic inbox sync, weakening terminal suppression. | Query latest inbound fields in SQL, stream all matching conversations in 200-row chunks, and use the canonical shared address suppression helper. A regression covers the **501st** contact and a second canonical contact with the same address. Existing malformed/inbound-authority tests remain intact. |
| HIGH | Manual cold campaigns did not perform the address-level initial-attempt dedup already enforced by reviewed outreach/Autopilot. A finder/manual duplicate could reopen an attempted address. | Exclude attempted addresses from manual cold preview, stop before claim, and recheck immediately at the HTTP/SMTP delivery guard, excluding only the current durable message record. A competing send during TLS writes no HTTP bytes. Autopilot's existing normal `ContactStopped` semantics and repeated opted-in/transactional mail are preserved. |
| HIGH | `email_api.post_email` checked HTTPS/public DNS, but did not recheck the configured EMAIL host allowlist at the sink. Direct/legacy callers could bypass form validation. | Revalidate approved HTTPS URL, credentials/query/fragment/port constraints immediately before opening a socket; reject request bodies over 256 KiB. Tests prove unapproved/malformed destinations and oversized payloads never create a socket. Existing provider response/error/idempotency tests pass. |
| HIGH | Dependency mail/finder/provider logging can include recipient/mailbox identities, content and raw provider exception strings. Redacting only the developer-log view does not protect persisted worker logs. | Install an idempotent production LogRecord factory before startup adapters. In `LEADZEN_ENV=production`, dependency/provider/HTTP SDK raw messages, arguments, exception traces and stack information become a safe category message before file/console handlers. Levels and logger names remain; LeadZen's safe job summaries remain visible. Tests inject synthetic tokens and private email addresses into arguments/exceptions and verify neither appears. |
| MEDIUM | Legacy plaintext LLM/mailbox fields remained after dashboard credential migration, and empty dashboard values did not remove stale child environment exports. | Saving dashboard settings clears the supported legacy plaintext LLM/mailbox/BetterContact copies after encrypted save. Explicit dashboard clears remove child exports instead of retaining stale values. Protocol/header control characters in all dashboard credential types are rejected. CLI-only fallback is retained. **This does not certify preexisting production rows/backups; see remaining actions.** |
| MEDIUM | Saving mailbox settings after the authorized worker field adapter was installed encrypted the stored password twice. A single read/decrypt returned ciphertext rather than the password. | Let the active encryption field adapter encode the raw in-memory value; preserve explicit encrypted storage in ordinary API processes. A synthetic regression checks the raw database token decodes exactly once and worker reads recover the intended value. No existing rows were rewritten automatically. |
| MEDIUM | Nonstream provider body reads used socket idle timeouts. A trickling body could exceed the operation budget and leave a cancelled async thread reading. | Shared chunk reader enforces byte limits and an absolute response deadline. A deadline timer shuts down the active or HTTP-detached response socket to interrupt blocked reads. AI nonstream body budget is 40 seconds; email body budget is 10 seconds; the deadline includes prior opening time. Tests cover trickle, oversized body, blocked socket and detached socket. DNS/TCP/TLS/header behavior remains subject to the socket/OS bounds described below. |
| MEDIUM | Follow-up scheduler and Autopilot dispatcher discarded child nonzero exits/timeouts along with all output, hiding failures before a workspace issue could persist. | Emit generic ERROR summaries with exit code or execution-deadline category; raw child output remains discarded. Tests verify nonzero/timeout visibility without synthetic exception/token output. |
| MEDIUM | CRM pages issued per-contact queries; a synthetic 100-profile page used **501 SQL queries**. Initial outreach eligibility scanned the entire ready pool into memory and used repeated safety queries per contact. | Batch bounded page facts using canonical profile/decision/latest receipt/session/reply/latest acceptance records. The same synthetic page now uses **4 queries**. Outreach uses equivalent `Exists` safety conditions, SQL count and LIMIT 25 selection: **2 queries** for count + selection. Tests compare exact payloads and preserve suppressed/deleted/prior-attempt/inbound/campaign exclusion. |
| MEDIUM | `DiscoveryLookup.source_id` had no index despite global paid-lookup idempotency and CRM receipt checks. | Add the additive `0019_discoverylookup_source_index` migration. No row deletion or identity change. Apply to control and initialized workspace databases in the coordinated maintenance window. |

The first new boundary run exposed an Autopilot regression: a new manual duplicate guard intercepted a normal automatic stop as a generic error. The helper was restricted to manual cold campaigns; the original Autopilot guard remains authoritative. Tests were not weakened or disabled.

## Security and domain review

- All assigned public views use the existing live-account/workspace access decorator, except service helpers that are invoked only through authorized routes/workers. Canonical contact/campaign/thread IDs resolve within the server-selected employee database; actor-owned reviews/discovery sessions additionally constrain the actor/thread. Full router/auth/MCP correctness is covered by the backend-security track, not asserted solely from these domain functions.
- Reads return saved records and bounded pages; they do not probe providers, buy addresses or send mail. Drafting, exact human review/final confirmation and standing automatic authorization remain distinct.
- Delivery checks live account/policy/access, current content/identity, suppression/deletion/opt-in, reply state, New York schedule, pacing and caps. SMTP rechecks at DATA body submission and HTTP rechecks after TLS before request bytes. Acceptance evidence stays distinct from inbox delivery.
- Queued job/recipient transitions use durable conditional updates; workspace and scheduler file locks serialize delivery processes. Interrupted or ambiguous sends remain `sending`/`review`, never automatically retried. Paid reservations and unknown provider usage remain conservative, not released on failure or presented as zero.
- Discovery caps action count, candidates, model requests, provider calls and paid receipts; profile-only discovery forcibly disables email/phone enrichment. Selected profile identity, setup revision, scope expiry and owned handles are checked again before provider actions. The cross-operator upstream contacts hub is disabled in monitored workspace discovery.
- SSRF controls cover host allowlists, HTTPS/SMTP TLS/IMAP TLS, verified certificates and pinned public-address sockets; private/link-local/loopback resolutions and redirects are rejected. Requests have bounded payload/response sizes. ORM queries do not interpolate user SQL; no shell-built domain commands or unsafe user file paths were found in assigned source.
- Model/profile/inbound text is untrusted data and cannot mint recipients, send/spend approval, connection credentials or external tools. Strict plain-text draft schemas and exact draft-ID/content checks remain.
- No customer subscription/card/payment/webhook system exists in assigned source. Provider AI/enrichment costs are the applicable financial boundary; no live billing/credit validation occurred.
- No arbitrary file upload/storage interface exists in assigned modules. Worker log access is bounded, job-ID/server-path-owned, regular-file-only and no-follow; it is separate from normal activity. Export/upload surfaces are reviewed in the web/settings audit.

## Database and migration review

All config migrations 0001–0019 and the current models were inspected. Existing migrations are additive except the intentional country-field rename, Chat active-run constraint replacement and New York metadata normalization. Foreign keys use cascade for dependent workspace rows and PROTECT for reviewed send evidence/Autopilot authorization records. Constraints prevent duplicate campaign/deal rows, review/deal rows, session/source candidates/lookups, request IDs, active actor runs, simultaneous generating reviews, enabled policies and same-actor/workday automatic runs.

Migration 0018 retains absolute timestamps and immutable policy scope, but its reverse is a no-op for wall-clock metadata; reverting migrations alone does not restore old metadata. Use the coordinated backup/restore rollback plan. Migration 0019 adds only the hot source-ID index; SQLite index creation takes a write lock, so pause intake/workers and use the maintenance window. No live database or production schema was modified by this track. Root verification owns clean/schema-upgrade/preservation/rollback scenario results.

## Remaining operational issues and UNVERIFIED items

| Severity / status | Remaining item / action |
| --- | --- |
| HIGH / UNVERIFIED | External alerting, follow-up-only scheduler heartbeat/watchdog, central API/DB/provider failure alerts and on-call delivery are not established by source alone. Autopilot policy heartbeat/issue and new safe process-exit logs provide local evidence, but require operator monitoring and tested alerts. |
| HIGH / UNVERIFIED | Full-server backup scheduling, encryption-key recovery, retention/access controls and restored control-plus-all-workspaces consistency need an operator-owned restore drill. A workspace export is not a full backup. |
| HIGH / UNVERIFIED | Inspect **presence/counts only** of legacy plaintext credential fields/mailbox rows in actual control/workspace databases. Saving encrypted dashboard settings now clears supported shadow copies, but existing CLI-only rows, old worker logs and backup copies were not destructively rewritten or deleted. Rotate/remediate retained old credentials and enforce access/retention under an approved plan. |
| HIGH / UNVERIFIED | Real provider keys/billing/limits, SMTP/IMAP operations, sender-domain SPF/DKIM/DMARC, mailbox acceptance/replies, delivery/inbox placement and non-Gmail plus-address unsubscribe routing require fresh, separately authorized live checks. No synthetic success certifies those. |
| MEDIUM / UNVERIFIED | SQLite/filesystem locking on the actual host, multi-instance sharing, cold-start model memory/ML downloads, disk exhaustion/retention and workload capacity need production-host/load measurements. Do not scale copies with independent local workspaces or assume network filesystem flock semantics. |
| MEDIUM / UNVERIFIED | DNS resolver delay and TCP/TLS/header parsing are bounded by OS/socket behavior; the new total deadline specifically prevents trickling/blocked **body** reads. Streaming retains its existing 90-second progress deadline plus bounded per-read socket behavior. Adversarial DNS/TLS/header stalls were not live-tested. |
| MEDIUM | Other bounded campaign/review/history serializers can still perform per-recipient queries; their caps make the work finite, but the full production workload and large historical datasets were not load-certified. CRM and eligibility hotspots were fixed rather than hidden behind tests. |
| LOW | One installed `pydantic_graph` test reports an event-loop deprecation warning. Dependency/framework compatibility and CVE scan results belong to the repository/dependency audit. |

## Production environment names relevant to this track

Secrets are stored server-side through workspace settings, not required as public frontend variables. The consolidated release report owns the full required environment table. Relevant names only:

- `LEADZEN_SETTINGS_KEY`
- `LEADZEN_ENV`
- `LEADZEN_DB`
- `LEADZEN_WORKSPACE_ROOT`
- `LEADZEN_LLM_HOSTS`
- `LEADZEN_MAIL_HOSTS`
- `LEADZEN_EMAIL_HOSTS`
- `LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED`
- `LEADZEN_AUTOPILOT_ENABLED`

The service flags default off; enabling them is separate from exact employee authorization. Internal worker identity names `LEADZEN_CONTROL_DB`, `LEADZEN_ACTOR_ID` and `LEADZEN_WORKSPACE_ID` are generated server-side, not browser-supplied deployment secrets. `OPENOUTFIND_*` / `OUTSEND_*` are internal/CLI dependency interfaces; dashboard workers scrub inherited provider exports and populate their own workspace settings.

## Verification commands and results

Commands run from repository root with disposable pytest databases and synthetic adapters:

1. Baseline assigned-domain regression:

```sh
.venv/bin/pytest -q tests/test_campaigns.py tests/test_reviewed_outreach.py tests/test_automatic_followups.py tests/test_autopilot.py tests/test_autopilot_discovery.py tests/test_autopilot_regressions.py tests/test_autopilot_send_boundaries.py tests/test_discovery.py tests/test_discovery_live.py tests/test_email_transports.py tests/test_runtime_settings.py tests/test_bettercontact_settings.py tests/test_lead_crm.py tests/test_lead_timeline.py tests/test_home.py tests/test_activity.py tests/test_branding.py tests/test_sending_schedule.py tests/test_sending_schedule_boundaries.py tests/test_sending_schedule_execution.py tests/test_new_york_time.py
```

**488 passed in 136.25 seconds** before fixes.

2. Initial boundary/settings/campaign/transport group:

```sh
.venv/bin/pytest -q tests/test_production_domain_boundaries.py tests/test_runtime_settings.py tests/test_email_transports.py tests/test_autopilot_send_boundaries.py tests/test_campaigns.py tests/test_bettercontact_settings.py
```

First run **100 passed / 1 failed** (normal Autopilot stop was incorrectly intercepted). After the source correction, **101 passed in 107.51 seconds**.

3. Scalable STOP/eligibility and existing send paths:

```sh
.venv/bin/pytest -q tests/test_production_domain_boundaries.py tests/test_reviewed_outreach.py tests/test_automatic_followups.py tests/test_autopilot_send_boundaries.py tests/test_outreach_workspace.py
```

**123 passed in 56.51 seconds**.

4. CRM batching and related saved-record flows:

```sh
.venv/bin/pytest -q tests/test_production_domain_boundaries.py tests/test_lead_crm.py tests/test_lead_timeline.py tests/test_outreach_workspace.py tests/test_discovery.py tests/test_discovery_live.py tests/test_home.py tests/test_activity.py
```

**145 passed in 55.28 seconds**.

5. Broader final domain group after production logging:

```sh
.venv/bin/pytest -q tests/test_production_domain_boundaries.py tests/test_runtime_settings.py tests/test_email_transports.py tests/test_autopilot_send_boundaries.py tests/test_campaigns.py tests/test_bettercontact_settings.py tests/test_reviewed_outreach.py tests/test_automatic_followups.py tests/test_lead_crm.py tests/test_lead_timeline.py tests/test_outreach_workspace.py tests/test_activity.py
```

**261 passed in 81.11 seconds**.

6. Final new response-deadline and actual provider wire/SDK regressions:

```sh
.venv/bin/pytest -q tests/test_production_domain_boundaries.py tests/test_email_transports.py tests/test_chat_ai.py tests/test_provider_stream_formats.py tests/test_autopilot_send_boundaries.py tests/test_reviewed_outreach.py
```

**164 passed, 1 deprecation warning, in 37.75 seconds** after the response deadline fix.

7. Final mailbox adapter/save ordering and settings/send regression:

```sh
.venv/bin/pytest -q tests/test_production_domain_boundaries.py tests/test_runtime_settings.py tests/test_email_transports.py tests/test_autopilot_send_boundaries.py tests/test_reviewed_outreach.py tests/test_campaigns.py
```

The new focused regression confirmed that one decryption returned a second encrypted token before the fix. After the fix, **148 passed in 41.32 seconds**. This is the latest domain source snapshot.

8. Reproducible disposable query measurement:

```sh
.venv/bin/python tests/scenarios/production_domain_measurements.py
```

Production CRM serializer uses **4 queries** at 1, 10 and 100 profiles; individual serializers use 6, 51 and 501. The 100-profile page measured **0.012 seconds** versus **0.1342 seconds** for the old individual loop on this tiny fixture. Outreach count plus 25 selected contacts uses **2 queries**. These are local comparative observations, not a load-capacity certification.

9. Schema drift, syntax and whitespace:

```sh
.venv/bin/python manage.py makemigrations --check --dry-run --settings=tests.settings
.venv/bin/python -m py_compile leadzen/crm.py leadzen/outreach.py leadzen/configuration.py leadzen/email_api.py leadzen/scheduler.py leadzen/autopilot_dispatch.py
.venv/bin/python -m py_compile leadzen/provider_io.py leadzen/production_logging.py leadzen/ai.py leadzen/email_api.py
.venv/bin/python -m py_compile leadzen/mailboxes.py
git diff --check
```

**No model migration drift; syntax and whitespace checks passed.** Full final clean-install/backend/frontend/build/container/migration/startup results are consolidated by the parent audit and should supersede overlapping focused snapshots.
