---
name: leadzen-chat-workspace
description: Implement or debug LeadZen's conversational agent, typed outreach tools, streaming, discovery progress, and immediate Chat-to-Workspace updates over shared canonical records.
---

# Chat over the existing Workspace

Read root `AGENTS.md` and the
[project current state](../leadzen-project/references/current-state.md).
Use this for Chat/domain behavior; use the UI quality skill for appearance.

## Canonical context and tool boundaries

Backend: `leadzen/chat/{context,tools,engine,views}.py`, `leadzen/chat_worker.py`.
Frontend: `dashboard/components/chat.tsx`, `chat-results.tsx`, `chat-history.tsx`,
`chat-response.tsx`, `dashboard/lib/chat.ts`, `chat-stream.ts`, `workspace-context.ts`.

Resolve “these three” from server-validated selected lead IDs, “it” from the active
canonical draft, and named people from actual records. Ask/select when consequential
references are ambiguous. Do not rely on model memory or names as canonical IDs.
Switching Workspace/Chat preserves UI context without duplicating domain records.

Extend existing strictly typed tools and domain handlers. Inspect `tools.py` for
actual schemas and approval groups. Never give the model shell, arbitrary SQL,
arbitrary URL requests, filesystem paths or credentials. Server-issued approval
tokens are tied to the actor, workspace, exact action/IDs/content and expiry;
the model cannot supply a valid token or bypass a consumed approval.

Clearly requested free discovery sets `includeEmails:false` and does not purchase
work emails. Safe stored reads, drafting/revision and approved free workflows can
execute directly. Paid enrichment, sending, external mailbox sync and unsuppression
retain the current confirmation boundaries. Drafting/praise never implies send.
Show complete sender/recipient/subject/body before sending. Report actual transport
acceptance only after the backend confirms it; distinguish deferred and uncertain.

Keep bounded decisions, requests, budgets, worker claims, deadlines, cancellation,
access revocation and sink guards. Read `docs/chat-orchestrator.md` for detail but
check newer current-state/release evidence when old deployment comments conflict.

## Streaming and live discovery

Show actual visible model output and tool status through authenticated SSE; never
invent reasoning, results, progress, or timestamps. Preserve stream parsing across
split UTF-8/CRLF frames, lease renewal, abort cleanup and saved-state fallback.
Queued-to-running transitions must not repeatedly restart a healthy stream.

Discovery uses `leadzen/discovery_progress.py` and the actual finder hooks. Persist
complete results as they arrive. Show discovered, evaluated, rejected, qualified,
pending and saved-result counts with their real meanings. Provider search-index
totals are not returned candidates. Candidate cards show actual identities and
qualification/rejection reasons, with canonical Workspace links. A bounded history
must keep recent updates when its limit is reached. Raw logs stay under optional
details and must remain redacted.

`ChatResponse` renders safe Markdown with a short reveal of newly received content.
Restored history/final content is immediate. Keep raw HTML disabled, remote tracking
images blocked, link destinations bounded, Unicode intact and reduced-motion
handling. Do not animate fake model tokens while waiting for a backend response.

## Immediate shared-record visibility

`dashboard/lib/workspace-updates.ts` emits invalidation for changed tool results,
discovery progress and run state. `client-api.ts` notifies after successful Workspace
mutations. `use-stored-data.ts` and manual-fetch screens consume the revision and
refetch canonical backend records. Focus/visibility restoration revalidates too.

BroadcastChannel messages contain no records or secrets. Ignore the originating
tab's echo, clean up listeners/channels, and do not refresh on every prose token.
Maintain this integration for any new manually fetched Workspace view. Validate
with Chat and Workspace open in separate same-origin tabs and watch saved counts
change without navigation. This mechanism does not promise push to other devices.

## History lifecycle

New, filter, rename, archive and delete operate on actor-owned conversations.
Delete requires explicit UI confirmation and successful backend response before
removing history. It uses `ChatThread.deleted_at`, not cascading record deletion.
Queued/running/paused/approval-pending tasks block deletion. Deleted conversations
are unavailable for reading, editing, continued messages and streaming. Preserve
canonical leads, drafts, campaigns, discovery sessions and operation audit records.
Guard message/delete races with the existing transaction/locking pattern.

## External assistant connections

Claude and ChatGPT use `leadzen/mcp/{auth,views,transport,tools,worker,guard}.py`
over these same services. OAuth records live in the account control DB, not the
employee database. Every read and operation is scoped to the verified employee;
operation polling/idempotency also bind the connection. External actions create
one direct-action ChatRun and the normal portal approval, then run one bounded
capability without calling the model planner. Never accept an assistant's boolean,
approval token or OAuth consent as approval to send/spend. Keep grant revocation,
account/password changes, cancellation and expiry checks at the real provider and
transport sinks. Preserve the original discovery goal when portal Resume rebuilds
a remaining-work action. See [MCP setup](../../../docs/mcp-connections.md) and
`tests/test_mcp_{auth,auth_integration,tools,transport}.py`.

## Regression focus

Check `tests/test_chat.py`, `test_chat_workspace.py`, `test_chat_ai.py`,
`test_discovery_live.py` and relevant dashboard Chat/protocol/presentation tests.
Exercise owner isolation, approval replay/expiry, stale context, actual persisted
results, stream interruption, fixed composer, reading-history scroll, reduced
motion, delete cancel/error/success, and same-tab/cross-tab updates. Use synthetic
providers for agent-driven tests unless the user freshly approves real costs/actions.
