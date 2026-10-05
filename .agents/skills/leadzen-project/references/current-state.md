# Last verified project state

Updated October 4, 2026 during production completion and controlled-release validation, following
interactive product-tour implementation, provider streaming validation and
employee Chat bubble refinement. This is a dated snapshot,
not a live health check. Current source, later user instructions and later verified
releases can supersede it.

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
