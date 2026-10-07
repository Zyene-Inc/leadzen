# Fresh user-experience audit — 2 October 2026

The covered local workflows pass after six user-facing corrections and two test
isolation repairs. This is evidence of a working local implementation, not a guarantee that
every input, outage, live model response or delivery outcome is perfect.

## Scope and preservation

The current user request authorized local inspection, testing and fixes. The attached
handoff and pasted product plan supplied requirements and historical context; they
were not treated as permission to deploy, purchase addresses or send messages.
The later Workspace | Chat specification takes precedence over older handoff text
that described approval for every discovery action and polling-only assistant output.

The existing Workspace was retained. No CRM rebuild, second dashboard, parallel lead
store or separate Chat outreach engine was introduced. All pre-existing uncommitted
and untracked work remains in the checkout. No reset, stash, commit, push, deployment,
real email, live AI request or provider credit purchase was performed. Existing user
records and production credentials were not inspected. Explicit migration operations
used disposable databases. Initial pytest startup made the registry's existing
idempotent schema probe before test-database creation; the final test bootstrap
now uses a separate temporary registry even when an existing database path is inherited.

This pass started with clean test fixtures and a new disposable local database,
then exercised the real Next.js → Django → private SQLite path. Provider/model/mail
transports were explicitly synthetic. The six-step browser setup began with an
unonboarded test account and existing synthetic server-side credentials.

## Corrections

| Finding | Correction | Verification |
| --- | --- | --- |
| A first sending batch defaulted to three even when only one/two leads or one daily slot were available. | Initialize the count within the actual eligible-contact/capacity limit. Zero capacity remains disabled. | Three small-batch cases and zero-capacity case, each repeated ten times. The only initial write prepares drafts. |
| A failed Leads load left its error visible after a successful search/retry. | Separate load errors from action errors and clear a recovered load error. | Recovery case ×10; successful rows appear without the obsolete alert. |
| Closing an email review left an active draft reference for later Chat commands. | Clear the active canonical draft on close and restore the appropriate Workspace context. | Sending-close case ×10 and Inbox-close assertions. |
| Editing an Inbox reply changed Chat’s Workspace return link to Sending. | Pass the Inbox route through the saved review and focused email preview. | Reply focus/edit/close case ×10 and real browser round trip. |
| Returning from Chat reopened the Inbox thread but hid its saved reply preview. | Preserve thread and review IDs in the bounded return link, restore the same saved review, and check the review’s canonical thread before displaying it. | Restoration and wrong-thread cases ×10; backend identity and malformed-link cases ×10; browser retained the same draft UUID without another generation. |
| Tour text described obsolete approvals and navigation labels. | Explain directly requested free discovery/drafting, separate AI usage, paid-email/mailbox/send approval and shared Workspace/Chat state. Match Dashboard/Leads labels. | Tour/control tests and fresh browser setup/tour. |
| A clean backend run depended on an inherited encryption environment value after a process-wide mailbox adapter was installed. | Give each test a fresh synthetic encryption key. Missing-key tests explicitly remove it and continue to check fail-closed behavior. | Baseline: 12 failed, 826 passed. Final: 898 passed with no shell-provided key. Production encryption behavior was not changed. |
| Django test startup could probe or upgrade an inherited existing database before pytest created its test database. | Use a test-only settings wrapper that selects temporary registry/workspace paths before importing production settings. | Ten subprocess cases preserve a disposable sentinel legacy database and create no upgrade backup, even with an inherited database override. |

The first journey regression run reproduced 60 failures and ten passes. The additional
round-trip tests reproduced 20 failures and 70 passes before the restoration fix.
The new backend restoration checks reproduced 20 failures and 30 passes before the
metadata/link changes. The ten bootstrap-preservation cases failed before the test
settings wrapper existed and pass after isolation. All now pass.

## Architecture and requirements

Workspace and Chat use the same employee database and existing finder, CRM,
reviewed-outreach, campaign, mailbox and suppression services. UI references contain
canonical IDs; backend context validation and workspace routing remain authoritative.
The agent has bounded typed capabilities, not unrestricted shell or SQL access.

| Product area | Fresh verification |
| --- | --- |
| Accounts, invitations, password setup, isolation and revocation | Full backend suite plus real local HTTP lifecycle; production HTTPS lifecycle checks secure cookies and foreign-origin rejection. |
| AI, BetterContact, identity, mailbox, product and audience setup | Full setup tests; browser completed all six stages, three explicit synthetic connection tests, target preview and tour. Saved values appear in Settings and Dashboard. |
| Dashboard and Workspace pages | Browser visited Leads, Campaign, Inbox, Sending, Suppression, Activity and Settings with no application-error alerts after loading. Stored metrics and settings rendered. |
| Free discovery | Browser saved three qualified records, six evaluated candidates and actual qualification reasons; all work emails remained unrequested and email-credit use was zero. Leads appeared immediately in Workspace. |
| Paid enrichment | Exact-lead/max-credit approval and duplicate/uncertain request protections are covered by backend/Chat tests. Browser opened Sarah’s one-credit confirmation and cancelled it. No live lookup was executed. |
| Leads and suppression | CRUD/import/filter, opt-out/terminal suppression and sending-sink checks run in the full suites. Browser inspected persisted lead detail and qualification reason. |
| Drafting and sending | Draft generation/revision, canonical draft references, approval invalidation, one-use send approval, failed/uncertain send handling, limits and cancellation are tested. Browser shortened a saved reply through synthetic Chat and showed it as unsent. |
| Inbox and replies | Browser read actual persisted fixture messages, prepared an unsent reply, edited/focused it and restored the exact preview through Workspace → Chat → Workspace. A mismatched thread cannot display/approve the draft. |
| Campaigns and automatic follow-ups | Full regression suite covers approved sequence scope, recipient/content guards, reply/opt-out stopping, scheduling/window/cap checks and uncertain failures. No automatic follow-up service was enabled. |
| Chat | Streaming transport/context/approvals/history/rename/archive/deep links and cancellation run in the full suites. Browser resolved “her” against Sarah’s current canonical record and “Make it shorter” against the active reply draft. |
| Database backup | Browser triggered Backup Database and received its success feedback; automated backend tests check backup behavior. The browser automation could not capture the blob-download file, so that file was not independently inspected in this browser pass. |
| Responsive interaction | At 390×844, Chat had a 390-pixel document width with no horizontal overflow; the navigation menu opened. Temporary viewport override was reset. |

Browser journeys above are individual end-to-end checks, not ten real-provider runs.
The test harness uses the actual persistence, access guards and SDK structured stream
with synthetic decisions/transports; it does not certify live LLM interpretation.

## Final verification

| Check | Result |
| --- | --- |
| Full backend suite | **898 passed**; one existing SDK event-loop deprecation warning |
| Full dashboard suite | **870 passed**, six test files, no unhandled errors |
| New UI journey regressions | Nine cases ×10 = **90 passes** |
| New backend restoration/link regressions | Five cases ×10 = **50 passes** |
| New bootstrap preservation regression | One case ×10 = **10 passes** |
| Dashboard TypeScript | Passed |
| Optimized dashboard build | Passed |
| Local development HTTP lifecycle | Passed |
| Optimized HTTPS HTTP lifecycle | Passed using the standalone server; production cookie/origin checks active |
| Django system checks | Zero issues |
| Model/migration consistency | No model changes detected; zero pending control migrations in the disposable preview |
| Python compilation / deployment-script syntax / diff whitespace | Passed; deployment script was not executed |
| React Doctor, full scope including local source | **71/100**, zero errors, 19 warnings; unchanged from baseline |

The changed-only React Doctor scan reported 100/100 across ten tracked files, but
most of this project’s current work is untracked. That narrower score is not used
as the whole-project result. The full scan covered 99 files and retained the same
19 warnings: eight complex components, four large components, duplicated admin JSX,
four locale-formatting warnings, invitation verification in an effect and Chat’s
asynchronous effect. No rules were suppressed. Loaded date labels are populated
after hydration; Chat’s requests use abort signals and stream callbacks check
cancellation. The remaining structural warnings are maintainability debt, not proof
that every user flow is broken. A broad component rewrite would conflict with the
instruction to preserve Workspace.

The inventory covers 256 ordinary project files. File-level coverage and hashes are in
[the fresh inventory](user-experience-audit-inventory-2026-10-02.json).
This pass combines new focused source inspection, fresh complete test/build execution
and the earlier broad/Chat audits for source outside the corrected journeys. Entries
explicitly distinguish fresh focused review from compile/build/test verification,
unchanged prior review and excluded/generated material. It does not claim a new
line-by-line manual review of every source file or every test assertion.

## Release limits

Live AI behavior, BetterContact credit accounting, actual SMTP/IMAP/API delivery,
inbox placement, production load/concurrency and migration of existing user data
remain unverified by this synthetic pass. They require a separately approved
staging/release exercise with backups and the existing encryption key. The local
follow-up implementation remains disabled operationally. No production readiness
certificate or “zero possible issues” claim is supported by these results.

Browser evidence: restored unsent Inbox draft at
`/tmp/leadzen-user-audit-inbox-proof.png`; shared conversational revision at
`/tmp/leadzen-user-audit-proof.png`. Raw test output remains in temporary local files
and is not exposed as the default product activity view.
