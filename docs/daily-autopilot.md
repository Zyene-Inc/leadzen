# Daily Autopilot

Local implementation, October 3, 2026. This document does not authorize deployment,
provider charges, service enablement or real mail.

## Employee experience

Open Settings → Sending hours → Edit. Select the days and start/end time for your
repeating weekly schedule. The entire platform uses **America/New_York (Eastern
Time)**; daylight-saving changes apply automatically. No timezone selection is
available. Open Outreach → Daily Autopilot → Off.
Review that schedule, saved sender, audience, offer, signature and booking link;
choose writing guidance, daily and
monthly new-contact/email-credit/AI-request limits, optional follow-ups and an
explicit authorization duration of 1–90 days. Confirm the visible recurring
paid-lookup, AI, inbox-check and automatic-send authorization. There is no daily
human review. The card then has one On/Off switch, status and expandable results.

Newly authorized policies start discovery at the selected start time on the selected
days, including weekends when selected, with daylight-saving changes handled in
New York time. Settings initially shows Monday–Friday, 8 AM–8 PM Eastern Time,
independent of country or browser timezone. Holidays are included. Catch-up is allowed
for two hours after the start, clipped to the selected end time. Newly generated
first emails can send until that day's end time; later days do not replay old
cold-email batches. Follow-ups use the same approved window, with delays measured
from the preceding accepted message. Working-day delays count selected sending days
for a configured schedule; calendar-day delays still use calendar dates and wait
for an allowed opening.
All mail shares the existing mailbox capacity and five-minute pacing. Those limits
may mean fewer first messages are sent than the daily contact maximum.
Enabling during the catch-up window shows today's available start rather than
claiming the first run is tomorrow. Historical policies without a saved schedule
retain their original 10 AM weekday discovery / 9 AM–5 PM follow-up hours. The
New York clock rollout holds previous approvals until reauthorized; historical
foreign-timezone scope is preserved as audit evidence and cannot execute.
Policies never silently gain weekend permission. Learned mailbox capacity can change without
invalidating the policy; the current capacity still gates every message.

Off revokes the policy immediately, cancels its pending discovery, and stops pending
first messages and follow-ups. An already accepted external request cannot be recalled.
Re-enabling creates a new policy; it never resurrects stopped sequences or creates
another run for the same employee workday. Offer/identity/connection changes invalidate
the saved policy, including edits to Sending hours. Expired authorization requires
a new explicit authorization. Saving Settings alone never starts a worker or sends
an email. Separately reviewed human Inbox replies remain immediately sendable.

## Architecture and truth

- `AutopilotPolicy` stores actor ownership, immutable scope, setup fingerprint,
  expiry, disable time and workspace heartbeat. `AutopilotRun` records the local
  workday, checkpoints, conservative provider reservations and issues. A database
  constraint prevents multiple employee runs on the same workday across policies.
- `autopilot_dispatch.py` launches up to four isolated workspace processes without
  waiting for slow employees. Workers use the existing shared workspace lock and
  worker identity checks. Processes are bounded to 15 minutes; preparation has a
  12-minute deadline. The existing scheduler's 30-second loop dispatches them.
- `autopilot_worker.py` uses the existing finder and DiscoverySession/Lookup receipts,
  counting and qualifying only new profiles actually discovered in today's run.
  Yesterday's unfinished profiles cannot satisfy today's quota. A discovery page
  containing only familiar profiles advances to the next page within the same
  deadline and budget. Free discovery cannot purchase or poll old email lookups.
  Enrichment is restricted
  to those canonical source IDs. Async requests are collected in the same owned
  discovery session with bounded waits and the provider's saved poll backoff.
  Collection cannot submit another paid lookup or poll another run's handle.
  Unrelated requests cannot consume this selection's lookup slots. Previously
  attempted/uncertain lookup IDs are not resubmitted. Only completed
  valid/deliverable results matching saved output email
  addresses can be enrolled; catch-all/unknown/invalid results are held out.
- Existing addresses, previous sends, suppression, deletion, replies and existing
  campaigns/reviews exclude contacts. Address matching is case-insensitive across
  canonical contacts, including pending, sending, accepted and uncertain manual
  reviewed messages. The first-send boundary checks again for competing outreach
  and excludes only its own just-recorded outbound message. No separate CRM or
  mailbox is introduced.
- AI generates the entire individual sequence together using saved offer facts and
  writing guidance. Structured copy validation requires the exact supplied IDs.
  Each CampaignRecipient saves `personal_steps` and an authorization fingerprint;
  EmailCampaign references the daily run. No human-reviewed flag or approval token
  is fabricated. Workspace, Chat and the lead timeline read these same records.
- Actual AI/provider sinks reserve daily/monthly request or credit capacity before
  making external requests and recheck cancellation, policy expiry and setup. These
  are request/credit caps, **not a currency spending guarantee**. Unknown responses
  keep their reservation. Monthly contact capacity conservatively reserves the
  planned batch size even when fewer contacts qualify.
  HTTP adapters recheck access and authorization after TLS connection and before
  writing request bytes; this second check does not reserve the request twice.
- The existing campaign sender adds signatures/opt-out text, checks inbox coverage,
  suppression, access, identity, capacity and pacing, and records transport acceptance.
  SMTP rechecks authorization at `sendmail` and again immediately before message
  body bytes after the server's DATA response; HTTP mail does so before its request
  and after connection. No recorded inbound reply allows further cold follow-ups, including
  unclassified or automatic replies. Customer replies are never answered automatically.
  A replied, suppressed, deleted or completed contact is stopped individually so
  other eligible recipients can continue; inbox or policy failures hold the batch.
- Process death during preparation leaves a visible held checkpoint and saved data;
  the next worker does not replay ambiguous paid work. Complete validated sending
  resumes from pending recipient rows. Claimed/uncertain sends are never retried.
  Failed copy is held for that recipient; valid recipients can proceed. Completed
  discovery results can survive a partial provider pass, while incomplete lookups
  cannot become send recipients.
- An active Chat/Find Leads task holds the morning start with a visible explanation.
  Finishing or stopping that task clears the busy explanation. A successful later
  delivery clears a recovered service warning only when no held or uncertain
  recipient remains; normal contact stops do not become service-failure alerts.

## Release requirements

Apply migrations `0016_daily_autopilot`, `0017_siteconfig_sending_schedule` and
`0018_new_york_time`
(and all earlier unapplied migrations) to the
control DB and all initialized employee workspaces during an authorized release.
Pause intake/scheduler and drain **autopilot_worker** as well as existing Chat/send
workers before migration/backup. Preserve credentials, encryption key, databases and
matching source as described in deployment.md. The deploy guard includes the new worker.
The additional schedule field changes setup fingerprints; existing queued reviewed
requests and automatic authorizations may need a fresh review after the migration, even before a custom
schedule is saved. This conservative hold must not be bypassed during rollout.
The fixed-clock fingerprint also requires fresh review of earlier approvals.
Migration 0018 preserves selected days/hours and absolute timestamps, normalizes
saved schedule/draft/campaign timezone metadata, and preserves immutable policy
scope as historical evidence. It performs no provider call or send.

The existing `leadzen-followups.service` runs `python -m leadzen.scheduler`.
`LEADZEN_AUTOPILOT_ENABLED=0` remains the default. With fresh rollout authorization,
set it to 1 in both API and scheduler environments and restart through the reviewed
release procedure. This enables execution capability only; each employee must still
authorize their own policy. Existing human-approved follow-ups remain controlled by
`LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED`. No Codex automation is used.

The UI reports a missing/stale heartbeat after 20 minutes. This is a saved workspace
heartbeat, not external infrastructure alerting. An operator should investigate stale
heartbeats, held runs, schema failures and uncertain transport outcomes. No blind
retry endpoint exists. Stop/archive a held sequence before creating separately reviewed
manual outreach. Provider billing, rate behavior and inbox placement require a separately
authorized live validation; synthetic tests cannot certify them.
