# Production completion and controlled-release evidence — October 4, 2026

**Cross-check update:** this report preserves the previous candidate and its
dated evidence. Subsequent verification found and fixed additional release-gate,
advisory, recovery, preflight and monitoring defects. Use the
[production cross-check report](production-crosscheck-2026-10-04.md) for the
current candidate and final verification; do not reuse the older bare PASS
attestations for deployment.

## 1. Production Readiness Status

**NOT READY. Production promotion is blocked.** Durable local controls and fixes
are implemented. Current production configuration, full recovery, real alert
receipt, target-host capacity, enabled integrations and external release controls
are not certified. The automated gate requires evidence for each, rather than
accepting a build as release approval.

Frozen final source: `73eb35d6be24bed880bef74ed1c237b2d649d6985ed8bb2d1753a965c7830af6`. Source archive:
`f69ac6d0ae7ebdebc93998dac20e649d21765cec13cb889f315b45a11991de79`. Linux amd64 image:
`sha256:14e4081f4f84af51b321f6fff75c2451401bc70b0f56ce57d147d7d261b53713`.
The candidate directory and exact wheel/standalone/image-archive and lock checksums
are in verification. A byte-verified durable copy is retained outside the checkout at
`/Users/ashishdikonda/Desktop/Openoutreach/leadzen-release-candidates/73eb35d6be24bed880bef74ed1c237b2d649d6985ed8bb2d1753a965c7830af6`.
This local release copy is not independent production recovery storage. The actual host architecture is **UNVERIFIED**. Fresh final
suites passed **1,475 backend / 1,196 frontend tests**; one existing backend warning.

This continues the [original audit](production-readiness-audit-2026-10-04.md).
Its findings were rechecked against the working tree, migration graph, fresh builds,
actual HTTPS browser execution and available read-only platform metadata. Earlier
reports remain dated evidence. No production deployment/migration, live credential
rotation, history rewrite, real email, paid provider operation, customer-data
mutation or external alert delivery occurred.

The machine-readable completion evidence and release-gate table are in
[verification](production-completion-2026-10-04-verification.json). This report is
not a claim of permanent security.

## 2. Critical Issues Found

| Severity | Finding and disposition |
| --- | --- |
| BLOCKER | HEAD does not contain the application: 360 intended release files are untracked. Whole-working-tree capture and checksum verification now preserve the complete 396-file release; HEAD is provenance only. No unrelated work was reset, staged or discarded. |
| BLOCKER | The current target's environment/schema/storage/private ingress and matched signing/encryption keys remain UNVERIFIED. A fresh Vercel production export lacked the newly required dashboard public-origin variable; an older backend export lacked two required names. The older backend cannot establish today's service-token match. Fail-closed checks reject missing/invalid settings. |
| BLOCKER | A current complete independently protected production recovery set and restore drill are unavailable. The authorized historical archive passed scoped checks but lacks the authentication signing key and does not prove today's full inventory/release/custody. |
| HIGH | The previous deployment procedure could update files/configuration and migrate an unvalidated namespace. It is retired in favor of candidate verification, hard release gates, maintenance holds, complete writer drain and recovery-bound forward migration. Actual cutover remains unauthorized/unverified. |
| HIGH | Scheduler drain could miss a child whose argv ends in `--workspace`, and the scheduler could dispatch between children after a hold. Matching, pass-lock observation and hold checks at entry/between employees are fixed and tested. |
| HIGH | Historical secret material survives Git history. There are 43 real or unresolved exposure locations requiring owner classification and administrative revocation evidence. Source deletion does not revoke a credential. |
| HIGH | The compatible available PCRE2 and vulnerable build-helper updates were applied. Remaining OS HIGH matches require exact risk decisions or compatible patches; the risk-decision file contains no approvals. Full findings are retained. |
| HIGH | No authorized external notification sink receipt, independent monitor-of-monitor coverage, current scheduled backup installation, real provider/client validation or promotion controls are verified. Prepared code/templates alone do not pass these gates. |
| MEDIUM | A denied contact URL first wrote an unverified Chat reference, producing a second API failure. Contact, Inbox and discovery context now wait for authorized returned records; denied refresh clears stale contact data. Five focused UI regressions and real-browser denial checks verify the fix. |
| MEDIUM | The backup bundle needed an explicit way to retain matching dashboard/proxy configuration. Protected-file capture now preserves those bytes privately, detects concurrent changes, rejects unsafe/oversized inputs and restores without executing configuration. Five regressions cover this addition. |
| MEDIUM | Local Mac bind-mounted SQLite isolation produced an I/O error; the same image/scenario passed on a native Docker volume. This is retained as a storage-specific failure, not assumed resolved on the actual host. |
| LOW | React Doctor has retained maintainability/performance warnings and one reviewed security hypothesis; the new context guard adds one Inbox complexity warning. The score did not regress under the same scanner version. No warnings were suppressed. |

## 3. Issues Fixed and Implemented

**Release preservation:** `leadzen.operations.release` captures intended source,
config, assets, dependency locks, tests and all migrations from the working tree.
It excludes credentials, databases, logs, generated/private files and historical
captured browser pages. It rejects unsafe paths, missing files, source drift,
unmanifested inputs and changed artifacts. It records target architecture, source
and archive hashes, lock hashes and exact runtime artifact hashes. Artifacts from
superseded snapshots are retained privately and are not substituted for the final
candidate.

**Configuration:** `leadzen.operations.preflight` validates private environment
ownership, mandatory backend/dashboard names, exact HTTPS origins/allowed hosts,
matching service credentials without printing them, trusted-proxy/private-listener
policy, storage permissions, every initialized server-derived employee namespace,
physical schema/index/FK constraints, integrity and the current migration graph.
It verifies decryption with the existing settings key, including settings,
invitations and mailbox records. Pending migrations remain BLOCKED. Enabled-feature
requirements are explicit; a disabled policy scope does not turn off runtime routes.
Unobserved firewall, mounts and host topology remain explicit limits.

**Maintenance/migrations:** a persistent private hold rejects new API/MCP intake,
prevents new scheduler dispatch and preserves ambiguous external-operation holds.
Drain accounts for requests, streaming, workers and the scheduler pass lock.
Recovery/migration require stopped reviewed writers, empty cgroups and stable
metadata/database versions. Forward migration derives every employee path from
control records, binds the matched recovery set and candidate, and checks schema,
integrity and decryption afterward. It never reverse-migrates or resumes scheduling.

**Recovery:** SQLite backup APIs capture committed WAL state for control and all
initialized employees, including inactive/deleted employees. The protected bundle
contains matching keys/backend environment, dashboard/proxy configuration,
deployed source/runtime artifacts and service definitions. Publication requires a
verified/fsynced copy on a different filesystem. Retention deletes only old complete
owned native copies with verified mirrors, keeps at least two, and preserves
foreign/incomplete/corrupt evidence. Isolated restore requires a new absent target;
provider networking, jobs and subprocess actions are disabled. Drills check
integrity/FKs, record preservation, decryption, authentication/session revocation,
existing routing and two synthetic employee isolation sentinels. Private metadata
is never emitted as an ordinary manifest or log. Remote encryption/custody,
installation and a current actual recovery drill remain operator gates.

**Monitoring:** bounded private probes and journal summaries detect API failures,
latency/authentication spikes, readiness/database failures, SQLite locks, disk/Linux
memory pressure, failed/stale jobs, scheduler silence and verified backup/mirror
freshness. Missing/saturated evidence is visible. Delivery uses bounded verified
HTTPS, public-address pinning, safe fixed categories, deduplication and a hard
child deadline. Default configuration cannot contact an external sink. A local
synthetic alarm receipt and dedup test passed; real delivery is BLOCKED.

**Dependencies/CI:** hash-locked runtime and build environments are separate.
The patched pinned Python 3.12.15 trixie image runs as UID 1000 without pip, pytest
or lint tooling. Gitleaks scans current source/new Git history with complete
redaction. Trivy retains full advisory output, with exact package/version/architecture,
reviewer, evidence and expiry required for risk acceptance. CI prepares backend,
frontend, trusted-browser and security jobs before publishing the scanned image.
No blanket ignore-unfixed rule, disabled test or approved risk waiver was added.
Actual repository/platform promotion enforcement remains UNVERIFIED.

**Browser/capacity:** the trusted HTTPS synthetic staging runner rejects inherited
provider credentials, invalid TLS, candidate drift and unguarded provider actions.
The five CI browser scenarios cover headers, auth, CRUD, settings/mobile,
invitation/onboarding and password revocation. Manual browser execution found and
verified the canonical-context fix. A bounded production Gunicorn/SQLite workload
uses real private employee databases, concurrent reads/writes and post-run
integrity checks; it reports actual-host certification separately.


**Before / After / Why:** the previous contact detail page recorded the requested
URL ID before an owned API record loaded and could retain stale detail after a
failed refresh. The updated contact/Inbox/discovery pages record only authorized
returned IDs, and stale contact data is cleared. This removes avoidable 400s and
prevents Chat from inheriting unverified references while preserving server-side
ownership enforcement. Focused component regressions, unchanged-frontend-source
comparison and actual final-artifact browser denial evidence cover the change.
Synthetic screenshots are under `docs/ui-progress-assets/`; viewport overrides
are reset after capture. Full password/setup/consent and broad visual/a11y coverage
remain explicit browser-gate limits, rather than assumed passes.

## 4. Remaining Issues and Release Gates

| Gate | Status | Evidence | Remaining action |
| --- | --- | --- | --- |
| preflight | **FAIL** | Fresh Vercel production export lacks LEADZEN_DASHBOARD_PUBLIC_URL; current VM settings/key/token/schema/storage unavailable. Older backend export is dated evidence. | Current private host/env/schema/ingress observations and no-secret preflight. |
| secret_current | **PASS** | Gitleaks 100% redaction: zero findings in exact frozen source archive; private env/cache/database files excluded. | Continue enforced new-change scanning; historical disposition remains separate. |
| credential_disposition | **BLOCKED** | 43 real/unresolved historical exposure locations; owners/revocation unverified. Questionable credentials were not used. | Owner classification and administrative revocation/session-termination receipts. |
| backend_tests | **PASS** | Fresh hashed build/runtime and installed wheel: 1475 passed, one existing PydanticAI deprecation warning. | No local suite failure remains. |
| frontend_tests | **PASS** | Fresh npm ci: 1196 tests in 26 files passed, including five new canonical-context cases. | Full browser gate has separate unperformed steps. |
| typecheck | **PASS** | npm run lint runs tsc --noEmit; fatal Python Ruff checks passed. | No general ESLint or Python static typing certification claimed. |
| dependency_audit | **PASS** | Current advisory feeds: 94 runtime and 7 builder Python packages, plus npm, zero known package advisories. | OS image findings have a separate FAIL gate. |
| image_advisories | **FAIL** | Exact final amd64 image: 0 CRITICAL, 44 HIGH, 61 MEDIUM, 60 LOW, 2 UNKNOWN; no risk acceptances. | Compatible tested patches/base or exact expiring owner-reviewed decisions for every HIGH/CRITICAL match. |
| production_build | **PASS** | Clean wheel, optimized standalone dashboard and Linux amd64 image built; exact three artifact hashes verified. | Actual Vercel/prebuilt artifact and Node version reconciliation remain external gates. |
| migrations | **BLOCKED** | Final image clean/prior schema preservation/integrity/FKs/drift passed locally; current production DB graph unavailable. | Current read-only whole-namespace schema evidence, matched recovery set and exact forward-migration authorization. |
| startup | **PASS** | Final image UID 1000, no pip/pytest/ruff, missing settings fail closed; real Gunicorn synthetic readiness and standalone trusted HTTPS succeed. | Actual host startup/configuration remains within blocked preflight/target gates. |
| browser | **BLOCKED** | Final trusted-browser subset passed: login/logout, themes, CRUD, settings, employee denial, focus/mobile/console/network; HTTP cookies/CSRF/nonce headers verified. | User handoff/full controlled runner for invitation/new passwords/onboarding; live-client consent and active CSP attack probes remain unperformed. |
| actual_recovery | **BLOCKED** | Synthetic native backup/restore/drill tests and authorized historical control+one employee drill passed. History lacks signing key/current full deployment/custody. | Current authorized matched full production recovery set, independent protected storage and isolated drill. |
| alert_delivery | **BLOCKED** | One local synthetic alarm receipt/dedup and timeout/redaction tests passed; no external sink contacted. | Exact authorized destination/on-call owner, bounded alarm receipt, independent monitor-of-monitor installation. |
| target_capacity | **BLOCKED** | Final local native-volume amd64 test: 20000 contacts/4 employees, 256 requests/32 writes at concurrency16, zero errors, p95 633 ms; integrity intact. | Approved budgets and isolated measurement on intended CPU/RAM/storage/ingress; production filesystem unverified. |
| enabled_integrations | **BLOCKED** | Real SDK/transport/MCP approval/STOP/duplicate/uncertainty regressions passed; provider-disabled fixture made zero external calls. | Exact enabled feature scope, private accounts, named recipients/clients and bounded send/spend/consent authorization. |
| external_release_controls | **BLOCKED** | Read-only upstream access lacks push/admin; protection 404/rulesets do not prove enforcement. Vercel Node24.x vs tested22.23.1; promotion checks not established. | Owning repository/platform admin evidence, required checks and exact tested Vercel artifact/promotion controls. |

The verification JSON retains command/results and hashes. PASS means
only the stated tested scope. A synthetic or earlier historical pass does not close
a current production gate. Both the actual release CLI and historical deployment wrapper were exercised
against this candidate: each returned **exit 2 / BLOCKED**, with ten not-passed
gates and no missing gate names. No deployment occurred. See [gate evidence](production-completion-release-gate-2026-10-04.json).

Concrete remaining requirements are:

1. Current VM read-only access and owning platform/repository access: inspect actual
   architecture, persistent filesystem, ownership, loaded units/children, firewall,
   proxy/listeners, service environment and complete account-derived DB inventory.
   Verify current service-token equality and preserve both stable keys. The available
   export did not provide a usable exact HTTPS origin for a bounded direct check;
   no request/token transmission occurred. Current service behavior remains
   **UNVERIFIED**, rather than a claimed endpoint failure.
2. A release/maintenance authorization for the reviewed target, current recovery
   manifest/artifacts/configuration and independently protected storage. Create and
   drill a fresh full recovery set before migrations. Review the backup timer's
   staffed maintenance/resumption requirement; it intentionally leaves intake held.
3. Credential owners' classifications/revocation receipts for the redacted historic
   findings. Revoke reusable secrets/sessions only under exact authorization; do
   not probe them against providers or casually replace the settings key.
4. An OS risk owner: compatible tested patches/base update or exact expiring
   dispositions for every HIGH/CRITICAL match. Installed-package reachability
   observations limit some findings but do not constitute accepted risk.
5. A user-controlled full browser workflow run or supported user handoff for new
   password entry and binding authorization steps. The browser control policy says:
   “Changing a password or other authentication credential: Ask the user to take
   over before any new credential is entered.” This is in the Browser capability
   documentation loaded through [the Browser skill](/Users/ashishdikonda/.codex/plugins/cache/openai-bundled/browser/26.930.21537/skills/control-in-app-browser/SKILL.md),
   not an inferred project restriction. Missing steps stay BLOCKED. Do not bypass
   certificate errors or switch browser tooling to evade that requirement.
6. Exact approved notification destination/on-call owner plus one bounded alarm
   test and confirmed receipt. Configure independent missed-heartbeat monitoring.
7. Intended-host load budgets and an authorized isolated workload on its actual
   filesystem/CPU/RAM/proxy. Local emulation does not certify the documented small VM,
   SSE/polling load, 80-second dashboard request budget or production storage.
8. Enabled integration scope and exact recipients/providers/models/credit/cost caps
   for the prepared checks in [integration instructions](production-integrations.md).
   Genuine MCP consent/refresh/revoke must use the selected real client and
   disposable employee. No real provider operation is implied by this report.
9. Owning repository required-check/branch protection and Vercel promotion evidence.
   Read-only upstream metadata shows no write/admin access. An empty ruleset list
   and a protection 404 are not proof of protection status. The Vercel snapshot
   reports Node 24.x while local verification uses Node 22.23.1, automatic Git deploys
   and production fast lane; required promotion checks were not established.
   Test the exact selected Vercel/prebuilt artifact and reconcile runtime versions
   before preparing a production promotion command.

## 5. Security Review

Authentication is invitation-based employee access. Password validators/hashers,
single-use invitation setup, hashed opaque sessions, expiry/revocation and account
state are tested. There is no public signup, unrelated social OAuth/account linking,
MFA/SSO or self-service forgot-password feature; these are explicit product absences.
MCP tests cover exact redirect/resource, S256 PKCE, hashed tokens, rotating refresh,
replay-family revocation, live actor/grant checks and consent failures. A genuine
external client remains unverified.

The server derives employee UUID/database paths and resolves IDs inside the owned
namespace. Staff features check current privilege, and workers recheck authorization
at external sinks. Overlapping IDs, forged selectors, private settings/exports,
Chat/drafts/runs, revoked workers and Inbox ownership have regressions and Linux
integration checks. Frontend context is a convenience reference, never authorization.
Host administrator/storage access is a separate unverified boundary.

API method/schema/body/pagination/origin/timeout/error protections, scoped CORS,
server-only service credentials, CSRF, no-store caching, secure HttpOnly SameSite
cookies and nonce CSP are retained. Current release-source scanning has no secret
findings; historical disposition is separate. Production logging tests enforce safe
categories without tokens, cookies, provider bodies, passwords or personal data.
Generated framework preview/RSC cache capabilities were identified in an accidental
post-build scan, preserved privately and confirmed absent from deployable source
and standalone cache paths; they were not reclassified as revoked provider keys.

Paid AI/enrichment and sending preserve approvals, STOP suppression, duplicate-send
protection and uncertain-operation holds. No customer Stripe/subscription/webhook
system exists. Synthetic transport success does not certify provider acceptance,
billing, inbox delivery or real client behavior.

## 6. Database/Migration Review

The inspected graph ends at config `0019_discoverylookup_source_index` and accounts
`0004_accountprofile_tour_state`, with dependency-app leaves derived dynamically.
Clean and previous-release upgrade tests verify preserved account/tour, config,
contact/deal relationships and time metadata, no migration drift, WAL and synchronous
FULL, integrity and foreign keys. Whole-namespace migration/preflight checks cover
all initialized employee DBs; they do not trust browser IDs or shell wildcards.

Migration 0018 normalizes schedule metadata and is not safely undone through a
schema-only reverse migration. Rollback must retain forward-schema compatibility
or coordinate a complete verified recovery set and reconcile later writes/effects.
Current production graph/schema and original encryption compatibility remain
UNVERIFIED until current read-only host evidence and the matched drill exist.

The historical Oct 3 control-plus-one-employee archive passed minimally revealing
integrity/relationships/decryption checks and an isolated current-schema/auth/isolation
drill. It lacks the signing key and current complete deployment inventory. See
[historical evidence](production-historical-recovery-validation-2026-10-04.json).

## 7. Infrastructure/Deployment Review

Deployment architecture is preserved: private single-host backend with persistent
SQLite, Vercel dashboard. The final candidate is a whole-source snapshot, not a
commit claim. Test/build/artifact identities, target architecture and exact commands
are recorded in verification. Immutable outputs are privately retained outside
this checkout; secrets, databases and recovery bundles remain excluded.

The release wrapper verifies only; it cannot deploy when a gate is incomplete.
Systemd backup/monitor templates are prepared and uninstalled. Persistent-storage,
independent custody, service hardening, proxy limits, host architecture, actual CI
required checks and Vercel promotion are explicit operator gates.

## 8. Tests Performed

Exact commands, exit/status, counts, candidate binding, artifact hashes and evidence
file checksums are in [verification](production-completion-2026-10-04-verification.json).
The final clean sequence includes hash-locked Python build/runtime installation,
full backend tests, npm ci, TypeScript, full frontend tests, npm/Python advisory
checks, optimized standalone build, target-architecture Docker build/full scan,
non-root runtime/fail-closed startup, migration/integrity/isolation scenarios,
bounded Gunicorn capacity, source secret scan, shell/Compose validation and
source/artifact checksum verification. Browser runs use trusted HTTPS. The final native-volume capacity samples both
returned 256/256 HTTP 200s and intact integrity: p95 837 ms and 633 ms; the latter
uses the exact retained bootstrap command. These are local samples, not production
SLO approval. Browser event retention truncated the earlier network window; the
fresh isolation window was complete and showed only the expected 404 plus successful
context writes. The later bounded console sample contained no warnings/errors;
whole-session console/network retention is **UNVERIFIED**. Seven canceled navigation
requests in the later network window are retained explicitly.

Compared with the original 1,387-backend/1,191-frontend baseline, release/operations,
provider-stream/drain/recovery and five context regressions add coverage. No test was
weakened to conceal a product failure. SSE fixtures now tolerate the specified
20-second transport rotation while still failing unexpected early closure, and
explicit rotation/expiry cases exercise the real provider SDK formats.

Intermediate failures are retained: one earlier real-SDK stream timing failure,
a recovery fixture password similar to a random UUID, an initial capacity PUT/POST
harness mismatch, scanner startup/cache/image-order mistakes, generated Next cache
secret findings outside frozen release input, fixture Host/peer-file configuration
errors, the Mac SQLite I/O failure, and an overstrict ad hoc HSTS subdomain assertion.
Corrections distinguish harness assumptions from actual application fixes. Current
HSTS is a one-year policy; subdomain/preload coverage was not asserted. Native
Docker-volume isolation passed; actual production filesystem behavior remains blocked.

## 9. Production Environment Variables Required

Names only; purpose and required/conditional/optional/injected classifications are
in [environment documentation](production-environment.md). Backend required:

```text
LEADZEN_ENV
LEADZEN_DB
LEADZEN_WORKSPACE_ROOT
LEADZEN_SETTINGS_KEY
LEADZEN_SECRET_KEY
LEADZEN_DASHBOARD_TOKEN
LEADZEN_ALLOWED_HOSTS
LEADZEN_PUBLIC_URL
LEADZEN_DASHBOARD_ORIGINS
```

Dashboard required:

```text
LEADZEN_API_URL
LEADZEN_API_TOKEN
LEADZEN_DASHBOARD_PUBLIC_URL
```

Conditional feature inputs:

```text
LEADZEN_RESEND_API_KEY
LEADZEN_INVITATION_FROM
LEADZEN_MCP_PUBLIC_URL
```

Optional runtime controls:

```text
LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED
LEADZEN_AUTOPILOT_ENABLED
LEADZEN_LLM_HOSTS
LEADZEN_MAIL_HOSTS
LEADZEN_EMAIL_HOSTS
LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS
```

`NODE_ENV` is host-injected in production. Per-employee provider credentials remain
server-side encrypted settings. Worker/test identity variables are injected internally.
Operations-template path/owner variables are conditional and documented separately;
none belongs in a browser/public variable. Preserve `LEADZEN_SETTINGS_KEY`; neither
historical credential remediation nor auth-key configuration authorizes replacing it.

## 10. Deployment Checklist

Follow the [controlled release runbook](production-release.md), which contains exact
prepared verification/hold/drain/recovery/restore/forward-migration commands and
makes unobserved runtime/Vercel cutover explicit:

1. Resolve every material gate; select and verify the frozen source and tested
   wheel/standalone/image. Never deploy old HEAD or rebuild during promotion.
2. Verify current environment, exact origins/private boundaries, stable keys,
   ownership/storage and whole-employee schema/inventory against actual host evidence.
3. Under exact maintenance authorization, hold API/MCP intake and scheduling, drain
   all workers/requests and scheduler passes; preserve ambiguous operations.
4. Stop only reviewed writer units after drain. Capture current deployed source,
   runtime, backend/dashboard environment, proxy/services, both keys and all DBs.
   Verify independent protected copy and isolated restore/drill before any migration.
5. Stage a new immutable runtime. Plan then apply whole-namespace forward migrations
   only with the matched verified recovery set and held/stopped writers.
6. Recheck physical schema/integrity/decryption and private readiness. Exercise the
   exact isolated provider-disabled candidate's auth/CRUD/isolation/browser flows;
   held production intentionally returns 503 for ordinary routes.
7. Verify selected host/Vercel artifacts and promotion controls, then request the
   exact deployment action. Runtime-pointer/Vercel cutover commands cannot be safely
   invented without current target inventory and remain BLOCKED.
8. Promote only under that authorization. Reconcile unknown/accepted external
   effects before opening intake. Resume scheduling only with separate confirmed
   authorization. Verify real monitoring/backup installation and observe agreed
   latency/error/lock/resource budgets.

## 11. Rollback Checklist

1. Hold intake/schedulers/MCP and conservatively drain; preserve logs and a fresh
   consistent incident snapshot without killing ambiguous provider work.
2. For a frontend-only issue, select the previous immutable compatible frontend;
   do not restore databases for a UI rollback.
3. For a backend issue, use the recorded previous runtime only after proving its
   forward-schema compatibility. Do not run destructive reverse migrations.
4. If coordinated data recovery is required, verify both copies of the complete
   matched control-plus-every-employee recovery set. Restore into a new absent
   isolated directory, preserving matching keys/environment/runtime/services/proxy.
   Run integrity/FK/preservation/decryption/auth/routing/isolation drills with
   outbound actions disabled. Never overwrite live files or restore one DB alone.
5. Reconcile legitimate post-backup writes and external acceptance/usage before an
   operator selects a coordinated data/runtime cutover. Exact pointer/platform
   commands require the current target inventory; no production rollback was tested
   or performed here.
6. Verify readiness/auth/isolation, reopen only authorized intake, resume scheduling
   only after reconciliation, and retain incident/recovery evidence privately.

## 12. Final Verdict

**I do not approve this candidate for production deployment with real customer data.**
The locally implemented controls and verified fixes materially improve release and
recovery safety. The exact final candidate and completed local results are identified
in verification; the remaining gates require the concrete access, authorizations,
provider/client/alert receipts and operator risk decisions listed above. No skipped,
simulated, historical or inaccessible check is counted as a production pass.
