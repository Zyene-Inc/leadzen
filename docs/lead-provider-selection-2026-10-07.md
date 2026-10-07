# BetterContact / AI Ark selection — October 7, 2026

## Scope and status

Local implementation only. No production settings, credentials, deployments,
provider purchases, emails, GitHub branches or commits were changed by this task.
The existing CRM, Workspace and Chat records remain the source of truth.

## Before / After / Why

Before, the lead provider and connection screens were hard-coded to BetterContact.
After, each employee can select BetterContact or AI Ark in **Settings → Lead
finding** or onboarding. Each provider has its own encrypted saved key; switching
does not overwrite the other key. Blank preserves a saved key; Remove clears only
the selected provider. Only key-presence flags reach the browser. Connection tests
read the selected account's balance without buying profiles or email addresses.

The selected provider drives Find Leads, Chat, connected-assistant operations and
selected-contact email lookup. Progress, activity, contact receipts, balance and
approval previews identify the provider. Provider changes invalidate outstanding
approvals; there is no automatic fallback to a different provider or billing key.

AI Ark profile searches are paid, unlike BetterContact's current discovery path.
Therefore AI Ark requires explicit approval even when email lookup is off. Its
documented API is pinned to `api.ai-ark.com`; credentials are sent only in the
`X-TOKEN` header. The existing HTTPS/DNS pinning, account revocation, cancellation,
deadline, workspace routing and settings-snapshot guards still apply.

## AI Ark behavior and cost limits

- Uses the active, saved structured audience: industry, current job titles,
  seniority, country and employee-size band. An incomplete/stale setup draft or
  an ad-hoc Chat audience override cannot silently broaden a paid search.
- One bounded profile-search page per approval: at most twice the requested lead
  count, billed at the documented 0.5 credits per returned profile. Duplicates and
  rejected profiles still consume that search budget. Further runs advance the
  saved page for the same filters/page size; results are deduplicated by profile.
- Existing campaign-first qualification judges each new profile. Only qualified
  records enter the same canonical contacts used by both interfaces. Company-size
  evidence is preserved for qualification rather than inferred from a title.
- Optional synchronous email lookup is limited to qualified profiles and up to
  one credit each. The returned LinkedIn identity must match. Only valid,
  non-generic, non-free SMTP-domain addresses are saved; unknown/catch-all
  addresses are conservatively withheld even if the provider charges for them.
- The existing per-run ceiling remains 25 lead-provider credits: up to 25 leads
  without email lookup, or 12 with both AI Ark search and email lookup. A selected
  existing-contact email action reserves only its email budget.
- Reservations are persisted and consumed before writing a paid request. A
  timeout or malformed response remains uncertain, not zero-cost; no paid POST
  is retried automatically. Completed profile pages are reused on Resume.
- Search cost is calculated from the actual returned profile count using the
  documented rate; email cost uses the documented valid-result billing rule.
  These are API-result-based usage records, not reconciliation against an invoice.
- AI/model charges are separate. No phone lookup, bulk export, external contact
  sharing, email send or paid preview is triggered by provider selection.

Daily Autopilot currently requires BetterContact. Its existing recurring approval
does not cover AI Ark's paid profile searches, so AI Ark is blocked at automatic
setup/execution rather than silently spending under an old authorization.

## Verification

All provider responses and model outputs used in automated tests are synthetic.
Focused coverage includes encrypted key preservation/clear, blank keys, provider
switches, free balance probes, fractional/invalid balances, exact search filters,
paid Chat/MCP approvals, one-contact email budgets, known/uncertain usage,
timeout/no-retry behavior, expired/cancelled/changed approvals, exact single-use
transport reservations, verified email mapping, unsafe-email rejection and shared
CRM ingestion. A real two-employee disposable SQLite scenario verifies separate
provider selections and encrypted credentials, including a forged workspace ID.

Frontend interaction tests cover separate provider key drafts, selected-only
submission, independent removal flags and the paid AI Ark cost preview. Full
frontend suite: **1,212 tests passed**; TypeScript passed. Production build passed.
Migration consistency (`makemigrations --check --dry-run`) and `git diff --check`
passed, and Django's system-check API returned no issues. The final combined
backend regression run passed **920 tests across 18 suites** in 285.56 seconds:
AI Ark, BetterContact settings, runtime settings, discovery, live-discovery
fixtures, setup wizard, Chat, Chat AI, Chat engine, Chat/Workspace, home, lead CRM,
activity, MCP tools, account integration, workspace settings, Autopilot and
operations preflight. All external provider operations in these suites were mocked.

Browser automation returned **“User unavailable”**. Disposable local preview
servers were started successfully and then stopped. No visual desktop/mobile,
theme, focus or screenshot verification is claimed. UI changes reuse the existing
native select, secret input and connection panel primitives.

React Doctor was initially network-blocked, then ran successfully. Its tracked
diff scan reported 72/100 with existing large-component/complexity and other
warnings. Full-tree score was **70/100 for both the isolated HEAD baseline and
modified tree** (version 0.9.17); no score regression. No scanner warning was
suppressed or dependency updated to improve the score. The first typecheck found
two pre-existing duplicate generated Next.js type files; these were moved to the
recoverable `/tmp/leadzen-next-types.nLBgMU/` directory, not deleted. Subsequent
typecheck and builds passed without source/config exclusions.

## Repeated cross-check — October 7, 2026

On the owner's request, reviewed provider routing, encrypted settings, exact
approval snapshots, paid transport reservations, resume behavior and usage
accounting again. Rechecked the official API contract. No live provider request,
production database change, commit, push or deployment was made.

Added 11 synthetic regression cases covering pause after a paid search and reuse
of its saved page, ambiguous email timeout/no retry, six failed/malformed search
responses, cancellation during pacing, budget overflow and separate provider
usage totals. The expanded adapter suite passed all 39 cases. One newly written
historical-usage fixture initially violated the existing one-active-run constraint;
marking that historical run completed corrected the fixture, not the application.
The migration preservation scenario now also checks the BetterContact default,
unchanged stored credential ciphertext and empty new search-receipt table.

- Full backend pass: **1,686 passed**, one existing Pydantic AI event-loop
  deprecation warning, 540.16 seconds. This was collected before the 11 new cases.
- Expanded 18-suite feature passes: **931 passed each of two runs**, 324.54 and
  270.81 seconds. Together with the full backend pass, the original affected
  tests ran three times; the 11 added cases passed the focused run and both
  expanded runs.
- Full frontend suite: **1,212 passed each of three runs** (42.10, 30.09 and
  35.10 seconds); no frontend source changes in this cross-check.
- Django system checks, migration consistency, added migration preservation
  scenario, final production build, TypeScript and whitespace checks passed.

The first typecheck found four byte-identical generated ` 2.ts` duplicates; these
were moved intact to `/tmp/leadzen-generated-type-duplicates.EUBtRc/`. A build
then failed while cleaning the old `.next/server` directory (`ENOTEMPTY`). With
no Next server running, the old cache was moved intact to
`/tmp/leadzen-build-cache.EizpIv/previous-next`; a fresh build and typecheck passed.
No source, lockfile, dependency, compiler check or test assertion was removed to
obtain a pass. The recurrence suggests an external cache-copy issue, but its
origin has not been established.

React Doctor reran with unchanged scores: tracked diff **72/100, 31 warnings**;
full tree **70/100, 32 warnings**. No new frontend code was introduced in this
cross-check. The full-tree redirect/frame warning at `lib/auth.ts:38` was inspected:
the redirect is a local login path, while `next.config.ts` sets `X-Frame-Options:
DENY` and `proxy.ts` sets `frame-ancestors 'none'`. This is not a demonstrated
provider-related vulnerability; the remaining pre-existing warnings were not
suppressed or converted into an unrelated UI refactor.

Chrome automation again reported **User unavailable** for both browser profiles.
Visual/browser verification and real provider billing remain unverified. Passing
automated tests does not establish universal correctness or deployment readiness.

## Release requirements

This feature is not live. Before a separately authorized release, back up the
control and initialized employee databases and stable encryption configuration;
apply **all migrations**, including `0020_lead_finder_provider`, to both control
and employee databases using the established release workflow. It adds the
provider selection column and durable paid-search receipt table. No plaintext
AI Ark key column or new environment secret is required.

Real API credentials, account entitlement, billing and provider response behavior
remain unverified. A live paid test requires fresh approval with an exact budget.

Official API contract consulted: [AI Ark API context](https://docs.ai-ark.com/docs/ai-agents).
