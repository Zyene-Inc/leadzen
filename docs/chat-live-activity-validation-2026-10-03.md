# Chat live activity — October 3, 2026

Implemented locally. No deployment or real provider operations. The existing
disposable preview was restarted against the same fixture directory to load the
additive run-timestamp fields. No migrations or dependency installation required.

## Before / After / Why

- **Before:** a transient work indicator plus a large discovery card duplicated
  progress in the transcript. The supplied reference component used hard-coded
  reasoning text, perpetual scrolling and an interval every five milliseconds.
- **After:** one compact current-task activity block, collapsed by default.
  Its title reflects actual queue, tool, response, pause, approval, stop or final
  state. Discovery counts come from that run's saved progress. Expand to read
  recorded actions and qualification events in a bounded, keyboard-focusable
  region. The user controls scrolling. Workspace links remain visible.
- **Why:** employees can see whether work is progressing without a large text
  panel. Recorded details remain available when they need to investigate.

The clock uses server `created_at` and `finished_at`, refreshes once per second
only for queued/running work and is labelled as elapsed since the request,
including waits. It is omitted while paused/awaiting approval or when old responses
lack timing fields; completed/stopped tasks use their saved end time. It is not
a fabricated processing-time estimate. Animation stops in nonactive states and
is disabled for reduced motion.

Current in-flight tool progress and the current lead-discovery result are represented
in the activity block. Other tool results, drafts, errors and approval cards remain
in their existing locations. Approved email budget and unknown credit reporting
remain visible when relevant. Older discovery cards stay in conversation history.
Reload uses the matching saved tool discovery payload when no live snapshot is
present; counts from an unrelated older run are never substituted.

Main implementation: `chat-live-activity.tsx`, Chat integration, `currentRunDiscovery`
in `lib/chat.ts`, shared CSS, and additive timestamps in `leadzen/chat/views.py`.
Existing streaming, cancellation, owner scoping and external-action approvals are
unchanged. Uses the existing brand and primitives, with no shadcn migration.

## Checks

- Full frontend: **1,042 passed**, 14 files (`npm test -- --maxWorkers=2`).
- Ten new activity tests cover expansion, actual counts, saved-history recovery,
  stale-run isolation, elapsed time, terminal/pause/approval timer cleanup, new-run
  reset, missing timestamps and failed-action counting.
- After final ARIA/focus edits: **37 passed** across live activity, Chat experience
  and Chat presentation suites.
- Backend: **491 passed** in `tests/test_chat.py` and `tests/test_chat_workspace.py`.
  The persisted completion test now verifies exact server timestamps. One existing
  Pydantic event-loop deprecation warning.
- TypeScript and optimized Next.js build passed after final edits. `git diff --check`
  passed. Initial TypeScript checking found duplicate generated `.next/types/* 3.ts`
  files; those generated duplicates were moved to a temporary backup, not source.
- React Doctor full scan: 116 files, **67/100**, 0 errors and 23 warnings. One
  complexity warning now covers `RunActivity` in place of the prior work indicator;
  overall warning count unchanged. An earlier scan had unavailable remote checks;
  the final scan completed and returned a score. Warnings were not suppressed.
- Actual browser, synthetic provider: five-lead run completed and retained a fixed
  **26s** duration after reload. A second run was stopped using the existing Stop
  task button; it reached `cancelled`, retained **12s**, and had no animated dots.
- Desktop **1440×1000**, mobile **390×844**, light/dark, native Enter expansion,
  manual disclosure, bounded event area and reduced motion checked. No page-level
  horizontal overflow. Event region is keyboard focusable; timer is outside the
  status live region to avoid second-by-second announcements. Final browser logs
  contained no warning/error entries. Viewport/media overrides reset; light restored.

Browser checks did not execute real paid lookup, sending or mailbox sync. Approval
and failure state handling were covered with synthetic automated tests. The preview
fixture includes sample names and records; its results are not real prospects.

## Screenshots

- [Compact completion](ui-progress-assets/chat-live-complete-desktop-2026-10-03.jpg)
- [Expanded saved events](ui-progress-assets/chat-live-expanded-desktop-2026-10-03.jpg)
- [Initial active state](ui-progress-assets/chat-live-collapsed-desktop-2026-10-03.jpg)
- [Mobile dark active state](ui-progress-assets/chat-live-mobile-dark-2026-10-03.jpg)
- [Mobile stopped state](ui-progress-assets/chat-live-stopped-mobile-2026-10-03.jpg)
