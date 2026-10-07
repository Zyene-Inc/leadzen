# LeadZen logo and favicon validation — October 3, 2026

## Complete artwork now in production

Following the owner's latest request, the shared `Brand` component uses the
unchanged attached complete light logo and the existing complete dark variant.
The separate native byline has been removed from this component so attribution
appears once, exactly as part of the approved artwork. Login uses a 240-pixel
logo; the sidebar uses a 196-pixel logo. The existing favicon is retained.

Production deployment `dpl_GmNa3MiHoPVsXHHSntmyX4BA5GUM` is ready and promoted
to `leadzen.zyene.com`. Backend **898** and dashboard **972** tests passed,
alongside TypeScript, both builds, and React Doctor **100/100** for changed files.
Public asset tests now cover both complete logo paths. Production login and
authenticated sidebar load the new artwork. A temporary document theme verified
the dark variant without changing stored preferences. The sidebar fits at
390 pixels with no horizontal overflow; temporary viewport settings were reset.

Screenshots: [Production login](brand-assets/leadzen-approved-logo-production-2026-10-03.png),
[dark rendering](brand-assets/leadzen-approved-logo-dark-2026-10-03.png), and
[mobile header](brand-assets/leadzen-approved-logo-mobile-2026-10-03.png).
Existing uncommitted work and previous image assets were preserved.

The sections below record the earlier compact-logo implementation.

## Result

The user-supplied folded-L identity is installed in Zyene's ink/paper palette.
Workspace and Chat retain their existing screens and records. The shared Brand
component also supplies login, invitation setup and password screens. Light/dark
logos switch through the existing root theme without changing application state.
The “by Zyene” attribution remains native Space Grotesk type, with a small TM.

The favicon uses the same folded-L mark. Root metadata declares a three-frame
ICO, PNG browser icons, and a 180-pixel Apple home-screen icon. Asset filenames
differ from the previous website icons to avoid reusing stale favicon URLs.
All artwork is served locally. Masters, accepted prompts and export details are
in [brand-assets/README.md](brand-assets/README.md).

## Fix found during verification

The authentication proxy originally redirected the new image URLs to login,
causing broken logos before sign-in. The static `/brand/` directory is now public.
A regression test verifies that assets load even without dashboard configuration,
while Workspace, Chat and API access still require authentication. No record or
API authorization rule was relaxed.

## Checks

| Check | Result |
| --- | --- |
| Dashboard UI suite | 972 passed across 8 files; the existing 97 scenarios repeat 10 times, plus 2 new public-asset/authentication checks |
| Python branding checks | 5 passed |
| TypeScript (`npm run lint`) | Passed |
| Production build (`npm run build`) | Passed; all 24 pages generated |
| React Doctor changed-files scan | 100/100, no issues in the tracked changed files |
| React Doctor full scan | 71/100, same 19 pre-existing warnings; no regression |
| `git diff --check` | Passed |
| Export validation | PNG dimensions/alpha verified; ICO contains valid 16/32/48-pixel PNG frames |
| Public asset HTTP checks | Logo and ICO return 200 with correct PNG/ICO content types before sign-in |
| Browser metadata | New icon URLs and size declarations present on login |
| Browser visuals | Light/dark Workspace, dark Chat, login and setup artwork loaded correctly |
| Responsive checks | 390 × 844 mobile navigation fits in both themes with no horizontal overflow |
| Accessibility | One named image (“LeadZen by Zyene”); internal variants/byline hidden from duplicate announcements |

Browser verification used the disposable synthetic preview API. No real lead
discovery, enrichment, mailbox sync, email sending or deployment was performed.
This validates the branding change and existing local UI regression suite; it
does not claim new validation of live provider integrations.

## Previews

- [Light Workspace](brand-assets/leadzen-dashboard-light-preview.png)
- [Dark Workspace](brand-assets/leadzen-dashboard-dark-preview.png)

The local preview remains available at `http://localhost:3001`.
Existing uncommitted work and the earlier website icon files are preserved.

## Attribution follow-up

At the user's request, complete light/dark artwork now includes “by Zyene” and a
small superscript TM. The app continues to use the same shared Brand component
with native Space Grotesk Bold attribution, increased to 14px with clearer spacing.
The complete logo artwork is saved as `leadzen-by-zyene-light.png` and
`leadzen-by-zyene-dark.png` in `dashboard/public/brand`; masters and exact built-in
generation prompts are recorded in the asset README. The folded-L favicon stays
compact enough to read at browser-tab sizes.

Desktop light/dark browser checks confirmed the 14px attribution and local font.
A 390 × 844 mobile check confirmed it fits without horizontal overflow. No
application logic changed, so the earlier regression/build results above were
not rerun for this CSS and artwork adjustment.

- [Updated light header](brand-assets/leadzen-by-zyene-app-light-preview.png)
- [Updated dark header](brand-assets/leadzen-by-zyene-app-dark-preview.png)
