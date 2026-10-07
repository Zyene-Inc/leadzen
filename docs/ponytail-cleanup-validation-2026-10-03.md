# Ponytail cleanup validation — October 3, 2026

The user authorized implementing the whole-repository Ponytail audit and required
ten cross-checks before implementation. The cleanup is implemented and verified
locally. Existing Workspace and Chat records, approval boundaries, employee
isolation and supported routes are preserved. No deployment, paid provider call
or real email occurred.

## Applied changes

- Removed the unreachable legacy Sending component and its CSS. `/sending` still
  redirects to the canonical `/outreach`. Saved-draft context coverage now renders
  the active Campaigns component; obsolete count-control tests were removed.
- Stored Inbox and suppression reuse `useStoredData` rather than a private copy.
  Loading still hides the previous error, and recovery clears it. Added two
  regressions for the pending-refresh and successful-recovery behavior.
- Removed the unused Home/Sending view flag, Space Grotesk registration/assets,
  callerless `hourLabel` and `isSessionConfigured`, and unused imports/constants.
  Legacy fractional schedule formatting is tested through the active helpers.
- Shared the identical legacy/custom sending-window helper between campaigns and
  outreach, preserving each module's existing patch binding and external sinks.
  Settings use their already-loaded effective values for presence booleans.
- Unified Chat discovery completion while retaining historical single-action
  requests without discovery metadata. Four new cases cover success, partial
  failure, pause and cancellation precedence, with no replay. MCP draft sends use
  the existing identical schema; public tool names/fields remain unchanged.
- Removed unused `compose/openoutreach` launch files. Current `compose/leadzen`
  remains supported. Removed unused dev dependencies `pytest-mock` and `pytest-cov`.
- Combined duplicate Python CI into `tests.yml`, retaining dashboard checks,
  distribution/image builds and backend-success build gating. PR runs test and
  dashboard; main runs test, dashboard and build; version-tag/manual runs test and
  build. No publishing or deployment step was added.

Measured against the exact dirty working-tree snapshot, the net reduction is
**379 source/config/test lines**: dashboard 258, backend including new regressions
24, legacy launch files 78, CI 17 and dev dependency declarations 2. This excludes
new validation documentation and the removed 93-line font license. The unused
font and accompanying license total **35,899 bytes**. Two development dependencies
were removed; runtime dependencies were retained.

## Ten checks before implementation

The gate remained closed until all four review areas completed ten distinct
read-only checks and both affected test groups passed ten times. At that point,
all **301 snapshotted source/config/test/asset files** matched their original
SHA-256 hashes. The snapshot includes uncommitted and untracked source; Git HEAD
was not used as the baseline.

| Area | Pre-edit checks | Evidence reviewed |
| --- | --- | --- |
| Dashboard | 10/10 | Route reachability, actual callers, retained Home UI, shared hook lifecycle/error timing, live selector siblings, fonts, session guards, schedule output, test coverage and exact snapshot |
| Domain/config | 10/10 | Configuration callers/effective values, secret boundaries, brand callers, import reachability, custom/legacy schedule paths, patch bindings, sink guards and baseline tests |
| Accounts/Chat/MCP | 10/10 | Reachability, lifecycle outcomes, cancellation precedence, pause/deadline/session writes, historical requests, replay protection, schema identity and strict input boundaries |
| CI/dependencies | 10/10 | Legacy Docker reachability, supported paths, recoverable originals, plugin consumers/runtime separation, event union, build gating, dashboard steps, source parsing and unchanged hashes |

Each of the ten pre-edit backend repetitions passed **865 tests across 16 files**:
Chat, AI, shared Workspace, discovery, MCP tools, accounts, settings, branding,
campaigns, reviewed outreach, sending-window boundaries/execution and New York
time. These repetitions disabled both removed pytest plugins and used an
in-memory fast password hasher solely for disposable test fixtures; no source or
runtime password setting changed. An additional normal-settings baseline run
passed the same 865 tests.

Each of the ten pre-edit dashboard repetitions passed **689 tests across eight
files**: remaining controls, user journeys, Workspace controls, outreach flow,
sending schedule, New York time, public assets and themes. These were ten actual
suite executions, in addition to any repetitions already defined by the tests.

The final small Sending-only CSS removal received another ten pre-edit checks.
PostCSS comparisons verified that every retained selector's declarations,
ancestor media scope and relative order remained identical. No broad cascade
rewrite was applied. Generated MCP schema comparison and 64 synthetic discovery
outcome comparisons passed before editing.

Raw snapshots, gate records, per-run results and logs are saved outside the repo:
`/var/folders/yb/nbmg2v3d3vd1tskfc45dzx600000gn/T/leadzen-ponytail-before-76nbvgjs`.
The snapshot is recoverable evidence, not a replacement for the user's working
tree or a durable application data backup.

## Final validation

| Check | Result |
| --- | --- |
| Full backend, normal `tests.settings`, removed plugins disabled | **1,237 passed**, one existing Pydantic AI deprecation warning |
| Full dashboard, `npm test` | **1,099 passed**, 20 test files |
| Dashboard `npm run lint` | Passed (TypeScript `tsc --noEmit`) |
| Dashboard `npm run build` | Passed; 26 generated pages, compatible routes retained |
| Built-in Django system check | Zero issues |
| `makemigrations --check --dry-run` | No changes detected |
| CI YAML/TOML, original step comparison and event matrix | Passed locally; GitHub execution not performed |
| Independent final snapshot/code reviews | Approved; only authorized cleanup and intentional test changes |
| `git diff --check` | Passed |
| React Doctor full comparable snapshot/current | **69/100 → 69/100**, warnings **29 → 28**, zero errors and no new diagnostics |
| React Doctor tracked diff | 100/100, no issues; full scan also run because many components are untracked |

The full backend run used normal password hashing. Focused post-edit domain,
interface and dashboard checks also passed before the full suites. Tests that
rendered only the unreachable Sending component were removed; active approval,
capacity, draft and canonical outreach tests remain. Test counts in older reports
refer to different snapshots and should not be combined with this run.

## Browser evidence

The existing disposable synthetic API preview remained on port 8000. Its Next.js
dev server was stopped only for the production build and restored on port 3001.
The browser checked authenticated Home, canonical Outreach, suppression stored
reads/refresh, Inbox conversations and stored-message expansion. The legacy
`/sending` URL visibly redirected to `/outreach`. Stored Inbox and Outreach fit a
390×844 mobile viewport with document scroll width equal to viewport width.
The viewport override was reset. No browser console errors were recorded.

Screenshots show synthetic records only:

- [Outreach desktop](ui-progress-assets/ponytail-outreach-desktop-2026-10-03.jpg)
- [Suppression desktop](ui-progress-assets/ponytail-suppression-desktop-2026-10-03.jpg)
- [Stored Inbox desktop](ui-progress-assets/ponytail-stored-inbox-desktop-2026-10-03.jpg)
- [Stored Inbox mobile](ui-progress-assets/ponytail-stored-inbox-mobile-2026-10-03.jpg)
- [Outreach mobile](ui-progress-assets/ponytail-outreach-mobile-2026-10-03.jpg)

Browser visual checks used the light theme. Automated theme and interaction tests
passed; no new live-provider, production deployment or complete manual keyboard/
reduced-motion certification is claimed. The retained React Doctor warnings are
outside this conservative cleanup.
