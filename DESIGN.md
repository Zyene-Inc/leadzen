# Zyene product materials

LeadZen is a Zyene working screen. Workspace and Chat share one visual system and
one application state. Preserve the existing navigation, layouts and workflows.

## Colors

| Role | Value |
| --- | --- |
| Ink | `#0A1015` |
| Ink hover | `#1B252F` |
| Paper | `#FBFBFA` |
| White | `#FFFFFF` |
| Line | `#E6E8EA` |
| Body text | `#4B525C` |
| Muted labels and help | `#5B626C` |
| Faint placeholders and incidental meta | `#8A8F98` |
| Signal blue, links and focus only | `#1F9BFF` |
| Danger state | `#B42318` |
| Warning state | `#9A6700` |
| Success state | `#1F7A4D` |

Paper is the app background. Cards, controls and menus are white with a 1px line
border. Primary actions are ink with white text. Navigation and progress remain
neutral. Semantic colors communicate actual state, with text alongside color.

## Typography

- Space Grotesk Bold: only the “by Zyene” wordmark beneath the product name, with
  a small TM there.
- Archivo Medium: one screen title, tracking `-0.03em`, line height `1.05`.
- Geist: compact Workspace controls and table text, 14px; reading copy, 15–16px;
  labels and help, 13px. Mobile inputs stay 16px to avoid focus zoom.
- Geist Mono: IDs, codes and timestamps, 11–12px, with slight letter spacing.
- Body line height: `1.6`.

The font files are self-hosted under `dashboard/app/fonts`, with their original
SIL Open Font License notices. No runtime font-provider requests are needed.

## Product logo

Use the user-provided folded-L LeadZen logo, refined in Zyene's ink-and-paper
palette. The shared Brand component renders the complete approved light/dark artwork,
which already includes “by Zyene” and its small TM. Do not add a second native
byline. The matching folded-L mark
is used for browser and home-screen icons. Assets are self-hosted under
`dashboard/public/brand`; masters and prompts are in `docs/brand-assets`.
This replaces the earlier website-favicon instruction at the user's request
on October 3, 2026. Preserve the surrounding Workspace and Chat layouts.
The complete light/dark exports preserve the approved attribution inside the
artwork. Use `leadzen-by-zyene-approved-light.png` and the existing complete dark
variant through the shared Brand component; see `docs/logo-validation-2026-10-03.md`.

## Controls and motion

- Inputs, cards and buttons: 12px radius. Page shells may use up to 28px.
- Workspace actions: at least 44px tall, including primary actions. Reduce padding
  and repeated explanations before reducing readable text or touch targets.
- Focus: 2px signal-blue ring at 20% opacity; focused fields also use a blue border.
- Transitions: 200ms, ease-out; honor reduced motion. No bounce or looping animation.

Login uses quiet fields, one title and one ink action. A dark industrial photo is
optional when a real brand asset is provided. Inside the product, use no photo.
Do not add another brand palette, Inter, glass, mesh gradients, neon or stock AI imagery.

### Chat-specific refinement

The October 3 Chat refinement uses 16px Geist message/input text, a 1.7 response
line height, 20px user-message bubbles, and a 24px desktop / 20px mobile composer.
Its compact conversation title uses 18px Geist. These Chat-specific choices leave
the normal Workspace typography and control shapes intact. Keep the composer
stationary while transcript and history scroll independently. Newly received text
has a short reveal; history and completed answers appear immediately. Actual live
task indicators may animate while work is active, then stop. Honor reduced motion.

## Themes and component library

The Dashboard has a Light/Dark control at the top right beside Refresh. Light is
the default. A browser preference is applied before first paint, survives reloads
and navigation, and synchronizes across tabs. Workspace and Chat use the same
root theme; it never changes application records or server configuration.

Dark mode uses ink as the canvas (`#0A1015`), a neutral raised surface (`#131C24`),
paper text (`#FBFBFA`) and quiet borders (`#2C3742`). Supporting text and semantic
states use lighter values for contrast. Links and focus retain signal blue.
The primary action inverts to paper with ink text. Avoid decorative color.

DaisyUI 5 supplies the grouped theme controls, Dashboard stats and summary cards.
Its classes use the `zy-` prefix and existing Zyene tokens. Tailwind 4 Preflight
and DaisyUI built-in themes are deliberately excluded to preserve existing
Workspace styles. Include only the component modules in use; preserve native
radio keyboard behavior, visible focus and 44px targets. UI Skills baseline
guidance informs spacing, hierarchy and interaction checks.

## Compact guidance (October 3, 2026)

Use `PageHeading` for compact screen titles and `HelpTooltip` for secondary
explanations. The question-mark button opens on hover, keyboard focus or tap;
Escape, blur, outside click, scrolling and resizing dismiss it. Help is rendered
outside clipped cards and kept within the viewport. Use `HelpText` when a short
visible topic label makes the guidance easier to find. Keep help buttons outside
headings, labels and other interactive elements.

Keep costs, send/paid approvals, errors, blockers, current state and the next action
visible in the workflow. Do not hide these in tooltips. Long record content belongs
in existing expandable details; infrastructure paths belong under Storage details.
Dashboard recent decisions use a keyboard-focusable scrolling region so the lead
queue stays close to the summary. Do not shrink Chat messages or its composer.
