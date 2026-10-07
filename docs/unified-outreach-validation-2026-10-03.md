# Unified employee outreach — October 3, 2026

## Before / After / Why

Before, employees chose between Sending and Campaigns, activated campaigns as a
separate step, and went into Chat to check their mailbox. Everyday navigation also
exposed supporting tools at the same level as core work.

After, `/outreach` is the shared entry point: select leads → review messages →
confirm outreach. AI-assisted preparation uses the existing authenticated Chat
orchestrator and canonical campaign draft service. Manual writing remains
available without AI. Follow-ups default off; employees can add up to two and
review the exact rendered sequence before explicitly approving automation.
Existing personal draft reviews and reply reviews remain accessible alongside
campaigns. Old `/sending?review=…` and `/campaigns?campaign=…` links redirect while
preserving record identifiers. No data migration or second CRM was introduced.

Activation happens inside the final reviewed campaign-send transaction. Opening
or saving a draft cannot activate it. A paused sequence requires a fresh review;
resuming does not silently restore its prior automatic-follow-up approval. All
recipient, content revision, worker, permission, sending-window and suppression
checks remain in the shared services.

Leads now groups Find leads, Import and Add contact, supports selecting up to 25
ready contacts and carries that canonical selection into Outreach. Home displays
saved drafts, human replies awaiting a response and sending/follow-up issues.
Failed or unconfirmed outbound attempts do not count as answered human replies.
Inbox's Check for replies prepares an inline, expiring, actor-bound approval over
the existing Chat sync capability. It restores pending checks on reload and stops
after that single approved action. Costs and mailbox identity remain visible.

Ask LeadZen is available for a lead, selected leads, draft, outreach or conversation.
The sequence editor saves its current copy before opening Chat. Save for later
persists a draft without sending. The navigation is Home, Leads, Outreach, Inbox
and Settings, with Activity and Do not contact under Workspace tools. The product
tour now teaches the same flow.

## Verification

- Frontend full suite: 1,049 tests passed (15 files), including restored selections,
  default-off follow-ups, exact final approvals, cancellation, repeat-click guards,
  saving drafts, inline mailbox approval and restoration, and attention links.
- After the final input and focus changes, 467 focused frontend checks passed
  across Outreach, Workspace controls and review controls.
- Backend broad regression: 584 passed for reviewed outreach, campaigns, Chat/
  Workspace and automatic follow-ups on the initial implementation snapshot.
- Backend follow-up regression: 63 passed across campaigns, Chat and the new flow
  tests; one pre-existing event-loop deprecation warning.
- Final new flow + real employee database routing: 13 passed, including separate
  SQLite workspace isolation, restored inbox approvals and failed-send attention.
- TypeScript and optimized Next.js build passed, including the new Outreach route.
- React Doctor full scan: 67/100, zero errors, 28 warnings. The score matches
  the prior recorded baseline; remaining warnings concern complexity and existing
  component patterns. The 100/100 tracked-diff scan covered only ten files and is
  not used as evidence for the untracked application.
- `git diff --check` passed. Existing uncommitted/untracked work was preserved.

## Limits

The browser tool rejected the existing preview tab under its URL policy before
visual inspection. No workaround was attempted. Desktop/mobile screenshots,
light/dark visual inspection and browser-level interactions remain unverified for
this change. Responsive styles and accessible semantic controls are implemented;
a passing component test suite is not a substitute for that visual review.

All tests use synthetic data/providers. No real email, mailbox sync, paid provider
request, deployment or production migration was performed. Automatic follow-up
availability still depends on the deployed scheduler configuration. The latest
local source has not been deployed. This report does not certify perfection or
live delivery behavior.
