# Zyene materials validation — October 2, 2026

The existing Workspace, Chat and authentication screens now use the material
specification in [DESIGN.md](../DESIGN.md). Navigation, application services and
canonical records remain shared; this change does not add another dashboard.

## Changes

- Exact ink, paper, white, line and text tokens; neutral navigation and progress.
  Signal blue is limited to links and focus. Semantic colors indicate real state.
- Self-hosted Geist and Geist Mono, Archivo Medium for screen titles, and Space
  Grotesk Bold for the “by Zyene” wordmark. The four WOFF2 files total 202,776 bytes.
  Archivo and Space Grotesk include only the required weight instances.
- Removed the separate LZ logo tile. Reused the existing Zyene website favicon
  and Apple touch icon. The small TM appears only in the wordmark component.
- 12px inputs, cards and controls; 52px primary actions; 200ms ease-out transitions.
  Removed looping loading animations. Focused fields use a 2px blue ring at 20%
  opacity and a blue border. Disabled buttons retain their disabled appearance.
- Timestamps use Geist Mono. Chat tool errors use danger, running tools use ink,
  and qualified lead badges use success.

## Validation

| Check | Result |
| --- | --- |
| UI regression suite, including ten repetitions of each control scenario | 870 passed |
| Python branding tests | 5 passed |
| TypeScript check | Passed |
| Next.js production build | Passed, all 24 static pages generated |
| Full React Doctor scan | 71/100; same 19 pre-existing warnings, no new findings |
| Whitespace / patch check | Passed |

An initial UI run alongside other CPU-heavy checks had four timing-related
failures. Two subsequent full runs with file parallelism disabled passed all
870 tests. No application behavior was changed to make these tests pass.

Browser verification used the isolated synthetic local preview. Checked login,
Dashboard, Leads, Find Leads, Settings and its editable AI fields, the setup
wizard, Inbox and persistent Chat. Verified loaded font assets, exact computed
colors and focus treatment, one screen-level h1, and primary-button dimensions.
Login, Settings and Chat also fit a 390px viewport without document overflow.
Settings cancellation, sign-out/sign-in and navigation between modes worked.

Preserved existing uncommitted work. No deployment, real email, live provider
request or provider-credit purchase was performed. Existing production-readiness
limitations in earlier audits are not resolved by a visual styling change.
