# Daily Autopilot — local validation, October 3, 2026

The later [complete code and logic cross-check](daily-autopilot-crosscheck-2026-10-03.md)
records additional repairs and the final full runs: **993 backend tests** and
**1,055 frontend tests** passed. Evidence below describes earlier snapshots and is
retained as history; overlapping counts must not be added together.

## Before / After / Why

Before: employees prepared and reviewed each initial batch. The optional scheduler
could send only explicitly reviewed follow-ups; it could not discover leads or send
new initial outreach under a recurring policy.

After: Outreach has one Daily Autopilot switch, a first-enable scope/authorization
form and compact saved results. At 10 AM weekdays, the isolated worker can discover
new leads, buy verified emails within caps, generate personal sequences, validate
and send through the existing campaign engine. Replies stop follow-ups. Employees
can inspect saved discovery/messages, pause a sequence, stop a contact or turn the
policy off. Home surfaces held daily runs and policy issues.

Why: remove daily screen switching and repeated approvals after a clearly scoped
standing authorization, while keeping the same contacts, suppression, history,
mailbox capacity, pacing, worker ownership and send safeguards. Automatic authorization
is distinct from human review in storage and in the UI.

## Verification

All external adapters used in these tests were synthetic. No real email, mailbox
sync, paid provider operation, production migration, deployment or service enablement
was performed.

- Full backend snapshot: **954 passed**, one existing pydantic-ai event-loop
  deprecation warning (`/tmp/leadzen-autopilot-full-backend.log`).
- After subsequent schedule/transport/timeline refinements: **139 passed** across
  Autopilot, email transports, automatic follow-ups, campaigns and lead timeline
  (`/tmp/leadzen-autopilot-last-backend.log`).
- Final preparation/status/discovery refinements: **87 passed**, including all
  **33 Autopilot tests**, discovery-live and Workspace attention/inbox tests
  (`/tmp/leadzen-autopilot-validation-final.log`). Counts are overlapping snapshots,
  not additive totals.
- Final cancellation and pause refinement: **35 Autopilot tests passed**
  (`/tmp/leadzen-autopilot-final-safety.log`). Stopping or pausing discovery cannot
  continue into drafting/sending, and cancellation status is not overwritten.
- Final independent review found and repaired two pipeline defects: async lookup
  handles needed same-session collection, and terminal recipients could block the
  queue. **177 passed** across Autopilot, discovery-live, campaigns, follow-ups and
  transports (`/tmp/leadzen-autopilot-review-complete.log`); **81 passed** in focused
  Chat/discovery regressions (`/tmp/leadzen-autopilot-chat-review.log`). The earlier
  wider review command was interrupted and is not counted as a completed run.
  The real pinned command/job/cycle/lookup is now exercised with synthetic HTTP
  and time: one selected POST, owned polling to verified completion, unrelated
  queued/in-flight rows untouched, revocation during wait, and an unknown POST
  handle retained without resubmission. Queue regressions cover replies,
  suppression, deletion and completed contacts, plus mutable mailbox capacity
  and accurate morning catch-up display.
- Final expected-stop status refinement: **44 Autopilot/regression tests passed**
  (`/tmp/leadzen-autopilot-review-final-safety.log`). Replies and opt-outs stop
  only their recipient and do not create a misleading service-failure alert.
  These focused runs overlap the earlier snapshots; their counts are not summed.
- Actual two-employee database/router isolation and fresh subprocess worker bootstrap:
  **1 integration scenario passed** (`/tmp/leadzen-autopilot-isolation.log`). The
  complete backend run also includes the scenario. Foreign workspace hints cannot
  read policies/results or disable another employee's policy.
- Full frontend: **1,053 passed / 16 files**
  (`/tmp/leadzen-autopilot-frontend-final.log`). Updated older mocks for the new
  read-only Autopilot request; the theme test now waits for initial attention data
  before measuring that theme changes make no domain requests.
- Final UI refactor: **434 passed / 3 files** (Autopilot, Workspace controls, themes;
  `/tmp/leadzen-autopilot-ui-last.log`). Explicit consent, double-click guards,
  error preservation, Off, cancel/Escape/focus are exercised.
- TypeScript and optimized Next.js build passed. Migration drift check reports
  **No changes detected**. `git diff --check` passed.
  TypeScript/build were refreshed after the review
  (`/tmp/leadzen-autopilot-review-types.log`, `/tmp/leadzen-autopilot-review-build.log`).
- React Doctor changed-file scan: 100/100 over only 10 tracked files; this is not
  a whole-app result. Full scan over 125 files: **67/100, zero errors, 29 warnings**,
  matching the prior overall score. No reported diagnostic targets the new
  Autopilot component after refinement. Remaining application complexity and
  existing effect/formatting warnings are not hidden or suppressed.

Behavior coverage includes weekday/noon catch-up/DST, daily uniqueness across policy
versions, only today's verified contacts, personal copy in previews and actual sends,
no fabricated human approval, daily/monthly conservative provider reservations,
request failure without reservation refunds, paused/interrupted/uncertain work,
revocation and changes at the send boundary, reply/opt-out/inbox failure, and SMTP
rechecks after connection. Failed or ambiguous sends are never automatically retried.

## Limits and rollout

Browser visual/responsive verification remains unverified: the earlier in-app
browser attempt was blocked by its URL security policy. No alternate browser or
raw-control workaround was used. Automated UI tests and the build are not visual proof.

The disposable preview API was restarted and migrated through 0016 using its existing
fixture encryption key; local Next.js is available on port 3001. External providers
and campaign sending remain disabled in that preview. No production state is claimed.

Migration `0016_daily_autopilot` is new. Deploy all current migrations to control and
initialized workspace databases only in an authorized rollout. Both API and scheduler
must intentionally enable `LEADZEN_AUTOPILOT_ENABLED`; it defaults off. Employee
policy authorization is still required separately.

Working days mean Monday–Friday, with no holiday calendar. AI limits count requests,
not currency spend. No deliverability/inbox-placement claim is made. Interrupted
preparation is held for inspection rather than replaying uncertain chargeable work;
validated pending sends resume normally. Heartbeat is shown in-app; external alerting
has not been provisioned. See [architecture and operations](daily-autopilot.md).
