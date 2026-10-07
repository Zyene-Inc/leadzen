# Sidebar sizing — local validation, October 3, 2026

## Before / After / Why

Before: the owner's screenshot showed a large sidebar logo and roomy gaps between
workspace identity, navigation and account details. The approved navigation was
already functional, with 44px action targets.

After: desktop sidebar width is 216px (previously 224px at wide widths); its logo
is 156px instead of 180px. Section margins, padding and row gaps are tighter.
Navigation icons are 16px, the account avatar is 28px and secondary captions/email
are 12px. Primary navigation remains 14px; mode labels and Sign out are 13px.
All navigation, mode links and account actions keep their 44px minimum height.
Mobile header padding and expanded section margins also follow the compact sizing.

Why: reduce the sidebar's visual weight and unused space while keeping readable
labels and usable controls. Approved branding, theme colors, login logo sizing,
Chat message/composer sizing and domain behavior remain intact. Long account
names and addresses can wrap inside the flex layout.

## Verification

- Source change: `dashboard/app/globals.css` only; no dependencies or React logic
  changes. No new mirrored style tests were added.
- Existing actual Sidebar navigation/context and Chat presentation regressions:
  **148 tests / 2 files passed** (`/tmp/leadzen-sidebar-compact-tests.log`).
- TypeScript passed (`/tmp/leadzen-sidebar-compact-types.log`).
- Optimized Next.js production build passed (`/tmp/leadzen-sidebar-compact-build.log`).
- `git diff --check` passed.
- Static review covered responsive overrides, retained action heights, independent
  Chat history scrolling, theme asset rules and long-text wrapping. These are
  source checks, not measured browser layout results.

The owner's attached screenshot supplies the before state. A new browser visual
comparison remains unverified following the earlier URL security-policy block;
no alternate browser or raw-control workaround was used. The local dev server
was restored on port 3001 after the build, ready for the owner's visual review.
Local only; no deployment, provider operations or real mail.
