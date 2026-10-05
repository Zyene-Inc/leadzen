# LeadZen production deployment

Historical deployment evidence verified on 3 October 2026. LeadZen is Zyene's internal tool for
outreach about its products and services, not the Zyene Reviews company.

The October 4 production audit changes are local and have not been deployed.
Service status, environment values and deployment IDs below describe the dated
October 3 checks; they are not a current live-state guarantee or continuing
authorization to deploy, send emails or spend provider credits. Follow the
[October 4 production audit](production-readiness-audit-2026-10-04.md) for the
current release requirements and final verification evidence.

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
scheduler and all worker types and creating matching recovery backups. These
newer migrations have not been claimed applied to production.

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
