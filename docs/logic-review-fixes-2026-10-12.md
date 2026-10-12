# Logic review fixes — October 12, 2026

A requested read-only logic review of `main` at `b6f350c` (after the selectable
lead-provider release), followed by fixes for every confirmed defect. Local source
only: nothing was committed, migrated, deployed, sent or billed. All checks use
synthetic transports; real AI Ark, BetterContact, SMTP/IMAP and billing were not
exercised.

## Baseline before changes

Backend 1,707 passed. Frontend 1,212 passed on a quiet run (an earlier run under
parallel load had 15 vitest 5-second timeouts that did not reproduce). TypeScript
and the production build passed. Passing tests did not cover the defects below.

## Fixed

### Outreach safety

- **Unsubscribe button ignored by automatic follow-ups/Autopilot (high).** Automatic
  reply checks skip classification by design (no AI spend), but classification was
  the only path that suppressed mail sent to the `+unsub` alias, which arrives in a
  new thread. `honor_saved_optouts` now suppresses unclassified inbound senders to
  that alias without reading bodies or calling AI, on every sync.
- **Reply in a new thread did not stop follow-ups.** Follow-up sends (step > 0) now
  stop when the contact's address sent any inbound message after our first email,
  in any thread, before the send and again at the transport guard.
- **Unrelated suppression invalidated campaign approvals mid-job.** The
  `send_campaign` snapshot hashed every workspace suppression, so a sync suppressing
  another contact parked the in-flight recipient in review with an unsent attempt
  counted. It now freezes only the approved recipients' suppressions.
- **API reactivation restored an old automatic approval.** `PUT /api/campaigns/<id>`
  to `active` now clears `followup_approval` for non-Autopilot campaigns, matching
  `start_campaign`.
- **Unsuppress could delete a later real opt-out.** Suppression keeps its first
  reason, so a manual block followed by STOP/unsubscribe still read "Manually
  suppressed". `unsuppress_contact` now refuses when an opt-out kind, `+unsub`
  message, exact STOP reply or dead-address bounce exists for the address.

### AI Ark

- **Paid email discarded on Stop.** The receipt was marked valid and a stop check ran
  before the address was saved, permanently blocking another lookup. The address is
  now saved before any stop check.
- **Run cut off by the 15-minute approval window.** Expiry was checked against the
  current time throughout the run, stranding already-bought profiles. It is now
  checked against the run segment's start; the run deadline bounds the rest. Resume
  after expiry is still refused.
- **Changing the lead count re-bought the same profiles.** The page cursor was keyed
  by filters plus page size. It is now keyed by filters only and advances past every
  profile already bought (legacy size-keyed receipts are honored).
- **Bought-but-unevaluated profiles were skipped.** A re-seen profile saved by an
  interrupted run with no verdict is queued for qualification.
- **Refused requests left a phantom uncertain charge.** A reservation refused before
  submission (provider switch, mismatch) is removed instead of blocking Resume.
- **Failures described as finished.** The run note no longer says "finished within
  the approved budget" after an error.

Unchanged after review: email credits follow the documented valid-result billing
rule; catch-all addresses remain withheld.

### Dashboard

- AI Ark totals (profile search + emails) are no longer labelled "Email credits" in
  live discovery, the Chat card and Chat activity; Find Leads explains that Start
  approves the AI Ark search and email limit. BetterContact wording is unchanged.
- A transient lead-page poll/refresh failure (network, 429, 5xx) keeps the loaded
  contact and polling; a denial or not-found still clears it and its Chat reference.
- The lead-count decrease button works when the count exceeds the provider maximum.
- A passed connection test whose settings refresh fails no longer reports failure.

## Verification

- 12 new backend regression cases in `tests/test_automatic_followups.py` and
  `tests/test_ai_ark.py`; each failed against the previous source and passes now.
- New frontend regressions in `discovery-ui`, `chat-live-activity`, `lead-polling`,
  `lead-provider` and `review-controls` tests.
- Final: backend full suite 1,720 passed (run before one AI Ark credit-rule edit was
  reverted, which also removed one test; the affected AI Ark and follow-up files were
  re-run afterwards: 95 passed). Frontend 1,219 passed; TypeScript, production build
  and `git diff --check` passed.
- Not exercised: real provider credentials, billing, SMTP/IMAP or browser visuals.

## Release notes

No migration is required. Pending `send_campaign` approvals created before this
change will fail closed once (their snapshot formula changed) and need re-approval.
