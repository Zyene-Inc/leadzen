# Approved automatic follow-ups

Production update, 3 October 2026: the owner explicitly authorized activation.
The reviewed systemd service is installed, active, and enabled on boot, with
`LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED=1`. Existing campaign approval requirements
are unchanged. No campaign was approved or email sent during activation. See
[deployment.md](deployment.md) for runtime and recovery evidence.

This is a local implementation. The follow-up service is disabled by default;
adding these files does not install it, enable it, or send emails. Starting it
against a real mailbox requires the owner's fresh sending approval.

## Approval and scope

Open Outreach and create an initial email with up to two optional follow-ups.
Open **Review & send**, and review the exact recipients and rendered messages.
When the service is enabled, **Approve automatic follow-ups for these recipients**
reveals the remaining messages for the selected recipients. Final confirmation
approves that exact sequence and starts the selected due run. Approval expires
after one year and does not include other recipients or new initial emails.

Changes to the campaign, sender settings, product/identity, signature or recipient
personalization invalidate the stored approval. Review the sequence again before
resuming. Pausing holds the campaign; archiving or Stop Sequence stops pending
messages. An inbox reply or suppression record stops subsequent follow-ups.

Employees can now edit **Settings → Sending hours** to choose repeating weekly
days and minute-precision start/end times. The entire platform uses fixed
**America/New_York (Eastern Time)** with automatic EST/EDT changes. Another
timezone cannot be selected or submitted in Settings. A saved schedule
governs manual outreach and newly reviewed automatic follow-ups. Its exact window
is visible in the final approval. Working-day delays count selected sending days;
calendar-day delays use calendar dates and wait for the next allowed opening.
Delays start after the preceding email was actually accepted. Holidays are included.
Mailbox capacity, daily limits and pacing remain enforced. Human Inbox replies
retain their immediate reviewed sending behavior.

With no custom schedule, historical automatic follow-ups retain Monday–Friday,
9 AM–5 PM hours, while manual due runs and initial outreach
retain 8 AM–8 PM weekdays. Changing Sending hours invalidates saved approvals;
review again before resuming. Migration `0017_siteconfig_sending_schedule` can
also invalidate earlier setup fingerprints and requires reviewing those holds.
Queued reviewed send requests also require a fresh review when their saved setup
fingerprint changes. Spring clock gaps use the first real permitted minute on the
due date; repeated hours are resolved as real instants. Preparation and transport
guards stop at the actual closing boundary.
Migration `0018_new_york_time` normalizes schedule and campaign timezone metadata
without moving absolute due/send timestamps or rewriting historical policy scopes.
The fixed business-clock fingerprint holds previous approvals for fresh review.
All business dates and daily totals use New York, regardless of operator country.

Every automatic send first requires a complete IMAP sync and checks again at the
transport boundary for a reply, opt-out, changed approval and revoked account.
Automatic inbox checks store replies without an AI call; classify and prepare
suggestions separately through the reviewed inbox workflow. SMTP/API traffic
and any provider usage remain subject to that provider's account terms.

## Running after owner approval

Apply all configuration migrations to the control and employee workspace
databases with the existing encryption key retained. The additive migration
`0013_campaign_followup_approval` leaves existing campaigns unapproved.

The controller runs with the control database's environment. Set
`LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED=1` explicitly, then run
`python -m leadzen.scheduler`. A reviewed systemd unit is provided in
`compose/leadzen/leadzen-followups.service`. Install/enable/start it only as part
of an approved release. Restart the API after changing the flag so the review
screen correctly reports service availability. No service-management command
was executed during this audit.

The controller dispatches isolated passes for active, onboarded employees with
an existing workspace. Each pass uses the same workspace sending lock as manual
runs, checks live account access, and processes at most 25 due approved messages
per campaign. A workspace subprocess has a 180-second timeout. An interrupted
or uncertain delivery remains `sending` or `review` and is never automatically
retried. Verify the provider's accepted messages before deciding how to recover.

## Releases and recovery

Stop API intake and the follow-up controller before schema changes or a backup
used for release recovery. Wait for existing `web_worker`, `chat_worker` and
workspace scheduler processes to finish. Preserve matching source, database,
environment/encryption key and service units. The release script now checks
these workers and retains the previous follow-up unit when present. It leaves
follow-ups stopped after a release so delivery holds can be reviewed before an
explicit restart. This script was syntax-checked locally; no deployment ran.

Database backup from Settings downloads only the current employee workspace.
Server recovery also needs the control database, all workspaces, encryption key
and environment. Do not treat an employee download as a complete server backup.

## Operational limits

The flag indicates configured availability, not proof that a service process is
healthy. There is no scheduler heartbeat or external alert configured yet. Check
service health and due/held recipient states during the approved staging pilot.
An approval hold is displayed on the campaign; its notice can remain until the
sequence is reviewed again. One internal VM is the current deployment target;
large-team throughput and crash recovery under real provider latency require
separate load and staging verification.
