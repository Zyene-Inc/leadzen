# LeadZen by Zyene — full project handoff

> Historical October 2 snapshot. For a new coding session, start with
> [the agent entry guide](agent-start-here.md) and its current-state reference.
> Later releases, approved logo/theme changes, automatic follow-ups, real streaming,
> and Chat history/shared-refresh refinements supersede relevant sections below.
> This document does not grant authorization for new external actions.

Prepared 2026-10-02, America/New_York. This is a consolidated context handoff,
not a verbatim transcript. It preserves the requirements, decisions, implemented
work, verification, deployment boundaries and historical concerns from the long
conversation. Real passwords, API keys, tokens and encryption keys are omitted.

## 1. Read this first

- Continue the existing project; do not rebuild it from scratch.
- Repository: `/Users/ashishdikonda/Desktop/Openoutreach/OpenOutreach`.
- Product name: **LeadZen by Zyene**. Correct domain: **leadzen.zyene.com**.
  The user briefly wrote LeadGen/leadgen, then explicitly confirmed LeadZen.
- Company: **Zyene**. **Zyene Reviews** (`zyenereviews.com`) is a Zyene product,
  not the company that owns this internal outreach platform.
- Support and first production administrator: **support@zyene.com**.
- The latest implementation request is completed locally. No new feature is
  implicitly pending just because this handoff exists.
- The owner explicitly chose **Keep it local for now** after the earlier
  deployment. The subsequent BetterContact/chat/wizard/CRM/reviewed-outreach
  changes have NOT been deployed. Do not deploy without fresh authorization.
- This document is context, not permission to send emails, buy addresses, run
  live AI/provider tests, change production, or create paid resources.
- No actual email or paid enrichment was performed during the latest local
  implementation/testing. Synthetic browser acceptance events are not real sends.
- The worktree contains extensive uncommitted and untracked user work. Preserve
  it; do not reset, discard, mass-revert, overwrite credentials or assume that
  untracked files are disposable. No commit or push was made in the latest work.

## 2. Business goal and original outreach context

Zyene Reviews is a reputation management product for local businesses and
agencies. The user described:

- One inbox for reviews from Google, Yelp and Facebook.
- AI feedback analysis and response drafting.
- Review requests through SMS, email, QR codes and integrations.
- Better feedback collection, consistent responses, unhappy-customer handling
  and local-search visibility.

Original target: owners, marketing managers and agency founders serving 2–50
locations, especially dental practices, home services, restaurants, salons,
real estate and auto repair. These businesses often juggle reviews manually.
The outreach goal is a short email that gets a reply and leads to a demo.

Later emphasis: digital marketing agencies that could resell Zyene Reviews to
their existing local-business clients, potentially white-label. This is a desired
sales pitch/market; do not invent implemented white-label capabilities or pricing.

The owner's outreach identity was Karthik, using `karthik@zyenereviews.com`.
Ashish Dikonda appeared as an employee/example operator. Login identity and
sending identity must be separate: employees can configure different products,
services, targets and mailboxes without changing their account login email.

Historical requests included checking replies, sending to a particular restaurant
owner, finding agency clients, and sending to 35 well-matched leads. Those old
requests are NOT standing authorization to run anything now. The bounded web
flows currently accept at most 25 per run, with explicit cost/send approvals.

The user pasted an earlier result saying 5 verified leads, 45 remaining credits,
5 queued emails and deferral outside sending hours, with data in
`/tmp/openoutreach-session.sqlite3`. This is historical user-provided context,
not a newly verified balance, queue or current production database. Do not use
that temporary file as the authoritative database without inspecting its status.
Current actual sent totals and genuine customer replies were not rechecked in
the latest work.

## 3. Product ownership, access and design requirements

LeadZen is a private internal company tool, not a public self-serve SaaS.

- Admin logs in at `/admin` and manages employees: totals, search, invite/create,
  resend/reset, disable/enable and confirmed soft deletion.
- No public signup. Admin creates an employee with name/email; an invitation is
  sent using backend Resend configuration. Employee opens a single-use setup
  link, chooses a password, logs in, completes onboarding and sees the tour.
- Employees have separate private SQLite workspaces and encrypted connection
  credentials. They must never see another employee's contacts, jobs, chats,
  settings, invitations or secrets.
- Account suspension, password reset and deletion revoke access/sessions.
- The user requested an owner-only file containing production admin access.
  That file already exists outside the repository; do not overwrite it with a
  demo login. Its path is listed under private access below.
- Visual direction confirmed by the user: calm, precise, professional, inspired
  by Stripe/Linear. Neutral canvas, indigo actions, modest headings, dependable
  forms, readable real states. Avoid flashy gradients, invented charts and
  landing-page decoration. Support keyboard focus, reduced motion, narrow screens
  and approximately 44px touch targets. Read `PRODUCT.md` before UI changes.
- All user-facing identity should be LeadZen/Zyene. Customer mail must NOT say
  “Sent with OpenOutreach.” Preserve required GPL and third-party attribution
  in legal/source material and the real upstream dependency interfaces.

## 4. Connections and provider choices

Each employee configures their own settings in the web interface:

- AI provider, model, API key and approved Base URL, including OpenAI-compatible
  providers rather than only Groq.
- BetterContact API key, with separate discovery and paid email lookup decisions.
- SMTP/API sending credentials and independent IMAP reply-inbox credentials.
- Mailbox switching preserves historical rows but only the selected active sender
  can perform new sends. Replies require the original active mailbox.
- Eye icons reveal/hide what the user is currently typing in every secret field.
  Saved encrypted secrets are never returned to the browser for reveal.
- Blank secret input preserves the saved key; replacement and explicit removal
  are separate actions.

Historical AI choice changed from `groq:llama-3.3-70b` to
`groq:openai/gpt-oss-120b`. Do not globally hard-code that model: employees can
choose supported providers/models. An additional exact host, `api.akashml.com`,
was approved for `https://api.akashml.com/v1` in production after the user saw
“This llm host is not approved.” Endpoint approval does not prove that a model
ID or API key is valid. Never remove host allowlists, public-IP checks, pinned
connections, TLS verification or no-redirect protection to accept arbitrary URLs.

SMTP port 465 was previously rejected and is fixed locally using verified implicit
TLS. Ports 587/2525 use STARTTLS; IMAP commonly uses 993. The user has a Zoho
Mail Lite 5GB plan and reported expiry 16 June 2027. Wizard examples used
`smtppro.zoho.com:465` and `imappro.zoho.com:993`; correct live hosts/account
permissions must be verified for the actual account rather than assumed.

BetterContact async endpoint discussed: `https://app.bettercontact.rocks/api/v2/async`.
No live key is included here. Email-cost UI uses up-to-N-credit estimates and
provider-reported actual usage; unknown usage is not displayed as zero.

Resend is configured for account invitations. Existing application policy restricts
Resend marketing to explicitly opted-in contacts and blocks it for the reviewed
cold-initial-outreach flow. ZeptoMail is restricted by existing policy to
transactional use, not cold outreach. Provider integration is not permission to
ignore provider policy. Reverify current official rules if changing policy.

## 5. Implemented employee flow (local, newest code)

### Six-step first-time setup

1. AI provider/model/key/Base URL and explicit Test connection.
2. BetterContact key, Test connection and checked credit balance. Explain profile
   discovery versus optional verified work-email credits; AI costs are separate.
3. Operator name, identity email and country; name cannot look like an email.
4. Sending mailbox, SMTP/API settings, app password and IMAP; explicit test.
   SMTP/IMAP authentication success is distinguished from untested API delivery.
5. Product/offer name/context: what the employee is selling. No invented facts.
6. Structured audience: industry, country, company size, roles, seniority and
   exclusions, then canonical Target Preview / confirmation.

Draft setup persists per employee and resumes after refresh. Test success uses
24-hour private HMAC receipts bound to exact settings/credentials; changed values
invalidate success. Failed retests clear success. Completion rechecks all stages,
writes into the existing engine configuration and leads to the product tour.
Connection tests are explicit and bounded; they do not search, buy an address or
send a test email. The local preview mocks those tests with synthetic credentials.

### Post-setup Dashboard

Shows greeting, found/qualified/email/contacted/replied totals, last checked
BetterContact balance, current target with Edit Target, qualification/rejection
activity and Find More Leads. Metrics are persisted facts, not fake charts.
Manual contacts are not automatically marked AI-qualified. Acceptance is not an
inbox-placement guarantee. Unknown and zero credit balances are distinct.

### Workspace and Chat navigation

Workspace menu, in this exact order:

1. Dashboard
2. Find Leads
3. Leads
4. Campaign
5. Inbox
6. Sending
7. Suppression
8. Activity
9. Settings

Activity/Settings have a visual gap above them. Purpose & setup and Product tour
remain reachable through Settings. Chat is a separate navigation mode with new
chats, filtering, age-grouped private history, saved conversations, a greeting,
suggestions, composer, tool results, approval cards and cancellation.

### Agentic Chat

The employee's saved model chooses allowlisted tools in a bounded model/tool/result
loop. The tools use the existing finder, contacts, campaigns and sender rather
than a second fake implementation. Stored-data reads do not send/buy/sync.
Discovery, writes, mailbox sync and sending need explicit action approvals.
Sending approval freezes recipients and rendered content. The agent is NOT an
unrestricted terminal/shell, arbitrary SQL runner or unrestricted URL fetcher.
The UI polls durable job results, not pretend token streaming or private reasoning.
Deadlines, request/cost reservations, live access checks, cancellation, redaction,
atomic claims and crash recovery are implemented. See `docs/chat-orchestrator.md`
for exact tool budgets and approval/execution details.

### Find Leads and live discovery

Default count 3, with decrement/increment and integer bounds 1–25.
“Don't find emails / Free discovery” is default, showing 0 BetterContact email
credits before Start Finding. “Find verified emails” explicitly shows up to N
credits. AI costs remain separate; no outreach is sent by either mode.

Live view displays real persisted candidate counts, evaluated/qualified/rejected
facts, actual saved results, provider-reported credit usage, search filters,
qualification reasons and safe profile links. Pause waits for a safe checkpoint;
Resume only continues the remaining approved goal; Stop preserves results.
Partial results do not appear as full completion. Missing usage stays unknown.
After free discovery, Review Leads / Find Emails / Find More are separate actions.
Never automatically purchase email addresses on discovery completion.

### Leads mini CRM

Search plus All / Qualified / Email Found / Contacted / Replied / Suppressed.
Rows and details show identity, title/company, safe LinkedIn/company links,
actual qualification reason, email state and permission/history. Find Work Email
first opens an up-to-1-credit review; Cancel buys nothing. Confirmation targets
only that exact qualified profile. Duplicate/uncertain lookups are not replayed.
Reported valid versus catch-all verdicts are distinguished.
Contacts have Edit, Stop, Opt out and confirmed Delete. Delete is soft deletion:
it hides the contact, stops future work and retains consent/conversation/suppression
history. It is not permanent data erasure and cannot recall accepted emails.

### Campaign

Name, target/product context, optional HTTPS booking link and campaign signature.
New sequences default to an initial message, follow-up after 3 working days and
another after 5 further working days. Working days are Mon–Fri in the selected
timezone; holidays are not modeled. Old calendar-day campaigns retain behavior.
Draft/edit/activate/pause/archive and exact personalized due-send reviews exist.
Follow-ups are MANUAL due runs, not an installed unattended scheduler.

### Sending / Email Preview (latest completed feature)

- Start Outreach shows actual eligible contacts, remaining capacity, active
  mailbox, count selection and the existing enforced window.
- Current engine window is **8 AM–8 PM, Mon–Fri**, country-based timezone.
  The user's 9 AM–5 PM mockup is not an implemented configuration setting.
- First Review & Start generates saved AI drafts only: exact To, Subject and
  final body/signature/STOP opt-out. It does not send or buy emails.
- Regenerate, Edit and per-message Approve. Edit/regenerate clears approval.
- Every draft must be approved before the separate final “Send emails to N
  people?” confirmation. No starts nothing; Yes starts only exact approved copy.
- No count-only shortcut invokes autonomous sending anymore.
- Durable progress records actual provider acceptance and event timestamp,
  per-recipient waiting/attempt/uncertainty state and Stop.
- Revalidate access, setup/copy, suppression, deletion, replies, sender identity,
  windows/capacity/pacing immediately before delivery. Sync failure fails closed.
- Approval expires after 15 minutes; deferred work needs a fresh review. Do not
  queue overnight sends or auto-retry ambiguous SMTP/API outcomes.
- Provider acceptance is not proof of delivery, Primary placement or spam avoidance.

### Inbox (latest completed feature)

Private saved conversation list, search and both sides of full plain-text history.
Known contact names appear alongside “You”; remote email HTML/images are not
rendered. Refresh only reads saved messages. Sync replies is separately approved
in Chat. All stored messages still opens the older classified-message view.

Suggest reply uses the saved provider in a bounded structured call with no tools.
Inbound text is untrusted data, not permission to act. The model cannot select
recipients, credentials, mailboxes or send actions. The latest eligible human
reply can get an unapproved suggestion; employee edits/approves it, then separately
confirms sending. Original recipient/mailbox, subject and threading headers are
server-owned. New inbound messages, opt-outs, changed setup or an existing answer/
attempt block stale replies. Exact STOP from a known contact is honored during
approved sync projection, not by merely opening the Inbox.

## 6. Spam, Promotions and historical limits questions

The user reported mail landing in Spam and then Promotions after “Not spam,” and
showed a customer screenshot with a STOP line and “Sent with OpenOutreach.”
The software attribution was removed through a source-owned branding adapter.
STOP remains as a suppression mechanism; removal of branding is not a promise of
improved deliverability. Spam versus Promotions versus Primary is a separate
mail-provider classification problem. No latest live DNS, SPF/DKIM/DMARC, bounce,
complaint, reputation, sending-limit or inbox-placement audit was performed.

The user questioned whether Zoho really limits sending to 7 mails. Do not repeat
that as an established Zoho plan limit. Distinguish app ramp/daily capacity from
the provider's current policy. Recheck official documentation and actual account
diagnostics if asked. Historical screenshots/credit reports are not current proofs.

## 7. Architecture and important code locations

- Python/Django backend, registry, CLI and private APIs: `leadzen/`.
- Next.js 16.3.8 / React 19 / TypeScript dashboard: `dashboard/`.
- Installed exact dependencies: `openoutfind==0.1.10`, `openoutsend==0.1.32`.
  Their Python namespaces/interfaces are retained (`openoutfind`, `cold_outreach`,
  `OPENOUTFIND_*`, `OUTSEND_*`). Do not edit installed site-packages.
- `leadzen/config/models.py`: runtime configuration, campaigns, chat, onboarding,
  discovery ledgers and email review/draft records.
- `leadzen/configuration.py`: validation, encryption, approved endpoints/settings.
- `leadzen/accounts/`: admin/employee access, sessions and invitation capabilities.
- `leadzen/workspaces.py`: actor-derived private database routing and worker access.
- `leadzen/branding.py`: LeadZen identity and sender attribution suppression.
- `leadzen/ai.py`: source-owned provider constructors, pinned HTTP, runtime guards;
  local fix for the removed upstream `OpenAIModel` import/SDK compatibility.
- `leadzen/setup_wizard.py`: six-step drafts, receipts, test adapters/completion.
- `leadzen/home.py`: real dashboard counts/credit snapshot/current target.
- `leadzen/discovery.py`, `discovery_progress.py`: discovery approvals/progress,
  lookup receipts/credit accounting, pause/resume and enrichment.
- `leadzen/crm.py`, `campaigns.py`: leads and campaign validators/offer/timing/sends.
- `leadzen/outreach.py`: exact AI draft/edit/approve/start/guard/send state machine,
  deterministic saved STOP handling and read-only conversation APIs.
- `leadzen/transports.py`, `mailboxes.py`, `email_api.py`: SMTP/API/IMAP, active
  sender, encrypted credentials, TLS and acceptance recording.
- `leadzen/chat/`, `chat_worker.py`: allowlisted model/tool loop and durable worker.
- `leadzen/web.py`, `web_worker.py`, `urls.py`: API routing and bounded send workers.
- Dashboard review UI: `components/email-preview.tsx`, `outreach-review.tsx`,
  `sending.tsx`, `inbox.tsx`; types/polling in `lib/outreach.ts`, `use-stored-data.ts`.
- Frontend API proxy: `dashboard/app/api/proxy/[...path]/route.ts`; server-only
  service token, live employee session, same-origin writes, allowed paths/methods.
- Docs: `docs/local-validation.md` (chronological evidence),
  `docs/chat-orchestrator.md` (current behavior/limits), `docs/deployment.md`
  (older deployed baseline/env/recovery), `docs/dashboard.md`, `PRODUCT.md`.

Read root `CLAUDE.md`, `dashboard/CLAUDE.md` and `dashboard/AGENTS.md` before edits.
Use `.venv/bin/python`, preserve user changes, keep secrets server-side and retain
GPL/third-party legal notices. Read relevant installed Next.js guides under
`dashboard/node_modules/next/dist/docs/`; this installed version differs from
older training examples. Use apply_patch for edits. Do not write/restructure
project memory/instruction files as part of ordinary feature work.

## 8. Latest verification — completed, not pending

- Full backend suite: **326 passed** in the final run.
- `tests/test_reviewed_outreach.py`: **43 passed in each of 10 consecutive runs**
  after final backend changes. These are automated regressions, not ten manual
  passes through every UI screen.
- Earlier six-step wizard work did document 10 complete synthetic browser wizard
  repetitions; other earlier feature repetitions are in `docs/local-validation.md`.
- `npm run lint` (TypeScript), optimized `npm run build`, Django system-check
  registry (zero findings), migration dry-run (no changes) and diff checks passed.
- Actual local Next.js → Django → disposable private SQLite HTTP flow passed:
  invite/password/setup/tour/contacts/campaign/isolation/revocation/logout.
- Reviewed-outreach tests cover exact preview/send equivalence, bounded counts,
  approval invalidation, duplicate confirmation/worker claims, pacing, window/
  access/suppression/deletion/sync guards, uncertainty/no-retry, original reply
  identity/headers, untrusted text, latest human reply, provider-sink revocation
  and the real Pydantic AI structured-output path with a synthetic test model.
- Real-file scenarios use two private employee databases and reject foreign IDs
  before loading credentials or calling a model/provider.
- Isolated browser tested unapproved previews, edit/regenerate/approval, final
  No without launch, then final Yes with a **synthetic** three-person run reaching
  3/3 fake acceptances. A sample inbound reply produced an edited/approved reply
  that was **synthetically** accepted into the same conversation; answering that
  inbound again was blocked. No real email or model provider was called.
- Desktop 1280x720 and mobile 375x812 visually checked, with no page overflow,
  framework overlay or page errors. Other earlier viewport checks are documented.
- React Doctor full-tree scan: 78 files, no errors, 14 pre-existing warnings;
  no new warnings in the latest review/sending/inbox components, no suppression.
  A changed-tracked-file 100/100 score is NOT full untracked-file coverage.
- Production build success does not certify authenticated production runtime.
  The local dev API is HTTP; production requires HTTPS and that requirement was
  not weakened. Live model keys, IMAP access, real email acceptance/delivery and
  billing remain unverified by these synthetic checks.

Safe standard checks (from repository root unless noted):

```bash
.venv/bin/pytest -q
.venv/bin/pytest -q tests/test_reviewed_outreach.py
git diff --check
```

From `dashboard/`: `npm run lint` then `npm run build`. Stop only your own verified
development server before a production build to avoid shared build-cache conflicts,
then restore dev and verify it in a browser. Never kill arbitrary port owners.

Important: this project's Django `check` command is overridden by the finder.
It may migrate the configured DB and attempt finder readiness checks. Use the
actual framework check registry (`django.core.checks.run_checks`) or the built-in
framework Command explicitly against a disposable DB, not `manage.py check`
against user/production data. One earlier diagnostic already forward-migrated
the local checkout DB; do not undo or downgrade it casually.

## 9. Current local preview and synthetic data

At handoff preparation, both listeners were rechecked:

- Dashboard: `http://localhost:3000`, listener PID **91892**; originating execution
  session **8178**. It uses the synthetic localhost API, not production.
- API: `http://127.0.0.1:8000`, PID **89307**, execution session **60064**.
- Disposable data: `/tmp/leadzen-preview.4jN21Q` (parent mode 700).
- Older `/tmp/leadzen-preview.RNCuxg` was preserved but is not the current preview.
- Synthetic accounts: `ready@preview.example` (completed setup),
  `employee@preview.example` (wizard), `admin@preview.example` (administration).
  The local-only test password is in `docs/local-validation.md` and the preview
  script; it is intentionally not repeated here. Do not substitute real logins.
- Entry points: `/sending`, `/inbox`, `/chat`, `/find-leads`, `/contacts`,
  `/campaigns`, `/settings`, `/onboarding`, `/admin`.
- `tests/scenarios/local_preview.py` disables external SMTP/API/model/mailbox
  providers and captures invitations locally. Its reviewed worker simulates
  acceptance only for fixture recipients. Campaign sends stay disabled.
- Sample Bruce/Sarah/David records and credit numbers are fixtures, not actual
  discovery results, live balances or customers. Synthetic initial and reply
  jobs are complete; do not interpret them as production activity.
- The isolated browser test session was closed. User browser tabs were not closed.
- Session IDs/PIDs may expire or be unavailable in a new chat. Check current
  processes before reusing/stopping anything. Preview ports are already in use;
  do not blindly start duplicate servers.

For recreating a safe preview, follow `docs/local-validation.md` and
`tests/scenarios/local_preview.py`, using a mktemp directory and explicit synthetic
environment. Do not start an unmocked sender/server against real credentials.
`tests/scenarios/http_flow.py <disposable-preview-directory>` exercises local HTTP
flow with a local mail catcher. Screenshot paths are in the validation report and
their files are mode 600; temporary files may not persist indefinitely.

## 10. Existing production deployment — older baseline only

Recorded deployment was verified 1 October 2026; it was not rechecked live while
making this handoff. Source: `docs/deployment.md`.

- Employee: `https://leadzen.zyene.com/login`.
- Admin: `https://leadzen.zyene.com/admin`.
- Vercel project: `zyenes-projects/leadzen-dashboard`.
- Google Cloud project: `zyene-reviews`.
- Existing VM: `leadzen-api`, zone `us-central1-a`, instance type `e2-micro`.
- Backend: `https://leadzen-api.zyene.com`.
- Gunicorn binds loopback; Caddy handles public HTTPS.
- Existing service: `leadzen.service`; VM environment `/etc/leadzen.env` (root-only).
- Existing production admin/invitation/auth foundation was deployed and checked.
  Newer local provider-adapter/wizard/chat/discovery/CRM/reviewed-outreach features
  were NOT part of that baseline. Do not assume production equals this checkout.
- The AkashML host allowlist addition WAS separately applied to production after
  explicit approval. It did not test inference or send anything.
- A historical production worker failure was reported. Local AI SDK compatibility
  fixes exist, but the complete newer fix has not been deployed. Do not assert a
  confirmed cause for a new failure without current safe diagnostics.

Already configured Vercel server-only env:

- `LEADZEN_API_URL=https://leadzen-api.zyene.com`
- `LEADZEN_API_TOKEN` matching backend `LEADZEN_DASHBOARD_TOKEN` (value omitted).

Backend env names (values containing secrets omitted):

- `LEADZEN_DB=/opt/leadzen/data/db.sqlite3`
- `LEADZEN_WORKSPACE_ROOT=/opt/leadzen/data/workspaces`
- `LEADZEN_SETTINGS_KEY` (stable credential encryption key)
- `LEADZEN_DASHBOARD_TOKEN` (private service token)
- `LEADZEN_PUBLIC_URL=https://leadzen.zyene.com`
- `LEADZEN_ALLOWED_HOSTS`, `LEADZEN_DASHBOARD_ORIGINS`
- `LEADZEN_RESEND_API_KEY`, `LEADZEN_INVITATION_FROM`
- `LEADZEN_LLM_HOSTS=api.akashml.com`

Employee API keys/mail passwords belong in their encrypted backend workspace,
not Vercel env or NEXT_PUBLIC variables. These latest local features need no new
required Vercel variable, but do require matching code and schema.

Latest local config migration: **0012_email_review**. Pending local additions
include 0006/0007 chat, 0008 deletion, 0009 onboarding, 0010 discovery, 0011 CRM/
campaign fields and 0012 reviews. Do not assume production has run them already.
On a future explicitly authorized release: backup control and employee data and
stable env; stop intake/wait for workers; install matching source/package;
migrate control AND EVERY initialized employee workspace through the current
graph; restart/verify backend; deploy matching dashboard; test actor isolation
and approved internal provider access. Migration of control alone is insufficient.

## 11. Private access, security and recovery

Historical real passwords and Groq/BetterContact/Resend keys were pasted in the
old chat. They are deliberately absent from this handoff. Rotation was recommended;
the user explicitly authorized reuse of the Resend key at the earlier deployment.
Do not claim rotation was completed. Do not quote, screenshot, log or commit
secret values, or upload private credentials/backups to model providers.

Documented owner-only directory outside the repo:
`/Users/ashishdikonda/.codex/private/leadzen/` (mode 700).

- `admin-login.txt`: actual production admin access, mode 600. Preserve it; only
  access it when necessary for a separately authorized login task.
- `production-backend.env`: private env copy, including stable encryption key.
- `predeployment-2Ythod.tar.gz`: recovery archive of matching DB/env/service/code.
- VM recovery directories: `/opt/leadzen-predeployment.ha94ZH` and
  `/opt/leadzen-accounts-backup.GOWLFK`.

No contents of these private files were read for this handoff. Never overwrite
the stable encryption key casually: existing credentials depend on it. Database
downgrade is not automatic; recovery must restore matching DB/source/env/service.
The previous deployment cleaned temporary key copies while retaining real access
and backups. Do not repeat old SSH/Cloud Shell authorization without current need.

## 12. Hosting/cost discussion history

The user asked about free hosting, Vercel, Hostinger shared hosting, Render sleep,
Google Cloud and Oracle free offerings, and clarified this is for internal use.
Architecture selected: Vercel for dashboard + persistent Google Compute Engine
VM for backend/workers/private SQLite. Vercel alone or generic shared web hosting
does not replace the durable worker/database part of this implementation.

The user reported **$2,000 Google for Startups Cloud credits** and a **$25 Render
plan**, plus free-service usage figures. These are historical user-reported facts,
not current balance/billing proof. No new VM/paid plan was created during the
recorded deployment. No current monthly bill, eligibility, resource allowance or
“free forever” guarantee is established here. Recheck actual account billing and
current official pricing if asked; do not recycle old cost estimates as facts.

The user also asked about competitors, extending the original tool, and external
web dashboards before choosing this custom LeadZen implementation. No current
competitor list/recommendation was verified in the latest work.

## 13. Where to continue in the new chat

There is no uncompleted mandatory step from the latest local implementation.
Start by confirming the user's next request and inspecting current files/status.
Do not repeat finished implementation, run historical campaigns or deploy just
because earlier messages said “go ahead.”

Possible next actions ONLY if requested:

- Review the local UI using safe synthetic data.
- Make a specific new feature/fix, with proportional regression/build/browser
  tests and preserved tenant/security boundaries.
- Investigate a new live failure with read-only diagnostics and sanitized evidence.
- Prepare/deploy the accumulated changes after explicit authorization and the
  multi-database migration/backup checklist above.
- Test a specific real provider/account or internal recipient after explicit
  authorization, stating what could incur AI/email/lookup costs or send mail.
- Add actual configurable sending hours or an unattended scheduler as a separate
  scoped request; neither is implicitly implemented by the latest UI.

For exact implementation history and evidence, prefer the latest dated sections
of `docs/local-validation.md` over earlier baseline counts/process session IDs.
Use `docs/chat-orchestrator.md` for current mechanics and `docs/deployment.md` for
documented production environment/recovery, without treating dated verification
as a live status check.
