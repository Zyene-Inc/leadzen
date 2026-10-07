# Interactive product tour — October 4, 2026

Local source and disposable preview only; not deployed.

## Before / After / Why

**Before:** `/tour` showed six text slides. Employees could not practice real
controls, progress disappeared on refresh, and the onboarding guard redirected
unfinished tours away from the Workspace.

**After:** 14 concise steps follow actual Home, Leads, Outreach, Inbox, Settings
and Chat screens. The employee clicks real Leads/Inbox/Settings links, opens the
real Add contact form and Sending hours editor, and closes those forms. Other
steps explain actual controls without executing discovery, drafting, sync or mail.
Settings → **Take Product Tour** restarts a finished/skipped tour; `/tour` resumes
an active one.

**Why:** practice and short explanations introduce the real workflow without
duplicating screens or generating demo records in an employee workspace.

## Implementation

- An internal `ProductTourProvider` in the persistent App Router layout uses
  existing theme, typography and button classes. No dependency was added.
- Stable `data-tour` attributes mark real UI. Readiness uses DOM observation,
  visible/enabled targets, loading state, actual route changes and click outcomes.
  A target must appear before the tooltip; a click alone does not complete a step
  that expects an opened/closed form or a destination route.
- Geometry settles after scrolling, followed by a 350ms reading beat and 200ms
  tooltip reveal. Reduced motion removes smooth scrolling and that beat.
  Safety timeouts offer undimmed Retry/Back/Skip rather than advancing blindly.
- An SVG overlay leaves the actual target visible. The overlay never intercepts
  product actions. Tooltip placement accounts for scroll, resize, observed element
  size and the mobile visual viewport, including a keyboard; the card can scroll.
- Keyboard arrows operate from the tour, Escape skips, Go to control focuses the
  actual action, and the native nonmodal dialog announces title, explanation and
  step count. Guidance for a native modal target is mounted inside that modal so
  the rest of the page's inert state does not hide its controls. The employee can
  leave the route and resume later.
- Server account state stores `tourStarted`, `currentStep`, `tourCompleted` and
  `tourSkipped`; pending browser recovery is scoped to the account ID. Serialized
  writes are checked against the current actor identity before dispatch. Unmounts,
  Skip and account changes cancel waits. Start waits for server acknowledgment
  before entering protected routes. Stale pending progress cannot revive a
  server-completed/skipped tour.
- Additive account migration `0004_accountprofile_tour_state` preserves earlier
  completed tours. `GET/POST /api/tour` uses the existing actor/session boundary.
  The tutorial gate accepts active/skipped tours; password, onboarding, admin,
  session and MCP redirect checks retain their order. Setup does not restart a
  skipped tour. The existing empty completion POST remains compatible.
- Tour writes do not broadcast domain-data refreshes. Existing Chat streaming,
  send approvals, automatic authorization and domain services are unchanged.

## Verification

- **1,165 frontend tests / 23 files passed** before the final focused lifecycle,
  native-dialog, dependency and marker refinements. The final focused run passed
  **69 tests**: 42 tour lifecycle/DOM/geometry/storage cases, 3 actual-product
  integration cases and 24 auth/login/MCP gate cases.
- The full 14-step integration uses the actual Overview, Contacts, Campaigns,
  Inbox, Settings, SendingScheduleEditor, Chat and Sidebar components with the
  production step definitions. It verifies real clicks and Finish. Separate
  refresh cases reopen the actual contact and schedule forms. Synthetic API
  fixtures are used; no provider, mail, sync or Settings-save operation occurs.
- Covered Back/Next/Skip/Finish, keyboard/focus, reduced motion, late and hidden
  targets, timeout/cancellation, scrolling/resizing/ResizeObserver, viewport-edge
  placement, slow saves, pending start acknowledgment, Skip while start is pending,
  stale terminal state, per-account recovery and guidance inside a native dialog.
- **85 backend tests passed** across tour state, accounts, invitations and setup;
  the isolated accounts/workspace integration and migration-backfill tests also
  passed during the backend implementation. Django checks reported zero issues
  and migration consistency passed.
- Real local HTTP checks with the disposable employee exercised start/progress,
  GET recovery, Skip, restart and Finish. Contacts, Outreach, Inbox, Settings and
  Chat returned HTTP 200 for an active tour; Home returned 200 after Skip; final
  completion was read back. The disposable employee was restored to completed
  status afterward.
- TypeScript, production build and whitespace checks passed. React Doctor tracked
  scan: 100/100. Full tree: 69/100, zero errors, 29 warnings. One new complexity
  warning covers the tour lifecycle controller; the remaining diagnostics span
  existing screens. No warnings were suppressed.
- The disposable API was migrated and the dashboard preview restored on 3001.

## Remaining validation

**Real-browser visual and interaction review is outstanding.** Automatic approval
review rejected access to the existing localhost tab with “URL protocol is not
allowed.” No alternate browser surface or automation workaround was attempted.
No screenshots were created. DOM integration and geometry tests establish the
checked behavior, but do not prove rendered CSS clipping, actual screen-reader
speech, light/dark appearance or mobile-browser behavior.

Before releasing, apply the account migration through the normal backed-up release
procedure and complete the browser walkthrough at desktop/mobile sizes, both
themes and reduced motion. Deployment and external operations were not performed.
