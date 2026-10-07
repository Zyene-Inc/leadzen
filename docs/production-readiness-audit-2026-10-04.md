# LeadZen production-readiness audit — October 4, 2026

## 1. Production Readiness Status

**NOT READY for approval of this exact working-tree release for real customer data.** Substantial local fixes and successful production simulations improve the application, but the release gates below remain unresolved or **UNVERIFIED**. A passing build is not deployment approval.

The audit covers the current working tree, including the substantial preexisting uncommitted/untracked `leadzen/`, dashboard, tests and deployment files. HEAD does not represent this application. No reset, stash, commit, push, deployment, real email, paid provider operation, production migration or production-data modification was performed. All mutation and failure-injection tests used disposable synthetic databases/adapters. Existing unrelated previews were preserved.

The [coverage ledger](production-audit-2026-10-04-coverage.json) distinguishes manual source inspection, reviewed test contracts, executed tests, static assets, historical evidence and excluded generated/private runtime data. The final ledger inventories **555 repository paths**. At consolidation it accounted for **252 runtime/release inputs**: 211 source/build-source paths, 21 configuration/deployment/dependency inputs and 20 static assets/font licenses; **zero unreviewed runtime inputs**. Historical documents/vendor agent instructions/screenshots were inventoried and text secret-scanned where applicable; exhaustive manual review of their historical prose or binary image contents is not claimed. Installed dependencies were audited as dependencies, not represented as manually reviewed vendor source.

Detailed scope reports: [backend security](production-audit-2026-10-04-backend-security.md), [domain/database/jobs/providers](production-audit-2026-10-04-jobs-data.md), [frontend](production-audit-2026-10-04-frontend.md). They include per-file ledgers, reproductions, exact focused commands and test limitations.

## 2. Critical Issues Found

Severity describes release impact; an **UNVERIFIED** gate is explicitly distinguished from a demonstrated vulnerability.

| Severity | Finding | Disposition |
| --- | --- | --- |
| BLOCKER / UNVERIFIED | Current production configuration, matching backend/frontend secrets, stable encryption-key recovery, every initialized employee schema, and release artifact completeness have not been verified for this source. New fail-closed startup requirements can reject the previous environment. | Manual release preflight required. October 3 deployment records are dated evidence, not proof of today's state. |
| BLOCKER / UNVERIFIED | Final frontend has not been exercised in a real browser with trusted HTTPS. Local certificate rejection prevented hydration, actual CSP execution, console/network, responsive and assistive-technology checks. | Run the browser release gate on trusted staging HTTPS before real users. HTTP and component tests passed. |
| HIGH | Password/login writes reused previously authenticated stale User objects. Concurrent password reset/disable/revoke could create an old-password session or overwrite account disable state. | Fixed; deterministic race regressions reproduce the prior failures. |
| HIGH | Invitation delivery held the shared control-database write transaction during external email I/O. A slow provider could block employee authentication writes. | Fixed; commit capability before I/O, recheck live authority, persist delivery outcome afterward. |
| HIGH | Backend dashboard fetch followed redirects while forwarding private session/service headers. | Fixed; redirects rejected, exact production HTTPS origin enforced. |
| HIGH | Authentication/proxy request bodies were buffered before size enforcement, with inconsistent byte/deadline handling. | Fixed; bounded incremental reads, strict UTF-8, deadlines and safe status codes. Ingress limits remain required. |
| HIGH | OAuth cleanup hid still-live MCP connections and discarded consumed-code replay evidence. | Fixed; retain records associated with live grants. |
| HIGH | Exact STOP handling only scanned the first 500 emailed contacts; manual cold campaigns lacked address-level attempt deduplication at the external sink. | Fixed; scalable complete suppression and preclaim/final-boundary duplicate checks. |
| HIGH | Direct/legacy email API callers could bypass the configured approved-host boundary. | Fixed; revalidate destination and body size at the final network sink. |
| HIGH | Vendor/provider logs could persist credentials, recipient identities, message text and raw exceptions. | Fixed for new production dependency records; historical logs/unknown rotated secrets remain UNVERIFIED. |
| HIGH | Bounded Docker discovery commands had an automatic restart policy that could repeat paid work. | Fixed; restart disabled for that bounded CLI service. |
| HIGH | Release worker guard omitted MCP workers and general scheduler commands, allowing a backup/migration race. | Fixed; all current worker/scheduler module commands included. |
| HIGH | Production SQLite used WAL `synchronous=NORMAL`, which can lose recently acknowledged transactions after host power loss. | Fixed; production uses FULL, verified against actual SQLite connections. Disk/storage guarantees still require host verification. |
| HIGH / UNVERIFIED | Git history retains browser fixture token/PII material and Chromium provider credentials. Current credential ownership, validity and revocation are unknown. | Private security follow-up required; current text scan clean. No history rewrite or unapproved credential use/rotation. |
| HIGH / UNVERIFIED | Current automated backups, independent recovery copy, complete restore drill, alert routing and scheduler watchdog have not been established. | Required operational release evidence; a workspace export and static health response are insufficient. |
| HIGH / UNVERIFIED | Real invitation delivery, approved provider billing/limits, SMTP/IMAP delivery/replies, sender-domain authentication and actual remote MCP client behavior are untested in this audit. | Separately authorized staging/live checks required for enabled features. |
| MEDIUM | Partial/stale settings saves overwrote unrelated values; legacy plaintext/stale environment credentials persisted; worker adapter ordering double-encrypted mailbox passwords. | Fixed in new saves/exports; existing rows/backups require counts-only inspection and approved remediation. |
| MEDIUM | Trickling provider bodies could outlive budgets; child process failures were hidden. | Fixed body deadlines/size limits and safe ERROR summaries; adversarial DNS/TLS/header stalls and alert delivery UNVERIFIED. |
| MEDIUM | Non-ASCII authorization and deeply nested JSON could produce 500s; saved job output could disclose old provider keys. | Fixed safe 401/400 handling and output redaction. Historical raw records retained. |
| MEDIUM | CRM page/query growth, full-pool outreach selection, missing lookup index and overlapping frontend polling increased production load. | Fixed major hotspots; realistic load/capacity is UNVERIFIED. |
| MEDIUM | Missing nonce CSP/private error-cache headers, insufficient explicit frontend production origin, short route duration and absent DB readiness/request outcomes weakened release behavior. | Fixed headers/origin/budgets/readiness/safe request logging; actual hosting limits and alerts remain UNVERIFIED. |
| MEDIUM | Container retains Debian advisories without a fixed Bookworm package version. | Available PCRE update applied; unused pip removed. Remaining reachability assessment below; not a demonstrated application exploit. |
| MEDIUM | `npm run lint` is TypeScript only; no general ESLint configuration or full Python type-check gate exists. | Explicit tooling limitation. Type checks and selected fatal Python static checks passed; no claim of full semantic lint/type certification. |
| LOW | Node engine metadata did not meet the locked test runner minimum; one installed Pydantic graph event-loop deprecation warning persists. | Node metadata fixed; warning retained and reported. |

## 3. Issues Fixed

The changes preserve Workspace/Chat shared records, employee database isolation, intended CLI behavior, exact send/spend approval and uncertain-operation holds. No unrelated redesign or destructive migration was added.

- **Accounts/MCP:** revalidate live account/session/password state inside critical control transactions; move invitation network I/O outside the write lock; retain live grant consent/replay evidence. Password hashes and opaque token hashes remain server-side.
- **Settings/secrets:** merge omitted fields under the workspace transaction; submit only the edited frontend section; enforce boolean credential clear flags; clear supported plaintext shadow copies and stale child exports; correct mailbox field-adapter double encryption. Existing encrypted/plaintext production rows are not silently rewritten.
- **API/transport:** bounded frontend request streams; reject redirects carrying private headers; compare authentication bytes safely; handle recursive JSON; redact saved job output before truncation; validate email destination/payload at the actual sink; enforce response body deadlines including detached sockets.
- **Delivery/jobs:** process exact STOP replies beyond the first 500 contacts; deduplicate manual cold initial attempts by address at preview, claim and transport boundaries; retain existing opted-in/transactional/Autopilot semantics; expose generic nonzero/timeout job failures; prevent automatic restarts of bounded paid CLI passes.
- **Database/performance:** batch CRM page facts; use SQL `Exists`/count/LIMIT for eligibility; add config migration `0019_discoverylookup_source_index`; use FULL WAL durability in production; refuse legacy rename when its reserved recovery copy is empty, corrupt or missing old tables.
- **Frontend/runtime:** nonce CSP and dynamic nonce-aware layout; production HSTS/frame/referrer/nosniff headers; private/no-store proxy responses; mandatory exact public HTTPS origin; one pending visible-tab contact poll with unmount cancellation; client cancellation and retry hints preserved; route budget aligned; Node engine minimum aligned.
- **Operations:** private control DB/schema readiness endpoint; safe request IDs, route templates, statuses and latency logs; production dependency record redaction before handlers; fail-closed WSGI environment validation before Django settings/import upgrade; explicit Host restrictions and rejection of alternate Django settings modules; Docker non-root/private umask retained, available OS updates applied and unused runtime pip removed; hashed Python runtime lock installed by Docker/CI; CI checks frontend on all release triggers and gates build on both suites; release worker guard includes MCP/scheduler; private local environment permissions tightened; ignore rules cover secrets/sidecars/builds; deployment docs distinguish historical evidence from new requirements.

Production code is intentionally still uncommitted. Preserve the entire reviewed snapshot when preparing a release; deploying HEAD would omit application files.

## 4. Remaining Issues and UNVERIFIED Requirements

1. **Release/host:** inspect exact live service versions, environment-name presence, origin/Host/proxy rules, stable encryption key, file permissions, current control/employee migrations, disk and memory capacity. Anonymous read-only HTTPS checks observed a working login, API health requiring authentication and `/api/ready` returning 404; this shows deployed endpoints differ from the local candidate, not which full release is installed. No authenticated production/customer read was performed.
2. **Credential retention:** resolve historical token/credential ownership and revoke/rotate where applicable. Inspect only presence/counts of legacy plaintext fields and credentials in actual databases/log archives, then use an approved remediation plan. Keep recovery keys recoverable; deleting old rows or rotating encryption keys without re-encryption risks data loss.
3. **Recovery/monitoring:** prove scheduled full backups of control plus every workspace and matching secrets/environment, independent protected storage, retention, integrity and a complete disposable restore. Test alerts for API 5xx/latency, DB/disk failure, auth failure spikes, scheduler silence, worker nonzero/deadlines and provider/payment-cost failures. No external error tracker or alert delivery is proven by this source.
4. **Trusted browser and enabled integrations:** execute real-browser login/setup/onboarding/tour/CRUD/settings/logout/reset, CSP/hydration/console/mobile/keyboard/focus/contrast and genuine MCP consent/refresh/revoke. Test real invitation/mail/provider failure behavior only under fresh specific approval. Synthetic provider success is not delivery/billing certification.
5. **Capacity/configuration:** benchmark realistic concurrency/data sizes on the selected host; confirm proxy body/connection/time limits and the hosting plan supports the 80-second dashboard handler. A documented e2-micro VM, SQLite IMMEDIATE writes, 8 WSGI threads, polling/SSE, SDK imports and child processes need measured memory/lock/latency budgets. Do not scale independent filesystem instances as shared tenant storage. Logs/history need bounded retention and disk alarms.
6. **Dependency/tooling:** review remaining OS advisory reachability and select a tested patched base when available; configure ongoing advisory scanning. No blanket assertion of package maintenance/lifecycle safety or branch protection/Vercel deployment gating is possible from repository files. GitHub required checks and Vercel promotion gates need operator verification.

## 5. Security Review

**Authentication:** invite-only employee accounts with admin reset/setup capability; no public signup, separate email-verification workflow, general social login/account linking, self-service forgot-password, MFA or SSO implementation. These absences are explicit, not missing endpoints assumed tested. Django password validators/hashers, single-use invitations, hashed opaque 12-hour sessions, expiry and revocation are covered. MCP has separate OAuth consent, exact callbacks/resource, S256 PKCE, hashed tokens, refresh rotation, grant/actor checks and replay-family revocation. Invalid state handling on a genuine external OAuth client remains UNVERIFIED.

**Authorization/isolation:** private API data requires the server service credential plus a live employee session. Administrator actions check live staff status. Employee workspace UUID/path is derived from the control account server-side. Canonical IDs resolve inside the employee's physical DB, with actor predicates for Chat/reviews and connection predicates for MCP. Workers recheck live account/capability at external sinks. Real-file tests with overlapping customer IDs, forged selectors, foreign runs/drafts/campaigns, export contents and revoked workers reject cross-employee access. OS administrators can read files; source-level tenancy does not certify host/storage ACLs.

**APIs/CSRF/CORS/SSRF:** explicit methods/routes, strict schemas, bounded input/pagination, safe status/error payloads, auth/OAuth throttles and approved public/TLS pinned provider connections were inspected. ORM and fixed subprocess argv are used; no user-controlled raw SQL, shell command, unsafe deserialization, eval, unvalidated server-selected file path or open redirect interface was found in network-facing APIs. The preserved operator CLI intentionally accepts local database/product/target file paths. Frontend cookie mutations require exact configured same origin and service/session headers stay server-side. Backend CORS uses explicit configured origins. Authenticated caches/SSE are private/no-store; user-specific server fetches force no-store. Ingress abuse limits remain an operational requirement.

**Browser/secrets/headers:** authentication cookies are Secure, HttpOnly, SameSite=Lax and bounded in production. Production TLS HTTP tests verify cookies/headers and theme/framework script nonces; the CSP excludes production unsafe-eval. Markdown raw HTML/remote images are disabled and links constrained; ordinary data is React-escaped. Provider/DB/service secrets have no `NEXT_PUBLIC_` export. No secret values are included in this report, environment inventory or safe request logs. A scan of 39 final client static assets found none of the configured synthetic service/signing/mailbox credential markers; real production credentials were never supplied to the build. Backend transport HSTS also requires trusted HTTPS termination; Caddy headers are configured without trusting arbitrary forwarded-proto headers.

**Git/dependencies:** Gitleaks scanned 1,043 commits: 3,646 historical matches at 46 unique rule/file/line locations. Most are repeated tokens in nine deleted browser fixtures; three migration-label hits are false positives; historical Chromium credentials remain ownership/validity UNVERIFIED. The complete current text snapshot scan returned zero findings. Names-only [history disposition](production-audit-2026-10-04-secret-history.json) retains no secret values. Ignored `dashboard/.env.local` had three unused names and was changed to mode 600 without displaying/deleting its contents. Current tracked real environment/credential/database files were not found.

`npm audit` and Python installed/locked runtime advisory checks returned zero known Python/npm advisories. Runtime Python transitive dependencies now have exact versions/hashes; frontend has `package-lock.json` and clean `npm ci`. Container scan after fixes still reports **279 OS advisories** (5 CRITICAL, 57 HIGH, 116 MEDIUM, 100 LOW, 1 UNKNOWN), and **zero Python-package advisories**. No remaining scanner entry has a fixed Bookworm version. These severity totals are scanner classifications, not 279 verified remote exploits.

The SQLite advisory requires crafted arbitrary SQL; no such application input path was found, but the installed Bookworm library remains affected. [Debian SQLite advisory](https://security-tracker.debian.org/tracker/CVE-2025-7458). The zlib critical match concerns MiniZip, which Debian says is not built into the relevant binary; that match is not applicable to this installed zlib binary. [Debian zlib advisory](https://security-tracker.debian.org/tracker/CVE-2023-45853). Perl advisories concern regex compilation/Archive::Tar; this application exposes neither, and one regex issue describes 32-bit builds whereas the tested image is 64-bit ARM. These are reachability observations, not an unqualified waiver or assurance for other deployment architectures. [Perl regex overflow](https://security-tracker.debian.org/tracker/CVE-2026-8376), [Perl archive paths](https://security-tracker.debian.org/tracker/CVE-2026-42496), [Perl regex matching](https://security-tracker.debian.org/tracker/CVE-2026-13221). No speculative OS-major change or vulnerability-ignore file was introduced.

## 6. Database/Migration Review

All account/config migrations and current models were inspected, with installed dependency migrations exercised. Control and employee files use WAL, IMMEDIATE write transactions, canonical foreign keys/constraints and current indexes. Production FULL durability is checked on actual SQLite connections. Unique constraints cover token hashes, request IDs, candidates/lookups, campaign/deal and review/deal pairs, active actor work, policies and workday runs. Delivery evidence protected by PROTECT and conservative pending/uncertain states is retained.

Clean databases and a seeded prior-release schema (`leadzen_config.0014`, `leadzen_accounts.0002`) upgrade to current leaves, preserve IDs/records/timestamp instants/tour progress, repeat idempotently and pass integrity/foreign-key/system/drift checks. A separate full disposable restore rehearsal backed up and restored the control DB plus all five employee DBs, matched encrypted settings with the fixture key and verified restored login/workspace access and service-only denial. [Restore evidence](production-audit-2026-10-04-restore.json). This does not establish actual production backup scheduling, independent recovery or matched-production restoration. The prior schema is based on documented October 3 evidence; today's actual production schema remains UNVERIFIED. Latest leaves are config `0019_discoverylookup_source_index` and accounts `0004_accountprofile_tour_state`.

Config 0018 intentionally normalizes New York schedule metadata and changes approval-review requirements while retaining immutable evidence. Its reverse is a no-op for normalized metadata; migration reversal does not recover old business values. Config 0019 adds an index without deleting data, but SQLite index creation takes a write lock. Plan a maintenance window, backup and explicit all-workspace migration. A readiness 200 verifies only the control DB/query/migration plan; it does not inspect every employee DB, storage write capacity or scheduler.

The CRM hotspot decreased from 501 queries for 100 profiles to four with equivalent payloads. Eligibility count plus a 25-contact page uses two queries. These tiny-fixture measurements establish improvement, not production load certification. Other bounded serializers, counted searches/high offsets and four-per-second stream snapshots still need workload measurements. No production/customer database was migrated, cleaned or deleted; disposable real SQLite databases were exercised.

## 7. Infrastructure/Deployment Review

Python 3.12 production runtime, Node 22.12+ supported LTS, Next standalone output, local fonts, pinned finder/sender and all declared runtime imports were reviewed. The frontend static bundle totals 1,527,500 uncompressed bytes across 39 shared assets; this is not a per-page transfer or browser CPU measurement. The image installs the hashed runtime lock plus the package without development dependencies, drops to UID 1000 through its entrypoint, uses umask 0077 and requires production WSGI configuration. Container WSGI imports, framework checks, SQLite integrity/FULL WAL and absence of pytest/pip passed. The tested final image is `sha256:a97a39a229f8b16b629f353ce045fe54361a7cb08000664ba05548c0dcc548d4`, ARM64 and 677,175,002 uncompressed image bytes; the actual deployment architecture and host capacity still require verification. A network-isolated Gunicorn container successfully served private health/readiness and rejected unauthenticated or service-only employee-data requests.

Compose remains a bounded CLI job and now cannot restart paid work automatically. It is not a web production orchestrator. Systemd runs a single Gunicorn process with eight threads and a separately controlled follow-up scheduler. The deployment script backs up SQLite consistently and checks workers; it is a helper, not a substitute for full installed-environment/independent recovery backup. Its wheel reinstall uses `--no-deps`, so the release's matching locked environment must be prepared and backed up separately first. The script must not be run blindly against an unknown host.

CI installs dependencies, checks advisory feeds and fatal Python syntax/undefined-name errors, executes both suites/TypeScript/frontend build, builds a Python distribution and Docker image, and gates release-build jobs on both test jobs. This repository does not prove branch-protection required checks or prevent an operator/Vercel integration from deploying outside that pipeline. Those promotion controls and actual cloud credentials/service flags remain UNVERIFIED. No deployment was attempted.

## 8. Tests Performed

The final clean verification uses a credential-free source copy and independently created Python environment/npm install in a mode-700 temporary audit directory. In the commands below, `TASK_AUDIT_DIR` is resolved with `TASK_AUDIT_DIR=$(cat docs/production-audit-2026-10-04-work-dir.txt)`; `<audit-dir>` denotes that private directory in explanatory paths. Commands containing fixture secrets are deliberately described by their executable and variable **names**, not by values. Detailed focused commands/results are in the three scope reports.

| Exact command / scope | Final result |
| --- | --- |
| `uv venv --python 3.12 "$TASK_AUDIT_DIR/clean-venv"`; `uv pip install --python "$TASK_AUDIT_DIR/clean-venv/bin/python" -e "$TASK_AUDIT_DIR/source[dev,web]"` | PASS, fresh Python install. |
| `uv pip install --python "$TASK_AUDIT_DIR/clean-venv/bin/python" --require-hashes -r requirements-production.lock`; `uv pip check --python "$TASK_AUDIT_DIR/clean-venv/bin/python"` | PASS, runtime hash lock installed, compatible dependency graph. |
| `npm ci` in clean `source/dashboard` | PASS, 229 packages added / 230 audited, zero advisories. |
| `npm run lint` | PASS, `tsc --noEmit`; actual ESLint is not configured. |
| `uvx ruff check leadzen tests --select F821,F822,F823,E9` | PASS, selected fatal undefined-name/syntax checks; not general Python lint/type checking. |
| `"$TASK_AUDIT_DIR/clean-venv/bin/python" -m pytest -q` in clean source | PASS, **1,387 tests**, one installed-library deprecation warning, **829.92 seconds**, against the exact final clean runtime source. |
| `npm test -- --maxWorkers=2` in clean dashboard | PASS, **25 files / 1,191 tests**, 62.17 seconds. |
| `npm run build` in clean dashboard | PASS, optimized Next production build/type validation; authenticated pages dynamic. |
| `.venv/bin/pytest -q tests/test_production_config.py tests/test_production_migrations.py tests/test_branding.py` | PASS, **39 tests**, 3.44 seconds after final FULL WAL and settings-module preflight checks. |
| `.venv/bin/pytest -q tests/test_cli.py tests/test_wizard.py tests/test_production_domain_boundaries.py tests/test_production_config.py` | PASS, **79 tests**, 7.65 seconds; reproduced logger-handler ordering covered. |
| `.venv/bin/python manage.py makemigrations --check --dry-run --settings=tests.settings` | PASS, no model migration drift. |
| `.venv/bin/python tests/scenarios/production_domain_measurements.py` | PASS, four CRM queries at 1/10/100 profiles; two eligibility queries. |
| `uv build --out-dir "$TASK_AUDIT_DIR/dist"` | PASS, wheel and sdist built from final runtime source. |
| `docker build -t leadzen:production-audit-20261004 -f compose/leadzen/Dockerfile .` | PASS, final production image. |
| `docker run --rm --network none --env-file "$TASK_AUDIT_DIR/docker-runtime.env" -v "$TASK_AUDIT_DIR/docker-data:/app/data" leadzen:production-audit-20261004 python -m leadzen migrate --noinput` | PASS, disposable migrations including 0019; final repeat no pending migrations. |
| Container `python -c 'from leadzen.wsgi import application'` with missing critical environment | PASS expected nonzero startup rejection; no secret values. |
| Container WSGI/system/SQLite/runtime-import and alternate-settings rejection assertions | PASS, non-root UID, no pytest/pip, integrity, WAL and synchronous FULL. |
| Container `python -m gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 8 --timeout 120 leadzen.wsgi:application`; authenticated/anonymous HTTP probes via `docker exec` | PASS, health/readiness 401 anonymous / 200 service auth; overview 401 service-only; private cache/request IDs. |
| `PYTHONPATH="$TASK_AUDIT_DIR/source" "$TASK_AUDIT_DIR/clean-venv/bin/python" "$TASK_AUDIT_DIR/restore-rehearsal.py" "$TASK_AUDIT_DIR"` | PASS, disposable control + five workspace backup/restore; counts, integrity/FKs, matched-key decryption, restored login/private access. Script hash retained in restore evidence; actual production recovery UNVERIFIED. |
| `NODE_ENV=production` standalone `node server.js` with server-only fixture environment and disposable TLS proxies | PASS, standalone server starts with runtime artifact only. Separate isolated artifact with no development-dependency ancestors served login plus all nine referenced assets. |
| `"$TASK_AUDIT_DIR/clean-venv/bin/python" tests/scenarios/http_flow.py "$TASK_AUDIT_DIR/leadzen-preview.production" https://localhost:3443 "$TASK_AUDIT_DIR/localhost.crt"` | PASS, invitation/password setup/reuse rejection, onboarding, tour, CRUD, campaign preview, blocked external send, cross-employee isolation, disable/re-enable and logout. |
| TLS HTML/header/readiness inspection | PASS, all inline/theme/framework script nonces match in the inspected login response, no production unsafe-eval, private cache/security headers and readiness authorization. [HTTP evidence](production-audit-2026-10-04-production-http.json), [readiness](production-audit-2026-10-04-readiness-http.json). |
| `npm audit --json`; `uvx pip-audit --path .venv/lib/python3.12/site-packages`; `uvx pip-audit -r requirements-production.lock --no-deps --disable-pip` | PASS, zero known Python/npm advisories. |
| Gitleaks v8.30.1 `git` history and `dir` complete current text snapshot, with `--redact --report-format json` | Completed; historic findings triaged, current zero findings across the 489-file final text input. |
| Trivy v0.69.3 `image --scanners vuln --format json leadzen:production-audit-20261004` with current advisory DB | Completed; 279 residual OS advisories / zero Python advisories, explicitly not a zero-vulnerability result. |
| `bash -n compose/leadzen/entrypoint compose/leadzen/start compose/leadzen/deploy-accounts.sh`; `docker compose -f local.yml config --quiet`; `git diff --check` | PASS. Release guard matched all six representative current worker/scheduler commands and excluded pytest. |
| Native browser HTTPS navigation | **UNVERIFIED**; browser rejected disposable self-signed certificate with `ERR_CERT_AUTHORITY_INVALID`; warning was not bypassed. |

Intermediate failures are retained rather than represented as clean passes: stale fixture Host settings after explicit production Host restrictions; newly added reproductions failing before fixes; a manual-send guard initially interfering with normal Autopilot stopping (scope corrected); logging capture affected by CLI handler setup and quiet-mode levels (actual redacted records asserted after explicit test emission); an ORM password assertion mistook the authorized worker's intended in-memory decryption for plaintext storage (the corrected test checks raw stored ciphertext plus the worker round-trip); timing failures with 24 frontend workers (unchanged suite passed with two); duplicated ignored generated Next type files (preserved outside the worktree); an initial lock-auditor virtualenv/ensurepip failure (explicit no-deps audit rerun passed); a system-pip removal command initially resolving the runtime venv (absolute base interpreter corrected); and one initial simultaneous Docker bind-mounted migration/WSGI test exited 135, while the separated migration rerun and final container checks passed. The cause of that nonrepeatable container signal is **UNVERIFIED**; actual deployment filesystem/architecture testing remains required. The corrected clean full suite passed 1,386 tests before the last settings-module preflight case; that final case passed in the 39-test group, followed by the complete final suite reported above. Two obsolete full-suite snapshots were interrupted after later source fixes; their partial passes are not full-suite results.

## 9. Production Environment Variables Required

Names only; no secret values. The [full names/reference inventory](production-audit-2026-10-04-env-inventory.json) also identifies optional/internal/CLI names.

**Backend WSGI required:**

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

**Dashboard production required:**

```text
NODE_ENV
LEADZEN_API_URL
LEADZEN_API_TOKEN
LEADZEN_DASHBOARD_PUBLIC_URL
```

**Required when invitations are enabled:**

```text
LEADZEN_RESEND_API_KEY
LEADZEN_INVITATION_FROM
```

**Required when public MCP is enabled:**

```text
LEADZEN_MCP_PUBLIC_URL
```

**Explicit optional deployment controls:**

```text
LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED
LEADZEN_AUTOPILOT_ENABLED
LEADZEN_LLM_HOSTS
LEADZEN_MAIL_HOSTS
LEADZEN_EMAIL_HOSTS
LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS
```

If supplied, `DJANGO_SETTINGS_MODULE` must identify `leadzen.settings`; production rejects alternate/test registries. Worker identity/control names are injected server-side and must not be browser-controlled. `OPENOUTFIND_*`/`OUTSEND_*` are CLI/child interfaces and per-workspace provider settings; not required public dashboard secrets. `LEADZEN_MCP_ALLOW_LOCAL` is forbidden by production preflight. `HOST_UID`/`HOST_GID` are optional container ownership controls. Three ignored local names (`api_key`, `model`, `ai_url`) are unused by this application and are not production configuration.

## 10. Deployment Checklist

These are operator steps, not authorization to deploy or send. They deliberately precede enabling real users/external actions.

1. Resolve the BLOCKER/HIGH release gates above. Select the exact reviewed working-tree snapshot, including untracked application/migration files; create an immutable source manifest, wheel, hashed runtime environment/image and frontend artifact. Record checksums. Do not use the repository's old HEAD as the candidate.
2. Run the verification commands in section 8 on that snapshot/target architecture. Complete trusted-HTTPS browser, required integration and realistic capacity checks. Verify CI required checks and manual promotion controls prevent bypass. Choose and document the OS advisory treatment.
3. Confirm actual control/employee schema leaves and read-only database integrity. Verify every initialized workspace from server-owned account UUIDs; reject symlink/unexpected paths. Confirm production environment **names** are present without printing values. Run `python -m leadzen.production` with the private backend environment. Preserve the existing settings key; verify frontend/backend service credentials and exact HTTPS origins match.
4. Announce a maintenance window. Stop API intake and follow-up/Autopilot scheduling; drain or conservatively hold active jobs. Confirm no `leadzen.web_worker`, `leadzen.chat_worker`, `leadzen.autopilot_worker`, `leadzen.mcp.worker` or `leadzen.scheduler` remains. Do not kill uncertain external work and replay it automatically.
5. Create consistent SQLite-backup-API copies of control and **all** employee DBs. Back up complete current source, installed environment, private environment/key material and service/proxy definitions together. Verify integrity/foreign keys/manifests; retain an independent protected copy and prove a disposable restore before schema changes. Do not copy live DB main files while ignoring WAL sidecars.
6. Stage the new locked Python environment/package and frontend artifact without overwriting the recovery release. Verify permissions/ownership and persistent local SQLite storage. Supply current required private environment; keep external-action service flags disabled during verification. If using `deploy-accounts.sh`, first satisfy its hardcoded host/release-path assumptions and matching locked-dependency/full-backup prerequisites; it is not a general deploy tool.
7. With intake/workers stopped, run `python -m leadzen migrate --noinput` for the control DB and each validated initialized employee DB using the server-derived workspace environment. Apply latest accounts 0004/config 0019. Check migration plans, integrity/foreign keys and framework checks afterward. 0018 metadata normalization is not reversed by a schema-only rollback.
8. Start the candidate API with the reviewed Gunicorn/service configuration. Check authenticated `/api/health` and `/api/ready`, anonymous 401s, service-only overview 401, security headers and log outcomes. Readiness alone does not certify employee schemas/jobs/providers.
9. Start candidate dashboard with required server-only variables. Verify TLS/nonce CSP/no-store/cookies, login/setup/reset/onboarding/tour/logout and synthetic CRUD/settings/export/admin/cross-employee probes. Confirm exact candidate artifact/version. Do not invoke real send/spend smoke tests without separate specific approval.
10. Promote traffic only after checks pass; monitor errors, latency, locks, memory/disk, auth and workspace/job outcomes during a defined observation window. Resume only previously authorized scheduling after reconciliation and health verification; new flags/policies or external operations need fresh specific approval. Keep the old artifacts and matched recovery set accessible.

## 11. Rollback Checklist

1. Stop new writes/intake and scheduler/workers; preserve current logs, audit records and a new consistent snapshot for incident analysis. Record uncertain sends/provider submissions and reconcile acceptance/usage before retrying.
2. For a frontend-only failure, return traffic to the last verified frontend artifact/environment and verify the existing backend contract. Do not restore an old database for a UI rollback.
3. For backend failure, prefer restoring the previous immutable code/runtime/environment if it is compatible with the forward schema. Inspect compatibility; additive columns/indexes do not establish every older version is safe. Restore service/proxy definitions and the matching stable encryption configuration.
4. If database restore is necessary, use the complete verified control-plus-workspaces recovery set with matching application/key/environment, while all writers remain stopped. Reconcile every legitimate post-backup customer change and accepted/unknown external effect first. A restore can otherwise lose customer work or repeat paid/sent operations. Never automatically run destructive reverse migrations or restore only one side of the control/workspace relationship.
5. Verify integrity/foreign keys, migration compatibility, health/private access, login, ownership and critical read/write flows in isolation. Reopen intake only after those checks pass; restart authorized scheduling only after uncertain operation reconciliation. Preserve failed-release evidence and recovery copies under private retention controls.

## 12. Final Verdict

**I would not approve this exact codebase for production deployment with real customer data yet.** The confirmed local defects have safe fixes and extensive synthetic verification, but trusted-browser execution, current deployment/migrations/configuration, historical credential disposition, full recovery, alert delivery and host/provider capacity/behavior remain unresolved or UNVERIFIED. Complete the explicit release gates, then review the immutable candidate with that evidence. Final clean suites passed **1,387 backend and 1,191 frontend tests**; production build/startup/migration/HTTP checks passed. No deployment or real customer/provider operation occurred during this audit. Machine-readable results and artifact hashes are in [verification evidence](production-audit-2026-10-04-verification.json).

## Complete category coverage

| Requested category | Evidence and boundary |
| --- | --- |
| 1. Build/runtime | Fresh Python/npm install, type check, standalone build/start, runtime-only container imports; production fail-closed WSGI/HTTPS. Developer localhost examples/test fixtures remain intentional. |
| 2. Environment/secrets | Names/reference inventory, preflight, encryption, current/history scans, browser exposure and private file mode; real secret validity/retention UNVERIFIED. |
| 3. Authentication | Implemented login/logout/password/invitation/session/MCP flows and races exercised; absent public signup/social login/MFA explicitly recorded. |
| 4. Authorization/tenancy | Every runtime entry point reviewed; real-file overlapping-ID/forged-selector/revocation/export isolation scenarios. Actual host ACLs UNVERIFIED. |
| 5. API security | Methods/schema/body/time/pagination/auth/throttle/origin/transport/error boundaries; ingress/load operational gates remain. |
| 6. Database | All account/config migrations/models reviewed, clean/prior-schema preservation/FK/integrity/drift tests, additive index and FULL durability. Current production schema UNVERIFIED. A quiesced disposable control-plus-five-workspace restore also passed integrity, FK, row counts, matching-key decryption and authenticated restored-workspace access. |
| 7. Payments/billing | No customer payment/subscription/Stripe webhook implementation exists. Paid AI/enrichment reservations, approvals, receipts, ambiguous cost holds and duplicate protection reviewed/tested synthetically. Actual provider bills UNVERIFIED. |
| 8. Integrations | AI, finder/enrichment, SMTP/IMAP/email API, Resend invitations and MCP boundaries/protocol fixtures; body deadlines/provider failures covered. Actual services, billing and adversarial connection stalls UNVERIFIED. |
| 9. Error handling | Safe API/parser/provider errors, worker outcomes, async cancellation/deadlines and rejected startup; failure regressions included. |
| 10. Logging | Safe request summaries/IDs, provider redaction before handlers and saved-output mitigation; old unknown secrets/PII retention UNVERIFIED. |
| 11. Observability | Private liveness/readiness and safe request/job outcomes added; actual external alerts/DB-workspace/scheduler watchdog/error tracking UNVERIFIED. |
| 12. Performance | CRM/eligibility query measurement and regression, bounded polling/lists/streams; real load/memory/cost/large-history capacity UNVERIFIED. |
| 13. Caching | Server fetch/proxy/authenticated page/SSE no-store, account-keyed local tour state, static assets intentionally public. |
| 14. Frontend | All pages/routes/components inspected, full component suite and production TLS HTTP journeys; real-browser hydration/console/mobile UNVERIFIED. |
| 15. Accessibility | Labels/semantics/live states/focus/keyboard/reduced-motion inspected and components exercised; real screen readers/contrast/browser certification UNVERIFIED. |
| 16. Security headers | Production CSP nonce/HSTS/nosniff/referrer/DENY and secure cookie HTTP assertions; real-browser enforcement/trusted production proxy UNVERIFIED. |
| 17. CORS | Complete explicit backend origin allowlist and frontend exact same-origin behavior; current deployed origin/Host/proxy state UNVERIFIED. |
| 18. Dependencies | Lock graph/lifecycle/runtime placement reviewed, fresh deterministic installs, Python/npm/OS advisory scans; residual OS advisories disclosed, no blind major upgrades. |
| 19. Jobs/queues | Durable claims/idempotency, process locks, bounded work/timeouts, conservative uncertain holds, safe failure logs and restart guard; actual scheduler monitoring UNVERIFIED. |
| 20. Files/storage | No arbitrary file-upload/cloud-storage API. CSV import schema/body bounded. Employee SQLite export is authorized/server-path/no-follow/size/time bounded; full restore separate. |
| 21. Races | Auth writes, invitations, settings, OAuth replay, paid reservations, job claims, duplicate sends and final transport authorization reviewed/regressed. Real host multiprocess stress UNVERIFIED. |
| 22. Production config | Docker/compose/systemd/Caddy/installers/scripts/runtime/Node/WSGI detection reviewed; container exercised offline. Exact cloud state UNVERIFIED. |
| 23. CI/CD | Tests/type/build/advisories/build dependency gates added; repository files do not prove branch protection or external deployment gate configuration. |
| 24. Deploy/rollback | Exact ordered runbook above; destructive rollback not attempted. Historical Oct3 recovery proof retained but current complete restore UNVERIFIED. |
| 25. Tests | Complete backend/frontend suites, targeted security/database/provider regressions, build/package/container/HTTP checks. No assertion weakening/disabled tests. |
| 26. Dead/debug code | Current runtime scan found no TODO/FIXME/HACK/debugger/console.log/console.error. CLI output, synthetic scenarios, compatibility labels and safe error logging inspected and retained intentionally. |
| 27. Git hygiene | Dirty work preserved, current text/history secrets scanned, private/generated/data files ignored, Docker build excludes key/env files. Historical token/PII remediation outstanding. |
| 28. Production simulation | Fresh production standalone/TLS, explicit production preflight, disposable actual SQLite and offline Gunicorn image; exact enabled live-provider and browser behavior remain UNVERIFIED. |
