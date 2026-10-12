# Provider search targeting — October 12, 2026

Follow-up to the [logic review](logic-review-fixes-2026-10-12.md). A trace of Chat
and Find Leads discovery found that neither provider reliably searched the
requested people. Local source only: not committed, migrated in production or
deployed. No email was looked up or sent.

## Problems found

- **BetterContact searched the first-ever target forever.** The pinned finder seeds
  one global search frontier from the campaign target only when none exists
  (`openoutfind/core/pipeline/discover.py` `_ensure_frontier`). A changed Target or a
  Chat audience only changed which returned profiles AI qualification rejected.
  This is the likely root cause of the October 7 mismatch (restaurant target,
  dental results, zero new profiles). Location/size/seniority were LLM guesses;
  all 12 seniorities were always searched; industry is not a Lead Finder filter.
- **AI Ark industries rarely matched.** AI Ark matches `account.industries` against
  919 fixed values. LeadZen sent the typed text ("Dental practices") in `WORD`
  mode, which most likely returned nobody. Countries used pytz names ("Britain
  (UK)"), and the Target had no state/city, so "dentists in Texas" searched the
  whole US and paid for out-of-state profiles.
- **Chat previews did not say** whether a request changed the provider search or
  only AI qualification.

## Changes

### BetterContact (`leadzen/search_plan.py`, migration `0021_search_plan`)

- Each run's target is fingerprinted (normalized text plus enforced location,
  size and seniority). Case, spacing and trailing punctuation are not meaningful.
- On a change, the finder's learned search state is **backed up** into
  `SearchPlan.state` (keywords, query nodes with page offsets/states, invented
  ideal profiles with embeddings), then cleared. Returning to an earlier target
  **restores** its saved plan instead of rebuilding. Up to 20 archives are kept.
- Real leads, decisions and contacts are never deleted. Real leads' optional
  `discovered_by` link to a removed query node becomes empty (the finder defines it
  as provenance only, `on_delete=SET_NULL`).
- During a run the finder sees only the current plan: new seed (with fresh ideal
  profiles), vocabulary from leads accepted under this plan, an unjudged pool of
  profiles found under this plan, and seniority/location keywords from the Target.
- Every Lead Finder request is constrained to the Target's location ("Texas,
  United States"), company-size band and seniority, both when the finder builds
  the query and again at the transport boundary.
- A one-off Chat audience builds its own plan. Chat can pass `country`/`region`
  with it so that search is restricted to that place; the saved Target's plan is
  archived and restored on the next normal run. `OPENOUTFIND_CAMPAIGN_TARGET` is
  now set on every run, so an earlier audience cannot linger in a process.

### AI Ark (`leadzen/ai_ark.py`, `leadzen/industries.py`, `leadzen/geo.py`)

- Industry text maps offline to up to three supported AI Ark values (ORed), e.g.
  "Dental practices" → `dental`, "Law firms" → `legal`, "Restaurant & hospitality"
  → `restaurants`, `hospitality`. Unmapped text searches company keywords
  (industry, keywords, description) instead of returning nothing. The list is
  copied in `leadzen/data/ai_ark_industries.txt` from AI Ark's published CSV.
- Titles and industries use AI Ark's recommended `SMART` matching.
- Countries use plain names ("United Kingdom", "South Korea") everywhere,
  including the country pickers.
- Target has an optional state/city (`region`). AI Ark searches it as
  `contact.location.all.include = [country, region parts]`.

### Target and Chat

- `region` is validated (single line, ≤120 characters) in setup, Target and the
  Chat `update_target` tool. Targets saved before this change remain active.
- Approval previews and discovery progress carry `search_scope`: whether the
  request changes the provider search, what the provider is asked for, and what is
  only checked by AI qualification. The dashboard shows both lines.

## State that is reset

On each employee's first BetterContact discovery after release, finder state that
predates target tracking is archived as a `legacy-…` SearchPlan and a fresh plan
is built for the current Target (one seed and ideal-profile AI call). Later resets
happen only when the Target or a one-off audience meaningfully changes. Unjudged
profiles found under an earlier target stay in the database but are no longer
auto-qualified by later searches. AI Ark has no learned state to reset.

## Verification

- New `tests/test_search_targeting.py` (28 cases): industry mapping, SMART and
  location filters, keyword fallback, country names, Target region and legacy
  Targets, plan backup/reset/restore, cosmetic edits, legacy archive, archive
  bound, request enforcement, finder scoping, an end-to-end Lead Finder request
  body through `find_leads`, Chat location overrides and search-scope previews.
- Updated `tests/test_ai_ark.py` (mapped industry, SMART, location) and
  `tests/test_autopilot_discovery.py` (frontier created under the active plan).
- Updated expectations: `tests/test_home.py` (saved audience includes `region`),
  `tests/test_operations_preflight.py` (latest migration is `0021_search_plan`).
- Dashboard: new `dashboard/tests/target-region.test.tsx` (9 cases) for the region
  field, preview text, older Targets, Home place, approval and discovery scope.
- Final: backend 1,747 passed; frontend 1,228 passed; TypeScript, production build,
  `makemigrations --check`, Django system check and `git diff --check` passed.

## Real-provider validation — October 12, 2026

Run with the employee-supplied keys passed only as process environment variables
(not stored). Dentists, owner seniority, 1-10 employees, Texas, United States:

- AI Ark, mapped industry: `dental` (SMART) with location `all.include [United
  States, Texas]` returned HTTP 200, 32 matching people; the returned profile was
  in Texas, United States, a pediatric dentist at an 8-person company.
- AI Ark, keyword fallback ("Chiropractors", no supported industry): HTTP 200,
  9 matching people; returned profile in Texas, a chiropractor business owner.
- AI Ark credits 99.0 → 98.0 for two returned profiles (0.5 each, as documented).
- BetterContact Lead Finder with `lead_location "Texas, United States"`, seniority
  `owner` and headcount 1-10, enrichment off: 48 matching people; returned profile
  in Texas, title "Owner dentist", no email returned.
- Quirks: AI Ark reports the matched dental company's industry as "hospitals and
  health care" (SMART also matches adjacent industries; AI qualification still
  checks fit). BetterContact reports countries in sentence case ("United states")
  while matching title case, which `as_place` already handles.

## Originally needed real-provider confirmation

No provider credentials were available locally (keys are encrypted in
workspace databases and no settings key or provider key was present), so no real
call was made at first. `tests/scenarios/provider_search_probe.py` runs two AI Ark People
Search pages of size 1 (dental, then the keyword fallback; at most 1 credit) and one BetterContact Lead Finder page
of 1 profile with enrichment off, for dentists in Texas, and prints locations and
industries only. Confirm with it:

- AI Ark accepts `all.include` location with a state and returns Texas profiles.
- `SMART` industry `dental` returns dental companies, and the keyword fallback works.
- BetterContact accepts the enforced `"Texas, United States"` location, the
  seniority list and the headcount band together.
- Production migration `0021_search_plan` must be applied to control and employee
  databases before the backend release.
