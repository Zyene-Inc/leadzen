# Workspace | Chat — local implementation and validation

This extends the existing application. Workspace screens and domain records remain
shared; Chat does not have a second lead, draft, mailbox, campaign or outreach store.
No changes were deployed, no real emails were sent and no live provider credits were
used. Existing uncommitted work was preserved.

## Architecture and behavior

Workspace selection → validated WorkspaceContext → persisted ChatThread/ChatRun →
strict typed capability → existing finder/CRM/configuration/reviewed-outreach service
→ the same employee database. UI context stores canonical references, not record
copies. Every message captures the current validated selection; deleted or foreign
references are rejected/cleared. Opening a rich card uses the existing Workspace
detail, Sending review, Inbox conversation or discovery page.

The agent has the initial capabilities requested in the product spec: Workspace
status/context, target read/update, free discovery/stop, lead list/detail, selected
email enrichment/credit usage, draft create/read/edit/regenerate, reviewed single or
batch sending, mailbox sync/replies/threads/reply drafts, suppression/unsuppression
and activity. Exact IDs and bounded arguments are validated with Pydantic schemas.
Existing legacy tools remain compatible. There is no model-selected shell, SQL,
arbitrary URL, actor ID or credential access.

Free discovery starts directly and cannot submit a work-email purchase. Its live
card displays actual candidate verdicts, qualification reasons, imported contact
IDs, counts and receipt-based credit usage. Discovery ends before another agent
action. Pause/resume retains the same run, saved results, remaining goal, setup
snapshot, original expiry and credit reservations. Interrupted or uncertain requests
are not automatically replayed.

Email enrichment requires an exact selected-lead confirmation and maximum credit
count. It updates the existing contact records. Actual reported usage is shown;
missing provider reports remain unknown. Previously submitted/uncertain purchases
cannot be submitted again automatically.

Drafts use the existing reviewed-outreach service and remain unsent. Conversational
revisions use the active canonical draft, prior copy and explicit instructions.
Imported full names remain visible in both interfaces and in generation context.
Editing/regenerating clears approval. “Looks good” does not create a send approval.

Explicit sending intent creates a complete From/To/Subject/body confirmation.
The durable, one-use server token binds the employee and routed Workspace to exact
draft/recipient IDs, current content, mailbox identity, eligibility and expiration.
Only a confirmed backend execution may consume it. Existing suppression, opt-out,
new-reply, account, pacing, window and cap guards remain enforced at the sending sink.
Only actual acceptance is reported as sent. The existing approved campaign follow-up
engine remains separate; Chat drafting does not start it.

Replies come from the existing mailbox records. Sync is separately confirmed;
viewing saved replies does not contact the provider. Reply drafts and sends use the
same review and approval flow. Suppression stops the same Workspace contact and
sequence. Removing a manual address block needs confirmation and never reverses an
opt-out or restarts a stopped sequence.

Conversations support New Chat, History/filter, Rename and Archive. Assistant text
streams through the pinned provider transport and authenticated SSE; tool observations
and progress are persisted. Cancellation, session revocation, response size and
deadline checks remain active. Each employee has one bounded SSE lease, with polling
fallback; API request concurrency must be configured accordingly.

## Verification

Final results:

| Check | Result |
| --- | --- |
| Full Python suite | 838 passed; one SDK event-loop deprecation warning |
| Full dashboard UI suite | 780 passed |
| New backend Chat behavior cases | 42 cases × 10 repetitions = 420 passes |
| New Chat UI behavior cases | 14 cases × 10 repetitions = 140 passes |
| Dashboard TypeScript | Passed |
| Dashboard production build | Passed |
| Django system checks | 0 issues |
| Migration/model consistency | No pending model changes; additive migration applied in disposable preview |
| Diff whitespace check | Passed |
| React Doctor | 71/100; no errors, 19 warnings |

React Doctor warnings include component complexity/size, client locale formatting
and asynchronous effect updates. The live-stream effect checks cancellation before
updating state and aborts on cleanup. Client date labels use hydrated saved data;
broad Workspace restructuring was left outside this feature to preserve its UI.

New backend behavior cases and Chat UI behavior cases run ten times with fresh
synthetic fixtures. This does not claim that every possible interaction was exercised
ten times or that an LLM always interprets every natural-language request correctly.

The disposable browser preview used the actual SDK structured-output streaming
path with TestModel and synthetic finder/provider/mail transports. Browser checks
covered persisted discovery/zero email credits, lead deep links, Workspace → Chat
active-lead context, exact enrichment confirmation and reported credit receipts,
draft creation/revision, full sending confirmation/cancellation, opening the same
saved draft in Workspace, restoring its Chat context and renaming saved history.
Preview fixtures have no access to live provider credentials.

Full-suite testing exposed and fixed a process-wide mailbox scoping issue: applying
the worker adapter must not hide deliberately configured legacy CLI mailboxes when
the current database has no dashboard runtime configuration. Tests also now explicitly
provide sending intent and explicitly remove the encryption key when checking that
missing-key writes fail closed.

## Release limits

Migration 0014 must be applied to the control database and every initialized employee
Workspace after backups, using the existing stable encryption key. This migration
was tested only against disposable databases. No existing user database was migrated.

Live AI interpretation, BetterContact billing, actual mailbox sync/delivery,
deliverability, production concurrency/load and a production migration have not
been certified by these local tests. They require an approved staging/release run.
The existing follow-up service is not enabled by this change. This is a verified
local implementation, not a claim of perfect or fully certified production readiness.
