# Focused repository maintenance — October 4, 2026

Confirmed Docker context gaps, implicit Python dependency contracts and stale
Docker documentation/examples are fixed. Seven existing files changed; application
logic, migrations, frontend manifests/lock, the original installed environments,
all nine uncertain cleanup candidates and all 19 preexisting deletions are preserved.
No deployment or commit was performed.

The [focused patch](repository-maintenance-followup-2026-10-04.patch) compares this
task with the **initial dirty working tree**, not Git HEAD. It excludes unrelated
prior work. Exact pre-edit file backups and detailed logs are in
`/tmp/leadzen-maintenance-followup/` for this local session. This report, patch and
linked current-state note are the intentional maintenance documentation outputs.

## Focused changes

| File | Change |
| --- | --- |
| `.dockerignore` | Exclude root/nested private environment variants, runtime data/media, SQLite/database sidecars and recovery copies, backup directories, logs, vendor environments, caches, coverage and generated build/package output. Retain safe `.env.example` and `*.env.example` templates; preserve source, migrations, package/legal metadata and Compose runtime helpers. |
| `pyproject.toml` | Add 11 explicit schema, agent, SDK and HTTP transport declarations with bounds anchored to existing tested versions. Preserve exact finder/sender pins and every existing dependency bound/extra. |
| `Makefile` | Replace the nonexistent infrastructure documentation reference with `docs/docker.md`; executable rules unchanged. |
| `local.yml` | Correct the documentation reference and bounded-CLI description; resolved Compose configuration unchanged. |
| `compose/leadzen/Dockerfile` | Correct checkout-install/Docker-guide comments; image instructions unchanged. |
| `compose/leadzen/start` | Correct the example to `docker compose -f local.yml run --rm app 10 emails`; executable content unchanged. |
| `docs/docker.md` | Describe context exclusions and runtime inputs; document the actual `app` service and provider-env delivery. The installed Compose 2.39.1 supports `--env-from-file`; plain Compose `--env-file` is interpolation input, not blanket container environment injection. |

Private environment/database/backup contents were not read or printed. Docker
context verification used synthetic sentinels, not real credentials or customer
records. No repository files were deleted in this follow-up.

## Dependency decisions

The application directly imports `pydantic`, `pydantic_ai`, `requests`, OpenAI,
Cohere and Google GenAI; it also dynamically selects two HTTP transports and six
SDK provider families. The pinned children already request the same slim Pydantic
AI distribution/provider extras. Declaring these contracts here avoids relying on
undocumented transitive availability.

| Added requirement | Why required |
| --- | --- |
| `pydantic>=2.13.5,<2.14` | Chat/outreach/MCP schema and validation APIs. |
| `pydantic-ai-slim[anthropic,cohere,google,groq,mistral,openai]>=2.52.0,<2.53` | Direct agent usage and dynamically imported supported model/provider adapters. |
| `requests>=2.34.2,<2.35` | Actual `Response` construction in the pinned BetterContact request adapter. |
| `openai>=3.22.1,<3.23` | Direct `AsyncOpenAI` custom-client construction. |
| `cohere>=7.2.0,<7.3` | Direct `AsyncClientV2` custom-client construction. |
| `google-genai>=2.26.0,<2.27` | Direct `HttpRetryOptions` and Google provider integration. |
| `anthropic>=1.11.0,<1.12` | Supported dynamic SDK; preserve tested modern HTTP client contract. |
| `groq>=1.7.0,<1.8` | Supported dynamic SDK; preserve tested legacy HTTP client contract. |
| `mistralai>=3.0.0,<3.1` | Supported dynamic SDK; preserve tested modern HTTP client contract. |
| `httpx>=0.28.1,<0.29` | Explicit legacy transport used by Groq/Cohere. |
| `httpx2>=2.13.1,<2.14` | Explicit modern transport used by OpenAI/Anthropic/Google/Mistral. |

Bounds allow compatible patch updates while excluding the next minor series.
They use versions whose SDK/client interfaces were inspected and tested, rather
than guessing older compatible releases. The original environment was not
upgraded. All 16 final runtime declarations accept its installed versions; all
103 active metadata requirements checked for the added packages and pinned
children are satisfied. Existing child provider extras, including Bedrock, remain
in the dependency union.

The two HTTP families are intentional: substituting `httpx2` everywhere would
violate the current Groq/Cohere constructor contracts. Dynamic SDK bounds are
justified by these explicit provider/transport choices, even where SDK imports
are performed by the Pydantic AI adapter.

## Disposable validation

The snapshot at `/tmp/leadzen-maintenance-followup/current-tree` was copied from
the actual filesystem, including current untracked source/assets/instructions and
relative skill symlinks. It contains **494 copied entries**; no Git archive/reset
was used. Private runtime/env data, installed dependencies and generated caches
were omitted. All nine uncertain candidates were explicitly checked for presence;
all 19 preexisting deleted paths remain absent in both the original and copy.

Fresh host Python installation used an empty virtual environment, public PyPI,
fresh package downloads and a constraint file containing only the original
installed package names/versions. Constraints select versions, not undeclared
packages. It installed **100 distributions with zero version changes**, then
passed `uv pip check`. This prevents unrelated dependency upgrades during the
host regression run. The actual Dockerfile additionally installed `/src[web]`
without that test constraint file, validating its normal Linux resolution path.

Fresh frontend installation used the existing npm lockfile, an empty vendor tree,
isolated npm config/cache and public registry. App/provider/cloud configuration was
absent, telemetry was disabled, and Next type generation preceded lint because
the copied generated declaration file initially referenced the omitted dev cache.
This regeneration occurred only in the disposable copy.

| Check | Result |
| --- | --- |
| Real Docker BuildKit context export | PASS — 37 private/cache/vendor/database sentinels excluded; all 98 required source/template/metadata inputs present. |
| Independent ignore-rule cross-check | PASS — 235 cases, including 134 actual Python source/test/migration paths; 65 original exclusion gaps confirmed. |
| Fresh Python install + dependency consistency | PASS — 100 distributions; zero unrelated version changes; `uv pip check` passes. |
| Python source distribution and wheel build | PASS — wheel built from the sdist; all 84 backend source/migration files present, required legal/metadata inputs present, console entrypoint/extras correct, no private DB/env/bytecode wheel members. |
| Python 3.11 Linux x86_64 resolution | PASS — dev/web extras resolve to 99 packages from public PyPI. All 11 additions resolve to tested versions; NumPy/SciPy select older interpreter-compatible releases. Resolution only, not Python 3.11 execution. |
| Focused original-environment provider tests | PASS — 21 synthetic tests, all seven provider variants and both HTTP transports. |
| Full fresh-host backend tests | PASS — 1,237 tests in 369.04s; one existing Pydantic AI event-loop deprecation warning. |
| Fresh-host Django/migration/route/CLI checks | PASS — zero Django issues, no model drift, 46 consistent migration nodes, 64 importable callbacks and installed console-script help. Only disposable test registries were initialized. |
| Uncached Docker image build | PASS — unchanged Docker instructions with updated manifest/context; Linux ARM64 Python 3.12 image, fresh `/src[web]` dependency install. |
| Installed Docker runtime smoke | PASS — networking disabled, package imported from `/opt/venv`; zero Django check issues, disposable migrations/no drift, 46 consistent migration nodes, 64 importable callbacks and seven provider variants constructed with socket connections forbidden. All 15 checked core runtime dependency versions match the original environment. |
| Fresh `npm ci` | PASS — 229 packages; all 16 direct dependencies match unchanged lock versions. |
| Fresh Next type generation + configured lint | PASS — `next typegen`, then `tsc --noEmit`. |
| Fresh frontend tests | PASS — 1,099 tests across 20 files. |
| Fresh production frontend build | PASS — all 28 source routes, Proxy and standalone server present. |
| Compose/shell/Makefile checks | PASS — Compose config without private env loading; before/after resolved models identical; shell syntax and `make -n build`. |
| Focused patch / preservation | PASS — reverse-apply check and diff whitespace pass; original source/environment versions unchanged outside the seven focused files and intentional maintenance documentation. All uncertain candidates/deletions preserved. |

Fresh npm installation reproduces the two earlier “extraneous” WASM entries
(`@emnapi/runtime` and `@img/sharp-wasm32`). Both are locked optional Sharp
transitives, not evidence of stale original-install debris. Dependency listing
exits zero; no vendor package or lock entry was pruned.

## Remaining limits and separate follow-up

**No remaining blocker.** The existing Pydantic AI event-loop deprecation warning
remains; the focused changes introduce no new test failures.
Python 3.11 was checked by dependency resolution, while executed host/container
checks use Python 3.12. Live provider credentials, billing, mail delivery and
deployment behavior remain outside this local synthetic maintenance validation.
The Compose environment-file option was verified against the locally installed
2.39.1 CLI; no remote installation was changed or inspected.

General lint is a **separate proposed change**: add scoped ESLint and Ruff checks,
first recording existing diagnostics and then selecting rules/CI gates. Preserve
the current TypeScript gate and avoid broad formatting or automatic rewrites.
No new lint dependency, formatting change or lint configuration was added here.

No production databases, live services, provider actions, paid resources, package
publishing or Git commits were involved. Detailed dependency, copy-integrity,
Docker, package, Python 3.11 and frontend evidence/logs are retained under the
temporary validation directory above. The image built by this task was removed
after its successful smoke check; no Docker build cache or unrelated image was
pruned. The disposable source/dependency copy remains available for review.
