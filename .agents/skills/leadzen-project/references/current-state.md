# Last verified project state

## Selectable lead providers — local source, October 7, 2026

Employees can choose BetterContact or AI Ark in Settings/onboarding, with separate
encrypted keys and no automatic fallback. Find Leads, Chat, MCP portal approvals
and selected-contact email lookup use the chosen provider over the same CRM.
AI Ark uses the active structured Target and explicitly approved, bounded paid
profile searches; uncertain purchases are not retried. Daily Autopilot remains
BetterContact-only because its standing approval does not cover paid searches.
Migration `0020_lead_finder_provider` is required; no production migration or
deployment was performed. Backend regression tests (920), frontend tests (1,212),
TypeScript, production build, Django system checks and migration consistency passed.
A subsequent requested cross-check passed the full backend suite (1,686), two
expanded feature runs (931 each), and three frontend runs (1,212 each). Added 11
provider failure/resume/budget regressions and migration-preservation assertions;
fresh build/typecheck passed after recoverably moving duplicate/generated caches.
No new application defect was found; React Doctor scores remained unchanged.
Visual browser validation was unavailable; real provider credentials/billing were
not tested. See the [implementation and validation report](../../../../docs/lead-provider-selection-2026-10-07.md)
for exact final regression results and release requirements. Earlier production
observations below remain dated history, not evidence this feature is live.

Updated October 7, 2026 after the discovery correction release. The October 6
installation summary below remains relevant but its VM sizing and deployed
discovery module are superseded by the newer sections. This is a dated
observation, not continuous health assurance.

## Discovery target mismatch — October 7, 2026

The live employee discovery run for US restaurant/hospitality and home-service
decision-makers saved four dental-practice leads. Its own qualification reasons
acknowledged the industry mismatch and favored broader product fit; the run
evaluated ten pre-existing candidates and discovered zero new profiles. An
earlier Chat run's audience explicitly included Dentist and Healthcare &
Dental, so its dental results were appropriate for that older target. A
target-precedence instruction and contradiction guard were added to the
qualification adapter, with focused synthetic regressions. Syntax and an
isolated five-case safeguard check passed. The four targeted Django regression
cases later passed locally. GitHub PR #6 and the post-merge `main` workflow passed
their checks. The PR was squash-merged to `main`
at `60936f74c6fd0747bfc17140ef27c213154a7b9b`. The live Google backend
still uses the October 6 installation, with only its discovery module updated
to the exact merged file; both API and scheduler were active, authenticated
health and readiness passed, and anonymous health returned 401. Vercel's new
ready production deployment `dpl_3yQhgRRMePMtaZRNtNQWbxZ1u1vt` was assigned
to `leadzen.zyene.com`; public login returned HTTP 200 with that deployment ID.
The existing four dental contacts were not changed. [Investigation and release](../../../../docs/discovery-campaign-mismatch-2026-10-07.md).

## Sign-in outage and VM recovery — October 7, 2026

The public login showed a temporary-unavailability error while the backend
timed out. The `leadzen-api` Google VM was an `e2-micro` (about 1 GB RAM, no
swap); systemd recorded an OOM kill of `leadzen.service` at 14:25:55 UTC.
The follow-up scheduler also recorded a worker exit and timeout beforehand,
but their root cause is unproven. With owner approval, a fresh ready-for-use
snapshot (`leadzen-api-pre-resize-20261007`) was taken, then the stopped VM
was resized to `e2-small` (2 GB RAM) and restarted with the same static IP.
The dashboard login page returned HTTP 200, a synthetic invalid login returned
the expected HTTP 401 instead of a gateway error, and both API and scheduler
services were active. At 15:05 UTC about 1275 MB RAM was available.
Google Cloud Ops Agent is installed for host metrics, and the owner-approved
email channel `support@zyene.com` exists. Memory metric export is currently
denied by IAM; the narrow metric-writer grant and alert policy await completion
and verification. No test notification, real login, real send, paid provider
operation, or code deployment was performed. See the
[incident report](../../../../docs/production-login-capacity-incident-2026-10-07.md).

Updated October 6, 2026 after a fresh Google backend installation, scheduler
activation, and removal of the old installation. Earlier
sections record production completion and controlled-release validation after
interactive product-tour implementation, provider streaming validation and
employee Chat bubble refinement. This is a dated snapshot,
not a live health check. Current source, later user instructions and later verified
releases can supersede it.

## Fresh Google backend — October 6, 2026

With the owner's explicit instruction to replace rather than migrate old data,
the existing Google VM now runs the complete GitHub `main` backend at `f1d8cfe`
from `/opt/leadzen-f1d8cfe-20261006` against a fresh SQLite database. All current
migrations were applied. The owner entered the generated password for the new
`support@zyene.com` administrator at the private bootstrap prompt; its owner-only
TXT file remains outside the repository. Public authenticated API health and
readiness returned HTTP 200, anonymous health 401, and the Vercel admin login
with the new credential returned HTTP 200 and routed to `/admin`; its verification
session was signed out. `leadzen.service` is active. On the owner's October 6
instruction, automatic follow-ups were enabled in the current root-owned
environment and `leadzen-followups.service` became active and enabled; its
scheduler heartbeat reported `ok`. No send or paid provider operation was run,
and the fresh database has no employee workspace. Protected VM and local
recovery copies of the new installation passed SQLite integrity verification.
The 24 enumerated old VM paths, including the old runtime and databases, were
removed after the owner's October 6 instruction; a repeat inventory found zero
superseded paths. The old employee workspace's 103 leads and 20 chat messages
were intentionally excluded from the fresh database and are now deleted with
that old workspace. Obsolete local backups and old credentials were removed;
the current administrator TXT and backup remain private and outside the repo.
Authenticated public API readiness returned HTTP 200 after cleanup.
[Installation report](../../../../docs/google-fresh-backend-2026-10-06.md).

## Deleted employee re-invitation — October 6, 2026

A backend fix now permits a new invitation for an email held by a soft-deleted
employee while retaining the old account and workspace separately. It was
merged through GitHub PR #5 into `main` at commit `f1d8cfe` and mirrored into
this working tree. The temporary branch was deleted. Focused account/invitation
tests passed (21), and GitHub Actions required checks passed. A narrow matching
hotfix was applied to the live Google backend with fresh user approval;
`leadzen.service` is active and authenticated health returned `ok: true`.
The rest of the live backend remains on its existing baseline. No real
invitation was sent or tested in production. [Incident note](../../../../docs/admin-reinvite-2026-10-06.md).

## Earlier main, Vercel, and Google VM sync check — October 6, 2026

The intended application source in this dirty checkout matches Zyene GitHub
`main` at `f1d8cfe`; a complete release-input comparison found only older local
README/CI/security-decision content and two test-only variations. GitHub remote
lists only `main`. The ready Vercel production deployment for `f1d8cfe`,
`dpl_E14WyTSQh5W4bKtUPtUKYTPYsoAL`, is now assigned to
`leadzen.zyene.com`; public login returned HTTP 200 with that deployment ID.
A private linux/amd64 source candidate from main was captured and verified at
`/Users/ashishdikonda/Desktop/Openoutreach/leadzen-main-release-f1d8cfe-20261006`
with source SHA-256 `2754d2cdddca10e3bed26b822a343f1a20dc1895a3274d6119a11d81cb4cf892`.
Its source archive and manifest were uploaded to the VM's root-only
`/srv/private/leadzen-staged-f1d8cfe-20261006/` and byte-verified there.
This is staging only; no service was pointed at it.

At the time of that sync check, the full Google VM backend was **not** updated
to main. It ran the October 3 baseline plus the narrow invitation hotfix. Its
old databases had accounts migration 0002 and configuration migration 0014;
main required 0004 and 0019. Its environment lacked `LEADZEN_ENV` and
`LEADZEN_SECRET_KEY`. That assessment was superseded by the owner's later
direction to use a fresh database and the verified installation above.
[Sync report](../../../../docs/main-vercel-google-sync-2026-10-06.md).

## Later verified production login state — October 5, 2026

The live API and current main Vercel deployment now use the same service token.
With fresh user approval, `leadzen.zyene.com` was assigned to the current main
deployment. The public login page loaded, a synthetic login reached password
validation, and the administrator signed in through Chrome and opened `/admin`.
This is a narrow login-path verification; the release gates and local-only
features recorded below retain their dated scope.
[Incident validation](../../../../docs/admin-login-production-2026-10-05.md).

## Local implementation

The working checkout is the primary source of newest work. Numerous directories,
including `leadzen/` and dashboard components/tests, are untracked. Do not reset
to the repository's old `openoutreach/` package or discard its recorded deletions.
The implementation now lives under `leadzen/`; finder/sender remain dependencies.

Latest local implementation:

- **Production cross-check**: independent reviews found additional release evidence,
  incomplete image-scan, backup publication, restore preservation, preflight feature
  and scheduler-monitoring defects. Narrow fixes and failing-before regressions
  are implemented; GitHub actions are pinned and frontend CI covers Node 22/24.
  The current [cross-check report](../../../../docs/production-crosscheck-2026-10-04.md)
  owns frozen source `f3498c958bb7b5f290e4d8f1a294915a153870b6007c13b7d1552624faec3e3e`,
  **1,649 backend and 1,196 frontend passes**, and matching immutable artifacts. The older
  completion candidate below remains preserved, with its own dated evidence.
  Production approval remains blocked by concrete external/configuration/recovery
  gates; no deployment, live mutation, real send, paid action or rotation occurred.

- **Production completion and release controls**: implemented whole-working-tree
  release capture/gates, private whole-namespace preflight, durable maintenance/drain,
  recovery-bound forward migration, consistent full-server backups with protected
  matching backend/dashboard/proxy/service/runtime metadata, independent-copy/retention
  checks, isolated restore drills, actionable monitoring/guarded alerts, hashed build
  dependencies, current secret/image scanning and trusted-HTTPS browser CI fixtures.
  Scheduler holds now cover pass gaps and children ending in `--workspace`; denied
  contact/Inbox/discovery context waits for authorized records and stale contact data
  is cleared. The frozen source is
  `73eb35d6be24bed880bef74ed1c237b2d649d6985ed8bb2d1753a965c7830af6`
  (396 files, 360 untracked; HEAD is not the release). Fresh **1,475 backend and
  1,196 frontend tests** passed, plus clean builds, Linux image migration/isolation,
  non-root fail-closed runtime, dependency checks and local bounded capacity.
  Exact final browser evidence, artifacts, commands and PASS/FAIL/BLOCKED scopes are
  in the [completion report](../../../../docs/production-completion-2026-10-04.md).
  **NOT READY**: current host/config/schema/recovery, historic credential disposition,
  remaining OS HIGH decisions, external alert receipt, full browser password/setup
  handoff, actual-host capacity, enabled providers/real MCP client and external
  promotion controls remain unresolved. No deploy/live mutation/send/spend/rotation
  occurred. Earlier audit counts and tour/browser limitations below are historical.

- **Complete production audit**: reviewed every current runtime/release input,
  preserved the dirty working tree, and fixed account-state races, invitation
  write-lock I/O, OAuth connection retention, credential/settings boundaries,
  duplicate cold sends/STOP suppression, provider body deadlines, query growth,
  production headers, private readiness/request logging and deployment guards.
  New WSGI preflight requires explicit production configuration including
  `LEADZEN_ENV`, `LEADZEN_SECRET_KEY` and exact origins; the dashboard requires
  `LEADZEN_DASHBOARD_PUBLIC_URL`. Python runtime versions/hashes are locked in
  `requirements-production.lock`; production SQLite WAL uses synchronous FULL.
  Additive config migration `0019_discoverylookup_source_index` is local only.
  **NOT READY for release approval** until the documented configuration/migration,
  trusted-browser, historical-credential, recovery/alert and host/integration
  gates are verified. Production standalone TLS journeys and non-root offline
  Gunicorn health/readiness checks passed; no deploy, paid call, real send or
  production-data operation occurred. **1,387 backend and 1,191 frontend tests** passed against the final clean
  source, with one existing library warning. The audit report owns the complete
  commands, results and remaining UNVERIFIED scope.
  [Audit](../../../../docs/production-readiness-audit-2026-10-04.md).

- **Interactive product tour**: replaced the six-slide tour with 14 synchronized
  steps over actual Workspace/Chat controls, real click/form/route readiness,
  accessible nonmodal guidance, viewport-aware positioning and safe undimmed
  recovery. Actor-owned progress, completion and Skip persist; Settings → Take
  Product Tour restarts it. Additive account migration `0004_accountprofile_tour_state`
  preserves earlier completion. **1,165 full frontend tests**, **69 final focused
  tour/auth tests** and **85 backend tests** passed, with actual-component 14-step
  and form-refresh integration, local HTTP persistence/gate checks, TypeScript/build
  and Django/migration checks. React Doctor full tree 69/100, zero errors, 29
  warnings. Disposable preview restored on 3001. **Browser visual review remains
  blocked by automatic approval review's localhost URL-protocol rejection**;
  no screenshots or alternate browser workaround. Local only, not deployed.
  [Validation](../../../../docs/product-tour-validation-2026-10-04.md).

- **Provider streaming validation**: preserved existing Chat UI/SSE and vendor
  adapters; added pre-I/O buffering for the installed non-streaming Cohere adapter,
  disabled its implicit SDK retries, and an exact-host server opt-in for validated
  JSON-text output on compatible gateways. **554 backend regressions**, **62 final
  provider tests** and **172 frontend Chat tests** passed, plus TypeScript/build.
  Five bounded AkashML requests used only disposable synthetic data: Kimi complete
  answers persisted, but progressive output remains unverified; Llama's visible
  response streamed progressively and Stop preserved received text after reload.
  Live key removed from disposable Settings and synthetic preview restored.
  Other providers have native SDK wire fixtures, not live-account certification.
  Local only, not deployed. [Validation](../../../../docs/provider-streaming-validation-2026-10-04.md).

- **Ponytail cleanup**: ten pre-edit affected-suite runs passed (865 backend and
  689 frontend tests per run), alongside ten distinct checks in each review area,
  before the implementation gate opened. Removed unreachable Sending UI/CSS/font
  assets and legacy Docker launch files, reused stored-read and sending-window
  helpers, consolidated discovery completion and duplicate Python CI, and removed
  two unused dev dependencies. Existing routes, approvals and isolation remain.
  Net 379 source/config/test lines removed; unused font/license assets 35,899 bytes.
  [Validation](../../../../docs/ponytail-cleanup-validation-2026-10-03.md):
  **1,237 backend and 1,099 frontend tests passed**, TypeScript/build, zero Django
  check issues and no migration drift. Full React Doctor 69/100, zero errors,
  warnings 29 → 28 against the exact snapshot; no new diagnostics. Synthetic
  desktop/mobile stored-record and Outreach checks passed, including `/sending`
  compatibility redirect. Preview restored on 3001. Local only, not deployed.

- **Claude and ChatGPT MCP connections**: Settings now includes compact branded
  setup cards, a copyable configured endpoint, authenticated connection status
  and disconnect controls. Remote Streamable HTTP uses employee OAuth consent,
  PKCE, hashed opaque tokens, rotating refresh tokens and live grant/account
  checks. Forty typed tools reuse the canonical Workspace and exact portal
  approvals; no client-supplied approval can send or spend. Background workers
  check revocation/cancellation/expiry at existing external sinks. Credentials,
  account administration and new standing automatic authorization stay in the
  portal. Account migration `0003_mcp_oauth` is additive. This is local source,
  not a deployed connector; public HTTPS configuration and a real client test
  are outstanding. **1,233 backend and 1,147 frontend tests passed**, along with
  TypeScript/build, zero Django check issues and no migration drift. Final checks
  repaired an old mailbox-preparation filter that hid campaign contacts and
  invalid-request consent handling. Synthetic preview is running at port 3001;
  browser visual and real client validation remain unverified.
  [Setup](../../../../docs/mcp-connections.md) and
  [validation](../../../../docs/mcp-validation-2026-10-03.md).

- **New York only**: the owner requires America/New_York for the entire platform.
  Settings edits weekly days/hours; timezone selection is removed. Autopilot,
  follow-ups, mailbox ledgers, Home/Chat daily counts, all displayed times and
  calendar grouping use New York with automatic EST/EDT changes. Identity country
  and UTC instant storage are retained. Migration `0018_new_york_time` normalizes
  schedule/draft/campaign metadata, preserves immutable policy and accepted/due
  evidence, and requires fresh review of previous approval fingerprints.
  [Validation](../../../../docs/new-york-time-validation-2026-10-03.md): 156 focused
  backend tests, **1,107 full frontend tests**, 14 New York tests under Tokyo host
  timezone, TypeScript/build and Django/migration checks passed. React Doctor full
  tree 70/100, zero errors, 28 warnings; tracked scan 100/100. Migration applied
  only to all four disposable local preview databases. Preview restored on 3001;
  real Autopilot and campaign execution remain disabled. Browser visual review
  remains unverified. Full backend run: 1,136 passed; one old India-zone assertion
  was updated to the correct New York output and all 16 final timeline tests passed
  without further source changes. This supersedes the editable-zone behavior below.

- Employee-editable weekly schedule in Settings → Sending hours: selected
  Monday–Sunday days, minute-precision start/end and IANA timezone. New Autopilot
  discovery uses the same selected days and start; outreach and approved follow-ups
  use that window. Saved settings never start providers. Setup changes require a
  fresh review of automatic approvals and queued reviewed sends. Legacy approvals
  keep their original windows until reauthorized; manual Inbox replies remain
  immediate. DST gaps/folds, mailbox local-day limits and late HTTP/SMTP submission
  checks are covered. New `0017_siteconfig_sending_schedule` is local only.
  [Validation](../../../../docs/sending-schedule-validation-2026-10-03.md):
  **1,112 backend and 1,089 frontend tests passed**, plus 19 final focused UI tests,
  TypeScript/build, zero Django system-check issues and no migration drift. React
  Doctor full tree 68/100, zero errors, 32 warnings; tracked scan 100/100. Local
  preview restored at port 3001, all real execution remains disabled. Browser
  visual review remains unverified after the earlier URL-policy block.

- Daily Autopilot in Outreach: explicit employee-owned standing authorization,
  scheduled timezone-aware discovery → verified enrichment → personalized
  sequences → automatic initial sending and reply-stopped follow-ups. Shared
  canonical CampaignRecipient personal copy, conservative daily/monthly caps,
  isolated bounded workers, same-day uniqueness, sink revocation and no ambiguous
  retry. New `0016_daily_autopilot` migration; execution defaults off through
  `LEADZEN_AUTOPILOT_ENABLED`. Local only, **not deployed or enabled for real mail**.
  [Architecture](../../../../docs/daily-autopilot.md) and
  [validation](../../../../docs/daily-autopilot-validation-2026-10-03.md) and final
  [code/logic cross-check](../../../../docs/daily-autopilot-crosscheck-2026-10-03.md):
  **993 backend tests and 1,055 frontend tests passed**, with actual workspace
  isolation, TypeScript/build, Django system checks and migration consistency.
  Review repaired async enrichment collection, terminal-recipient queue blocking,
  old backlog consuming today's discovery quota, duplicate manual/automatic
  outreach across canonical IDs, and HTTP revocation during connection. Real
  dependency lifecycle and HTTP/SMTP tests use synthetic responses; unknown paid
  requests and uncertain sends are never replayed. Busy/recovered warnings,
  saved one-follow-up policies and archived sequence links have regressions.
  Full React Doctor 67/100, zero errors, 29 warnings. Browser visual review remains
  unverified after the earlier URL-policy block. No live provider/billing/delivery
  validation. That earlier validation used first emails 10 AM–5 PM and follow-ups
  9 AM–5 PM in policy timezone; historical policies keep these windows. Newly
  authorized policies now use the Settings schedule described above.

Latest local UI changes:

- Employee Chat messages now have visible rounded neutral bubbles: existing line
  fill and ink text adapt to light/dark themes; right alignment, 20px corners,
  responsive width and 16px text are retained. Submitting and saved messages share
  the style. **172 Chat tests**, TypeScript/build and actual desktop/mobile theme
  checks passed. Local only, no streaming/UI state changes for this styling.
  [Validation](../../../../docs/employee-chat-bubble-validation-2026-10-04.md).

- Modestly compact shared sidebar: 156px logo, 216px desktop column, tighter
  section/footer spacing, smaller icons/avatar and secondary labels. Primary
  navigation stays 14px with 44px action targets; long account text can wrap.
  [Validation](../../../../docs/sidebar-density-validation-2026-10-03.md): 148
  navigation/presentation tests, TypeScript/build passed. Local preview restored
  on port 3001; fresh browser visual comparison remains unverified. Local only.

- Unified Outreach at `/outreach`: select leads → review messages → confirm, with
  optional follow-ups and final-confirmation activation. Existing Sending/Campaign
  links and records remain compatible. Leads groups acquisition and selection;
  Inbox checks replies with a restorable inline approval; Home surfaces saved work
  needing attention; contextual Ask LeadZen preserves canonical references.
  [Validation](../../../../docs/unified-outreach-validation-2026-10-03.md): 1,049
  frontend tests, broad backend regressions, new two-workspace isolation checks,
  TypeScript/build. Browser visual review was blocked by URL policy and remains
  unverified. Local only, not deployed; no new migration for this change.

- Chat now has a compact, collapsed-by-default live activity block with recorded
  action/discovery events, server-timestamp elapsed time, terminal summaries and
  Workspace links. It preserves its discovery counts after reload and stops motion
  for approval, pause and terminal states. [Validation](../../../../docs/chat-live-activity-validation-2026-10-03.md):
  1,042 frontend tests, 491 targeted backend tests, TypeScript/build and synthetic
  desktop/mobile checks passed. Additive run timestamp API fields; no migration.
  Local only, not deployed.
- Compact Workspace headings, controls, tables and form spacing; shared accessible
  question-mark help on hover, focus and tap; shorter setup/tour guidance. Dashboard
  recent activity is bounded so the lead queue remains close to the summary.
  Costs, approval terms, errors and blockers remain visible. Chat reading/composer
  behavior is preserved. See the [compact UI validation](../../../../docs/compact-ui-validation-2026-10-03.md):
  1,032 frontend tests, TypeScript/build and desktop/mobile route checks passed;
  React Doctor full scan has 0 errors and 23 warnings. Local only, not deployed.
- Compact Workspace discovery and Chat with actual engine progress: discovered
  candidates, review state, qualified/rejected decisions and saved reasons.
- Real visible assistant-text streaming over authenticated SSE, bounded reconnect
  and saved-state recovery; no private reasoning or fabricated terminal animation.
- Viewport-height Chat with a stationary composer, independent transcript/history
  scrolling, user-controlled following and Jump to latest.
- Safe formatted assistant Markdown and short progressive reveal of incoming text;
  history/final answers are immediate, reduced-motion preference is respected.
- 16px Chat message/input text, 1.7 response line height, 20px user bubbles and
  24px desktop / 20px mobile composer. LeadZen ink/paper styling retained.
- Sidebar Delete with confirmation. Owner-scoped `ChatThread.deleted_at` hides
  the conversation, preserves Workspace/audit records, and refuses active tasks.
- Chat saved results and discovery progress invalidate canonical Workspace reads,
  including other same-origin tabs. Broadcasts carry no record data and ignore
  their originating tab. No copied CRM state or manual reload required.

Migration `0015_chatthread_deleted_at` is local and must be applied to the control
and initialized employee databases before deploying the new backend. The new
`0016_daily_autopilot` migration must also be applied; it was validated only in
disposable test/preview databases. It has been
applied only to disposable preview databases during this validation.
`0017_siteconfig_sending_schedule` must also be applied to control and initialized
employee databases; it was applied only to disposable preview/test databases.
Its added setup field may invalidate earlier reviewed requests/automatic
fingerprints even before a custom schedule is saved; review those holds again.
`0018_new_york_time` is also local only and required for the fixed New York rollout.
It does not shift absolute timestamps or approve previously held sequences.

Latest evidence:

- [Focused maintenance](../../../../docs/repository-maintenance-followup-2026-10-04.md):
  confirmed Docker context exclusions, explicit tested Python provider/transport
  dependency bounds, and corrected Docker links/Compose examples. A disposable
  current-tree copy with fresh dependencies passed **1,237 backend and 1,099
  frontend tests**, TypeScript/build and packaging checks. Actual Docker context,
  image and network-disabled installed-runtime checks passed; Python 3.11 Linux
  dependency resolution passed. Original environments, migrations, nine uncertain
  candidates and 19 preexisting deletions preserved. Local only, no deployment.

- [Repository cleanup audit](../../../../docs/repository-cleanup-audit-2026-10-03.md):
  current-tree reference/discovery inspection classified 496 entries. Removed only
  Finder metadata, an obsolete ignored Python lock and a stray root Vitest cache;
  added ignore rules. Application source, migrations, dependencies and historical
  evidence were retained. This is local repository hygiene, not a deployment.

- [Chat presentation validation](../../../../docs/chat-presentation-validation-2026-10-03.md):
  1,026 frontend tests; 491 targeted backend Chat/Workspace tests; TypeScript and
  optimized build passed. Chrome saw Contacts **53 → 56 → 58** during a five-lead
  synthetic Chat run without reloading. Full React Doctor: no errors, 24 warnings.
- [Earlier discovery/Chat validation](../../../../docs/ui-chat-discovery-validation-2026-10-03.md):
  full backend 908 tests and the earlier frontend 1,018; focused suites repeated
  ten times. These counts describe different snapshots, not a new combined run.
- Desktop/mobile screenshots are under `docs/ui-progress-assets/`.

## Last documented production state

The [deployment report](../../../../docs/deployment.md) records the October 3
release to `leadzen.zyene.com` (Vercel) and `leadzen-api.zyene.com` (existing Google
VM). It records the full application through migration 0014, followed by approved
automatic-follow-up activation and the complete owner-supplied logo.

The scheduler was documented active/enabled with
`LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED=1`. This does not approve recipients or prove
current health. Exact sequence approval remains required; no real mail was sent
in the activation checks. Latest Chat/discovery/presentation changes above were
**not deployed**. New deployment requires fresh authorization.

Known limitations: no scheduler heartbeat/external monitoring documented; real
provider billing, inbox placement and live send/reply behavior were not exercised
in the latest synthetic preview. Static-analysis maintainability warnings remain.
Do not silently label these as completed production certification.

## Historical contradictions to avoid

- October 2's handoff predates later releases. Its indigo palette, nonstreaming
  Chat, manual-only follow-ups, and blanket “not deployed” descriptions are stale.
- Use the complete approved logo including “by Zyene” once; do not restore the
  earlier native byline beside artwork that already includes it.
- Without a custom schedule, historical approved follow-ups use **9 AM–5 PM
  weekdays** and manual due/initial sends use **8 AM–8 PM**, all in New York.
  A saved schedule now governs newly reviewed outreach and Autopilot; its exact
  selected days, hours and timezone must be displayed rather than hard-coded.
- Skill descriptions and documents are not runtime truth. Check source and current
  configuration for any task depending on exact limits or service status.

## Continuing locally

The last disposable preview used port 3001 for Next.js and 8000 for the API.
Processes and temporary databases may no longer exist in a new session; inspect
before reusing or restarting. Create a new disposable preview if needed, following
[verification](verification.md). Do not replace an unrelated process on port 3000.
Fixture accounts and credentials are in the preview script, never production.

There is no implied pending implementation merely because this snapshot exists.
Continue the user's next task and update this file after material changes.
