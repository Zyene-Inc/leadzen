# LeadZen chat orchestrator

> Architecture reference with historical release notes. Read
> [current project state](../.agents/skills/leadzen-project/references/current-state.md)
> for the later deployment boundary, migration 0015, history deletion and shared
> Workspace invalidation. Campaign automatic follow-ups are documented separately
> in [automatic-followups.md](automatic-followups.md); the older manual-only notes
> below describe individual due-send passes, not the application's current scope.

Implemented locally; not deployed. This is a bounded outreach agent, not an
unrestricted terminal agent or a background campaign scheduler.

## Employee experience

Complete onboarding, then configure the AI provider/model/key/Base URL, email
sender/reply inbox and BetterContact in Settings. BetterContact is required for
profile discovery, including discovery without email enrichment.
Switch the sidebar between **Workspace** and **Chat**. Workspace lists Dashboard,
Find Leads, Leads, Campaign, Inbox, Sending, Suppression, Activity and Settings.
Chat provides a greeting, suggestions, composer, filter, new chat,
private conversations grouped by age, saved tool results and archiving.
Conversations also support rename. Switching modes carries canonical selected
lead, active draft, thread, discovery run and campaign IDs. These are validated
against the employee's existing database and persisted as UI references, never
copies of CRM or outreach records. Cards link into the existing Workspace screens.

The employee's actual model chooses a validated action. The backend executes an
allowlisted tool, persists its result, and asks the model what to do next. The UI
streams the model's visible assistant text and actual job state over authenticated
SSE; it does not display reasoning. Provider HTTP chunks are forwarded incrementally
through the same pinned HTTPS transport. A disconnected stream falls back to saved
progress. One 20-second stream lease per employee bounds open connections and
rechecks session/account access before every snapshot.

Tools inspect connections, counts, contacts, stored replies and campaigns; discover
leads; draft sequences; run due campaign emails; pause a campaign; and sync replies.
Discovery calls the existing finder (`find N emails --json --new`, or the no-email
unit) and imports its JSONL into the existing contacts engine. Campaign drafting
and sending share the workspace validators and sending implementation.
The initial typed capabilities also read/update the saved target, inspect canonical
contacts/drafts/threads, enrich exact selected profiles, compose/revise individual
outreach and replies, send reviewed drafts, suppress contacts and summarize activity.
`leadzen/chat/tools.py` validates their schemas and adapts existing domain handlers;
it does not give the model a shell or an arbitrary HTTP client.

### Structured Find Leads

`/find-leads` starts with three leads and **Don't find emails** selected. The
counter accepts 1–25; the review shows **0 BetterContact email credits** by default.
Selecting **Find verified emails** shows an estimate of **up to N credits** before
Start Finding. AI-provider charges are separate. No outreach mail is sent by this
action. Verified-email discovery can retain qualified profiles without an email
while seeking the requested number of verified addresses.

The authenticated `/api/discovery` endpoint submits the exact count, email choice,
displayed budget, configuration revision and idempotency ID. It reuses chat's
employee-scoped durable worker, single-use approval, cancellation and live access
checks, but executes one finder action and ends without another orchestrator
decision. The finder still uses the employee's AI provider for qualification.
Changed settings/target, invalid budgets, incomplete setup and concurrent active
tasks block execution. Retrying the same request does not launch it twice.
Opening the screen reads stored configuration only; it does not test providers,
purchase addresses or create a job. Start Finding opens `/find-leads/<run-id>`;
the saved chat remains available as a transcript and links back to the live view.

### Live discovery and separate email lookup

The worker observes the pinned finder's search, harvest and persisted verdict
hooks in memory; it does not parse colored terminal logs or alter installed
dependencies. Each run has a durable candidate ledger and bounded event feed in
the employee's private database. Complete JSONL records are imported immediately.
Counts are actual new profiles, verdicts and saved results, not the search index's
estimated match count. Existing queued profiles can also be qualified/enriched.
Completion requires the actual saved-results goal, not worker success alone.

Pause waits for a safe persisted action checkpoint. Resume atomically requeues
the same run for only its remaining goal, preserving the original credit/model
reservations, configuration snapshot, provider receipts and 15-minute approval
expiry. A paused run blocks another task. Stop keeps results already saved and
cannot undo an accepted external request. Cancelled, expired or stale work is
never automatically resumed. Execution segments retain the ten-minute deadline.

Free discovery cannot submit a paid enrichment request. Receipts are reserved
before an approved POST; ambiguous requests are not resubmitted. Actual email
usage comes from the provider's `credits_consumed` report, not a guessed charge
per candidate. Missing usage is explicitly unknown, never labeled zero. Paid
requests disable phone/profile/catch-all add-ons; budgets and live access are
checked again at the sink. Discovery requests are capped at 200 per run, events
at 1,000 (the page shows the latest 100), candidates at 5,000, and displayed
qualified profiles at 50. Employee profiles are not read from or contributed to
the upstream shared contacts hub in these monitored web runs.

After profile discovery, **Find Emails** opens a read-only selection review.
Only eligible qualified results from that run are offered, excluding existing
addresses, deleted contacts and previously submitted/uncertain lookups. The
employee explicitly confirms the selected IDs and displayed up-to-N credit
limit. The worker restricts enrichment and confidence ranking to those exact
profiles; it cannot search for new profiles or send emails. Existing confidence
gates still apply, so unavailable or insufficiently ranked results can leave the
goal short. Opening the review or completing discovery never buys addresses.
Provider usage can be pending after a stop; no automatic poll or paid retry is
scheduled. Reconcile final usage with the provider if its report is absent.

## Approval and execution boundaries

- Reads of stored workspace data do not send emails or buy lead credits. Chat
  model calls use the employee's configured provider and may incur AI charges.
- Clearly requested free discovery, draft creation/revision, target changes and
  suppression execute directly. Free discovery sets `includeEmails:false`, prohibits
  work-email purchase at the provider sink and finishes before another model-selected
  action. Selected enrichment, every send, manual unsuppression and external mailbox
  sync require an explicit confirmation. Draft praise never authorizes sending.
  Sending previews freeze recipients, sending identity, templates and rendered
  email copy. Approvals are single-use, expire after 15 minutes and are invalidated
  by relevant changes. An approval is recorded before the external action.
- Reviewed draft sends use a server-issued token bound to the employee, routed
  Workspace, exact draft/recipient IDs, content, identity and current eligibility.
  The model cannot issue a token. The backend consumes the durable approval before
  entering the existing sending service, and rechecks live guards at transport.
  Cards show full From/To/Subject/body before confirmation and report actual provider
  acceptance; queued or deferred messages are never described as sent.
- Each turn allows eight model decisions, at most 32 guarded AI HTTP requests
  including the discovery engine, up to 25 verified-email credit reservations,
  and up to 25 email reservations. Each execution segment has a ten-minute deadline.
  Other discovery/model-provider charges are separate, not a guaranteed dollar cap.
- One active chat task per employee; duplicate message requests and worker claims
  cannot replay an action. Conversation/message/rate limits bound resource use.
- Account revocation, cancellation, approved public endpoints and budgets are
  rechecked at external sinks. TLS verification, pinned public-IP connections,
  response limits and no redirects protect AI/provider calls. No shell, arbitrary
  SQL, arbitrary URL fetches or agent-selected API credentials are exposed.
- Campaign sends retain live suppression, consent, reply, sending-window, pacing,
  daily-cap and mailbox-identity guards. Accepted mail is not an inbox guarantee.
  A due-send pass may defer remaining emails. It does not schedule the next run.
- Provider uncertainty is not automatically retried. Interrupted workers are
  surfaced as failed after their lease expires. Review contacts/campaigns before
  retrying; a stop request cannot undo an in-flight accepted email.

## Local preview and release

Use the disposable preview described in [local-validation.md](local-validation.md),
then open `http://localhost:3000/chat` as `ready@preview.example`. The model is
visibly labeled **LOCAL PREVIEW — no external calls**. Its scripted decisions use
the real persistence/approval loop; provider sends/lookups remain disabled. It is
not evidence that a live provider key, domain or sender is valid.

Tests include the actual Pydantic AI structured-output path with a synthetic model,
seven provider constructors, both SDK HTTP clients, the existing finder command
and partial JSONL import, approvals/replays/expiry/settings changes, exact sending
recipients, budgets, cancellation, stale recovery, and separate-process employee
isolation/revocation. Real API charges, inbox syncing and delivery were not tested.

A future authorized release requires backing up and migrating the control DB
**and every initialized employee workspace** through migration 0014 before
starting this backend, followed by the matching dashboard. No new Vercel variable
is required. Preserve existing stable encryption keys and server-to-server auth.
Migration 0014 is additive: UI references/stream leases, conversation context and
revision instructions live beside the existing lead/draft/mailbox records. Configure
an API server with concurrent request workers for SSE (the local service template
uses eight threads). A single-thread server cannot serve Workspace during a stream.
The local provider-factory adapter also fixes the removed `OpenAIModel` import
without changing installed dependencies. Production remains on its existing code
until an approved release; no production SDK fix has been deployed.

## CRM and campaign controls

Leads now exposes saved qualification, email, contact, reply and suppression
facts, search, safe profile/company links and individual detail pages. A manual
contact is not labeled AI-qualified. A work-email request is an explicit,
one-profile approval, routed through the same bounded finder worker and durable
credit ledger as the structured discovery screen. Opening or cancelling its
review performs no lookup. Missing billing/verdict data is not invented; a safe
catch-all address is distinguished from an individually verified mailbox.

Campaign drafts store target/product context, an optional HTTPS booking link and
a campaign signature. `{{booking_link}}` inserts the link where the employee
chooses; planning context is not automatically added to the copy. The signature
overrides only that campaign's messages, not the shared mailbox. New UI sequences
start with an initial email and two follow-ups after 3 and 5 further working days.
Working days mean Mon–Fri in the saved sending-country timezone, without holidays.
Existing calendar-day sequences retain their timing until explicitly edited.

Workspace campaign sends open a read-only, personalized recipient/content review.
Confirmation freezes the saved settings, sender, recipients and message content;
it has a 15-minute expiry and stable request identity. The worker atomically claims
the job once and rechecks the review at each external sink. Replies, suppression,
consent, sending hours and pacing still apply. This is a bounded due-send pass,
not an automatic follow-up scheduler. Interrupted/uncertain mail is not replayed.

## Reviewed initial outreach and Inbox

`/sending` no longer starts autonomous mail from a count alone. It shows actual
eligible contacts, remaining daily capacity, sending identity and the existing
engine's enforced window (8 AM–8 PM, Mon–Fri, in the saved country timezone).
**Review & Start** prepares saved, personalized AI drafts only. The exact preview
includes the sender's signature and STOP opt-out; there is no software attribution.
Each message supports Regenerate, Edit and Approve. Editing or regenerating clears
approval. AI draft generation uses the employee's configured provider and can incur
charges; it does not find emails, spend BetterContact credits or send outreach.

After every draft is approved, a separate final confirmation names the exact
recipient count and sender. The server binds that approval to the current copy,
setup and contact/inbox state; duplicate submissions return the same saved job.
The worker sends only those frozen messages, without an agent choosing recipients
or additional actions. It checks employee access, replies, suppression, deletion,
window, pacing and capacity again at the external sink. Each attempt is recorded
before transport. Actual provider acceptance and its timestamp drive progress;
an uncertain attempt cannot be automatically replayed. Approval expires after
15 minutes, and deferred contacts need a fresh review rather than an overnight run.
Stop preserves already accepted attempts and cannot retract an in-flight email.
This flow does not schedule follow-ups; those remain campaign due runs.

`/inbox` lists private saved conversations and displays plain-text history for both
sides. Opening or refreshing it never syncs a mailbox, calls AI or sends. Mailbox
sync is separately approved in Chat. **Suggest reply** creates an unapproved draft
for the latest eligible human reply using a bounded structured model with no tools.
Inbound text is explicitly untrusted. The model cannot choose addresses, credentials
or execution. Subject and thread headers are server-owned. Edit/Approve and a
separate **Yes, send this reply** confirmation are still required. A new inbound
message, sender change, opt-out or previous answer invalidates the old suggestion.
Only the original active sending mailbox can answer the thread. Exact known-contact
STOP replies are honored during the approved inbox-sync projection, not as a side
effect of viewing messages. The older classified-message view remains available
under **All stored messages**.

Migration **0012** stores actor-owned reviews, exact draft approvals and durable
attempt state in the existing employee database. No new environment variable is
required. The disposable preview uses visibly synthetic draft bodies and acceptance
events, with all external email/AI providers disabled. It tests persistence and UI,
not real sender credentials, provider billing, deliverability or inbox placement.

The current Chat/Workspace validation is recorded in
[chat-workspace-validation-2026-10-02.md](chat-workspace-validation-2026-10-02.md).
