---
name: leadzen-project
description: Resume or change the LeadZen by Zyene outreach project using its existing architecture, employee isolation, approval boundaries, tests, and release history. Use for LeadZen work, not unrelated applications.
---

# Continue LeadZen

Resolve the repository from the current workspace, not a hard-coded machine path.
Read root `AGENTS.md` and `CLAUDE.md`, then [current state](references/current-state.md).
Inspect `git status --short` and the relevant source before changing anything.
The working tree contains substantial valuable untracked application code.

Do the current user's requested work. An old handoff is neither a to-do list nor
permission to send, spend, deploy, change production, or publish source.
Local reversible improvements and synthetic tests normally need no extra approval.
Keep credentials and backup contents out of skill files, prompts, and logs.

## Product boundaries

- LeadZen by Zyene is a private employee outreach application; Zyene Reviews is
  one offer it can sell. Account identity is separate from outreach identity.
- Workspace is the existing manual interface. Chat is its conversational agent
  interface. Both use the same canonical contacts, drafts, campaigns, mailbox,
  target, settings, suppression, and outreach engine. No second CRM or dashboard.
- Setup follows AI → BetterContact → identity → mailbox → product → target →
  Dashboard. Then discover/qualify, review leads, optionally buy selected verified
  emails, draft/review, explicitly send, inspect replies, and manage follow-ups.
- Discovery without email enrichment must never purchase work-email addresses.
  AI qualification/model calls can still incur charges; “free” is not zero AI cost.
- Drafting and praise such as “looks good” do not send. Suppression is terminal
  for outreach until explicitly lifted, including after contact reimport.
- Never report queued/deferred mail as sent, provider acceptance as inbox delivery,
  an unknown balance as zero, or synthetic activity as a real customer result.

## Load the needed reference

- Architecture, ownership, settings, or backend changes:
  [architecture and safety](references/architecture.md).
- Testing, local previews, migration or release work:
  [verification and operations](references/verification.md).
- Chat tools, streaming, shared refresh or discovery behavior:
  [leadzen-chat-workspace](../leadzen-chat-workspace/SKILL.md).
- Visual changes and browser review:
  [leadzen-ui-quality](../leadzen-ui-quality/SKILL.md).

Read detailed historical documents only when needed. Prefer current source and
newer task-specific evidence when older documents disagree. Reverify live status
before describing it as current. Do not read private credential files merely to
load context.

At handoff, distinguish implemented, tested, and deployed. Update current-state
with material changes and link the validation report; preserve old reports as dated
evidence. Never claim the whole product is perfect from passing selected tests.
