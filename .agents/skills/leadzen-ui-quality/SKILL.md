---
name: leadzen-ui-quality
description: Refine LeadZen UI/UX using Zyene's approved logo, neutral colors, typography, compact Chat, purposeful live feedback, light/dark themes, and responsive interaction checks without redesigning Workspace.
---

# LeadZen UI quality

Read root `AGENTS.md`, `PRODUCT.md` and `DESIGN.md`. Preserve existing Workspace
screens and behavior. Improve the requested interaction in place rather than
building another CRM, dashboard, logo, or decorative component system.

## Materials

Use the existing CSS tokens: ink `#0A1015`, hover `#1B252F`, paper `#FBFBFA`, white
surfaces, line `#E6E8EA`, body `#4B525C`, muted `#5B626C`, faint `#8A8F98`.
Signal blue `#1F9BFF` is for links/focus. Danger `#B42318`, warning `#9A6700`,
success `#1F7A4D` communicate actual state with text. No blue-themed sidebars,
purple/teal/orange decoration, gradients, glass, neon or stock AI graphics.

Geist is the UI face; Archivo Medium is the normal screen-title face; Geist Mono
is for small IDs/timestamps. Space Grotesk belongs only to the Zyene wordmark.
Use locally hosted fonts and existing theme tokens. Never install Inter or fetch
a second display font to imitate a reference product.

`dashboard/components/brand.tsx` uses the complete approved folded-L logo with
“by Zyene” already included. Preserve both light/dark variants and favicon metadata.
Do not add duplicate native attribution. Assets under `dashboard/public/brand`
must remain available before authentication; do not broaden API access to do this.

## Density and motion

General controls/cards use 12px radii, 1px borders. The October 3 compact Workspace
refinement uses 44px minimum action targets, 14px control/table text and 13px help;
mobile fields retain 16px text. Move secondary explanations into `HelpTooltip`
or `HelpText`, with hover, keyboard and touch access. Keep costs, approvals,
blockers and errors visible. Use `PageHeading` for compact titles. Chat intentionally
uses 16px message/input text, 1.7 response line height, 20px user bubbles and a
24px desktop / 20px mobile composer. Its compact conversation title uses Geist.
These are the approved local design choices, not measured pixel clones of Claude
or ChatGPT. Preserve useful reading width and space between paragraphs.

Chat's viewport shell keeps its composer stationary while transcript and history
scroll independently. New output follows only while the user is following the end;
reading earlier messages must not be pulled forward. Preserve Jump to latest,
layout-resize handling, IME/Shift+Enter behavior, busy states and cancellation.

Use short opacity/transform transitions, around 200ms ease-out, and disable
unnecessary motion for reduced-motion users. Active text/task indicators can move
while actual work is ongoing; stop when it finishes. Do not add indefinite idle
animation, bounce, invented progress or arbitrary delays to simulate intelligence.
Use actual discovery arrivals, qualification reasons and tool status for live UI.
Chat's `ChatLiveActivity` is the compact current-task presentation: keep it collapsed
by default, preserve real saved event history and Workspace links, and stop the
server-timestamp elapsed clock and motion outside queued/running states. Elapsed
time includes waits, not just model processing. Do not add simulated thinking text,
looping auto-scroll or a second progress card for the same current discovery.

## Existing component system

DaisyUI 5 and Tailwind 4 are installed. DaisyUI uses prefix `zy-`, selected component
modules and existing Zyene tokens; built-in themes and Preflight are excluded.
Read the relevant local DaisyUI skill when changing its components. Reuse existing
primitives before adding dependencies. The owner's request for professional
components is not a requirement to repeatedly run installers or replace the stack.
Review a third-party component's current official docs/license when introducing it.

Light/dark preference is shared by Workspace and Chat, applied before first paint,
persists through navigation and synchronizes across tabs. The Dashboard's theme
control remains at top right. Theme changes never modify domain data or credentials.

## Review and verification

Read [verification](../leadzen-project/references/verification.md) for safe preview
setup. Check relevant controls in desktop and narrow mobile widths; inspect actual
font/composer layout when sizing matters. Verify keyboard focus, dialog Cancel and
Escape, repeated submission guards, error feedback, overflow, both themes and
reduced motion. Keep raw Developer Logs closed by default and out of ordinary flows.

Use browser screenshots of the implemented result, not a mockup. Save proof under
`docs/ui-progress-assets/` with synthetic data, and reset viewport overrides afterward.
Write a concise **Before / After / Why** review plus exact checks and limitations
in a dated validation report. Link it from the project's current-state reference.
Passing tests establish checked behavior, not universal perfection or live-provider
readiness. Keep the final answer clear about local versus deployed changes.

## Unified employee workflow (October 3, 2026)

The current local primary Workspace navigation is Home, Leads, Outreach, Inbox and
Settings. Activity and Do not contact live under Workspace tools. `/outreach`
replaces the separate employee-facing Sending/Campaign choice; old routes redirect
with their record IDs. Keep select → review → confirm, follow-ups off by default,
and exact sender/recipient/message/timing approval visible. Inbox uses an inline
approval for external reply checks. Preserve saved drafts and pending approvals
when employees return; see the unified-outreach validation report for its current
verification limits.


Daily Autopilot is a compact card inside Outreach, with one On/Off switch and a
first-enable scope/authorization form. Keep recurring costs, automatic sending,
follow-up scope, expiry and blockers visible. Read-only polling must never enable,
sync or send. Policies and daily results use canonical saved records; show accepted
messages rather than claiming delivery. Opening settings captures a review snapshot;
background refresh must not silently change what the employee authorizes.

Sending hours is editable in Settings with a repeating weekly day selection,
start/end time. The platform timezone is fixed to **America/New_York**; show
“New York (Eastern Time)” with optional DST help and never offer another timezone.
All rendered dates, daily groups and greetings use the shared `lib/date-time.ts`
helper, independent of browser timezone. Keep the summary compact; show selected
days and minute-precision hours in Outreach and automatic approvals. Newly
authorized Autopilot uses the same selected days/start time for discovery. Do not
restore hard-coded weekday or 10 AM labels for those policies. Changing the
schedule requires reviewing automatic authorization again. Human Inbox replies
keep their immediate reviewed behavior.
