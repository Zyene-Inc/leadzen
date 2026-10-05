# LeadZen local validation — 2026-10-02

Brand and intended production URL: **LeadZen by Zyene**, `leadzen.zyene.com`.
Company support and first administrator: `support@zyene.com`.
These changes are local only. No live invitations or outreach emails were sent.

## Implemented

- Administrator-only employee invitations via Resend, resend/reset via email,
  employee totals, search, disable/enable and soft deletion. No public signup.
- Hashed, single-use setup capabilities expiring after 48 hours; passwords are
  chosen by employees. Account suspension/reset/deletion revokes sessions.
- Employee-specific SQLite workspaces and encrypted connection credentials.
- Purpose and audience onboarding for Zyene products or services, optional AI,
  SMTP or API sending, independent IMAP reply credentials and a five-step tour.
- Contacts, CSV imports, permission records, opt-out and stop controls.
- Editable draft campaigns, up to five sequence steps, personalization,
  activate/pause/archive and bounded due-email runs with job history.
- Sending-hour, mailbox pacing and capacity checks. Replies and opt-outs stop
  follow-ups; unreadable/incomplete inbox sync fails closed. Uncertain delivery
  is held for review, never retried automatically. Provider acceptance is counted
  separately from unconfirmed attempts and does not prove inbox placement.

## Evidence

- Backend: `python -m pytest -q` — **80 passed**.
- Next.js optimized production build and TypeScript compilation passed.
- Migration consistency: `manage.py makemigrations --check --dry-run` — no changes.
- Django system-check registry — zero issues. The CLI's `check` command instead
  reports finder readiness; it is not Django's built-in system check.
- Deployment script syntax: `bash -n compose/leadzen/deploy-accounts.sh` — passed.
- Actual local Next.js-to-Django HTTP flow, with real disposable private SQLite:
  invitation, password, onboarding with AI disabled, tour, contacts, campaign,
  employee isolation, account disable/re-enable, CSRF origin check and logout.
- Chrome: employee login, contact creation with opt-in, two-step draft creation,
  activation, pause, sequence inspection, configuration controls and disabled
  preview sends verified in the UI. Screenshots saved under `/tmp/leadzen-*-local.jpg`.
- React Doctor changed-tracked-file scan: 100/100, no findings. This does **not**
  cover all new files. Full-tree scan: 74/100 with 8 warnings: large components,
  duplicated admin structure and fragment-token bootstrap fetching in an effect.
  No diagnostics were suppressed. Fragment bootstrap must happen client-side
  because the token is intentionally excluded from HTTP URLs and server logs.
- Chrome's installed browser extension adds `data-tsenta-overlay-*` attributes
  before React loads, producing a development hydration warning. This was not
  hidden or “fixed” by weakening hydration checks.

## Visual refresh and private admin handoff

- Confirmed calm, precise product-dashboard direction: cool-neutral canvas,
  indigo actions, quiet icon navigation, compact headings, one divided metric
  strip, consistent forms, employee initials and semantic account states.
- Mobile navigation opens and closes accessibly. At a 390px viewport, admin,
  contacts and settings stayed within a 390px page; wide tables scroll within
  labeled, keyboard-focusable regions instead of expanding the page.
- Keyboard focus was verified on the employee form with a visible 2px outline.
  Reduced-motion emulation produced zero-duration button transitions.
  Calculated sRGB contrasts: field boundary 3.21:1, primary button text 6.30:1,
  muted sidebar text 5.70:1. This is not a complete accessibility certification.
- Re-ran all **80 backend tests**, the disposable local HTTP flow, TypeScript
  and optimized build. Final full React scan: 37 files, 74/100, the same eight
  existing warnings. The expanded admin row was extracted without changing
  permissions, confirmations or backend actions. No diagnostics were suppressed.
- Also ran the generated standalone frontend against a loopback-only HTTPS
  proxy to the disposable API. A one-day test certificate was trusted only in
  that frontend Node process through `NODE_EXTRA_CA_CERTS`; TLS verification
  stayed enabled. No browser warnings were bypassed and no system CA was installed.
  Compiled-mode employee/admin login, logout and authenticated pages worked.
- Refreshed screenshots: `/tmp/leadzen-admin-refreshed.jpg`,
  `/tmp/leadzen-admin-mobile-refreshed.jpg`, `/tmp/leadzen-login-refreshed.jpg`,
  `/tmp/leadzen-overview-refreshed.jpg`.
- The synthetic preview credentials below are local-only. The owner-only
  `/Users/ashishdikonda/.codex/private/leadzen/admin-login.txt` file now contains
  **production** access for `support@zyene.com` (mode 600, parent directory 700).
  Do not overwrite it with a preview fixture. See [deployment status and
  environment guide](deployment.md) for the completed production deployment.

## Repeat the safe local preview

From the repository root, create a disposable directory and run the API:

```bash
preview_dir=$(mktemp -d /tmp/leadzen-preview.XXXXXX)
LEADZEN_PREVIEW_DIR="$preview_dir" .venv/bin/python tests/scenarios/local_preview.py
```

In another terminal, from `dashboard/`:

```bash
LEADZEN_API_URL=http://127.0.0.1:8000 \
LEADZEN_API_TOKEN=synthetic-local-dashboard-token \
npm run dev -- --hostname localhost --port 3001
```

Synthetic preview accounts share the **local-only** password
`LeadZen-preview-only-3487!`:

- `admin@preview.example`: employee administration.
- `employee@preview.example`: onboarding.
- `ready@preview.example`: contacts, campaigns and connections.

Open `http://localhost:8000` (redirects to the preview Dashboard), or
`http://localhost:3001/admin` or `/login`. Invitation emails are captured in
`last-invitation.json` in the disposable preview directory; it is private and
must not be published. Campaign sending is disabled; reviewed outreach runs only
with synthetic recipients and simulated acceptance, never an external provider.
Full HTTP test:

```bash
.venv/bin/python tests/scenarios/http_flow.py "$preview_dir"
```

## Production deployment and future release checklist

The production deployment was completed and verified on 1 October 2026; current
evidence and environment locations are in [deployment.md](deployment.md). The
owner explicitly approved reuse of the existing invitation provider key;
revocation/rotation is not completed. No live invitation or campaign was sent
during deployment verification. Preserve these checks for future releases:

1. Rotate the invitation key shared in chat and configure the replacement only
   on the backend. Verify the Resend sender domain and a single approved internal
   invitation delivery; live provider delivery was deliberately not tested here.
2. Use `compose/leadzen/runtime.env.example` for backend variables. Preserve the
   existing stable encryption key and back up the control and employee databases.
3. Install a fresh wheel and matching source; the earlier release archive is
   stale. Stop API intake and wait for workers, then migrate the control database
   **and every existing employee workspace** before restarting.
4. Configure the HTTPS backend and matching server-to-server secret on Vercel.
   Deploy `dashboard/` and verify the admin and invited employee flow on
   `leadzen.zyene.com`. Bootstrap the administrator privately if still absent.
5. Verify employee provider credentials, sender authentication, reply access and
   provider rules with approved recipients before enabling live outreach.

Resend is permitted here only for explicitly opted-in recipients; see
[Resend acceptable use](https://resend.com/legal/acceptable-use). ZeptoMail is
restricted to single transactional notifications; see
[Zoho transactional email](https://www.zoho.com/mail/help/adminconsole/transactional-email-integration.html).
Generic SMTP/API availability does not imply permission to send cold marketing.

Campaign follow-ups are **manual due runs**, not a continuously scheduled service.
The existing autonomous CLI engine is retained, but this change does not enable
a new unattended scheduler or guarantee spam-free/inbox delivery.

## BetterContact setup — local only, 1 October 2026

The owner explicitly chose **Keep it local for now**. Google Cloud, Vercel,
production employees, saved production credentials and live outreach are unchanged.

- Added **Lead finding → BetterContact API key** to onboarding and Connections.
  Keys are encrypted in the employee workspace. Responses expose presence only.
  Blank input preserves the key; replacement and explicit removal are supported.
- Both HTTP setup paths validate input before writes. Existing CLI configuration
  remains compatible, including explicit environment overrides and older schemas.
  A successful settings save migrates any old plaintext BetterContact key into
  encrypted storage; clearing cannot resurrect that old value.
- Regression evidence: tests failed on the missing field/storage/export first,
  then passed after implementation. Final full backend suite: **95 passed**.
  Dashboard type check and optimized production build passed; `git diff --check`
  and Python compilation passed.
- Real local browser verification: save, blank-preserving save, reload, replace,
  remove, onboarding save, and readback in Connections. Only synthetic keys were
  used; the preview disables outreach workers and external email delivery.
- React Doctor changed-tracked-file scan: 100/100. Full scan: 74/100 with the
  same eight existing diagnostics documented above; none were suppressed.
- Preview: `http://localhost:3000/settings`, disposable data directory
  `/tmp/leadzen-preview.RNCuxg`. API execution session: 27432; frontend: 81497.
  Screenshot: `/tmp/leadzen-bettercontact-connections.png`.
- Provider validity and credit balance were not checked. No lead search,
  enrichment, real AI request, invitation or outreach email was triggered.
  Overview still sends stored leads, not new searches. The separately diagnosed
  production AI SDK compatibility problem is not fixed by this change.
- A future approved release needs the backend first, then the Vercel frontend.
  No new Vercel variable or schema migration is needed for the BetterContact key.

## Chat orchestrator — local only, 2 October 2026

The owner requested Claude-style agentic outreach with a Workspace / Chat switch.
The earlier **Keep it local for now** decision still applies. No Google Cloud,
Vercel, production account, live key or outreach changes were made.

- Added private saved chat history, age groups, filtering, new chats, archiving,
  composer, task suggestions, actual tool results, cancellation and approval cards.
  The six workspace links remain available. Existing theme tokens were reused.
- Implemented a bounded model/tool/observation loop using employee AI credentials.
  Discovery uses the installed finder and JSONL ingest; campaigns share existing
  validation and sending guards. All writes, discovery and mailbox sync require
  single-use approval, with recipient/copy previews for sending.
- Added source-owned provider adapters for all seven saved provider types, pinned
  HTTPS clients, runtime access checks, deadlines, request/spending reservations,
  crash recovery and key redaction. No installed site-packages were edited.
- Local full backend suite: **121 passed**. Optimized frontend build/type check,
  migration drift check, Python compilation and `git diff --check` passed. Tests
  use synthetic providers only; live delivery/credential validity is unverified.
- Browser checks: multi-step read-only request, persisted history, lead-credit
  approval and one-time resume, Workspace navigation, and the 393px mobile layout.
  Synthetic preview reports zero purchased leads and zero external calls.
- React Doctor changed-tracked-file scan: 100/100. Full scan: 68/100, with no
  errors and 12 warnings. Nine concern existing setup/admin/workspace components;
  chat adds a render-complexity warning and two locale-render warnings. Dates
  only appear after client-side API loading, so those do not imply a server/client
  hydration mismatch. The polling cleanup issue was corrected; no findings were
  suppressed. This is not an independent security or accessibility certification.
- Screenshots: `/tmp/leadzen-chat-home.png`, `/tmp/leadzen-chat-approval.png`,
  `/tmp/leadzen-chat-mobile.png`, `/tmp/leadzen-chat-conversation.png`. Local preview
  data remains in `/tmp/leadzen-preview.RNCuxg`. API session 79325 and frontend
  session 35922 serve `http://localhost:3000/chat`.
- Deployment and execution caveats are in [chat-orchestrator.md](chat-orchestrator.md).
  New forward migrations 0006/0007 are needed on all databases in a future release.
  The production AI SDK issue is not changed until that release is authorized.

## Credential visibility, SMTP 465 and contact deletion — local only, 2 October 2026

The previous **Keep it local for now** decision remains in force. No Google
Cloud/Vercel deployment, production credential update, provider lookup or real
email send was performed.

- Added one shared, labeled secret input to all 11 password/API-key entry fields
  across login, invitation setup, password change, onboarding and Connections.
  Eye controls are keyboard-operable, have explicit Show/Hide names and 44px
  targets. They reveal only current input; saved encrypted credentials are never
  returned. Clearing a controlled input resets its reveal state.
- Settings accept SMTP 465, which performs verified implicit TLS before reading
  the SMTP greeting/authentication. 587/2525 retain STARTTLS, public destination
  pinning and hostname/certificate checks. Provider acceptance logging is kept.
  Unsupported SMTP ports and non-public destinations remain blocked.
- Contacts now have separate Edit, Stop, Opt out and confirmed Delete actions.
  Delete removes the contact from visible lists/counts and chat results, stops
  queued outreach, and retains conversation/consent/suppression history. It is
  not permanent personal-data erasure. Duplicate imports do not resurrect the
  removed address. There is no restore interface in this change.
- API/worker tests cover foreign and unauthenticated deletion, idempotency,
  preserved opt-outs/history, deletion before transport, and deletion while an
  already-started provider send completes. Completion cannot revive follow-ups.
  An email already accepted by a provider cannot be recalled by deleting a lead.
- Red-before-green evidence: six initial behavioral failures, then an additional
  delivery-completion race reproduced and fixed. Final backend suite: **135
  passed**. Dashboard type check/optimized build, migration drift, Python
  compilation and `git diff --check` passed.
- React Doctor changed-tracked-file scan remains 100/100; the full 44-file scan
  remains 68/100 with the same 12 prior warnings and no errors or suppressions.
- Local browser verification: typed synthetic secrets reveal/hide for all five
  connection credential kinds; keyboard operation on all three password-change
  fields; 465 save/reload; Delete/Cancel and Stop behavior; final contact removal.
  Only the synthetic disposable contact was removed; no real account password
  or production contact was modified. Screenshots:
  `/tmp/leadzen-credential-eyes.png`, `/tmp/leadzen-contact-delete-confirm.png`,
  `/tmp/leadzen-contact-deleted.png` (mode 600).
- Local preview: `http://localhost:3000/settings`; disposable workspace remains
  `/tmp/leadzen-preview.RNCuxg`. API session 79149 and dashboard session 6308.
  External sends/worker dispatch are disabled. Real Zoho delivery and live
  credential validity have not been verified.
- A future approved release requires migration **0008** on every employee
  database, in addition to the earlier pending chat migrations. No new environment
  variable is needed. Coordinate the frontend/backend update and reload old
  clients: the former Stop button used DELETE; the new Stop uses PUT while
  DELETE now removes a contact from the list.

## Six-step employee wizard — local only, 2 October 2026

The owner requested the six screens in order and ten tests of every step. The
earlier **Keep it local for now** decision remains in force. No production
deployment, live key, mailbox, account, credit balance or provider call was used.

- Implemented AI provider → BetterContact → employee identity → SMTP/API sender
  and IMAP → product/offer → structured audience. Public drafts persist per
  employee; incomplete setup resumes after refresh. Completed accounts can
  review it. Successful completion opens the existing tour/workspace and writes
  the offer and canonical target to the existing engine, not a separate demo
  campaign store. Identity and sending mailbox are separate; login email is
  never changed by setup.
- Explicit production test adapters invoke one model request, GET the
  BetterContact account balance, or authenticate SMTP/IMAP and select INBOX
  read-only. They do not search for leads, enrich an email, send mail or fetch
  messages. Email API delivery is **not** validated by the IMAP test; the UI
  distinguishes inbox success from sending credentials merely saved.
- Connection success requires private, 24-hour HMAC receipts tied to exact
  settings/credentials. Failed retests clear prior success. Per-workspace test
  leases, per-user/kind throttles, post-probe session revalidation and concurrent
  settings checks prevent duplicate tests, revoked saves and stale overwrites.
  Final completion revalidates every stage. Keys are encrypted and returned only
  as presence flags. Typed-secret eye controls remain shared and accessible.
- Red-before-green evidence: initially 17 missing-route/probe failures; then
  eight regressions covering failed retests, simultaneous settings changes,
  identity defaults and malformed structured inputs; finally a real Groq SDK
  request (with the HTTP boundary mocked) exposed a doubled `/openai/v1` path.
  Fixed SDK-native Groq base normalization, enabled low-effort GPT-OSS checks
  with a 256-token allowance, and kept one request/no tools/no retries.
- **10 fresh backend workflows × 6 sequential steps = 60 successful step
  assertions**, plus completion/resume checks. **10 complete Chrome wizard
  repetitions × 6 steps = 60 successful browser step checks**, each running AI,
  discovery and mailbox test buttons with distinct synthetic credentials.
  The first empty employee setup also reached and completed the six-screen
  product tour. Additional browser checks covered invalid names, refresh/resume,
  changed-model invalidation/blocked Continue, saved connection status and all
  five eye toggles on Connections. Unsaved eye-test inputs were discarded.
- Provider boundaries in browser tests were explicitly mocked and labeled
  **Synthetic local test — no external provider calls**. The displayed 40
  credits is a fixture, **not a live BetterContact balance**. Separate adapter
  tests cover actual SDK request serialization, real account-response parsing
  (including zero/invalid balances) and SMTP/IMAP calls without delivery/read.
  Real credentials, response latency, provider account permissions, delivery,
  and inbox placement remain unverified.
- Final full backend suite: **178 passed**. Optimized Next.js build, TypeScript,
  migration drift, Python compilation and `git diff --check` passed. Real-file
  integration verifies two-employee draft/check isolation, ignored forged
  workspace identifiers, encrypted secrets and revocation before provider calls.
- Responsive browser checks: every screen at 375×812 had no horizontal overflow;
  the temporary viewport was reset. Existing calm-neutral/indigo tokens,
  keyboard focus, 44px controls and reduced-motion rules were retained. Design
  and credential/tenant/TDD skills guided the shared forms and fail-closed
  connection proofs; this is not an independent accessibility/security audit.
- React Doctor: changed tracked-file scan **100/100** (not full coverage);
  full **52-file** scan **68/100**, no errors and **12 warnings**. The warning
  count/score are unchanged from the prior checkpoint; the old giant onboarding
  warning is replaced by a Connections size warning. No findings suppressed.
- Screenshots (mode 600): `/tmp/leadzen-six-step-ai.png`,
  `/tmp/leadzen-six-step-audience.png`, `/tmp/leadzen-six-step-mobile.png`.
  Preview: `http://localhost:3000/onboarding`, disposable database directory
  `/tmp/leadzen-preview.RNCuxg`; API session **91319**, dashboard **3078**.
  The preview permits synthetic setup checks only and forbids outbound mailbox
  sockets, provider sends and worker dispatch.
- Future approved rollout: migrate **0009** on the control database and **every
  employee workspace**, following the pending 0006–0008 migrations; deploy
  backend before the matching dashboard. No new environment variable is needed.
  Preserve the stable encryption key. Live internal credential testing and any
  send require separate authorization; this release has not been deployed.

## Post-setup home dashboard (2026-10-02, local only)

- Added a time-of-day greeting using the saved operator identity, five real
  workspace totals, a dated BetterContact balance with an explicit account-check
  action, current target, qualification decisions/reasons, and Find More Leads.
  Existing queue, mailbox capacity and job controls remain below the summary.
- Count definitions: found = real finder profiles, not training anchors or
  manually imported contacts; qualified = explicit positive finder states,
  excluding rejected/disqualified/deleted profiles; with email = qualified
  profiles holding an address. Contacted = distinct normalized recipient
  addresses with recorded provider acceptance, including imported contacts.
  Replies = distinct human senders in accepted outbound threads, not auto-replies,
  bounces, unrelated mail or opt-outs. Counts span saved targets, not just today;
  historical verdicts are not silently re-qualified when the target changes.
- Credits are the last account-check snapshot, never an invented/live number.
  Changed keys invalidate the displayed balance; zero and unknown are distinct.
  Refresh reuses the bounded, rate-limited setup probe and does not enrich leads.
- `/target` edits only active audience instructions and the corresponding wizard
  draft. It reuses step-six validation without requiring connection retests.
  Unfinished wizard edits cannot replace the active target card. Chat shortcuts
  prefill reviewable requests without creating a run or spending credits on click.
- Five focused tests failed before implementation, then nine home/web tests passed.
  Full backend suite: **183 passed**. Real-file integration additionally checks
  discovery totals/reasons and target reads/writes across two isolated employees,
  including forged workspace identifiers. TypeScript, optimized Next.js build,
  Python compilation and `git diff --check` passed. No new database migration or
  environment variable is required for this home-page change.
- Browser validation in the disposable employee workspace covered persisted
  metrics (4 found / 2 qualified / 1 with email / 1 contacted / 1 reply), cached
  credit refresh, target edit/save/return, Find More Leads and Review replies
  prefilled chat requests, and responsive layouts at 375x812 and 1440x1000.
  No horizontal overflow; activity icons and text have a verified 10px gap.
  A loading-state flicker was fixed so unavailable data is not presented as empty
  connections. Viewport overrides were reset after testing.
- React Doctor tracked-file scan: **100/100**. Full scan: **55 files, 68/100**,
  no errors, 13 warnings (12 prior warnings plus a locale-render warning in the
  new summary). The new warning is not an SSR hydration path: that component
  mounts only after the parent's browser fetch resolves; SSR shows a skeleton.
  The formatter is reused. No diagnostics were suppressed and score did not drop.
- Screenshots (mode 600): `/tmp/leadzen-home-desktop.png` and
  `/tmp/leadzen-home-mobile.png`. Preview home: `http://localhost:3000/`.
  API session **17278**, dashboard session **28662**, disposable data
  `/tmp/leadzen-preview.RNCuxg`.
  Preview qualification/mail records and the 40-credit balance are explicitly
  synthetic. No actual discovery, enrichment, email send, production change,
  commit, push or deployment was performed. Live provider behavior is unverified.

## Workspace navigation (2026-10-02, local only)

- Workspace now lists Dashboard, Find Leads, Leads, Campaign, Inbox, Sending,
  Suppression, then a visual gap before Activity and Settings. Chat mode and
  conversation history are unchanged. Purpose & setup and Product tour are
  available from Settings, with Settings highlighted for those child pages.
- Find Leads opens the existing orchestrator with a reviewable discovery request
  and Workspace navigation. Sending reuses the existing queue, mailbox capacity
  and guarded worker controls. Activity combines recent saved qualification,
  mailbox and job events. Neither navigation nor page refresh starts a job.
- Inbox reads saved inbound messages with classification, search, pagination and
  plain-text details; it never renders email HTML or loads remote content.
  Mailbox sync is a separate reviewable chat request, not a side effect of opening
  the page. Suppression is a searchable, paginated read-only opt-out ledger.
- New inbox/suppression APIs require an authenticated, onboarded employee and use
  the existing per-employee database router. Pagination/search/body sizes are
  bounded; forged workspace identifiers cannot select another employee's file.
  No new migration or environment variable is needed.
- Four route tests failed before implementation. Focused route/integration tests:
  **14 passed**. Full backend suite: **196 passed**. Coverage includes anonymous
  access, two actual employee database files, forged workspace IDs, filters,
  pagination, method restrictions, oversized message bodies and secret omission.
  TypeScript, optimized Next.js build, Python compilation and diff checks passed.
- Browser checks visited all nine destinations, inspected exact labels/hrefs and
  selected-page state, exercised inbox expansion/filter/search-empty states, and
  verified mobile menu open/close. Desktop 1440x1000 and mobile 375x812 had no
  horizontal overflow or framework error overlays; page error logs were empty.
- React Doctor tracked-file scan: **100/100**. Full **61-file** scan: **68/100**,
  no errors, 14 warnings. Score unchanged; the added locale formatter warning is
  in stored-data views mounted only after a client fetch, not an SSR date-render
  path. No findings suppressed. The interface/security skills guided consistent
  menu spacing, accessible controls, safe text rendering and tenant-scoped reads.
- Screenshots: `/tmp/leadzen-workspace-menu-desktop.png`,
  `/tmp/leadzen-inbox-desktop.png`,
  `/tmp/leadzen-workspace-menu-mobile.png`, `/tmp/leadzen-inbox-mobile.png`.
  Disposable preview data remains `/tmp/leadzen-preview.RNCuxg`; API session
  **3091**, dashboard session **48794** at `http://localhost:3000/`.
  All provider calls/sending are disabled in that preview. No real
  discovery, enrichment, email send, production change, commit, push or deployment
  was performed.

## Structured Find Leads (2026-10-02, local only)

- Replaced `/find-leads`'s chat landing with **Find New Leads**: a default count
  of 3, decrement/increment controls, numeric input bounded to 1–25, and explicit
  email choices. **Don't find emails / Free discovery** is selected by default.
  The review displays **Finding 3 leads** and **0 BetterContact email credits**
  before Start Finding. Verified-email selection updates both the option label
  and review to **up to N credits**. AI-provider charges are separately disclosed.
- The new authenticated `/api/discovery` reads saved configuration without
  provider requests, then validates the exact submitted count, email choice,
  displayed budget, setup revision and idempotency ID before launch. Employee
  identity is derived from the session, never from client workspace identifiers.
  Changed targets/settings, incomplete setup, active tasks and shared rate limits
  block launch. Reusing an identical request returns its run without replaying it;
  reusing its ID for different choices is rejected.
- Start Finding records an explicit, server-generated single-action approval and
  uses the existing employee-scoped chat worker. It finishes after the finder
  result, without an orchestrator model decision that could change the request or
  choose a send. Live access, snapshot/expiry checks, atomic claims, cancellation,
  deadlines and provider guards are retained. Partial results remain recorded and
  the run stops as failed. Neither mode sends outreach emails.
- The existing CLI receives `find N leads --json --new` for free discovery, or
  `find N emails --json --new` for verified lookup. The latter uses the engine's
  verified-address credit cap, not the potentially broader `--emails` flag on a
  leads run. Qualified profiles without an address can also be retained; the UI
  explains this. Discovery itself still uses the employee's AI provider.
- Thirteen focused tests failed before the feature existed. Final discovery/chat/
  real-file integration checks: **33 passed**. Full backend suite: **214 passed**.
  The **17 discovery tests passed in each of 10 consecutive runs**. Coverage
  includes both choices, exact budgets/arguments, duplicate dispatch, invalid
  counts/types, stale setup, setup blockers, partial results, rate limits and
  unauthenticated access. Two real employee database files additionally verify
  own-target reads and foreign-thread/cancellation rejection despite forged
  workspace IDs. No real finder, model or email provider was used by these tests.
- Browser checks verified default free selection/cost, live verified estimates,
  both counter buttons, lower/upper bounds, empty/zero/26/fractional rejection,
  keyboard radio selection and successful synthetic starts. The free run records
  3 leads with a zero-credit budget; the verified run records 4 with an up-to-4
  budget, both ending without a send. Desktop 1440x1000 and mobile 375x812 have
  no horizontal overflow; the cost is above the start button in both layouts.
  Page-error logs are empty and no framework error overlay was observed.
- TypeScript, optimized Next.js build, Python compilation and diff checks passed.
  React Doctor tracked scan: **100/100**; full **62-file** scan: **69/100**, no
  errors and the same 14 pre-existing warnings. The initial new complexity
  warning was fixed by separating options, cost review and saved-setup notices;
  no findings were suppressed. Interface/security skills guided clear cost review,
  native accessible inputs and exact tenant-bound approval rather than AI guessing.
- Screenshots: `/tmp/leadzen-find-leads-desktop.png`,
  `/tmp/leadzen-find-leads-desktop-verified.png`,
  `/tmp/leadzen-find-leads-mobile.png`,
  `/tmp/leadzen-find-leads-mobile-verified.png`,
  `/tmp/leadzen-find-leads-run-verified.png`. Preview:
  `http://localhost:3000/find-leads`; disposable data
  `/tmp/leadzen-preview.RNCuxg`, API session **38828**, dashboard session **8670**.
  Preview runs use a synthetic finder that does not purchase or invent contacts.
- No new migration or environment variable is needed for this change. A future
  authorized release must deploy the matching backend before the dashboard. No
  production changes, deployment, commit, push, real discovery, enrichment,
  credit spending or email sends were performed. Live provider behavior remains
  unverified.

## Live finder progress (2026-10-02, local only)

- Added authenticated `/find-leads/<run-id>` with actual saved-results progress,
  discovered/evaluated/qualified/rejected counters, provider-reported email
  usage, search filters, qualification reasons, safe profile links and a results
  table. Partial results cannot be presented as the requested completed goal.
  The design follows the existing restrained neutral/indigo dashboard, semantic
  progress/status controls, keyboard-focusable results and responsive layout.
- Pause waits for an action checkpoint; Resume continues only the remaining goal
  without renewing approval or reserving extra credits. Stop preserves results.
  Employee ownership is checked before credentials or launch, including in two
  actual private SQLite files. Changed setup, stale authorization, foreign controls,
  deleted/unqualified profiles, duplicate dispatch and uncertain provider requests
  are covered. The secure-SaaS workflow guided actor-derived scope and repeated
  authorization/cost checks at external sinks.
- **Find Emails** opens a read-only review with nothing selected. Choosing profiles
  updates the estimate; explicit confirmation creates an exactly scoped email-only
  run. Neither completion nor opening the review buys emails or sends outreach.
  Selected email runs cannot discover other profiles. Missing usage is unknown
  rather than zero, and accepted uncertain work is not replayed.
- Initial progress tests: **4 failed, 1 passed** before implementation. Final
  full backend suite: **244 passed**. All **47 discovery tests passed in each of
  10 consecutive runs**. Mocked pinned HTTPS verifies free/paid separation,
  disabled paid add-ons, reported credit accounting and cancellation after an
  accepted submission. Adapter tests exercise actual saved qualifier verdicts
  without a live model. Domain-only companies and email goals without an address
  are tested. Live provider credentials, billing and delivery remain unverified.
- TypeScript, optimized Next.js build, Django system checks and whitespace checks
  passed. Migration dry-run reports no missing migration. React Doctor tracked
  scan: **100/100**; full **66-file** scan: **69/100**, 14 existing warnings,
  no new findings in the discovery components. No findings suppressed.
- Isolated headless browser checks used disposable accounts/sample data: completed
  3/3 free profiles at zero credits; paused at 2/25, resumed the remaining goal,
  and stopped after more results; opened read-only email review, selected one
  profile, recovered a stale review, explicitly confirmed and obtained a clearly
  labeled synthetic 1/1 email result. Transcript links return to the live view;
  results survive navigation/server restart. Desktop 1440x1100 and mobile 375x812
  were visually reviewed. Mobile has no page overflow; the results table remains
  internally scrollable. Error logs were empty and no framework overlay observed.
- Screenshots: `/tmp/leadzen-live-complete.png`, `/tmp/leadzen-live-paused.png`,
  `/tmp/leadzen-live-email-complete.png`, `/tmp/leadzen-live-mobile.png`.
  Preview: `http://localhost:3000/find-leads`, API session **20873**, dashboard
  session **50733**. All provider calls/sending are disabled; sample credit values
  are simulated, not real billing. Preview databases were migrated through **0010**.
  Future authorized deployment must migrate the control database and **every
  initialized employee workspace** before starting the matching backend/dashboard.
  No new environment variable is needed. No real discovery, paid enrichment,
  email send, production change, commit, push or deployment was performed.

## Leads mini CRM and campaign offer/sequence (2026-10-02, local only)

- Leads now has search and All / Qualified / Email Found / Contacted / Replied /
  Suppressed filters, saved identity/title/company, safe profile/company links and
  a detail view with the actual qualification reason. Manual contacts are not
  automatically labeled qualified. Addressless leads remain editable; deleting
  or stopping a lead prevents subsequent enrichment/sending without erasing
  history. Employee scope is derived from the authenticated actor before reading
  credentials or resolving a contact.
- Find Work Email first opens a read-only, single-profile review with an explicit
  up-to-1-credit cost. Cancel creates no work. Confirmation binds the request to
  the saved profile/setup and uses the existing bounded worker. Duplicate requests
  cannot relaunch a purchase, and uncertain accepted lookups cannot be retried
  automatically. Email verification and credits are provider-reported facts;
  missing usage stays unknown and catch-all results are not individually verified.
- Campaign drafts store name, target, product, optional HTTPS booking link and
  signature. New sequences default to initial outreach plus follow-ups after 3
  and 5 further working days. Mon–Fri timing uses the saved timezone and actual
  preceding send, including daylight-saving transitions; holidays are not modeled.
  Existing calendar-day sequences retain their behavior. Due messages still need
  an employee-run pass; this change does not install an automatic scheduler.
- Run Due opens the exact personalized subject/body/recipient review. A bounded
  confirmation expires after 15 minutes, is idempotent and is checked again at
  the sending sink. Opt-outs, replies, deletions, access changes and changed
  content revoke execution. A worker atomically claims a queued job and cannot
  resurrect a claimed/completed job. The design/security skills guided restrained
  styling, accessible inline confirmations/focus return and exact paid/send
  approvals rather than trusting arbitrary client recipient IDs.
- Final full backend suite: **283 passed**. All **53 focused CRM/campaign tests
  passed in each of 10 consecutive runs**. Tests cover stage facts, foreign
  contacts before credentials, source identity, costs, lookup verdicts, stale and
  duplicate approval, stopped/deleted/unqualified profiles, template/signature
  rendering, working-day/DST timing, legacy timing, exact send review and worker
  replay/sink guards. Real-file account scenarios exercise two private employee
  databases. The local HTTP invitation/login/onboarding/contact/campaign/privacy/
  logout flow passed; actual sending deliberately returns the preview-disabled
  response. Provider behavior and real billing/delivery remain unverified.
- TypeScript, optimized Next.js production build, Django's built-in system check
  (zero issues), migration dry-run (no missing migration) and whitespace checks
  passed. React Doctor tracked scan: **100/100**; full **71-file** scan: **70/100**,
  14 existing warnings. New component complexity was reduced by splitting offer,
  sequence, lookup-result and confirmation components; no findings were suppressed.
- Isolated headless browser checks exercised search/filters, contact detail,
  Cancel without lookup, explicitly confirmed synthetic verified email with a
  clearly labeled simulated 1-credit result, campaign creation/draft edits,
  activation and the exact read-only sending preview. Desktop and 375x812 mobile
  views were visually inspected. The mobile Leads page is 375px wide with no
  outer overflow; its table scrolls internally. Error logs were empty and no
  framework overlay was observed. No real sending confirmation was executed.
- The standalone production build served its login page, but correctly refused
  authentication against the plain-HTTP local backend. The production HTTPS
  requirement was not weakened. Development mode was restored and its complete
  HTTP flow passed again. An authorized production release must use the existing
  HTTPS backend; authenticated production end-to-end operation was not verified
  by this local-only check.
- Migration **0011** adds campaign offer/timing fields, reported email verdicts
  and bounded send-job approval. Preview control/employee databases were migrated.
  A diagnostic invocation of the finder-owned `manage.py check` also forward-
  migrated the local checkout's `data/db.sqlite3`, then stopped at incomplete
  onboarding before any provider or email action. No rollback was attempted;
  subsequent system checks used Django's built-in check command explicitly.
  Future authorized deployment must migrate the control database and **every
  initialized employee workspace** before starting the matching application.
  No new environment variable is needed.
- Preview: `http://localhost:3000/contacts` and `/campaigns`, disposable data
  `/tmp/leadzen-preview.RNCuxg`, API session **43282**, dashboard session **50317**.
  Screenshots: `/tmp/leadzen-crm-mobile.png`,
  `/tmp/leadzen-campaign-mobile.png`, `/tmp/leadzen-campaign-review.png`.
  Preview provider calls/sending are disabled and samples are synthetic. No real
  credits were spent, outreach sent, production changes made, deployment, commit
  or push performed.

## Human-reviewed outreach and threaded Inbox (2026-10-02, local only)

- Sending now prepares saved personalized drafts rather than sending from a
  count-only action. Email Preview shows the exact recipient, subject, final
  body, signature and STOP opt-out, without software attribution. Each draft
  supports Regenerate, Edit and Approve; changes clear approval. All messages
  must be approved before a separate final count/sender confirmation can start.
- The UI displays actual eligible contacts, remaining capacity and the existing
  engine's enforced **8 AM–8 PM Mon–Fri** window in the saved country timezone.
  The requested 9 AM–5 PM example is not presented as an enforced setting.
  Provider acceptance and its event timestamp drive per-person progress. Pacing,
  windows, daily capacity, fresh inbox sync, account access, suppression and
  deletions are checked again before transport. Stop retains accepted history.
  Uncertain attempts are held for review, not automatically retried. Deferred
  contacts need a fresh approval; no new follow-up scheduler is installed.
- Inbox now shows saved two-sided conversations, search and pagination. Refresh
  reads saved data only. Mailbox sync needs separate Chat approval. Suggest reply
  uses a bounded structured model with no tools, never automatically sends, and
  treats incoming content as untrusted data. Addresses, mailbox, reply subject
  and threading headers are server-owned. Editing, approval and final explicit
  sending remain required. New replies, previous attempts and opt-outs block
  stale suggestions; exact known-contact STOP replies are honored during sync.
- Backend suite: **326 passed**. All **43 reviewed-outreach tests passed in each
  of 10 consecutive runs** after the final backend changes. These are automated
  regression repetitions, not ten manual browser passes per screen. Tests cover
  no-send previews, bounded counts, copy/signature/opt-out equivalence, edits,
  regeneration, final confirmation, idempotent launch/worker replay, pacing,
  windows, uncertain attempts, live access/suppression/deletion checks, fixed
  reply identity/headers, prompt-injection text, provider-sink revocation and the
  actual Pydantic AI output path using a synthetic test model. Separate-process
  scenarios check two actual private employee databases and reject foreign IDs
  before credentials/model access. No live provider call was needed.
- Local Next.js-to-Django HTTP invitation/password/onboarding/tour/contact/
  campaign/isolation/revocation/logout flow passed. TypeScript and optimized
  Next.js production build passed. Django system-check registry returned zero
  findings; migration consistency reported no changes. The finder-owned Django
  `check` command was also invoked against the disposable control database: it
  stopped at incomplete finder onboarding, without a provider action. The true
  system-check registry was then invoked directly. Whitespace checks passed.
- Isolated browser checks covered unapproved previews, editing/regeneration,
  all-message approval, final No without starting, then final Yes for a synthetic
  three-person run. Progress reached 3/3 fake acceptances; a saved human reply
  produced a separate unapproved suggestion, was edited/approved, explicitly
  sent through the synthetic transport, and appeared in the same three-message
  conversation. A second answer to that inbound message was blocked. Desktop
  1280x720 and mobile 375x812 were visually checked; the mobile page remained
  375px wide, with no horizontal overflow, framework overlay or page errors.
- React Doctor full-tree scan: **78 files**, no errors and **14 pre-existing
  warnings**, none in the new review/sending/inbox components. No warnings were
  suppressed. Security/email skills guided exact tenant-bound approval and no
  automatic actions from inbound text; design guidance kept the existing neutral/
  indigo theme, accessible inline confirmations and mobile conversation layout.
- Migration **0012** adds review/draft approval and durable attempt state.
  Preview control and initialized employee databases were migrated. A future
  authorized release must back up and migrate the control database **and every
  initialized employee workspace**, then deploy the matching dashboard.
  No new environment variable is required. Authenticated production runtime,
  actual model credentials, IMAP sync, sender authentication and real delivery
  remain unverified by these local-only tests.
- Preview: `http://localhost:3000/sending` and `/inbox`, disposable data directory
  `/tmp/leadzen-preview.4jN21Q`, API session **60064**, dashboard session **8178**.
  Screenshots include `/tmp/leadzen-start-outreach-desktop.png`,
  `/tmp/leadzen-email-preview-desktop.png`,
  `/tmp/leadzen-outreach-progress-desktop.png`,
  `/tmp/leadzen-inbox-reply-review-desktop.png`,
  `/tmp/leadzen-inbox-thread-mobile.png`, `/tmp/leadzen-inbox-reply-mobile.png`,
  `/tmp/leadzen-sending-final-mobile.png` and `/tmp/leadzen-inbox-final-desktop.png`.
  Screenshot files are owner-readable only (mode 600).
  Preview bodies, recipients and acceptance events are synthetic. All external
  providers are disabled. No real emails, paid enrichment, production changes,
  deployment, commit or push occurred.

## Lead timeline and Do Not Contact — October 2, 2026

- Lead detail now shows stored outreach events and campaign follow-up dates.
  Transport acceptance timestamps distinguish accepted emails from unconfirmed
  attempts. The saved next-send date is authoritative; later dates are labeled
  estimates and respect campaign timezone and working-day settings. Follow-ups
  still require the existing reviewed Run Due action; no scheduler was added.
- Stop Sequence requires inline confirmation and retains email history. Saved
  human replies and opt-outs remove future sequence steps and show why the
  sequence stopped. Automatic replies remain distinct from human replies.
- Do Not Contact supports searchable, paginated email/reason/date records and
  confirmed additions. A shared helper normalizes addresses, preserves existing
  reasons and dates, stops matching open contacts and campaign recipients, and
  keeps suppression effective after deletion and reimport. Historical mixed-case
  addresses are normalized without changing their record identity or metadata.
- Backend suite: **341 passed**. Coverage includes real upstream import behavior,
  terminal suppression, acceptance/reply timestamps,
  automatic replies, authentication/revocation and two separate employee database
  files with overlapping IDs and addresses. Providers and credentials are mocked.
  Frontend lint and optimized production build passed; whitespace checks passed.
- React Doctor full-tree scan: **80 files**, no errors and **14 pre-existing
  warnings**, with no new findings or suppressed rules. No migration is needed.
- Synthetic browser checks covered saved/estimated follow-up dates, Stop Sequence
  cancellation and confirmation, suppression cancellation and confirmation,
  searchable records and reply-stopped timelines. Desktop and 375px mobile views
  were visually checked; the mobile list and timeline had no horizontal overflow.
  Screenshots: `/tmp/leadzen-timeline-desktop.jpg`,
  `/tmp/leadzen-do-not-contact-mobile.jpg` and
  `/tmp/leadzen-timeline-reply-mobile.jpg`, all owner-readable only (mode 600).
- Preview is now at `http://localhost:3001`, with `/suppression` and `/contacts/4`
  showing synthetic records. It uses `/tmp/leadzen-preview.4jN21Q` and the local
  provider-disabled API. All pre-existing uncommitted work was preserved. No real
  email, provider credit usage, deployment, production change, commit or push
  occurred.

## Readable Activity and optional Developer Logs — October 2, 2026

- Activity now groups saved events by day with local times, plain-language action
  names and lead names or result counts. Discovery, qualification/rejection,
  email acceptance, reply classifications, outreach jobs and suppression are
  represented without displaying worker output. Older finder decisions remain
  visible without duplicating monitored verdicts. The dashboard run list also
  uses a readable requested count instead of raw worker output.
- The finder observation adapter records actual returned page counts separately
  from provider index totals. Unavailable pages do not invent a completed search.
  Older runs retain their existing saved facts; counts are not parsed from logs.
  The live discovery page renders the new completion event and count as well.
- Developer Logs starts closed, requests diagnostics only when opened, and shows
  bounded saved worker output plus recent private log tails. Paths and workspace
  identity are server-owned; symlinks, nonregular files and foreign employee
  identifiers cannot select another file. Known credentials and protocol
  authentication lines are removed. Credential-redaction errors fail closed.
- Backend suite: **356 passed**, including **58 focused activity/discovery/view
  checks**. Tests cover returned-row truth, no provider action on reads, duplicate
  verdict prevention, classification/acceptance timestamps, output bounds, secret
  removal, invalid log files, session revocation, and two actual private employee
  databases and log directories with overlapping run/job IDs.
- React Doctor full-tree scan: **82 files**, **14 pre-existing warnings**, no new
  findings or suppressed rules. Frontend type checking and the optimized
  production build passed. No migration or environment variable is required.
- Synthetic browser verification covered default-hidden logs (zero terminal
  blocks in the feed), keyboard opening, focus on the revealed heading, closing
  with focus restored to the opener, and reload restoring the closed default.
  Desktop 1280px and mobile 375px views were checked. Both feed and logs stayed
  within 375px on mobile; event links have at least 44px targets. No browser
  console errors were observed. Screenshots, mode 600:
  `/tmp/leadzen-activity-desktop.jpg`, `/tmp/leadzen-activity-mobile.jpg`,
  `/tmp/leadzen-developer-logs-desktop.jpg` and
  `/tmp/leadzen-developer-logs-mobile.jpg`.
- Preview: `http://localhost:3001/activity`, using the same disposable local data
  directory and provider-disabled API. Preview search and protocol events are
  explicitly synthetic fixtures. Existing uncommitted work was preserved. No
  deployment, production change, real email, provider credit usage, commit or push
  occurred.

## Central Settings and workspace backup — October 2, 2026

Settings now presents AI, BetterContact, identity, mailbox, product, target,
signature, booking link and local data together. Each section opens an inline
editor; cancel discards edits and restores focus. Identity edits preserve the
login account. Public workspace edits preserve encrypted connection credentials.
Product and audience changes update both the canonical engine configuration and
the onboarding draft, using the existing validation and target review controls.
The six-step setup and the existing dashboard/discovery/email review journey
remain in place. Buying verified emails and sending still require explicit
approval. Follow-ups remain reviewed, manually initiated due runs; this change
does not install an unattended scheduler.

Connection status and BetterContact credits come from matching saved test
receipts, with the test date visible. Page loads and saves never probe providers.
Test opens a confirmation describing its effect, including possible AI charges;
only Confirm test invokes the existing bounded check. No credentials are returned.

Data shows the employee's server-derived combined SQLite database path and size.
Backup Database downloads a consistent SQLite backup containing committed WAL
records. The exported copy uses single-file rollback format, so opening it does
not require creating WAL sidecars. Its contents belong only to the signed-in
employee; supplied paths and workspace IDs cannot choose another database. The
control database and the server encryption key are excluded. The UI explains
that restoring encrypted connections also needs that key. Backups are private,
non-cacheable downloads; creation is bounded to ten seconds and 512 MB.

GET localhost:8000 redirects to LEADZEN_PUBLIC_URL. For this disposable preview
that is localhost:3001, preserving the unrelated website already using port 3000.
Invalid origins, credentials, malformed ports and self-redirects fail closed.

Validation:

- Final full backend suite: **369 passed in 111.16 seconds**. An earlier run's
  mocked Groq probe exceeded its unchanged seven-second deadline under load;
  all three probe variants passed in isolation, and the final full run passed.
  The 13 Settings/backup tests also passed after tightening the WAL-aware
  512 MB export limit; the connection deadline remains unchanged.
- TypeScript (`npm run lint`) and optimized Next.js build passed.
- React Doctor changed tracked files: 100/100. Full tree: 86 files, 72/100,
  the same 14 pre-existing warnings; no new Settings findings or suppressions.
- Real two-employee backup/restore scenario checks finder records, sender records,
  configuration, committed WAL data, SQLite integrity, format and isolation.
  Forged workspace IDs and paths are ignored. Existing connection clients can
  round-trip GET responses; read-only summaries are separate from editable values.
- Browser: identity cancel/save and focus restoration, HTTPS booking validation,
  test cancellation, three mocked connection confirmations, dated credit balance,
  mailbox status and actual proxy download succeeded. The downloaded synthetic
  database was restored for inspection: integrity OK, own operator, zero control
  login sessions. The browser download-event waiter timed out, but the download
  was present on disk and the UI confirmed completion.
- Desktop and 375px mobile screenshots: `/tmp/leadzen-settings-desktop.jpg` and
  `/tmp/leadzen-settings-mobile.jpg` (mode 600). The responsive layout fits the
  viewport; a later automation geometry read timed out. The viewport was reset.
- No deployment, live email, external provider test or provider-credit spend.
  All original uncommitted work remains in the checkout.
