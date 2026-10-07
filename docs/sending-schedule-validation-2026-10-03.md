# Employee sending hours — local validation, October 3, 2026

## Before / After / Why

Before: Outreach displayed fixed weekday hours. Employees could not choose their
weekly days or times in Settings, and Autopilot had separate discovery hours.

After: Settings → Sending hours → Edit provides Monday–Sunday selections,
Weekdays/Every day shortcuts, minute-precision start/end times and an IANA timezone.
The schedule repeats weekly. Outreach, final message review, Autopilot authorization
and lead timelines show the effective schedule. Autopilot discovery starts on the
same selected days and start time, with the existing two-hour catch-up allowance
clipped to closing time. Sending and follow-ups use the approved window.

Why: one employee-owned schedule removes conflicting clocks and lets employees
understand when discovery and outreach will happen. Optional explanation uses the
shared accessible help control. Required approval terms remain visible.

## Logic and boundaries

- `SiteConfig.sending_schedule` is stored in each routed employee database. New
  migration `0017_siteconfig_sending_schedule` is additive with an empty legacy
  default; control and all initialized employee databases need it at release.
- The server validates exact keys, a nonempty set of integer weekdays, strict
  24-hour HH:MM times, end after start within one day, and a valid IANA timezone.
  One shared time window applies to all selected days. Overnight windows and
  holiday calendars are not supported; selected days include holidays.
- New Autopilot authorizations take the schedule from Settings, ignoring a
  browser-supplied replacement. Saving Settings does not start discovery or send.
  Setup fingerprints hold changed automatic approvals and queued reviewed requests
  until a fresh review. Migration alone may also invalidate older fingerprints.
- Without a custom schedule, legacy initial outreach retains its country-based
  weekday 8 AM–8 PM window. Historical automatic follow-ups retain weekday
  9 AM–5 PM in their saved timezone, and historical Autopilot discovery retains
  weekday 10 AM. Existing authorization is never silently widened to weekends.
- For custom schedules, working-day delays count selected sending days;
  calendar-day delays use calendar dates and wait for a permitted opening.
  DST gaps advance to a real permitted minute; repeated hours use actual instants.
  Preparation deadlines clip to the first actual window closure.
- Daily mailbox headroom, attempt counts and receiver-pause ledgers use the
  selected timezone's day. Existing capacity, five-minute pacing, account access,
  canonical recipient checks, approval expiry, inbox sync and reply/opt-out stops
  remain enforced. Reviewed human Inbox replies remain immediately sendable.
- HTTP checks run after TLS and before request bytes. SMTP checks run at sendmail
  and again after the DATA response before body bytes. A known pre-submission
  schedule closure safely defers the pending message without a false failure.
  Permission changes and uncertain transport failures remain held for review.
  An accepted message remains recorded even if the window closes before QUIT.

## Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Full backend suite | **1,112 passed**, one existing dependency deprecation warning | `/tmp/leadzen-sending-schedule-backend-full.log` |
| Full frontend suite | **1,089 passed / 17 files** | `/tmp/leadzen-sending-schedule-ui-full.log` |
| Final schedule / Autopilot UI after copy refinement | **19 passed / 2 files** | `/tmp/leadzen-sending-schedule-ui-final.log` |
| Schedule execution checks | **27 passed** | `/tmp/leadzen-sending-schedule-debug.log` |
| DST / real synthetic SMTP boundaries and existing helper / adapter checks | **111 passed**, including 14 new boundary cases | `/tmp/leadzen-sending-schedule-boundaries.log` |
| TypeScript | Passed | `/tmp/leadzen-sending-schedule-types-final.log` |
| Optimized Next.js build | Passed | `/tmp/leadzen-sending-schedule-build.log` |
| Django built-in system checks | Zero issues | `django.core.checks.run_checks()` in isolated test settings |
| Migration drift | No changes detected | Isolated `makemigrations --check --dry-run` |
| React Doctor tracked changes | 100/100, no findings | `/tmp/leadzen-sending-schedule-react-diff.log` |
| React Doctor full tree | 68/100, zero errors, 32 warnings | `/tmp/leadzen-sending-schedule-react-full.log` |

These are separate scopes and snapshots; their counts must not be added together.
The full frontend run preceded the final follow-up-label refinement, which the
19-test focused run and final TypeScript check cover. Full React Doctor covers the
untracked components omitted by its tracked scan; its score did not regress from
the previous 67/100. Existing complexity/maintainability findings remain. New
schedule-editor array-lookup warnings concern seven bounded weekday choices and
do not indicate a measured performance issue; no diagnostic was suppressed.

Coverage includes exact opening/closing minutes, selected weekends, discovery
catch-up, daily uniqueness, reauthorization, approval changes during TLS/DATA,
safe deferral versus uncertain sends, context cleanup, Inbox reply exception,
timezone day boundaries, US spring/fall changes, Lord Howe's half-hour jump,
Santiago's skipped midnight, malformed settings, cancel/Escape/focus, double
submission, retained drafts on rejection and legacy labels. Real two-employee
SQLite tests verify independent schedules, spoofed workspace-ID rejection and
exact schedule inclusion in the employee's own consistent database backup.

## Local preview and limits

The disposable fixture `/private/tmp/leadzen-preview.vd9NXa` was retained with its
fixture encryption key and migrated through 0017, verified in all four disposable
control/employee databases. The API was restarted after
final source changes; Next.js is running on port 3001. Authenticated local reads
confirm Settings, Outreach and Autopilot agree on the same schedule. Preview
Autopilot execution and campaign sends remain disabled; existing reviewed sends
use synthetic acceptance only.

Browser visual validation remains unverified following the earlier URL security
policy block. No alternate-browser workaround was used. The day grid was reviewed
from source and made container-responsive to avoid the narrow desktop overflow.
The owner can review [Settings locally](http://localhost:3001/settings#sending-hours).

Local only: no deployment, production migration, service activation, real mailbox
sync, provider charges or real email was performed. This does not establish live
delivery, provider latency or inbox placement.
