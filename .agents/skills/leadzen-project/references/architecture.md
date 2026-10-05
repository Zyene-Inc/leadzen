# Architecture and execution boundaries

Paths here are relative to the repository root. Inspect current definitions
before editing; this map is a navigation aid, not an alternate API specification.

| Concern | Implementation |
| --- | --- |
| Next.js UI, authenticated API proxy | `dashboard/app/`, `dashboard/components/`, `dashboard/app/api/proxy/[...path]/route.ts` |
| Private Django API / CLI / configuration | `leadzen/web.py`, `leadzen/urls.py`, `leadzen/__main__.py`, `leadzen/config/`, `leadzen/configuration.py` |
| Accounts, sessions, invitations | `leadzen/accounts/` |
| Employee database routing and worker identity | `leadzen/workspaces.py` |
| Setup and central Settings | `leadzen/setup_wizard.py`, `leadzen/workspace_settings.py` |
| Agent context, typed tools, orchestration, stream | `leadzen/chat/context.py`, `tools.py`, `engine.py`, `views.py`, `leadzen/chat_worker.py` |
| Discovery and actual candidate progress | `leadzen/discovery.py`, `leadzen/discovery_progress.py` |
| Leads / suppression / activity / timeline | `leadzen/crm.py`, `suppression.py`, `activity.py`, `timeline.py` |
| Reviewed drafts, campaigns, mailbox | `leadzen/outreach.py`, `campaigns.py`, `mailboxes.py`, `transports.py`, `email_api.py` |
| Due follow-ups and scheduler | `leadzen/followups.py`, `leadzen/scheduler.py` |
| Runtime services and deployment helpers | `compose/leadzen/` |

## One engine, isolated employees

The control database owns account/session/access data. Each employee has a private
SQLite workspace combining finder, sender and LeadZen domain records. Chat history
and UI context sit beside those existing records, not in a second CRM store.
The finder/sender packages are pinned dependencies in `pyproject.toml`; retain their
`OPENOUTFIND_*` and `OUTSEND_*` interfaces. Do not edit installed site-packages.

Derive actor, workspace routing and file paths from the authenticated server
identity. Browser/model-supplied IDs are references, not authorization. Resolve
records in the routed database and apply actor checks where required. Test with
separate employee databases containing overlapping IDs. Worker subprocesses carry
server-owned actor/workspace identity and recheck account access at external sinks.

Dashboard server uses `LEADZEN_API_URL` and `LEADZEN_API_TOKEN`; backend uses
`LEADZEN_DASHBOARD_TOKEN`, `LEADZEN_DB`, workspace routing and `LEADZEN_SETTINGS_KEY`.
Preserve the stable encryption key; changing it can make saved connections unreadable.
Keep provider credentials server-side. Blank secret input preserves a saved secret;
explicit replacement/removal are separate actions. Never return saved plaintext
credentials to implement an eye/reveal control.

AI/provider transport guards include approved endpoints, public-IP validation,
pinned connections, TLS verification, no redirects, bounds and timeouts. Do not
weaken them to make a custom model endpoint work. Keep session revocation, CSRF/
origin checks and proxy route allowlists intact. Logo assets can be public while
records and APIs remain authenticated.

## Outreach truth and approvals

Profile discovery, qualification, email enrichment, drafting, transport acceptance
and reply are different states. A manual lead is not automatically AI-qualified.
Read-only screens never test connections, sync mail, buy addresses or send emails.
Explicit connection tests may call providers; saved receipts are bound to settings.

Paid enrichment approves exact selected IDs and a maximum budget, with a one-time
server approval. Missing actual provider usage is unknown, not zero. Never retry an
ambiguous paid request automatically. Draft sends require exact recipient/sender/
content review; the model cannot mint approvals. Enforce eligibility at transport,
not only in the UI. Changed copy, identity, reply state or suppression invalidate
eligibility/approval. A stop cannot retract an already accepted external request.

Use the shared suppression helper so matching campaign recipients and pending
sequences stop, and suppression survives deletion/reimport. Human replies stop cold
follow-ups; automatic responses remain distinct. Reply drafts use the canonical
thread and original active mailbox, with untrusted inbound text kept out of authority.

Automatic follow-ups cover only the exact approved sequence/recipients, not future
recipients or initial mail. They check a complete IMAP sync before sending and obey
reply, suppression, identity, window, capacity, pacing and revocation guards. Changes
invalidate approval. See `docs/automatic-followups.md` for the separate scheduler,
approval expiry and manual-versus-automatic sending windows. Enabling the service
is separate from approving campaigns. Do not use the Codex reminder/automation tool
as the application's scheduler.

Keep GPL and third-party source attribution. Product branding suppresses sender
tool attribution centrally through `leadzen/branding.py`; do not erase legal notices.


## Daily Autopilot standing authorization (local, October 3)

The manual paths above retain exact human review. Daily Autopilot adds a distinct
explicit policy authorization for future new leads/paid lookups/AI/initial messages
and follow-ups within saved limits, expiry and setup identity. The model cannot
enable it or mint policies. Reuse `autopilot.py`, `autopilot_worker.py` and the shared
campaign sender. Never mark these generated messages as manually reviewed. Turning
the policy off stops pending automatic work. See `docs/daily-autopilot.md` and the
current-state validation link. Employee **Settings → Sending hours** now supplies
selected weekly days and start/end times. **America/New_York is the only business
timezone**, independent of operator country and browser. Newly authorized Autopilot
uses that start time for discovery and the same window for delivery. Custom
schedules govern manual outreach and approved follow-ups, including selected
weekends, with checks at the HTTP/SMTP boundary. Settings edits invalidate automatic
approvals; legacy policies without a scope schedule retain their hours. The fixed
clock fingerprint holds earlier authorization for a fresh review. Foreign-zone
historical policy scopes are retained as evidence and never executed.
Human Inbox replies remain immediately sendable after exact review. The additive
`0017_siteconfig_sending_schedule` and `0018_new_york_time` migrations are local only.
The latter normalizes saved schedule/draft/campaign timezone metadata, preserves
absolute timestamps and immutable policy scope, and updates campaign defaults.
Django dates, mailbox ledgers and pinned CLI clocks use New York; aware ORM
timestamps convert before working-day arithmetic. UTC instant storage is retained.
Service enablement and live tests still require
fresh specific approval; the local implementation does not grant it.
