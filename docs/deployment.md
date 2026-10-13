# LeadZen production deployment

LeadZen is Zyene's internal tool for outreach about its products and services,
not the Zyene Reviews company.

The most recent deployment is the **October 13, 2026** release of `0273acb`,
below. An earlier October 13 release of `42e9bbc` was not recorded here; it was
the runtime replaced by this one. The October 12 and October 8 records follow. It was recorded by the operator who performed it and copied here
on October 12 from the closed Zyene-Inc/leadzen#10; it has not been re-verified
against the live VM since. Every section is dated evidence, not a current
live-state guarantee or continuing authorization to deploy, send emails or spend
provider credits. Follow the
[October 4 production audit](production-readiness-audit-2026-10-04.md) for
release requirements.

## October 13, 2026 — backend, database and dashboard `0273acb`

**Source released:** `main` at `0273acb` (Merge PR #18: bulk email lookup, AI
follow-ups, Results analytics, simpler Workspace UI). No dependency changes from
`42e9bbc`. Wheel SHA-256
`f7724daa6d26a77af1cbf7d6299987d3ea64d3e2c7757cb373403aa58c2bde7b`.

**Verified before release (live VM):** `42e9bbc` at `/opt/leadzen-42e9bbc-20261013`
with `/etc/leadzen-42e9bbc.env`; control database at `leadzen_config.0024`.

**Recovery points:** VM snapshot `leadzen-api-pre-0273acb-20261013` (READY);
on-VM backup `/srv/private/leadzen-pre-upgrade-0273acb-20261013` (data after WAL
checkpoint, env file, both unit files); previous runtime
`/opt/leadzen-42e9bbc-20261013` left untouched with its unmigrated data.

**Cut-over:** staged `/opt/leadzen-0273acb-20261013` (copied venv, replaced the
`leadzen` package); created `/etc/leadzen-0273acb.env` (root 600, paths
updated); stopped both services; checkpointed (integrity `ok`) and backed up;
copied data; import smoke test; migrated control and the one workspace
(`97bd43a2-…`) to `0025_campaignsend` as the service user with Autopilot and
follow-ups forced off (integrity `ok`; backfill attributed 1 earlier campaign
send in the workspace); pointed both units at the new runtime. Downtime about
two minutes. A first attempt stopped at the smoke test because the service user
cannot read the root-only env file; the old runtime was restarted unchanged
after about one minute, and the script now loads the env file as root.

**Vercel:** the `main` push built `0273acb` for production and
`leadzen.zyene.com` took it automatically (`autoAssignCustomDomains` on).

**Production verification:** both services active, zero restarts, no warnings
in the journal; authenticated `/api/health` and `/api/ready` 200; anonymous
public API 401; dashboard login 200. Signed-in browser check as the employee:
Results showed live figures (1 sent, 1 reply) and Leads showed the new counts.
No email was sent and no paid lookup was made during the release.

**Rollback path:** stop services → restore the two unit files from the on-VM
backup (they point at `/opt/leadzen-42e9bbc-20261013` and its env file) →
`systemctl daemon-reload` → start. Or recreate the VM from the snapshot.
Migration `0025` only adds a table, so the older runtime runs on it unchanged.

## October 12, 2026 — backend and dashboard `1fb9799`

**Source released:** `main` at `1fb9799` (PRs #11 outreach safety, AI Ark billing
and provider search targeting; #12 AI connection probe timeout; #13 docs). Wheel
SHA-256 `e44b12a052bcad78d4ce9978071851ca993aef1b5c77e5205643f1e077857225`;
`pydantic-ai-slim` and `pydantic-graph` 2.52.0 → 2.53.0 (CVE-2026-107286), both
verified against `requirements-production.lock` hashes.

**Verified before release (live VM):** `b6f350c` at `/opt/leadzen-b6f350c-20261008`
with `/etc/leadzen-b6f350c.env`; control and the one initialized workspace
(`97bd43a2-…`) at `leadzen_config.0020`, integrity `ok`; October 8 snapshot and
on-VM backup present. Vercel `leadzen.zyene.com` still served the October 7 build.

**Recovery points:** VM snapshot `leadzen-api-pre-1fb9799-20261012` (READY);
on-VM backup `/srv/private/leadzen-pre-upgrade-20261012` (data after WAL
checkpoint, env file, both unit files); previous runtime
`/opt/leadzen-b6f350c-20261008` left untouched with its unmigrated data.

**Cut-over:** staged `/opt/leadzen-1fb9799-20261012` (copied venv, replaced
`leadzen` and the two pydantic packages); smoke-tested imports and production
environment validation; stopped both services; checkpointed and backed up;
copied data; created `/etc/leadzen-1fb9799.env` (root 600, paths updated);
migrated control and workspace databases to `0021_search_plan` as the service
user with Autopilot/follow-ups forced off (integrity `ok`); pointed both units at
the new runtime. Downtime about 2–3 minutes.

**Post-release changes:** removed `LEADZEN_MAIL_HOSTS=*` and
`LEADZEN_EMAIL_HOSTS=*` (copy kept at `/etc/leadzen-1fb9799.env.pre-mailhosts-20261012`).
They were not wildcards — `approved_host` compares literal names — so they had no
effect; Zoho hosts are in the built-in allow-list. Restarted the follow-ups
scheduler (Autopilot and automatic follow-ups flags remain `1`).

**Vercel:** promoted `dpl_EU3u4kNzsUEmTyrZZT3SSvaEC37c` (`1fb9799`) to
`leadzen.zyene.com` and re-enabled the project's `autoAssignCustomDomains`, which
an earlier rollback had left off, so later production builds take the domain.

**Production verification:** authenticated `/api/health` and `/api/ready` 200
(database and migrations OK); both services active with zero restarts and no
warnings since release; public login 200; anonymous API 401. Operator-requested
tests to an internal inbox: invitation path through Resend (verified
`leadzen.zyene.com` sender) accepted; the employee mailbox SMTP and IMAP login
passed and one labelled test email was accepted by Zoho; BetterContact Lead
Finder with the employee key and saved Target filters (United States, 1-10,
nine seniorities) returned a US profile with enrichment off and nothing stored.

**Open item:** the employee's AI provider key (`openai_compatible`,
`api.akashml.com`, model `moonshotai/Kimi-K3`) returns 401 on both the old and
new runtime. Until it is replaced in Settings, AI qualification, search-plan
seeding and Autopilot drafting fail safely; the first real BetterContact
discovery (which archives legacy finder state) was therefore not run.

## October 8, 2026 — backend `b6f350c` (selectable lead providers)

**Source released:** `main` at `b6f350c` (Merge PR #9, selectable AI Ark /
BetterContact providers). Source archive SHA-256 of the wheel uploaded to the VM:
`3f451961b8541e9fe226da8676d312f5970e6ba677358fd1f348cde4ea196a88`.

**Vercel frontend:** already current — `leadzen.zyene.com` was serving
deployment `dpl_8sGCGAoK4qSq1rMoMG9iWhvzf14p` built from `b6f350c` **before**
this backend release, so no Vercel action was required.

**Google VM:** `leadzen-api` (`zyene-reviews`, zone `us-central1-a`).

**Pre-release safety:**
- VM snapshot: `leadzen-api-pre-b6f350c-20261008` (READY, 3.78 GB, created
  2026-10-08T10:33Z). Boot disk `openoutreach-api`.
- On-VM backup: `/srv/private/leadzen-pre-upgrade-20261008` (7.1 MB). SQLite
  integrity verified `ok` on the control DB and the only initialized workspace
  (`97bd43a2-0025-4e48-b9f1-dcd4b796c331`). Services were restarted inactive
  within ~6 seconds for the backup and confirmed healthy before continuing.

**Cut-over steps taken:**
1. Built wheel `leadzen-0.1.0-py3-none-any.whl` from local `HEAD` (= `b6f350c`).
2. Uploaded to VM `/tmp/` over `gcloud compute scp` (SSH managed via
   `gcloud compute config-ssh` with project `zyene-reviews`).
3. Staged runtime at `/opt/leadzen-b6f350c-20261008` by copying the existing
   compatible venv and extracting the wheel into its `site-packages`. Verified
   migration `0020_lead_finder_provider.py` present.
4. Stopped services, copied `/opt/leadzen-f1d8cfe-20261006/data` to the new
   runtime, copied env file to `/etc/leadzen-b6f350c.env`, updated hard-coded
   paths (`LEADZEN_DB`, `LEADZEN_WORKSPACE_ROOT`, `LEADZEN_PUBLIC_URL`) to the
   new runtime location. Restarted.
5. **Detected and fixed** a real regression introduced during cutover: the
   follow-ups scheduler logged `Workspace follow-up worker failed (exit code 1)`
   after the first restart. Root cause: `LEADZEN_DB` and `LEADZEN_WORKSPACE_ROOT` still
   pointed at the old runtime directory, so the worker could not see the
   workspace database. Fixed via `sed` on the env file; services restarted;
   the scheduler is silent in subsequent minutes (no due work).
6. **Migrations** — control DB already at `0020` (applied during a pre-flight
   `django check`); workspace DB upgraded from `0019` → `0020_lead_finder_provider`
   via `python -m django migrate --no-input` against the workspace SQLite file.
   Verified via `PRAGMA integrity_check = ok` and post-migration listing.

**Post-cutover verification:**
- `systemctl is-active leadzen.service` = active; `leadzen-followups.service` = active.
- Anonymous `GET https://leadzen-api.zyene.com/api/health` and `/api/ready` → **401**.
- `GET https://leadzen.zyene.com/login` → **200**, still serving deployment
  `dpl_8sGCGAoK4qSq1rMoMG9iWhvzf14p` (no Vercel change required).
- `GET https://leadzen.zyene.com/api/proxy/health` anonymous → **401**.
- Static assets (woff2 font, brand PNG) → **206 Partial Content** with correct
  `content-type` — the directive, CSP nonce and HSTS headers all present.
- No recent ERROR-level entries in either service's journal.

**Not exercised:** admin login (`support@zyene.com` secret lives outside the
repository), any outbound email, real BetterContact/AI Ark paid request,
real inbox placement, or browser-driven full HTTPS journey. The single-use
automation that owns those flows still requires fresh, scoped approval.

**Rollback path:** stop services → restore `/srv/private/leadzen-pre-upgrade-20261008`
to `/opt/leadzen-b6f350c-20261008/data` and `/etc/leadzen-b6f350c.env` →
point `leadzen.service`/`leadzen-followups.service` back to
`/opt/leadzen-f1d8cfe-20261006` via the previously-copied unit files → start.
Or recreate the VM from snapshot `leadzen-api-pre-b6f350c-20261008`. Migration
`0020` only adds a column and a new table; the schema is forward-compatible
for roll-back on the older runtime.

### Post-release opt-in flags enabled — same day, 17:50 UTC

Following owner approval, these optional flags were added to `/etc/leadzen-b6f350c.env`
(previous values preserved at `/etc/leadzen-b6f350c.env.pre-enables-20261008`):

```
LEADZEN_AUTOPILOT_ENABLED=1
LEADZEN_MAIL_HOSTS=*
LEADZEN_EMAIL_HOSTS=*
LEADZEN_MCP_PUBLIC_URL=https://leadzen-api.zyene.com
LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS=https://leadzen.zyene.com
```

- `production.py` fail-closed validation passed.
- Both services restarted and stay active; scheduler has no errors since restart.
- Autopilot code path confirms `enabled() = True`; zero Autopilot policies in DB.
- **What changes for employees:** each employee can now authorize Daily Autopilot
  in `/outreach`; the first `AutopilotRun` is created during their next
  New-York 10:00–12:00 kickoff window if no blockers exist (mailbox, target,
  product, BetterContact, AI Ark not selected — AI Ark is still
  blocked-at-autopilot by design). First email paced within 10:00–17:00 NY.
- **Security note (added October 12):** `*` disables the mail/email host allow-lists, so
  the server may connect to any SMTP/IMAP/email API host an employee enters. Restrict
  these to the real providers before relying on them.
- **What did NOT change:** no real emails have been sent; no paid provider call
  has been made; admins must still send invitation emails manually
  (`LEADZEN_RESEND_API_KEY` remains unset until an operator supplies one).

## Earlier dated evidence

## Application addresses recorded on October 3

- Employee login: https://leadzen.zyene.com/login
- Administrator: https://leadzen.zyene.com/admin
- Support and first administrator: `support@zyene.com`
- Vercel project: `zyenes-projects/leadzen-dashboard`
- Google Cloud project: `zyene-reviews`
- Existing VM: `leadzen-api`, `us-central1-a`, `e2-micro`
- API: `https://leadzen-api.zyene.com`

The administrator creates employee accounts. Employees receive a one-use setup
link, choose their own password, and complete onboarding. There is no public
signup. No outreach campaign was started during this deployment.

## Last documented deployed release — 3 October 2026

### Approved follow-up activation and complete logo

The owner explicitly requested enabling automatic follow-ups and using the
complete attached LeadZen by Zyene logo. The existing VM now has the reviewed
`leadzen-followups.service` installed, **active**, and **enabled on boot**.
`LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED=1` is present in both the scheduler and API
process environments; the API was restarted and authenticated public HTTPS
health returned **200**. All other environment values, including the stable
encryption key, were preserved. The prior environment is retained root-only at
`/etc/leadzen.env.pre-followups-20261003T160856Z`.

Preflight found **1** active onboarded employee workspace, **0** approved
automatic campaigns/recipients, and **0** queued/running outreach jobs. A bounded
pass against that existing workspace exited **0**. Subsequent checks found both
services active with **0** scheduler restarts. No campaign approval was created,
no email was sent, and no live AI or paid enrichment request was made.
Automatic messages still require review and approval of the exact recipients
and remaining sequence; they run 9 AM–5 PM weekdays in the campaign timezone
and stop on replies, suppression, stopped sequences, or changed approvals.

The shared `Brand` component now displays the complete artwork, including its
byline, instead of the earlier compact wordmark plus separate native text.
`leadzen-by-zyene-approved-light.png` is an unchanged copy of the owner's latest
attachment (SHA-256
`56ad327372392beb9795548b2cddd5153bfca9cef176e75a58da66e9d3d11bac`).
The existing complete dark variant is used in dark mode. Existing logo assets
and favicon remain preserved.

Vercel deployment **`dpl_GmNa3MiHoPVsXHHSntmyX4BA5GUM`** is **READY**, was
promoted, and inspection of `leadzen.zyene.com` resolves to this deployment.
Candidate: `https://leadzen-dashboard-eh3cq9dvy-zyenes-projects.vercel.app`.
The immutable frontend snapshot and source manifest are retained privately at
`/Users/ashishdikonda/.codex/private/leadzen/releases/20261003-followups-logo/`.
Only the shared logo component, its CSS, public-asset coverage, and the newly
added attachment changed from the prior reviewed application source.

Validation: **898 backend tests**, **972 dashboard tests**, TypeScript, local
optimized build, and Vercel build passed. The focused automatic follow-up and
branding run passed **45** tests. React Doctor's changed-files scan returned
**100/100**. Production logo files load on login and the authenticated sidebar.
A temporary document-only dark theme verified the reversed artwork; no saved
theme preference changed. The authenticated header fits a 390-pixel viewport
without horizontal overflow, and the viewport was restored after verification.

Public proof: `docs/brand-assets/leadzen-approved-logo-production-2026-10-03.png`,
`leadzen-approved-logo-dark-2026-10-03.png`, and
`leadzen-approved-logo-mobile-2026-10-03.png`.

### Earlier full application release

The owner freshly authorized deployment to the existing Google Cloud and Vercel
projects. The current local application was uploaded from reviewed snapshots;
no Git commit, upstream GitHub push, reset, or stash was performed. Uncommitted
application work remains intact, including Workspace/Chat, reviewed outreach,
the setup wizard, the neutral Zyene theme, light/dark controls, and the new
LeadZen logo, “by Zyene” attribution, and favicon.

- Production deployment: `dpl_Fgn3pzTPHeSXnLgtN4ydfXDtzVpW`, **READY**.
- Candidate: `https://leadzen-dashboard-gousdko96-zyenes-projects.vercel.app`.
- Vercel promotion succeeded. The project overview shows this deployment with
  `leadzen.zyene.com` and `leadzen-by-zyene.vercel.app`; inspecting the custom
  production domain resolves to the same deployment ID.
- Local backend suite: **898 passed**, one existing Pydantic AI deprecation
  warning. Dashboard suite: **972 passed**, including the existing repeated
  control checks. Fresh dependency install, TypeScript checks, optimized local
  build, and Vercel production build passed. These counts describe the uploaded
  dirty-source snapshot, not a committed revision.
- Both the control database and the existing employee workspace database passed
  integrity checks before and after migration. Both now include
  `leadzen_config.0014_workspacecontext_chatthread_context_and_more` and
  `leadzen_accounts.0002_accountprofile_tour_completed_at_employeeinvitation`.
- Every original table's existing records and columns were compared with the
  recovery backup. They match; Django added expected content types and
  permissions without changing existing framework rows. Production environment
  values and the stable encryption key were preserved. The only environment
  update was `LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED=0`.
- Authenticated public HTTPS API health returned **200**. Anonymous and
  service-token-only requests for employee overview data returned **401**.
  Direct Django framework checks returned **0 errors and 0 warnings**. The
  dependency overrides the CLI `check` command with discovery readiness checks;
  that command was not used as framework-check evidence.
- All **68** deployed source files and **65** installed package files match the
  reviewed backend archive and wheel. Synthetic Groq/OpenAI model constructors
  passed without sending any inference requests.
- Candidate and production administrator sign-in rendered the actual team
  accounts. Anonymous production visits to Workspace, Chat, leads, campaigns,
  settings, and administration redirect to login. Seven production brand assets
  match the local files byte-for-byte, including favicon and both logo themes.
- `leadzen.service` is active; `leadzen-followups.service` is inactive. No
  invitation, mailbox sync, campaign email, discovery request, paid enrichment,
  or live AI request was executed during release verification.

Backend source archive SHA-256:
`1276fb1cea19de09235b581327bd4d82b8eff7f60bc1dd07f56d4b83c225ac68`.
Backend wheel SHA-256:
`d063dd247a08ada16a4422aaa29a8c94a82cd5e1ed5a6da16334579555a01961`.
Reviewed backend bundle SHA-256:
`1b3fffa78ad494dd28ec4c1782dc84ee2480042495f6f1a42a430f81584011b2`.
The complete frontend source manifest is retained with the private release
snapshot; no application source drift was detected after deployment.

Production screenshots: `docs/brand-assets/leadzen-production-login-2026-10-03.png`
and `docs/brand-assets/leadzen-vercel-production-2026-10-03.png`. The authenticated
administrator screenshot and release logs are in the owner-only release folder.

### Recovery point recorded on October 3

Before migrations, intake and workers were stopped. The complete previous
application, installed dependencies, configuration, service definitions, and
consistent SQLite backups were archived. An independent Cloud Shell copy was
verified before upgrading; a local owner-only copy was subsequently verified.
Both copies passed **23,856 file checksums and 2 database integrity checks**.
SQLite backups are standalone snapshots; local validation used immutable
read-only mode so SQLite does not require live WAL sidecars.

- VM recovery directory: `/opt/leadzen-release-backup-20261003.Y66bzF`.
- VM recovery archive: `/opt/leadzen-release-backup-20261003.Y66bzF.tar.gz`.
- Additional installer backup: `/opt/leadzen-accounts-backup.EeCaPt`.
- Independent Cloud Shell archive:
  `/home/zyene_inc/leadzen-release-backup-20261003.Y66bzF.tar.gz`.
- Independent local archive, mode 600:
  `/Users/ashishdikonda/.codex/private/leadzen/leadzen-release-backup-20261003.Y66bzF.tar.gz`.
- Matching current release source, manifests, and evidence, in a mode-700 folder:
  `/Users/ashishdikonda/.codex/private/leadzen/releases/20261003/`.
- Recovery archive SHA-256:
  `f83f74d99ab46fd1145fb1f4864dba3e62469868c16ed7e05bc35f6c3b9d450d`.

Recovery requires stopping intake/workers and restoring the matching `app/`
tree, `previous.env`, and service definitions together. Restore the application
to `/opt/leadzen` so its installed environment retains its original paths. This
was an integrity-verified recovery archive, not a destructive live rollback
exercise. Protect the archive as credential-bearing private data.

Live employee discovery, AI output, mailbox delivery/replies, paid enrichment,
and actual unattended email delivery remain operational verification items.
The latest update verified scheduler activation and a bounded existing-workspace
pass; actual delivery continues to require the reviewed campaign approval flow.
Discovery or paid provider checks still require the owner's fresh approval
where external actions or provider credits are involved.
The existing administrator's empty personal outreach configuration is not the
onboarded employee workspace. No legal acknowledgement, provider configuration,
credential rotation, new VM, paid plan, or monitoring subscription was changed.

## Environment settings — dated evidence and current release requirements

The tables preserve the October 3 configuration evidence and identify new
requirements in the current source. Verify the live values privately before a
new release; the audit did not inspect the current production environment.

### Vercel

Open **zyene's projects → leadzen-dashboard → Settings → Environment Variables**.
The API URL and token were recorded as configured for **Production** on October
3. The current source also requires the explicit public dashboard origin below.

| Variable | Purpose |
| --- | --- |
| `LEADZEN_API_URL` | `https://leadzen-api.zyene.com` |
| `LEADZEN_API_TOKEN` | Private service token matching the backend's `LEADZEN_DASHBOARD_TOKEN` |
| `LEADZEN_DASHBOARD_PUBLIC_URL` | Required by the current production source: exact HTTPS dashboard origin, such as `https://leadzen.zyene.com`, without a path, query or credentials |

Redeploy the dashboard after changing its environment variables. These are
server-only values: do not rename secrets with a `NEXT_PUBLIC_` prefix.

### Google Cloud VM

VM environment settings were recorded in **`/etc/leadzen.env`**, not the Vercel
dashboard. The October 3 file was root-owned and mode 600; `leadzen.service`
loaded it. Reverify ownership and service configuration before release.

| Variable | Purpose |
| --- | --- |
| `LEADZEN_ENV` | Required by the current WSGI preflight: `production` |
| `LEADZEN_DB` | `/opt/leadzen/data/db.sqlite3` |
| `LEADZEN_WORKSPACE_ROOT` | `/opt/leadzen/data/workspaces` |
| `LEADZEN_SETTINGS_KEY` | Stable private encryption key for employee credentials |
| `LEADZEN_SECRET_KEY` | Required by the current WSGI preflight: stable strong Django signing key, at least 50 characters |
| `LEADZEN_DASHBOARD_TOKEN` | Private service token matching Vercel |
| `LEADZEN_PUBLIC_URL` | `https://leadzen.zyene.com` for invitation links |
| `LEADZEN_ALLOWED_HOSTS` | `leadzen-api.zyene.com,localhost,127.0.0.1` |
| `LEADZEN_DASHBOARD_ORIGINS` | Required by the current WSGI preflight: explicit HTTPS origins including `LEADZEN_PUBLIC_URL`; recorded October 3 value was `https://leadzen.zyene.com` |
| `LEADZEN_RESEND_API_KEY` | Owner-approved invitation provider key; backend only |
| `LEADZEN_INVITATION_FROM` | `LeadZen by Zyene <accounts@leadzen.zyene.com>` |
| `LEADZEN_LLM_HOSTS` | `api.akashml.com`: owner-approved additional AI host |
| `LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED` | Recorded October 3 value: `1`, following that release's specific owner approval; current activation/health remain unverified |

The current production WSGI startup fails closed if any required backend
variable is missing or invalid. Database/workspace paths must be absolute;
public origins must use HTTPS, hosts must be explicit, and the service token
must be strong. Preserve the existing encryption key. Invitation credentials
are additionally required for employee invitation/reset delivery; MCP requires
`LEADZEN_MCP_PUBLIC_URL` when that optional integration is exposed.

After editing with `sudoedit /etc/leadzen.env`, restart with
`sudo systemctl restart leadzen.service`. Never replace the encryption key
without a coordinated re-encryption procedure and a tested backup. If rotating
the shared service token, update both Google Cloud and Vercel together.

Known supported provider hosts are allowed by default. Additional approved
public hosts can be configured with `LEADZEN_LLM_HOSTS`, `LEADZEN_MAIL_HOSTS`, or
`LEADZEN_EMAIL_HOSTS`; do not allow arbitrary/private network endpoints.

### Current schema and health checks — local source only

The October 3 deployment recorded configuration migration 0014 and account
migration 0002. The current source requires **all** migrations through
`leadzen_config.0019_discoverylookup_source_index` and
`leadzen_accounts.0004_accountprofile_tour_state` in the control database and
every initialized employee database. Apply them only after quiescing intake,
scheduler and all worker types and creating matching recovery backups. The
October 12 release above applied `leadzen_config.0021_search_plan` to the control
database and the one initialized workspace.

The new authenticated `/api/ready` checks the control database and pending
migrations, returns 503 on dependency/schema failure, and does not expose paths
or raw errors. `/api/health` remains process liveness. The readiness endpoint
exists only in the new local source until an authorized backend deployment;
it does not certify employee schemas, scheduler health or external providers.
Validate those separately using the audit's release checklist.

### Employee settings

Employees configure their own outreach email account and optional AI provider
in **onboarding / Connections**: SMTP or supported email API, credentials,
provider, model and approved endpoint URL. These per-employee secrets are
encrypted on the backend. They do not belong in Vercel environment variables.

## Historical release and verification evidence — 1 October 2026

- Vercel deployment: `dpl_9MPjcFdV2bMSP6p1TT1GzyvNTpNG`, **READY**, production.
- Deployment build: Next.js `16.3.8`; build completed in 11 seconds.
- Verified `leadzen.zyene.com` resolves to this deployment after promotion;
  authenticated production admin page rendered successfully in Chrome.
- This was a CLI upload of the current, uncommitted working tree, not a Git push.
- Backend source archive SHA-256:
  `fae673aa848d416b4983e7bbc2cedad8fa5efef377bb74219a46d6b012965d1d`.
- Backend wheel SHA-256:
  `ff203235ed4cc8008201a165bde118f7daa1a46796ed759da5b9c52f3aa0c6b1`.
- Local regression suite: **80 passed**. TypeScript and optimized deployment
  build passed. Deployed Django framework checks: **0 errors**.
- Verified HTTPS health; anonymous access and service-token-only access cannot
  read employee data. Verified login, admin rendering/users API, logout, revoked
  sessions and unavailable public signup on both candidate and production URLs.
- API and Caddy services are active. Gunicorn binds only `127.0.0.1:8000`;
  Caddy provides public HTTPS and automatic certificate management.
- Resend reports `leadzen.zyene.com` **verified**, sending enabled. Invitation
  configuration was validated; no live invitation or campaign email was sent.
- Historical data/credentials in all original columns of **22 non-framework
  tables** match the pre-migration backup. Framework tables changed as expected.
- Current deployment returned **0 runtime error log records** in the checked
  30-minute window. This is a point-in-time check, not a configured monitor.
- Chrome also reported extension warnings and storage-context errors while
  loading login. The dashboard source has no browser-storage calls, and login
  and admin actions passed. Storage-message attribution was not confirmed; no
  browser extensions or security settings were disabled.

## Private access and recovery files

Outside the repository, owner-only directory:
`/Users/ashishdikonda/.codex/private/leadzen/` (mode 700).

- `admin-login.txt`: actual production administrator login (mode 600).
- `production-backend.env`: private copy of the active backend environment,
  including the stable encryption key (mode 600).
- `predeployment-2Ythod.tar.gz`: independently copied and integrity-checked
  recovery archive: database, prior environment, service and source/package
  (mode 600).
- VM recovery directories: `/opt/leadzen-predeployment.ha94ZH` and
  `/opt/leadzen-accounts-backup.GOWLFK`.

Temporary local deployment key copies and duplicate secret files in the VM's
release staging directory were removed after verification. Active environment,
administrator credentials, recovery backups and the original Cloud Shell SSH
key were retained. Local preview servers were stopped; production stays running.

Do not commit, share, screenshot or upload the credential/recovery files.
Database downgrade is not automatic: stop intake/workers and restore matching
database, source/package, environment and service together from the backup.

## Operational notes

The owner explicitly chose to reuse the Resend key previously shared in chat.
That key was not rotated or revoked; rotation remains recommended.

Automatic follow-ups after explicit sequence approval were recorded **enabled**
in production following the owner's fresh request on 3 October 2026. The service
was active and started on boot at that check; enabling it does not approve campaigns or new
recipients. Reviewed manual due runs remain available. The existing workspace
pass and public API health were verified, but actual external email delivery
was not exercised. No external uptime monitor was added. Test employee provider
access and email
delivery with approved recipients before starting outreach. Delivery to an
inbox/Primary category is not guaranteed.

Vercel reported the existing broad Node engine range as an automatic-upgrade
warning; the current build passed. If the VM is stopped and started and its
external IP changes, update the API's DNS record. No new VM or paid plan was
created.

## AkashML endpoint approval

On 1 October 2026 at 10:47 p.m. Eastern, the owner approved the exact additional
AI host `api.akashml.com`. It is configured in `/etc/leadzen.env` on the existing
Google VM; `leadzen.service` was restarted and its live process environment was
checked. No Vercel environment or application source change was required.

Employees can select **OpenAI-compatible** and enter
`https://api.akashml.com/v1`, their own AkashML key, and a model ID available in
their AkashML account. The original error occurred before API-key authentication:
the custom host was not on LeadZen's approved list.

Verification: deployed URL validation accepted the endpoint, authenticated HTTPS
API health returned 200, and the production login page returned 200. Four local
settings regression tests and four configuration-preservation checks passed.
The pre-change environment is retained root-only at
`/etc/leadzen.env.pre-akashml-20261002T024701Z`; the local private environment copy
was updated with the same host approval. No employee settings were submitted,
credentials changed, AI inference requested, or email sent during this change.
