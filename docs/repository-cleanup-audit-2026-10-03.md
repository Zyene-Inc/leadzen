# Repository cleanup audit — October 3, 2026

Three confirmed artifacts were removed, totaling **635,049 bytes (620.2 KiB)**.
No application source, route, component, migration, dependency, deployment file,
or historical evidence was deleted. Existing modified/untracked work and the
19 preexisting tracked deletions were preserved.

This audit covers the **current working tree**, not the old Git HEAD. It is a
cleanup/reference audit, not a certification of live providers or production.

## Coverage and method

The initial inventory contains 491 regular files outside explicitly excluded
vendor/runtime/cache directories. Three Claude skill symlinks, `data/.gitkeep`,
and the stray root Vitest cache bring the classified inventory to **496 entries**.
The [per-file inventory](repository-cleanup-inventory-2026-10-03.json) records every
path, classification, action, retention reason and reference evidence.

Coverage includes Python source, Django views/URLs/management commands, Next
pages/API routes/proxy, components, utilities, CSS, tests/scenarios, package
manifests, environment examples, CI, Docker/Compose/systemd/release scripts,
documentation, images/fonts/licenses, plugins and agent instructions.

Verification used full-file text/AST inspection; static imports/reexports and
literal dynamic imports; constructed subprocess/module names; Django app,
command and migration discovery; Next App Router conventions; CSS/public URL
references; package scripts and lock consistency; CI/Docker/deployment consumers;
environment variable names, including constructed names; byte hashes; and Git
history for ambiguous historical assets. Images were decoded and inspected;
GIF metadata and a representative frame were inspected, not every animation frame.

Vendor installations, Git internals, generated build/cache directories and private
runtime data were inventoried at their boundaries and excluded from authored-file
reference analysis. Metadata enumeration counted 50,813 files in those excluded
trees at the baseline snapshot; their contents were not treated as deletion
candidates. Private credentials, databases and recovery backups were not read.
The exclusion reasons are included in the inventory. Generated/vendor contents
can change during checks, so this is not a persistent file-count guarantee.

| Classification | Entries | Outcome |
| --- | ---: | --- |
| SAFE TO DELETE | 4 | Three removed; the already ignored TypeScript cache retained because validation recreates it. |
| LIKELY UNUSED — REVIEW | 9 | All retained. |
| REQUIRED | 482 | All retained. |
| UNKNOWN / DO NOT TOUCH | 1 | Browser fallback asset retained; excluded private/runtime regions are separately protected. |

## Files removed — SAFE TO DELETE

| File | Bytes | Verified evidence |
| --- | ---: | --- |
| `.DS_Store` | 6,148 | Finder metadata; no source, framework, script or configuration consumer. |
| `uv.lock` | 628,567 | Ignored with an explicit no-consumer rationale. No `uv sync`, `uv run`, `uv lock` or lockfile consumer exists in source/config/CI/docs. Install/build paths use `pyproject.toml`; stale lock metadata contains removed development extras. |
| `node_modules/.vite/vitest/da39a3ee5e6b4b0d3255bfef95601890afd80709/results.json` | 334 | Old failed Vitest-run cache; the only file in the accidental root `node_modules` tree. Actual dependencies/configuration live under `dashboard/`. |

The now-empty root cache directory chain was removed. Copies of the three files
are available at `/tmp/leadzen-cleanup-audit/removed-backup/` for this local session.
Root `.gitignore` now excludes `.DS_Store` at every level and `/node_modules/`.

`dashboard/tsconfig.tsbuildinfo` also meets SAFE TO DELETE criteria, but it was
already ignored and the required type check/build regenerates it. Retaining this
cache has no effect on committed repository clutter. Active `.next` dev/build
state, installed dependencies and embedding caches were retained.

## Files retained — LIKELY UNUSED — REVIEW

These are whole-file candidates with insufficient evidence for deletion.

| File | Evidence and reason to retain |
| --- | --- |
| `tests/scenarios/preview.py` | Older standalone seeder with no discovered caller; current preview guidance uses `local_preview.py`. Manual invocations and the purpose of this untracked work remain uncertain. |
| `docs/demo.gif` | Legacy upstream terminal demo; only dated inventories currently reference it. Git history proves earlier README use. Historical/provenance value needs review. |
| `docs/logo.png` | Legacy upstream wordmark replaced in the current README. Git history proves earlier use; provenance value remains uncertain. |
| `dashboard/public/favicon.svg` | Current metadata uses the ICO, but proxy configuration still allows this public URL. External/cached consumers are unknown. |
| `dashboard/public/brand/leadzen-logo-light.png` | Superseded in current rendering; public-assets tests and brand documentation preserve this reusable export. |
| `dashboard/public/brand/leadzen-logo-dark.png` | Same public/test/release compatibility evidence as the earlier light wordmark. |
| `dashboard/public/brand/leadzen-by-zyene-light.png` | Current UI uses the approved larger export; brand documentation explicitly preserves this distinct reusable export. |
| `dashboard/public/brand/leadzen-icon-16.png` | No separate metadata use; documented standalone icon family member and public URL. The ICO also contains this resolution. |
| `dashboard/public/brand/leadzen-icon-48.png` | Same reusable-icon/public compatibility evidence as the 16px export. |

The two legacy docs assets alone occupy 7,395,724 bytes (~7.05 MiB). They are the
largest remaining review opportunity, but neither was deleted.

## Files retained — REQUIRED

The inventory supplies individual reasons for all 482 entries. Key groups and
false positives are listed here:

- All active backend modules, settings, registry/model facades, API callbacks,
  console/WSGI entrypoints and workers remain referenced through source, installed
  app configuration, subprocess/module strings or service units. No whole backend
  module or top-level definition was proved dead after resolving these hooks.
- All **21 local migration modules** remain necessary for the complete install/
  upgrade graph. No replacement/squashed chain exists. `leadzen/upgrade.py` remains
  an active, explicitly protected legacy-table/recovery hook.
- All **28 Next route modules**, root layout and proxy are framework entrypoints.
  `/campaigns` and `/sending` are deliberate compatibility redirects with current
  links and potentially persisted URLs. All **58 component modules** and **22
  library modules** are reachable from app entrypoints; no orphan source module or
  unused non-framework export was established.
- Both stylesheets are imported. Of 391 global CSS class names, 384 occur literally
  in runtime source and the other seven are constructed by `crm-${status}` and
  `state-${event.kind}`. All 26 MCP CSS module class names have consumers.
- Pytest and Vitest convention discovery, fixture/setup imports and subprocess
  filename construction retain the test suites and supporting scenarios. The
  loopback TLS proxy supports documented manual production-build validation.
- All three local font files are used by `next/font/local`. Their OFL files remain
  legal notices. Byte-identical Geist/Geist Mono licenses accompany distinct fonts;
  eight identical empty Python package markers serve distinct package/discovery
  paths. These are intentional duplicates, not deletable payloads.
- Manifests, the npm lockfile, TypeScript/Next/PostCSS/Vitest configuration, CI,
  Docker/Compose/systemd/release files and environment examples have active
  conventional or explicit consumers. All environment-example names have source
  consumers; `LEADZEN_{kind}_HOSTS` is constructed dynamically.
- Product/legal docs, current project context, dated audits/releases/screenshots,
  brand masters and reference images retain evidence/provenance value. Historical
  dates do not establish obsolescence.
- The complete daisyUI guide bundle is indexed for per-task agent lookup. The three
  Claude skill symlinks are adapters to canonical instructions, not duplicate files.
  `data/.gitkeep` preserves the ignored runtime directory in Git.

`dashboard/next-env.d.ts` is locally required generated typing input. The build
temporarily changed its generated import paths; its exact pre-build contents were
restored for the existing development preview. Git tracking deserves a separate
review with clean-checkout type-generation order, rather than deleting required
declarations during this cleanup.

## UNKNOWN / DO NOT TOUCH

`dashboard/public/apple-touch-icon.png` is not the current explicitly selected
Apple icon, but its filename is a browser-conventional fallback public URL. Static
imports cannot establish whether legacy or external clients use it.

Private data/environment/recovery state, Vercel project association, installed
vendor trees, active preview/build outputs and downloaded model caches were
retained/excluded with reasons. No live deployment or provider state was inferred
from their names or timestamps.

## Dependencies and additional manual opportunities

**No unused declared Python or dashboard dependency was found. No dependency was
removed.** Django, cryptography, finder/sender, pytz, pytest/pytest-django, gunicorn
and Hatchling have application, test, deployment or packaging consumers. Dashboard
runtime, Markdown, CSS, type and testing packages likewise have consumers.

| Finding | Classification and follow-up |
| --- | --- |
| Installed-only npm packages | UNKNOWN / DO NOT TOUCH: `npm ls` reports extraneous `@emnapi/runtime@1.11.3` and `@img/sharp-wasm32@0.35.5`. They are not unused declared dependencies. Review optional image/WASM install provenance before a future clean install; do not manually prune the current vendor tree. |
| Direct Python imports supplied transitively | REQUIRED: `pydantic`, `pydantic_ai`, `requests`, `openai`, `cohere`, `google.genai`, `httpx` and `httpx2` support active behavior. Review explicit direct requirements/bounds because the manifest comment promises direct-import declarations. |
| `.dockerignore` build-context policy | File REQUIRED; policy LIKELY UNUSED — REVIEW: `COPY . /src` can include frontend/vendor/build caches and private runtime/environment files omitted from current exclusions. Review scope before using Docker; no deployment configuration was changed. |
| Missing `docs/infrastructure.md` references | Text LIKELY UNUSED — REVIEW; files REQUIRED: comments in `Makefile`, `local.yml` and `compose/leadzen/Dockerfile` cite a missing historical document. Align with maintained deployment documentation after confirming the intended workflow. |
| Compose example in `compose/leadzen/start` | Comment LIKELY UNUSED — REVIEW; startup REQUIRED: example uses service `leadzen`, while `local.yml` defines `app`. |
| `.github/FUNDING.yml` sponsor target | Configuration REQUIRED; target LIKELY UNUSED — REVIEW: GitHub conventionally consumes the upstream `eracle` sponsor setting. Confirm intended sponsorship. |
| `skills/find-leads/SKILL.md` installation/cost guidance | Skill REQUIRED; guidance LIKELY UNUSED — REVIEW: registry installation advice conflicts with current private-checkout guidance; “free” qualification language needs alignment with AI cost boundaries. |
| Sixteen screenshots named `.png` with JPEG contents | Evidence REQUIRED; naming LIKELY UNUSED — REVIEW: they decode/render correctly. Exact paths are in the inventory. Any future rename must preserve documentation links. |
| `dashboard/tests/chat-agent.test.tsx:92` callback parameter `init` | Test REQUIRED; parameter LIKELY UNUSED — REVIEW: stricter unused-parameter checking flags this test-only argument. No unused runtime locals/parameters were reported. |
| Generated typing tracking/general lint | Configuration REQUIRED: review ignoring `next-env.d.ts` only after arranging generation before clean-checkout lint. The configured lint script is TypeScript checking; there is no configured general ESLint/Python lint or Python static type-check gate. |
| Machine-specific historical evidence links | History REQUIRED; portability LIKELY UNUSED — REVIEW: local Markdown targets resolve here, but dated `/tmp` or absolute workspace links may not survive another checkout. |

These are review findings, not changes to application behavior or authorization.

## Validation

Baseline: **1,237 backend tests passed** and **1,099 frontend tests passed**;
configured frontend lint/type checking passed. The backend emitted one existing
dependency deprecation warning about event-loop lookup.

Post-cleanup results:

| Check | Result |
| --- | --- |
| Dashboard production build | PASS — optimized Next 16.3.8 build, including TypeScript and prerendering. |
| Dashboard tests | PASS — 20 test files, 1,099 tests. |
| Dashboard lint/type check | PASS — `npm run lint` executes `tsc --noEmit`. |
| Full backend tests | PASS — 1,237 tests in 326.34s; the same existing dependency deprecation warning as baseline. |
| Python syntax/import discovery | PASS — all 135 Python files parse; all 64 Django URL callbacks import. |
| Django system checks | PASS — zero issues, using Django's core check command. |
| Migration consistency | PASS — no model drift; all 46 graph nodes consistent, including dependency migrations. Only disposable test registries were initialized. |
| Next build route coverage | PASS — all 28 source page/API route modules appear in the build manifest; compiled proxy manifest present. |
| Shell/configuration checks | PASS — shell syntax, Makefile build dry-run, JSON/TOML parsing, environment consumers, symlink targets and ignore rules. |
| Work preservation / diff hygiene | PASS — original file hashes unchanged except intended `.gitignore`, the linked current-state update and regenerated ignored TypeScript cache; all preexisting deletions preserved and `git diff --check` passes. |

The finder dependency overrides the management command named `check`; its readiness
command needs provider onboarding settings. Validation explicitly used Django's
core check implementation. An initial lint invocation from the repository root
was rerun from `dashboard/`; the table reports the correct final commands.
No general ESLint/Python lint or Python type-check command exists in this checkout,
so those additional static-analysis gates remain unconfigured, not passed.

No deployment, real email, chargeable provider call, paid provisioning, production
database migration or Git commit was performed. Functional validation is local and
synthetic; static searches cannot prove the absence of external/manual callers.

The audit report and per-file inventory are intentional review deliverables, not
application build output. Detailed worker reports and command logs are retained
outside the repository at `/tmp/leadzen-cleanup-audit/` for this local session.
