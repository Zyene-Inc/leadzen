# Chat and discovery UI validation — October 3, 2026

This change makes Chat and discovery more compact, adds progress driven by actual engine events, and keeps the Chat composer stationary while the transcript scrolls. Workspace and Chat continue to use the same persisted records, configuration, permissions, and action approvals. Existing uncommitted work was preserved.

## Review

| Before | After | Why |
| --- | --- | --- |
| Large spacing, headings, and discovery summaries | Smaller page padding, headings, card spacing, and metrics; usable touch controls remain | More useful information fits on a working screen |
| Long Chat conversations pushed the composer down the page | A viewport-height Chat shell with one transcript scroll region and a separate composer dock | The message box remains available during long operations |
| Little feedback while the model or a tool worked | Actual streamed text, a streaming cursor, current tool activity, and active task feedback | Users can see what is happening without fabricated progress |
| Search totals did not explain individual candidates | Persisted profile arrivals, current AI review, candidate names, and exact accepted/rejected reasons | Discovery and qualification are visibly different states |
| Progress history could stop updating at its event limit | Bounded rolling history retains the original start event and recent progress | Long discovery runs continue to show new activity |
| Pending review counts could subtract unrelated totals | Exact persisted awaiting-review count | Previously queued profiles do not produce misleading progress |
| Scrolling earlier messages could compete with incoming text | Following pauses when reading history; Jump to latest is interruptible and respects reduced motion | Users keep control over their reading position |
| Growing cards or resizing could briefly interrupt automatic following | Only user scrolling leaves following; a cleaned-up resize observer tracks transcript and viewport changes | Current live activity stays visible during changing layouts |
| A queued-to-running transition could restart the live connection | One connection survives that status transition; recovery uses saved state and clears stale notices | Avoids reconnect races and misleading connection warnings |
| Mobile Chat title and controls competed for space | One compact title line with actions on a separate row | Fits narrow screens without horizontal overflow |

New arrivals use short opacity/position transitions. Activity motion stops when the operation stops. Reduced-motion preferences disable decorative motion and make jumping instant. The approved LeadZen by Zyene artwork, ink/paper colors, light/dark themes, and existing Workspace routes are retained.

## Automated validation

| Check | Result |
| --- | --- |
| Full Python suite | 908 passed; one existing PydanticAI deprecation warning |
| Focused discovery/activity backend checks | 72 passed |
| Full dashboard Vitest suite, final integrated code | 1,018 passed across 11 files |
| Focused Chat experience, SSE protocol, discovery UI suites | 46 passed on each of 10 consecutive final runs |
| Dashboard TypeScript check | Passed |
| Optimized Next.js build | Passed; all 24 pages generated |
| Git whitespace check | Passed |

Focused tests cover actual streaming, CRLF/multiline SSE frames, split UTF-8 delivery, aborted readers, session expiration, composer placement, IME and Shift+Enter input, duplicate-submission protection, cancellation, following/history behavior, smooth-jump interruption, layout growth and observer cleanup, stream recovery, actual candidate identities/reasons, canonical links, preserved prior verdicts, partial-goal completion, arrival motion, and polling recovery.

One concurrent run hit the existing five-second timeout in two Workspace control tests. The complete suite was then rerun alone without changing timeouts or assertions: all 1,018 passed in 25.98 seconds. Duplicate generated Next.js type files with “ 2” filenames were removed before the final type/build check; source files were preserved.

React Doctor's tracked-change scan reports 100/100 for 10 files. Many existing project components are untracked, so a separate full scan was also run: 108 files, no errors, 22 warnings. The full scan is the relevant coverage for those components. Its remaining groups were reviewed rather than suppressed:

| Warning group | Assessment |
| --- | --- |
| Component complexity, size, duplicated JSX | Maintainability warnings; no runtime defect identified. Includes existing large Workspace components and the new conditional Chat/activity rendering. Low immediate impact; high confidence that splitting components could improve readability. |
| Locale/timezone formatting | Presentation warnings. Discovery timestamps are rendered from client-fetched progress and intentionally use the viewer's locale; no hydration failure observed. High confidence for the discovery case; broader timezone product decisions are outside this polish. |
| State updates after awaiting an effect | Chat stream and refresh paths guard abort state and conversation epoch; regression tests cover stale history and stream recovery. High confidence that the reported Chat path has its required lifecycle protection. |
| Setup fetch inside an effect | Existing setup implementation; unrelated to this change. No new failure observed. |

## Browser validation

Chrome checks used the disposable local preview database and synthetic AI/discovery adapters. They exercised the real application persistence and streaming paths without calling external providers.

- Desktop Chat: the page height stays equal to the viewport; only the transcript scrolls. The composer dock stays at the bottom through long conversations.
- Smooth Jump to latest: the control remains hidden during intermediate scroll positions and reaches the actual bottom. Earlier messages remain readable without being pulled forward by new text.
- Mobile Chat at 390 × 844: no page-width overflow; title/actions fit and the composer remains anchored. Light and dark variants were checked; viewport overrides were reset afterward.
- Workspace discovery: completed synthetic runs of 3 and 10 qualified leads, including intermediate progress, saved accept/reject reasons, live candidate activity, and zero email credits.
- Chat discovery: live current-candidate feedback, actual streamed messages, saved results, and successful completion without a stale connection warning.
- Shared records: a Chat result opens its canonical Workspace lead, showing the same qualification reason and “Not yet requested” email state. Returning to Chat preserves the current lead context and conversation.
- Browser console: no warnings/errors observed during the live-stream checks.

Screenshots use clearly labeled sample leads:

- [Workspace live discovery](ui-progress-assets/discovery-live-light.png)
- [Chat live discovery](ui-progress-assets/chat-live-light.png)
- [Mobile Chat, light](ui-progress-assets/chat-mobile-light.png)
- [Mobile Chat, dark](ui-progress-assets/chat-mobile-dark.png)

## Scope and limits

These UI changes are local and have not been deployed. No real emails were sent, provider credits spent, database migrations added, or production configuration changed during this work. The preview runs at http://localhost:3001 using disposable synthetic data.

This is validation of the changed interactions plus the existing automated regression suites. It does not claim that every production action was manually tested ten times or that third-party provider behavior was tested live. Live provider and production checks remain subject to the user's explicit approval.
