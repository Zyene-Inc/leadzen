# Fixed New York time — local validation, October 3, 2026

## Before / After / Why

Before: Settings offered an editable IANA timezone; old sender windows derived
their zone from operator country, Django daily totals used UTC, and some date
renderers used the browser's local timezone.

After: **America/New_York is the only platform business timezone.** Settings keeps
weekly days and start/end times editable and shows “New York (Eastern Time)” as a
read-only label with optional daylight-saving help. Schedules, Autopilot discovery,
follow-ups, mailbox ledgers, Home/Chat daily totals, greetings, history groups,
Activity, Inbox, discovery status, approval expiry and timelines use New York.
EST/EDT changes apply automatically, including gap/fold boundaries.

Why: every employee sees and authorizes the same business clock, independent of
computer timezone and identity country. The request changes the business timezone;
it does not restrict employee country metadata or overwrite external mail facts.

## Implementation and existing records

- `leadzen/timezone.py` defines the server clock and source-owned adapters for
  the pinned CLI sender's operator timezone and aware working-day arithmetic.
  Eagerly imported mailbox/outreach aliases receive the same clock.
- Django `TIME_ZONE` is America/New_York and `USE_TZ` remains true. Timestamp
  persistence and wire ISO instants remain UTC-aware; there is no fixed -5-hour
  offset or rewriting of accepted/send/due times.
- Settings accepts only the canonical America/New_York value; another valid
  timezone, an alias or a malformed value is rejected before any update. Effective
  reads of previously saved foreign-zone schedules retain days and hours while
  using New York. Autopilot derives its timezone from server Settings.
- New migration `0018_new_york_time` normalizes schedule, saved setup draft and
  campaign timezone metadata and updates the campaign model default. It preserves
  selected days/hours, connections, personal messages, due/send timestamps, daily
  run evidence and immutable historical policy scopes. The operation is idempotent
  and makes no provider request or send.
- The business-clock value is part of reviewed-request and automatic-follow-up
  fingerprints. Earlier approvals are held for fresh review, including previous
  New York approvals. A foreign historical Autopilot scope is also explicitly
  blocked even if someone replaces its hash. Its read API returns the current
  New York clock with a setup-change hold and no scheduled start; audit evidence
  remains stored unchanged. Reapproval never resurrects stopped recipients.
- `dashboard/lib/date-time.ts` centralizes fixed-zone formatting, New York day
  keys and hour selection. Caller-supplied timezone options cannot override it.
  History grouping uses calendar dates rather than assuming DST days last 24 hours.
  Original ISO values remain in semantic dateTime attributes.

## Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Full backend run | **1,136 passed**, one outdated India-zone timeline assertion corrected afterward | `/tmp/leadzen-new-york-backend-full.log` |
| Final timeline suite after test-only correction | **16 passed** | `/tmp/leadzen-new-york-timeline.log` |
| New York backend and schedule suites | **156 passed** | `/tmp/leadzen-new-york-backend-tests.log` |
| Full frontend | **1,107 passed / 18 files** | `/tmp/leadzen-new-york-ui-full.log` |
| Settings/Autopilot/controls | **373 passed** | `/tmp/leadzen-new-york-ui-tests.log` |
| Date rendering and existing presentation | **154 passed** | `/tmp/leadzen-new-york-dates.log` |
| New York cases with host TZ=Asia/Tokyo | **14 passed** | `/tmp/leadzen-new-york-dates-tokyo.log` |
| TypeScript | Passed | `/tmp/leadzen-new-york-types.log` |
| Optimized Next.js build | Passed | `/tmp/leadzen-new-york-build.log` |
| Django built-in system checks | Zero issues; current/default/dependency clock is New York | `django.core.checks.run_checks()` in isolated test settings |
| Migration consistency | No changes detected | `/tmp/leadzen-new-york-migrations.log` |
| React Doctor tracked scan | 100/100, no findings | `/tmp/leadzen-new-york-react-diff.log` |
| React Doctor full tree | 70/100, zero errors, 28 warnings | `/tmp/leadzen-new-york-react-full.log` |

Counts are separate scopes and must not be added together. Full React Doctor
covers the untracked application files omitted by its tracked scan. Its score
improved from the preceding 68/100; remaining warnings concern existing complexity,
state/fetch patterns and the seven-option weekday lookup. No findings were hidden.
The full backend run had one failing historical assertion expecting an India
timezone; actual output already correctly used New York and preserved days/hours.
Only that test assertion/name changed after the run. The 16-test final timeline
suite passed; the entire backend suite was not repeated after this test-only
correction. One existing dependency event-loop deprecation warning remains.

Regressions check strict foreign-zone rejection, stale cached setup/summary
normalization, no editable timezone, preserved days/minutes, UTC midnight versus
New York midnight, winter/summer offsets, spring/fall clock jumps, calendar groups,
Autopilot expiry and same-day discovery uniqueness after UTC midnight. Real
two-employee SQLite tests retain isolation with different schedules in the same
zone. Migration tests use historical Django models, preserve immutable approval
and accepted/due evidence, and verify reruns and no external effects.

## Preview and release status

The existing disposable preview `/private/tmp/leadzen-preview.vd9NXa` and its key
were retained. All four control/employee databases were migrated through 0018.
The API and dashboard were restarted; [Settings is available locally](http://localhost:3001/settings#sending-hours).
Authenticated API reads confirm New York in Settings, Outreach and Autopilot.
A synthetic foreign-zone PUT returned 400 and left the saved schedule unchanged.
Autopilot execution remains disabled; preview campaign sends remain blocked and
reviewed acceptance is synthetic only.

Browser visual inspection remains unverified following the earlier URL-policy
block; no alternate browser or raw-control workaround was used. Local changes
were checked with source review, API integration and automated UI tests.

No deployment, production migration, real email, live mailbox sync, provider
charge or service activation was performed. During an authorized release, apply
0018 to control and initialized employee databases and review the existing approval
holds before enabling delivery. Retain the normal backup/drain/release procedure.
