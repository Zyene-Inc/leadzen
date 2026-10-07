# Daily Autopilot — code and logic cross-check, October 3, 2026

## Outcome

The second audit found concrete gaps beyond the earlier passing tests. They were
fixed and covered by regressions. The final complete backend and frontend suites,
TypeScript, production build, Django system checks and migration drift check pass.
This is local implementation evidence, not certification of live delivery or a
production rollout. No real provider request, paid operation, mailbox sync, email,
production migration, deployment or service enablement occurred.

## Before / After / Why

Before: the shared finder could consume today's quota with older unfinished
profiles; Autopilot would then correctly exclude those profiles and send nothing.
Manual reviewed messages on another contact ID could escape address deduplication.
An authorization revoked during an HTTP connection could pass the earlier guard.
Saved warnings and some saved-message UI paths could misrepresent the actual state.

After: only the current session's genuinely new profiles count toward the daily
discovery goal; existing outreach is checked by address again at first delivery;
HTTP authorization is rechecked after connection before request bytes; and saved
status/messages remain inspectable through the compact Outreach interface.

Why: the employee's switch must produce bounded daily work, avoid duplicate contact,
honor Off at the actual external boundary, and explain waiting/held results clearly.

## Scope and repairs

The audit traced setup and policy authorization, actor/workspace identity, weekday
and timezone scheduling, daily uniqueness, worker dispatch/locks, discovery and
enrichment ownership, personal copy, quotas, initial sends, follow-ups, mailbox
sync/replies, opt-outs, cancellation, restarts, status, frontend/API wiring and
release configuration. Independent reviewers covered discovery, delivery and
UI/release wiring; shared-source changes were verified in the final full suites.

1. **Daily discovery cohort.** The finder counts and qualifies only profiles
   discovered in this session with source IDs beyond its saved starting point.
   Older pending/ready profiles and unrelated profiles created during the run do
   not consume the daily target or AI qualification cap. A cold finder continues
   beyond an all-familiar page. Free discovery cannot poll/buy old lookups. Cached
   and first-import finder aliases release their temporary session guards on exit.
2. **Duplicate outreach.** Case-insensitive reviewed-email checks include pending,
   sending, accepted and uncertain records across different canonical IDs.
   Initial delivery rechecks READY state, previous outbound messages, reviews and
   competing campaign recipients. Its own newly recorded outbound message is the
   only excluded message. An expected duplicate stops that recipient and lets
   other eligible recipients continue; follow-ups retain their own prior history.
3. **Late HTTP cancellation.** AI/provider and mail adapters recheck access and
   authorization after TLS, before writing HTTP bytes. Failed guards close the
   connection. Permission failures retain their meaning instead of being wrapped
   as transport outages. AI budget is reserved once, with conservative retention
   for revoked/unknown outcomes.
4. **Truthful status.** Active Chat/Find Leads work explains why the morning start
   waits. The busy explanation clears when that task ends without overwriting
   stronger warnings. Successful delivery clears a recovered warning only when no
   held/uncertain recipient remains. Replies, opt-outs and normal stops do not
   produce false service alerts.
5. **Saved UI state.** A supported one-follow-up policy can be edited and explicitly
   reauthorized. A link to an archived Autopilot sequence reveals its personal
   messages under All. Ordinary Outreach visits still open the Open filter;
   polling preserves an employee's later filter choice. Navigation is read-only.

Earlier repairs remain covered: same-session async lookup collection; selected
canonical enrichment IDs; no repeat submission of an unknown paid lookup;
recipient stop isolation; mailbox capacity and pacing; accurate same-day catch-up;
strict personal-copy fingerprints; shared manual/automatic send checks; and no
fabricated human approval. The policy cannot be minted by a model tool.

## Final evidence

| Check | Result | Local log |
| --- | --- | --- |
| Complete backend | **993 passed**, 282.60 seconds; one existing pydantic-ai event-loop deprecation warning | `/tmp/leadzen-autopilot-crosscheck-final-backend.log` |
| Complete frontend | **1,055 passed / 16 files**, 30.17 seconds | `/tmp/leadzen-autopilot-crosscheck-frontend.log` |
| TypeScript (`npm run lint`, `tsc --noEmit`) | Passed | `/tmp/leadzen-autopilot-crosscheck-types.log` |
| Optimized Next.js production build | Passed | `/tmp/leadzen-autopilot-crosscheck-build.log` |
| Migration drift, disposable test settings | No changes detected | `/tmp/leadzen-autopilot-crosscheck-migrations.log` |
| Built-in Django system checks | 0 issues | `/tmp/leadzen-autopilot-crosscheck-django-system.log` |
| Full React Doctor, 125 files | 67/100; 0 errors, 29 warnings, matching the prior baseline | `/tmp/leadzen-autopilot-crosscheck-react-full.log` |
| Tracked changed-file React Doctor scan | 100/100; does not include most untracked application files | `/tmp/leadzen-autopilot-crosscheck-react-diff.log` |
| Whitespace check | `git diff --check` passed | Local command |

Focused discovery and sending reviews passed 98 and 172 tests respectively; an
earlier affected discovery/Chat run passed 579. These and the first full backend
snapshot of 970 tests overlap the final 993-test suite and are not additive totals.
The final source was stable before the complete runs. Remaining React Doctor
warnings were neither hidden nor suppressed.

Tests exercise the actual pinned finder command/job/cycle/lookup with synthetic
HTTP, cold and warm imports, repeated days, old backlog and all-familiar pages.
Delivery tests exercise actual HTTP and SMTP adapters with synthetic acceptance,
late competing outreach, revocation during TLS and one-time AI reservation.
The full backend also covers two real disposable employee databases/router
isolation and subprocess bootstrap, timezone/DST, daily/monthly caps, expiry,
reply/opt-out stops, missing inbox coverage, paused/interrupted preparation and
uncertain send holds. These adapters never contacted live providers.

`manage.py check` is the application's finder readiness command, not Django's
built-in system check. An attempted readiness check correctly rejected an empty
disposable fixture as `onboarding_incomplete`; the built-in checks above were then
run directly. No production database was involved.

## Current state and practical limits

The disposable preview API was restarted with the final source and its existing
fixture key; local Next.js is available on port 3001. Preview provider/sending
operations remain disabled. Execution defaults off through
`LEADZEN_AUTOPILOT_ENABLED`; each employee still needs their own scoped policy.
Production application of migrations 0015/0016, enabled API/scheduler environments
and live validation require a separately authorized release.

Browser visual/responsive verification remains unverified after the earlier URL
security-policy block. No alternate browser or raw-control workaround was used.
Build/component tests are not visual proof. Provider billing, provider rate
behavior, real reply coverage and inbox placement remain unverified live.

Working days currently mean Monday–Friday, including public holidays. The
30-second dispatch loop and bounded worker pool aim for 10 AM local time, with
same-day catch-up before noon; they do not promise every employee starts at the
exact second. Shared capacity and five-minute pacing can reduce first messages
sent before the same-day cutoff. Request/credit caps are not currency guarantees.
Unknown paid requests and uncertain sends are held rather than replayed.

See [architecture and release requirements](daily-autopilot.md) and
[earlier validation history](daily-autopilot-validation-2026-10-03.md).
