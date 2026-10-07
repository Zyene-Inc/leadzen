# Compact UI validation — October 3, 2026

Local implementation only. No deployment, real email, paid lookup or provider
operation was performed for this UI change. Existing dirty/untracked work was
preserved. The existing disposable preview on localhost:3001 / 127.0.0.1:8000
was used with synthetic employee records.

## Before / After / Why

| Before | After | Why |
| --- | --- | --- |
| Repeated breadcrumb, title and instructional paragraph on each screen | Compact title with a question-mark help control | Keep the action and working content easy to scan |
| Metric definitions and workspace instructions always visible | Metric definitions available on hover, focus or tap | Read numbers quickly without losing their meaning |
| Eight recent decisions pushed the lead queue below the desktop viewport | Bounded, keyboard-focusable recent activity region | Keep the queue close to the summary; retain every decision |
| Large action padding, table rows, forms and panel headers | 44px minimum action targets, tighter spacing, 14px Workspace control/table type | Increase usable density without tiny controls |
| Repeated setup and campaign instructions | Short help topics for identity, offers, mailbox setup, personalization and timing | New employees can ask for detail when needed |
| Database filesystem path mixed with ordinary settings | Storage details disclosure | Keep implementation details out of the normal workflow |
| Long tour paragraphs | Short task guidance with optional deeper explanation | Make initial orientation easier to read |

Shared changes cover Workspace headings (including admin, setup, discovery and
live discovery), dashboard, leads, campaigns, inbox, sending, activity, suppression,
settings, target and Chat header. Existing record details, forms, approvals,
credentials, request payloads and domain services remain in place. Chat retains its
16px reading text, composer and scrolling behavior. Costs, approval terms, blocking
states, errors, provider restrictions and privacy notes remain visible.

`HelpTooltip` portals text outside clipped cards, clamps to the viewport and supports
hovering the explanation, keyboard focus, tapping, Escape and outside dismissal.
It closes when the page scrolls or resizes. Its button never submits a form.
Escape dismisses help without also bubbling into an enclosing editor/dialog.
No new dependency or external asset was added.

## Verification

- `npm test -- --maxWorkers=2`: **1,032 passed**, 13 files. Six new tests cover
  tooltip association, keyboard, hover handoff, portal rendering, tap/outside
  dismissal, scroll/resize, form submission and Escape propagation.
- Initial default-worker run: 1,025 passed and one existing test timed out at
  5 seconds. The two-worker full run passed, and the final full run after the last
  UI edits also passed. An initial focused command was run from the wrong directory
  and could not resolve test setup; the final suite ran from `dashboard/`.
- `npm run lint`: passed (TypeScript). `npm run build`: passed, all 24 static
  pages generated and dynamic routes compiled. `git diff --check`: passed.
- React Doctor changed scan: 100/100, no findings, but only 10 tracked files.
  Full scan: 114 files, 67/100, **0 errors / 23 warnings** across existing fetching,
  complexity, locale formatting, effect/state and component-size patterns. No
  finding in the new help or heading components. This is not a clean full-codebase
  health claim; the tracked scan misses much of this untracked application.
- In-app browser: populated pages checked at **1440×1000** and **390×844**.
  Dashboard, discovery form, Leads, Campaign, Inbox, Sending, Suppression,
  Activity, Settings, Target, Tour and Chat had no page-level horizontal overflow.
  Table scrolling remains available inside its containers.
- Verified actual hover help on desktop, click help on mobile, viewport containment,
  Escape dismissal, Settings editor Cancel, light/dark theme rendering and
  `prefers-reduced-motion: reduce` (help animation is `none`). Browser log read
  returned no warnings/errors for the final route checks. Temporary viewport and
  reduced-motion overrides were reset; light theme restored.

No Python/domain behavior changed, so backend suites were not rerun. Browser
validation used the ready employee fixture; admin and initial account setup were
covered by frontend regression tests, not a separate authenticated admin browser
journey. Real provider billing, sending, delivery and reply sync were not tested.

## Screenshots

- [Desktop dashboard](ui-progress-assets/compact-dashboard-desktop-2026-10-03.jpg)
- [Dark desktop with hover help](ui-progress-assets/compact-dashboard-dark-desktop-2026-10-03.jpg)
- [Mobile discovery help](ui-progress-assets/compact-discovery-mobile-2026-10-03.jpg)
- [Mobile Settings help](ui-progress-assets/compact-settings-mobile-2026-10-03.jpg)
- [Dark mobile dashboard](ui-progress-assets/compact-dashboard-dark-mobile-2026-10-03.jpg)
- [Mobile Chat](ui-progress-assets/compact-chat-mobile-2026-10-03.jpg)
