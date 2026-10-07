# Production cross-check and final controlled candidate — October 4, 2026

## 1. Production Readiness Status

**NOT READY. I would not approve this exact candidate for production promotion.**
The cross-check found real defects in previously implemented controls, fixed them,
and verified the replacement candidate. Local implementation and available checks
are complete; material current-host/recovery/credential/image/alert/browser/provider
and release-control gates remain unresolved. No permanent-security claim is made.

The [original audit](production-readiness-audit-2026-10-04.md) and
[previous completion](production-completion-2026-10-04.md) remain dated evidence.
The previous completed source `73eb35d6…` is preserved. Intermediate `5ecab15b…`
was superseded by final canonical preflight fixes; its interrupted backend suite
is **not PASS**. Only the final results below apply to this candidate.

No production deployment/migration/data mutation, live credential rotation, Git
reset/discard/commit/history rewrite, real email, paid provider call, paid resource,
or external alert delivery occurred. Unrelated dirty/untracked work was preserved.

## 2. Exact tested candidate

- Source SHA-256: `f3498c958bb7b5f290e4d8f1a294915a153870b6007c13b7d1552624faec3e3e`.
- Source archive SHA-256: `15b8e93a32ddba0f7b30a5db309083450ba1e52dfacab3fe2f93646bf80cd005`.
- Git provenance: `0c3fc7a63205069e3380c0b8d5e8bb6738bb2946`; **HEAD is not the application**.
- Complete intended source/config/assets/tests/migrations: **397 files, 361 untracked**.
- Backend image: `sha256:ba1bafae3d354891897035dd528d7ecfcea983025af7b30ca67390797f5b6947`, **linux/amd64**, Python 3.12.15, UID 1000.
- Local frontend: Node 24.21.0 / Next 16.3.8, **darwin/arm64** standalone. This is the
  protected local verification artifact; an exact Vercel/prebuilt Linux platform
  deployment artifact is **UNVERIFIED**. Actual target-host architecture is also
  **UNVERIFIED**. The manifest's architecture identifies the backend image target.
- Browser runtime-input digest: `9d9b12af13ab4fd73f56804a9d5ea1f94ebd3dafd8565b8cc1092486642914d0`;
  this subset identity is distinct from the complete release source hash.
- Durable protected release directory: `/Users/ashishdikonda/Desktop/Openoutreach/leadzen-release-candidates/f3498c958bb7b5f290e4d8f1a294915a153870b6007c13b7d1552624faec3e3e`. The byte-verified source,
  artifacts and evidence exclude environment exports/databases/private fixture logs.
  This same-host release copy is **not independent production recovery storage**.
  [Durable-copy verification](production-crosscheck-durable-candidate-2026-10-04.json).

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| backend-wheel | 272382 | `37996323ad16fbd030d2e198964559ecdf5c6d7b2f30fe357baeb8310c1d5211` |
| dashboard-standalone | 14364342 | `1097c9879d664f6673e6b5a8eb77c62f9dfcfc700d86f188d9a8986bad509652` |
| container-image | 665636864 | `670736d70b578d9f5f1d459a159b7de651245061a3321bfebadd2b77a9a5e87a` |

Dependency lock hashes and complete commands/evidence are in
[verification](production-crosscheck-2026-10-04-verification.json). Frozen runtime
artifacts are used directly; rebuilding or changing any artifact requires a new
candidate/evidence. The wheel and installed image package each match all 98 frozen
package files. Docker image ID, saved archive configuration ID and Trivy metadata ID
match. Current intended root inputs still match the frozen source.

## 3. Issues found and fixed

| Severity | Defect | Durable fix |
| --- | --- | --- |
| HIGH | Release evidence accepted unbound/stale bare PASS records. | Schema 2 binds source/archive/architecture/full artifacts; every PASS has UTC expiry of at most 24 hours and nonempty relative hash-verified evidence; legacy/stale/mismatched records fail closed. |
| HIGH | An empty or unrelated image report could pass. | Require complete OS/package scan, actual metadata architecture/ImageID and current scan time. CI scans and saves the immutable inspected ID. |
| HIGH | Backup stability checks preceded expensive copying. | Recheck databases/namespace/keys/env/service/protected files and release artifacts after local and independent copies immediately before publication; late drift aborts and retains evidence. |
| HIGH | Maintenance holds lacked directory durability and admitted a counter-publication race. | Fsync parent/directory entries; recheck hold after publishing in-flight counter and before handler execution. |
| HIGH | Historical recovery imports could authorize real forward migrations. | Execution now requires complete native matched recovery; historical imports remain scoped evidence. |
| HIGH | Restore PASS flags were not fully measured after upgrade. | Privately compare every original business record; validate original relationships, post-upgrade integrity/FKs and actual decryption before synthetic authentication. Baseline normalization cannot mask a wrong resulting timezone/identifier. |
| HIGH | Preflight could revive cleared settings or use the wrong runtime row. | Match RuntimeSettings singleton 1 precedence, including explicit clears; reject stale/unselected credentials. |
| HIGH | Enabled features accepted unusable transport/endpoints or mailbox ciphertext. | Verify public approved SMTP/IMAP hosts, supported TLS ports/reply credentials, AI/mail endpoint semantics, actual password shape and single encryption. No DNS/provider call or key/data rewriting. |
| HIGH | Correct index names could hide incorrect definitions. | Compare physical columns/order/uniqueness/partial predicates from current migration descriptors. |
| HIGH | Startup/preflight disagreed on canonical public origins. | Share the canonical HTTPS validator for dashboard/API/provider host boundaries; reject numeric loopback aliases, multicast/private/internal/invalid DNS despite an allowlist. Preserve valid public IPv6 and transport DNS case. |
| MEDIUM | Worker startup errors/timeouts could leave healthy scheduler heartbeats. | Propagate failed passes and retain last_failed_at through subsequent successes; monitor recent failure window and control-index DB/WAL copy stability. |
| MEDIUM | Backup/monitor examples could read an inaccessible root-owned environment. | Use a privately verified service-owner, mode 0600 current environment copy; correct stop-before-quiescence ordering and explain residual-WAL BLOCKED evidence. |
| MEDIUM | CI action inputs and runtime selection were insufficiently fixed. | Pin six actions to official commit SHAs without major upgrades; CI checks Node 22/24 and browser uses 24. Clean local Node 24.21 verification matches observed Vercel major; actual promotion remains blocked. |

The focused before-fix reproductions failed as expected; the final full suite
passed. No test was disabled or weakened. Keys and existing production data were
not re-encrypted or rewritten. See the shipped
[preflight](production-preflight.md), [recovery](production-recovery.md),
[monitor](production-monitoring.md), [environment](production-environment.md),
[secrets](production-secrets.md), and [release/rollback](production-release.md)
procedures for repeatable commands and their explicit boundaries.

## 4. Release-gate table and remaining action

PASS means only the stated measured scope. Synthetic, earlier historical,
inaccessible and unperformed checks do not close production gates.

| Gate | Status | Evidence | Remaining action |
| --- | --- | --- | --- |
| actual_recovery | **BLOCKED** | Stronger synthetic full restore/regressions passed; authorized historical recovery evidence is incomplete. No current matched production set/independent custody/drill. | Authorize fresh matched current control+all employee recovery, independently protected custody and isolated full drill. |
| alert_delivery | **BLOCKED** | Local delivery/redaction/deadline regressions passed; exact authorized destination and external on-call receipt/monitor-of-monitor installation unavailable. | Approve exact sink/on-call owner and one bounded alarm; verify receipt plus independent missed-monitor coverage. |
| backend_tests | **PASS** | Clean hashed builder/runtime install and same-source wheel: 1649 passed, one existing PydanticAI deprecation warning in 526.33 seconds; no skipped check claimed. | No local suite failure remains; retain exact candidate evidence. |
| browser | **BLOCKED** | Final trusted HTTPS subset passed login/logout/private routes, CRUD, settings, mobile/focus/contrast, foreign sentinel denial; full password/setup/onboarding and active CSP attack probes unperformed. | User handoff or user-controlled full five-scenario runner for new passwords/setup/onboarding; actual consent and active CSP/broad accessibility checks remain unperformed. |
| credential_disposition | **BLOCKED** | 43 real/unresolved historical exposure locations require owner classification/revocation receipts; no questionable credentials used. | Identify owners for 43 real/unresolved locations and retain administrative classification/revocation/session-termination receipts; no provider probing. |
| dependency_audit | **PASS** | Fresh current advisory feeds: 94 runtime Python + 7 build Python + npm zero package advisories; OS scan separate FAIL. | Continue current advisory checks; image risk has separate FAIL. |
| enabled_integrations | **BLOCKED** | Provider-disabled candidate made 0 blocked external calls; STOP/approval/duplicate/uncertainty/MCP protocol regressions passed. No authorized real provider/client sandbox identity/recipient/cost cap consent flow. | Choose enabled features/private sandbox identities and named recipients/clients, operations and spending/credit caps for prepared tests. |
| external_release_controls | **BLOCKED** | GitHub upstream pull-only protection404/rulesets0, owning repository unclear; Vercel current Node 24 match tested locally but required promotion checks/exact prebuilt Linux platform artifact UNVERIFIED. | Owning release repository/platform admin evidence; required checks/promotions and exact tested Vercel artifact. No external setting was changed. |
| frontend_tests | **PASS** | Fresh npm ci, Node 24.21.0: 1,196 tests across 26 files passed in 39.50 seconds. Full browser/password workflows separately BLOCKED. | No component suite failure remains; complete separate browser gate. |
| image_advisories | **FAIL** | Fresh exact ImageID-bound Trivy scan retains 44 HIGH, 61 MEDIUM, 60 LOW, 2 UNKNOWN, 0 CRITICAL; no risk decisions approved. | Apply available compatible tested fixes or obtain exact package/version/architecture/reviewer/evidence/expiry risk decisions for 44 HIGH matches. |
| migrations | **BLOCKED** | Current production namespace/schema unavailable. Final Linux clean/prior-schema/integrity/FK/data-preservation scenarios passed locally only. | Current production graph/whole namespace and complete native recovery evidence, then specific forward-migration authorization. |
| preflight | **FAIL** | Current authorized Vercel production export lacks LEADZEN_DASHBOARD_PUBLIC_URL; available sensitive values unusable for safe probe. Current VM config/schema/storage/key equality remain UNVERIFIED. | Obtain current VM read-only access; privately reconcile required origin, service-token and configuration verification. |
| production_build | **PASS** | Clean Python wheel, Node 24 optimized standalone (darwin/arm64 local verification), no-cache Linux amd64 backend image. Exact Vercel/prebuilt target artifact remains externally BLOCKED. | Exact Vercel/prebuilt Linux platform artifact and deployment contract remain external controls; local standalone is verification-only. |
| secret_current | **PASS** | Exact final source archive Gitleaks full redaction: zero findings. Historical credentials separate. | Require the pinned scan for future release changes; historical disposition remains separate. |
| startup | **PASS** | Exact Linux amd64 backend UID 1000, with no pip, pytest or Ruff, invalid config rejected before DB creation; real synthetic Gunicorn readiness +trusted HTTPS standalone run Node 24. | Actual-host runtime/configuration still governed by blocked preflight/target gates. |
| target_capacity | **BLOCKED** | Final local Linux amd64 emulated native-volume workload: 4 employees, 20,000 contacts, 256 requests, 32 writes, concurrency 16, 0 errors,p95 1060ms. Actual CPU/RAM/storage/proxy budgets unknown. | Provide intended CPU/RAM/storage/proxy architecture and approved budgets; authorize isolated workload there. |
| typecheck | **PASS** | tsc --noEmit and fatal Ruff F821/F822/F823/E9 passed; not general Python typing or ESLint certification. | No unresolved fatal/type-check failure; broader tools are not certified. |

The actual final release CLI and historical deploy wrapper both returned
**exit 2 / BLOCKED**, with all 17 categories present, **7 PASS / 2 FAIL / 8 BLOCKED**, ten
not-passed gates, zero missing gates and zero invalid local attestations.
[Gate result](production-crosscheck-release-gate-2026-10-04.json). Schema 2 PASS
attestations are bound to retained evidence bytes and expire within 24 hours;
they are operator attestations, not independent signatures/certification.

## 5. Security and credential review

Authentication/session/invitation/MCP token tests, employee authorization/IDOR,
real private-file routing/revoked workers, CSRF/no-store/cookies, provider action
approvals/STOP/duplicate-send/uncertain-operation holds all passed in the final
available regression scope. No feature, consent, sender suppression or spending
approval was removed. Current logging tests retain safe categories without
credentials/personal/provider payloads. Real provider/client behavior remains
blocked. Product absences documented in the original audit are unchanged.

The exact-source Gitleaks scan had zero findings. Historical ownership/revocation
is separate: [43 per-location dispositions](production-credential-disposition-2026-10-04.json)
record service, owner if known, file/line/commit, reusable-secret classification
and precise administrative remediation, without values. Three scanner false
positives are separate. No questionable credential was tested. Deleting source or
cleaning history cannot invalidate old material. Preserve the existing settings
key with matching complete recovery; any actual rotation needs a separately
approved compatibility/re-encryption/recovery procedure. Signing-key recovery is
also required and cannot be inferred from the older archive.

Fresh npm, 94 Python runtime and 7 builder advisory checks returned zero package
advisories. The exact-image complete scan retains **0 CRITICAL, 44 HIGH, 61 MEDIUM,
60 LOW, 2 UNKNOWN**. The 89 OS package inventory matches the earlier reviewed image;
44 HIGH binary matches cover eight distinct CVEs, and none has a fixed version in
this fresh scanner report. Fresh inspection confirms mount/nsenter/infocmp present,
systemd-homed and Perl Archive::Tar absent. This limits some described paths but
is not a blanket non-exploitability claim. The
[previous scoped OS review](production-completion-os-review-2026-10-04.md) is
supported by the current inventory/reachability comparison retained privately.
No risk waiver was added; actual-host privileges/mounts remain unknown.

## 6. Database and recovery review

The inspected graph remains accounts0004/config0019 with dependency migrations.
Final Linux clean and prior-schema scenarios passed data preservation, physical
schema/system/migration checks, integrity/FKs and isolation. Stronger native
backup/restore tests now verify original records and actual post-upgrade
ciphertext across every restored database before synthetic auth. Counts reflect
measured original/encrypted records and databases rather than constant PASS flags.

Actual current production recovery remains **BLOCKED**. The authorized October 3
historical archive evidence is scoped and incomplete: control plus one employee,
matching decryptable settings/mailbox, but missing stable signing key/current full
inventory/runtime/custody. It does not close this gate. Scheduled services/timers
are prepared and uninstalled; the backup intentionally leaves intake held/services
stopped until operator reconciliation. Installation needs approved storage,
staffed maintenance/resumption and failure alerting. No live checkpoint/migration
or partial production restoration was performed.

## 7. Infrastructure, capacity and integration review

Read-only current Vercel project/deployment metadata reports Node 24.x; local
Node 24.21.0 clean verification now matches that major. Exact sensitive plaintext
origin/service-token equality is not established. A fresh authorized production
export lacks `LEADZEN_DASHBOARD_PUBLIC_URL` and cannot supply usable configuration
for a bounded safe public API probe; no credential request was transmitted. Its
export limitation is not proof of an endpoint failure. Actual VM architecture,
loaded environment/units, persistent filesystem, all schemas, private ingress and
trusted proxy remain **UNVERIFIED**.

[GitHub observations](production-crosscheck-github-controls-2026-10-04.json):
upstream eracle/OpenOutreach access is pull-only, protection returned 404 and
rulesets returned 0; the owning release repository/enforcement is not established.
[Vercel controls](production-crosscheck-vercel-controls-2026-10-04.json):
create-deployment/fast-lane options appear enabled, but no Git link/check records
were shown. That is not proof of active automatic deployment or required-check
protection. Pinned workflow syntax passed Actionlint; GitHub execution/enforcement
and platform promotion are separate blocked gates.

Final isolated native-volume workload used 4 employees × 5,000 contacts, 16 concurrent
clients, 256 requests / 32 writes: **256 HTTP 200 responses, zero errors, intact
integrity, p95 1,060 ms, 42.74 requests/sec, maximum response 14,202 bytes**. It ran on local emulated Linux amd64,
with other verification activity, and is not an intended-host SLO certificate.
Earlier 633/837 ms samples are retained separately; no benchmark was hidden or
used to invent capacity budgets. No unmeasured performance refactor was made.

Local alarm delivery/dedup/timeout/redaction tests passed. Real on-call receipt,
independent missed-monitor coverage and installed timers remain blocked.
Prepared provider/client operations and limits are in
[integration instructions](production-integrations.md); private sandbox identities,
recipients/client selection and exact approved send/spend/consent actions are still
needed. Do not retry an ambiguous external effect to make a test pass.

## 8. Browser and accessibility evidence

The final exact standalone archive was extracted for staging. Its actual listener
loaded the checksum-verified Node 24 binary. Trusted HTTPS used normal certificate
validation and provider-disabled generated fixtures. Login/logout/private redirect,
contact create/edit/delete, settings save/reload, mobile 375 × 812 layout without overflow,
navigation/keyboard 2 px focus, sampled text contrast 19.13, overlapping employee IDs
and denial of an existing foreign sentinel were executed.
[Browser scope](production-crosscheck-browser-2026-10-04.json).

Bounded final-tab console read captured 0 warnings/errors. Fresh denied-contact
reload network evidence was untruncated: 31 responses, one expected contact 404,
zero unexpected HTTP/uncanceled transport failures, four canceled requests;
Chat context responses were 200. Broader earlier workflow network capture is not claimed
complete. HTTP tests verified Secure/HttpOnly/SameSite=Lax/Path cookies,
foreign-origin 403, private health/readiness 200, anonymous 401, HSTS/nosniff/referrer,
no-store/no-transform and all 11 scripts matching the response CSP nonce; no unsafe-eval.
The fixture recorded 0 blocked external calls. Active CSP attack probes and broad
screen-reader/contrast certification remain unperformed/unverified.

Full invitation/setup/new-password/onboarding and genuine client consent are not
marked passed. The Computer Use confirmation policy explicitly requires user
handoff **before any new authentication credential is entered**, with entry,
confirmation and submission done by the user. A human-controlled CI/local runner
can execute the prepared full five-scenario suite; the agent did not use another
browser tool or shell automation to bypass this restriction.

The final trusted synthetic staging tab is prepared at
[password handoff](https://temple-discounted-comparing-leu.trycloudflare.com/password).
The existing temporary password is entered and masked; both new-password fields
remain empty. The user must enter, confirm and submit a disposable password, then
sign in again themselves. This is a generated non-production account; providers
remain disabled. The transient staging URL is not a production deployment.
[Handoff screenshot](ui-progress-assets/production-crosscheck-password-handoff-2026-10-04.png).

## 9. Exact verification commands and results

Set `base` from `docs/production-crosscheck-2026-10-04-work-dir.txt` and
`candidate="$base/candidate-crosschecked-final-20261004"`; run artifact commands
from `candidate/source`. Private executable scripts retained in candidate evidence
contain the full pinned install/build commands. The durable directory retains
source/locks/artifacts/evidence, not installed dependency/cache directories.

| Check | Exact command | Result/scope |
| --- | --- | --- |
| backend clean install/build/full test | `bash "$base/verify-crosscheck-backend.sh"` | **PASS** — 1,649 passed, 1 warning, 526.33 seconds; fresh builder/runtime hashes + installed same-source wheel |
| frontend clean install/typecheck/test/build | `bash "$base/verify-crosscheck-frontend.sh"` | **PASS** — Node 24.21.0; npm ci, tsc, 1,196 tests in 26 files in 39.50 seconds, npm advisories 0, optimized Next 16.3.8 build |
| no-cache image build/save | `bash "$base/verify-crosscheck-image.sh"` | **PASS** — Linux amd64 pinnedbase; actual image/archive/scan binding PASS |
| fatal Python lint | `uv tool run --from ruff==0.16.10 ruff check --select F821,F822,F823,E9 leadzen tests` | **PASS** — No fatal lint findings; not whole Python typecheck certification |
| Python advisory feeds | `uv tool run --from pip-audit pip-audit -r requirements-production.lock --no-deps --disable-pip --format json --output "$candidate/evidence/runtime-dependency-audit.json"; same command with requirements-build.lock` | **PASS** — 94 runtime + 7 builder, zero findings |
| current-source secret scan | `docker run --rm -v "$candidate/source-scan:/repo:ro" -v "$candidate/evidence:/evidence" ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f dir /repo --redact=100 --report-format json --report-path /evidence/current-secrets.json` | **PASS** — Exact source.tar extraction, zero findings; historical disposition separate |
| complete actual-image advisory scan | `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$candidate/evidence:/evidence" -v leadzen-trivy-cache:/root/.cache/trivy aquasec/trivy@sha256:bcc376de8d77cfe086a917230e818dc9f8528e3c852f7b1aff648949b6258d1c image --timeout 20m --no-progress --scanners vuln --format json --output /evidence/image-advisories.json leadzen:crosschecked-final-20261004` | **PASS** — Execution passed; scan Metadata.ImageID, archive config and actual Docker ID all match; risk FAIL separate |
| image risk gate | `python -m leadzen.operations.advisories "$candidate/evidence/image-advisories.json" --image-id sha256:ba1bafae3d354891897035dd528d7ecfcea983025af7b30ca67390797f5b6947 --architecture linux/amd64 --decisions docs/production-image-risk-decisions.json --output "$candidate/evidence/image-assessment.json"` | **FAIL** — Exit 1, 44 unaccepted HIGH; complete findings retained |
| Linux isolation/revocation | `docker run --rm --network none --platform linux/amd64 -e DJANGO_SETTINGS_MODULE=leadzen.settings -e LEADZEN_ENV=production -e LEADZEN_ALLOWED_HOSTS=testserver -e LEADZEN_WORKSPACE_ROOT=/app/data/workspaces -v leadzen-crosscheck-final-isolation-20261004-f3498c95:/app/data -v "$candidate/source/tests/scenarios:/verification:ro" leadzen:crosschecked-final-20261004 /opt/venv/bin/python /verification/accounts.py` | **PASS** — Disposable owned native volume, real private files/routing/auth/worker settings/Chat revocation |
| Linux clean/prior migrations | `docker run --rm --network none --platform linux/amd64 -v "$candidate/source/tests/scenarios/production_migrations.py:/verification/migrations.py:ro" leadzen:crosschecked-final-20261004 /opt/venv/bin/python /verification/migrations.py /app/data/migration-drill` | **PASS** — Clean + prior record preservation, integrity/FKs, system checks, no drift; no actual production DB |
| local native-volume capacity | `docker run --rm --network none --platform linux/amd64 -e LEADZEN_CAPACITY_NETWORK_ISOLATED=1 -v leadzen-crosscheck-final-capacity-20261004-f3498c95:/app/data -v "$candidate/source/tests/scenarios/production_capacity.py:/verification/capacity.py:ro" leadzen:crosschecked-final-20261004 /opt/venv/bin/python -c 'from pathlib import Path; import runpy,sys; Path("/app/data/leadzen-capacity.final-crosscheck").mkdir(mode=0o700); sys.argv=["/verification/capacity.py","--root","/app/data/leadzen-capacity.final-crosscheck","--employees","4","--contacts","5000","--concurrency","16","--requests","256"]; runpy.run_path(sys.argv[0],run_name="__main__")'` | **PASS** — 256 HTTP 200 / 32 writes / 20k contacts / concurrency 16 / integrity true; p95 1,060 ms; actual host BLOCKED |
| trusted exact-archive staging | `PATH="$base/node24/node-v24.21.0-darwin-arm64/bin:$PATH" "$candidate/verification-env/bin/python" dashboard/e2e/stage.py --authorize-public-synthetic-fixture --standalone "$candidate/standalone-tested"` | **PASS** — Extracted exact standalone archive, actual Node 24 binary loaded, TLS verified, providers disabled, 0 blocked external calls |
| HTTP/cookie/CSRF/nonce readiness | `python3 "$candidate/evidence/trusted-http-checks.py"` | **PASS** — Allcookieattrs,foreignOrigin403,privatehealth/ready200anonymous401,11nonce-matching scripts; noactive CSPattackprobe |
| real browser subset | `cua_repl native/DOM browser operations against exact trusted synthetic candidate` | **PASS** — Login/logout/private route/CRUD/settings/mobile/focus/19.13 contrast/foreign sentinel denial; bounded network and console scopes explicit |
| full five browser scenarios | `python dashboard/e2e/stage.py --authorize-public-synthetic-fixture --standalone "$candidate/standalone-tested" --test` | **BLOCKED** — Not executed by agent; new password/setup handoff or user-controlled runner required |
| Compose/shell/git | `docker compose -f local.yml config --quiet; bash -n entrypoint/start/deploy-accounts.sh individually; sh -n backup-safe; git diff --check in originalcheckout` | **PASS** — Every actual command separately exit 0; initial Gitcheck in non-Git archive failed 129 and was corrected, not counted as PASS |
| workflow syntax/types | `official checksum-verified actionlint1.7.12 -color -shellcheck= -pyflakes= .github/workflows/*.yml` | **PASS** — 0 findings; pinned official commit references; actual GitHub jobs/enforcement UNVERIFIED |
| release gate | `python -m leadzen.operations.release gate "$candidate" --checks "$candidate/release-checks.v2.json"` | **BLOCKED** — Actual CLI exit 2, no missing/invalid attestations, 10 not-passed gates; refusal control works |
| deployment wrapper | `LEADZEN_RELEASE_PYTHON="$candidate/verification-env/bin/python" bash compose/leadzen/deploy-accounts.sh "$candidate" "$candidate/release-checks.v2.json"` | **BLOCKED** — Actual wrapper exit 2, no live action |

Compared with the previous completed candidate, backend coverage is 1,475 → 1,649
(+174 collected cases); frontend remains 1,196. One existing PydanticAI event-loop
deprecation remains visible. The intermediate superseded suite was interrupted,
not counted. An initial Git diff check in the intentionally Git-free source copy
failed with wrong working directory; all actual shell/Compose checks and corrected
original-checkout Git diff check were individually rerun and passed.
The initial durable-copy attempt also failed safely on an older system-Python
archive API; its partial staging is preserved. The completed copy used verified
Python 3.12.11 and separately verified every source/archive/artifact/evidence hash.

## 10. Production environment variables

Required backend names only:
`LEADZEN_ENV`, `LEADZEN_DB`, `LEADZEN_WORKSPACE_ROOT`, `LEADZEN_SETTINGS_KEY`,
`LEADZEN_SECRET_KEY`, `LEADZEN_DASHBOARD_TOKEN`, `LEADZEN_ALLOWED_HOSTS`,
`LEADZEN_PUBLIC_URL`, `LEADZEN_DASHBOARD_ORIGINS`.

Required dashboard server names only:
`LEADZEN_API_URL`, `LEADZEN_API_TOKEN`, `LEADZEN_DASHBOARD_PUBLIC_URL`.

`NODE_ENV` is host-injected. Full purposes/required/conditional/optional/internal
classification, dynamic allowlists and operations/test-only inputs are in
[environment inventory](production-environment.md). Saved per-employee provider
credentials are protected settings, not global/public browser variables. Feature
scope booleans must be explicit; an excluded policy feature does not turn off
routes or authorize automation. Service-owner600 matching config copies and stable
keys are mandatory for the reviewed operations tools. No secret values appear here.

## 11. Deployment and rollback checklists

The shipped [controlled release runbook](production-release.md) contains the exact
prepared preflight/hold/drain/stop/full matched backup/independent verification/isolated restore/
forward migrate/readiness/gate/resumption commands, including MCP workers and
residual-WAL handling. They are prepared operator actions, not authorization.

1. Obtain current target/unit/storage/private config/release inventory and owning
   platform/repository controls; close every gate with same-candidate fresh evidence.
2. Verify source + three frozen artifacts and current configuration. Preserve stable
   keys. Do not replace the tested artifact with a fresh platform build.
3. Hold intake and API/MCP/scheduler dispatch; drain tracked streams/workers/pass
   gaps. Stop reviewed writer units only after drain; backup then proves inactive
   units/zeroPID/emptycgroups. Leave ambiguous operations held.
4. Create and independently verify a **current complete native matched recovery**
   set before migrations; retain keys/env/dashboard/proxy/runtime/unit bytes privately.
5. Restore/drill isolated copies with outbound denial; validate all original records,
   relationships/decryption/auth/isolation. Run forward-only whole-namespace migration
   under the stopped-writer/recovery contract, then full preflight/readiness.
6. Stage exact runtime/artifacts, test critical flows/isolation, run release gate,
   and promote only after approved target-specific cutover and every gate PASS.
7. Reconcile uncertain effects; release intake and resume scheduling only under
   explicit reviewed authorization. Observe configured alerts and recovery freshness.

Rollback: keep intake/scheduling/MCP held, drain reviewed writers, then stop reviewed
units, preserve
incident evidence/full consistent snapshot, and reconcile accepted/unknown external
operations. Frontend-only rollback selects the previous immutable compatible
artifact; backend-code rollback requires forward-schema compatibility. If data
restoration is needed, verify the **complete** matched set, restore all databases
and keys into a new absent isolated path, drill and reconcile legitimate post-backup
writes before a coordinated operator cutover. Never reverse destructive migrations,
partially restore one employee/control DB, overwrite live storage, or blindly resume.
Actual target-specific runtime-pointer/Vercel promotion and rollback commands remain
BLOCKED until the current inventory/access/authorization is supplied; none was guessed.

## 12. Final verdict and only remaining requirements

**NOT APPROVED for real-user/customer-data production deployment.** Local durable
fixes and final available verification are complete. Remaining requirements are:
current VM/platform/release-repository access and configuration decisions; historical
credential owners/receipts; current authorized matched full independent recovery;
OS risk owner/patch decisions; user-controlled complete browser credentials/setup;
exact alarm destination+confirmed receipt; intended-host capacity budgets/workload;
enabled sandbox/real-client scope with recipients and bounded approved spend/send;
and explicit reviewed deployment/migration/promotion/rollback authorization.
These are specific gates in the table, not implied approvals or generic suggestions.
