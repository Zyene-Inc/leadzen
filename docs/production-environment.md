# Production environment inventory

Maintained October 4, 2026 for the current local source. This covers all **66 names**
in the [audit inventory](production-audit-2026-10-04-env-inventory.json), plus three
dynamically constructed host-allowlist names below. It classifies runtime inputs,
server-injected fields, offline CLI exports and names merely scrubbed by the service.
Source references identify the implementation; dated inventory line numbers may move.
See [production preflight](production-preflight.md) for a no-secret validation command.

The operation templates add configuration for maintenance tooling, separately
from application runtime inputs: `LEADZEN_OPS_APP_USER`,
`LEADZEN_BACKUP_ENV_FILE`, `LEADZEN_BACKUP_RELEASE_MANIFEST`,
`LEADZEN_BACKUP_ROOT`, `LEADZEN_BACKUP_INDEPENDENT_ROOT` and `LEADZEN_DB` are
conditional on installing the reviewed backup service. `LEADZEN_RELEASE_PYTHON`
is an optional operator executable override for the release validation wrapper.
The `LEADZEN_E2E_*` names and `LEADZEN_CAPACITY_NETWORK_ISOLATED` are injected only
in disposable tests; they are not production application settings. Monitoring
paths, thresholds and the separately approved alert destination are private JSON
configuration, not additional environment requirements.
Backup and monitoring environment paths must refer to a mode-600 file owned and
readable by their service identity. Their templates use a privately verified
runtime-owner copy at `/srv/private/leadzen-runtime.env`; a root-owned API systemd
EnvironmentFile does not itself meet that requirement. Copy ownership and exact
current-byte synchronization require operator verification.

`LEADZEN_BACKUP_DASHBOARD_ENV_FILE` and `LEADZEN_BACKUP_PROXY_FILE` are also
required for the scheduled backup template: they identify private, current,
matched deployment configuration copies. They are conditional operations inputs,
never browser/public application settings and never replacements for the stable
settings encryption key.

## Required production configuration

Backend WSGI requires these names to be explicitly configured:

- `LEADZEN_ENV`
- `LEADZEN_DB`
- `LEADZEN_WORKSPACE_ROOT`
- `LEADZEN_SETTINGS_KEY`
- `LEADZEN_SECRET_KEY`
- `LEADZEN_DASHBOARD_TOKEN`
- `LEADZEN_ALLOWED_HOSTS`
- `LEADZEN_PUBLIC_URL`
- `LEADZEN_DASHBOARD_ORIGINS`

Frontend server runtime requires:

- `LEADZEN_API_URL`
- `LEADZEN_API_TOKEN`
- `LEADZEN_DASHBOARD_PUBLIC_URL`

`NODE_ENV` is host-injected by a production Next/Vercel runtime, not an additional
operator-required dashboard variable. Backend/frontend service tokens must match
exactly; do not trim or normalize credentials to hide mismatch. The frontend API
URL is server-only; none of the service/provider keys belongs in `NEXT_PUBLIC_*`
variables or the browser bundle. Production preflight rejects unreviewed public env
inputs and explicit development runtime configuration.

Keep environment files mode 600 in private operator storage. For backend and
employee SQLite storage, use a dedicated non-root service account, persistent
storage, mode-700 directories and mode-600 database/initialization files; verify
mounts/firewall/proxy ownership on the actual target host. The policy example in
[preflight documentation](production-preflight.md#inputs) defines exact HTTPS
origins, literal private listeners, narrowly scoped trusted CIDRs, forwarded proxy
addresses, expected host/architecture and service/environment owners. Policy
attestation does not establish observed host topology or durability.

Preserve the existing `LEADZEN_SETTINGS_KEY` with the complete matched recovery
set. Do not generate a replacement for an existing installation: runtime settings,
mailbox passwords and invitation capabilities use it. Preserve the stable signing
key separately. Retrieve/set credentials privately from the approved vault; never
place values in reports, command arguments, source, screenshots or terminal logs.

## Conditional feature configuration

Invitations need a private Resend key and explicit verified sender; MCP needs its
exact public API `/mcp` endpoint. Their validation does not contact a provider.
Saved employee connections supply AI/BetterContact/mailbox credentials. Enabling
Chat, discovery, mail or automatic outreach in the release policy requires the
corresponding account configuration and decryptable credentials in every initialized
employee database checked. False policy flags mean excluded/disabled **release
scope**, not an application feature toggle. Only the actual Autopilot/follow-up env
switches control those runtime automation gates; activation needs the applicable
specific owner authorization. Credentials alone do not authorize paid work/sending.

## Complete 66-name classification

| Name | Classification | Purpose and enablement | Exact source |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | Unused by service | Ambient SDK key is scrubbed by worker_environment. Employee keys come from encrypted settings; do not add a global provider key to enable the employee service. | [leadzen/workspaces.py](../leadzen/workspaces.py) · worker_environment / assert_worker_access |
| `APP_HOME` | Internal | Internal Docker build ARG controlling WORKDIR, not a required runtime environment variable. | [compose/leadzen/Dockerfile](../compose/leadzen/Dockerfile) |
| `COHERE_API_KEY` | Unused by service | Ambient SDK key is scrubbed by worker_environment. Employee keys come from encrypted settings; do not add a global provider key to enable the employee service. | [leadzen/workspaces.py](../leadzen/workspaces.py) · worker_environment / assert_worker_access |
| `DJANGO_SETTINGS_MODULE` | Internal | Internal launch setting: leadzen.settings. WSGI rejects other modules; preflight graph ignores it and never imports it. | [leadzen/__main__.py](../leadzen/__main__.py) |
| `EDITOR` | CLI / fixture | CLI/container editor selection; not required by the web runtime. | [compose/leadzen/Dockerfile](../compose/leadzen/Dockerfile) |
| `GOOGLE_API_KEY` | Unused by service | Ambient SDK key is scrubbed by worker_environment. Employee keys come from encrypted settings; do not add a global provider key to enable the employee service. | [leadzen/workspaces.py](../leadzen/workspaces.py) · worker_environment / assert_worker_access |
| `GROQ_API_KEY` | Unused by service | Ambient SDK key is scrubbed by worker_environment. Employee keys come from encrypted settings; do not add a global provider key to enable the employee service. | [leadzen/workspaces.py](../leadzen/workspaces.py) · worker_environment / assert_worker_access |
| `HOST_GID` | CLI / fixture | Local container entrypoint GID remapping; verify persistent-volume ownership matches the runtime identity. | [compose/leadzen/entrypoint](../compose/leadzen/entrypoint) |
| `HOST_UID` | CLI / fixture | Local container entrypoint UID remapping; use a deliberate dedicated non-root runtime identity, not a browser input. | [compose/leadzen/entrypoint](../compose/leadzen/entrypoint) |
| `LEADZEN_ACTOR_ID` | Internal | Internal server-derived employee user ID for workers; never accept from browser/operator ambient service environment. | [leadzen/autopilot.py](../leadzen/autopilot.py) · worker_environment / assert_worker_access |
| `LEADZEN_ALLOWED_HOSTS` | Required | Explicit backend Host allowlist including the API hostname; no wildcard/development override. | [leadzen/production.py](../leadzen/production.py) · validate_environment |
| `LEADZEN_API_TOKEN` | Required | Frontend server-only service bearer token; exact constant-time match to backend token. | [dashboard/lib/auth.ts](../dashboard/lib/auth.ts) · backend |
| `LEADZEN_API_URL` | Required | Frontend server-only exact HTTPS API origin; no credentials/path/query/fragment. | [dashboard/lib/auth.ts](../dashboard/lib/auth.ts) · backend |
| `LEADZEN_AUTOMATIC_FOLLOWUPS_ENABLED` | Optional | Optional runtime feature switch, only exact 1 enables; default disabled. Does not approve recipients or sends. | [leadzen/autopilot_worker.py](../leadzen/autopilot_worker.py) |
| `LEADZEN_AUTOPILOT_ENABLED` | Optional | Optional runtime feature switch, only exact 1 enables; default disabled. Must agree with release policy and existing specific authorization. | [leadzen/autopilot.py](../leadzen/autopilot.py) |
| `LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS` | Optional | Optional exact host opt-in for validated prompted JSON output on compatible AI gateways; no credential, consent or spend approval. | [leadzen/chat/engine.py](../leadzen/chat/engine.py) |
| `LEADZEN_CHAT_RUN_ID` | Internal | Internal actor-owned run capability injected into Chat/MCP workers for live approval/revocation checks. | [leadzen/chat/engine.py](../leadzen/chat/engine.py) |
| `LEADZEN_CONTROL_DB` | Internal | Internal worker control database pointer injected by worker_environment; does not select arbitrary tenant data. | [leadzen/autopilot_worker.py](../leadzen/autopilot_worker.py) · worker_environment / assert_worker_access |
| `LEADZEN_DASHBOARD_ORIGINS` | Required | Explicit HTTPS dashboard CORS origins; production preflight policy expects its exact dashboard origin. | [leadzen/production.py](../leadzen/production.py) · validate_environment |
| `LEADZEN_DASHBOARD_PUBLIC_URL` | Required | Frontend exact HTTPS dashboard origin for same-origin mutations; required by current source. | [dashboard/lib/auth.ts](../dashboard/lib/auth.ts) · sameOrigin |
| `LEADZEN_DASHBOARD_TOKEN` | Required | Private backend service bearer token; strong, at least 32 characters; match frontend LEADZEN_API_TOKEN exactly. | [leadzen/production.py](../leadzen/production.py) · validate_environment |
| `LEADZEN_DB` | Required | Canonical absolute persistent control SQLite file; preserve data. | [leadzen/__main__.py](../leadzen/__main__.py) |
| `LEADZEN_ENV` | Required | Backend production detection; must be production. | [leadzen/observability.py](../leadzen/observability.py) |
| `LEADZEN_INVITATION_FROM` | Conditional | Invitations enabled: explicit verified sender identity. Preflight requires explicit configuration despite historical source fallback. | [leadzen/accounts/invitations.py](../leadzen/accounts/invitations.py) · invitation_config |
| `LEADZEN_MCP_ALLOW_LOCAL` | CLI / fixture | Fixture/development-only local MCP transport override. Production must leave disabled; WSGI rejects exact 1. | [leadzen/mcp/auth.py](../leadzen/mcp/auth.py) |
| `LEADZEN_MCP_PUBLIC_URL` | Conditional | MCP enabled: exact HTTPS API-origin endpoint ending /mcp; real OAuth client interop remains a separate gate. | [leadzen/mcp/auth.py](../leadzen/mcp/auth.py) |
| `LEADZEN_PUBLIC_URL` | Required | Exact HTTPS dashboard origin used by invitation links and MCP consent. | [leadzen/accounts/invitations.py](../leadzen/accounts/invitations.py) |
| `LEADZEN_RESEND_API_KEY` | Conditional | Invitations enabled: private Resend credential; configuration check never sends an invitation. | [leadzen/accounts/invitations.py](../leadzen/accounts/invitations.py) · invitation_config |
| `LEADZEN_SECRET_KEY` | Required | Stable strong Django signing key, at least 50 characters; distinct from the Fernet key. | [leadzen/production.py](../leadzen/production.py) · validate_environment |
| `LEADZEN_SETTINGS_KEY` | Required | Valid stable Fernet key; must decrypt existing settings, mailbox and invitation data. | [leadzen/accounts/views.py](../leadzen/accounts/views.py) |
| `LEADZEN_WORKSPACE_ID` | Internal | Internal server-derived employee UUID; validated against live control ownership. | [leadzen/workspaces.py](../leadzen/workspaces.py) · worker_environment / assert_worker_access |
| `LEADZEN_WORKSPACE_ROOT` | Required | Canonical absolute private persistent employee database root. | [leadzen/production.py](../leadzen/production.py) · validate_environment |
| `MISTRAL_API_KEY` | Unused by service | Ambient SDK key is scrubbed by worker_environment. Employee keys come from encrypted settings; do not add a global provider key to enable the employee service. | [leadzen/workspaces.py](../leadzen/workspaces.py) · worker_environment / assert_worker_access |
| `NODE_ENV` | Internal | Host-injected Next.js runtime setting; production hosts set production. Not an additional operator-required Vercel variable. Explicit development override fails preflight. | [dashboard/app/api/auth/login/route.ts](../dashboard/app/api/auth/login/route.ts) |
| `OPENAI_API_KEY` | Unused by service | Ambient SDK key is scrubbed by worker_environment. Employee keys come from encrypted settings; do not add a global provider key to enable the employee service. | [leadzen/workspaces.py](../leadzen/workspaces.py) · worker_environment / assert_worker_access |
| `OPENOUTFIND_ACCEPT_LEGAL_NOTICE` | CLI / employee export | Recorded finder legal acceptance; not fresh paid/send approval. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_AI_MODEL` | CLI / employee export | Finder provider:model exported from employee AI settings. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_APOLLO_API_KEY` | CLI / employee export | Legacy offline CLI Apollo enrichment credential; private, not dashboard BetterContact configuration. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_BETTERCONTACT_API_KEY` | CLI / employee export | Employee BetterContact key for discovery and explicitly approved enrichment. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_CAMPAIGN_TARGET` | CLI / employee export | Employee targeting description supplied to finder. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/chat/engine.py](../leadzen/chat/engine.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_CONTACTS_API_TOKEN` | CLI / employee export | Legacy finder contacts-hub identity token; private. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_EMAIL_FINDER` | CLI / employee export | Employee email-enrichment provider selector; current dashboard uses BetterContact. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_LLM_API_BASE` | CLI / employee export | Employee compatible-model HTTPS endpoint. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_LLM_API_KEY` | CLI / employee export | Employee protected AI provider key. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_NEWSLETTER` | CLI / employee export | Recorded optional newsletter consent; false/unset must not imply consent. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_OPERATOR_COUNTRY` | CLI / employee export | Employee operator jurisdiction, separate from fixed New York business time. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_OPERATOR_EMAIL` | CLI / employee export | Employee outreach/operator identity, separate from login account. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OPENOUTFIND_PRODUCT_DOCS` | CLI / employee export | Employee product/offer description. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_AI_MODEL` | CLI / employee export | Sender provider:model exported from employee AI settings. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_BOOKING_LINK` | CLI / employee export | Optional employee booking URL. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_CAMPAIGN_TARGET` | CLI / employee export | Employee target description supplied to sender. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_HOME` | Internal | Internal employee worker state root; launchers derive it from server-owned workspace path. Deliberate offline CLI may override separately. | [leadzen/settings.py](../leadzen/settings.py) |
| `OUTSEND_IMAP_HOST` | CLI / employee export | Employee approved IMAP TLS host. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_IMAP_PORT` | CLI / employee export | Employee IMAP TLS port; dashboard validation accepts 993. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_LLM_API_BASE` | CLI / employee export | Employee compatible-model HTTPS endpoint. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_LLM_API_KEY` | CLI / employee export | Employee protected AI provider key. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_MAILBOX_ADDRESS` | CLI / employee export | Employee authorized sender mailbox address. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_MAILBOX_PASSWORD` | CLI / employee export | Employee mailbox app credential decrypted only server-side for authorized work. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_OPERATOR_COUNTRY` | CLI / employee export | Employee sender jurisdiction, separate from fixed New York scheduling. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_OPERATOR_EMAIL` | CLI / employee export | Employee outreach/operator email. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_OPERATOR_NAME` | CLI / employee export | Employee outreach/operator name. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_PRODUCT_DOCS` | CLI / employee export | Employee product/offer description. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_SIGNATURE` | CLI / employee export | Employee outgoing email signature. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_SMTP_HOST` | CLI / employee export | Employee approved SMTP TLS/STARTTLS host. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `OUTSEND_SMTP_PORT` | CLI / employee export | Employee SMTP TLS/STARTTLS port; dashboard accepts 465, 587 or 2525. Legacy SiteConfig/CLI export; web workers strip ambient values and derive employee settings. | [leadzen/config/models.py](../leadzen/config/models.py) · FINDER_ENV / SENDER_ENV; apply_dashboard_overrides |
| `PATH` | Internal | Internal container executable lookup. Runtime image prepends the bundled virtual environment. | [compose/leadzen/Dockerfile](../compose/leadzen/Dockerfile) |

## Dynamic host allowlists

[approved_host](../leadzen/configuration.py) constructs these names dynamically,
so the literal-name scanner did not include them in the 66-name audit inventory:

| Name | Classification | Purpose |
| --- | --- | --- |
| `LEADZEN_LLM_HOSTS` | Optional / conditional | Explicit additional HTTPS AI endpoint hostnames, including a deliberately approved compatible gateway. Required only when its endpoint is outside built-in hosts. |
| `LEADZEN_EMAIL_HOSTS` | Optional / conditional | Explicit additional HTTPS mail-API hostnames for a deliberately approved compatible transport. |
| `LEADZEN_MAIL_HOSTS` | Optional / conditional | Explicit additional SMTP/IMAP hostnames outside built-in provider hosts; retain required TLS ports. |

These are server-approved exact hostname extensions, not wildcard origin lists.
They do not prove a destination's runtime DNS/network behavior or provider health.
Per-account API URLs and credentials remain protected employee settings, not new
browser or globally shared service environment variables.

## Authorized configuration snapshot evidence — October 4, 2026

A fresh authorized read-only Vercel Production env pull and an older private local
backend env snapshot were compared offline without printing any values:

| Observation | Result | Scope |
| --- | --- | --- |
| Backend required names absent | `LEADZEN_ENV`, `LEADZEN_SECRET_KEY` | Older local backend snapshot; actual VM configuration **UNVERIFIED**. |
| Frontend required name absent | `LEADZEN_DASHBOARD_PUBLIC_URL` | Fresh Vercel Production pull at the time of inspection; recheck after configuration change. |
| Exact backend/frontend service token match | `false` | Comparison of those two local files; may reflect an old backend snapshot, so actual VM token match **UNVERIFIED**. |
| Backend WSGI configuration validation | `FAIL` | That local snapshot against current source requirements; no VM startup/deployment attempted. |
| Current target-host schema, ownership, encryption compatibility, mounts/proxy/firewall | **BLOCKED / UNVERIFIED** | No target-host database/storage access was obtained by the offline comparison. |

The pulled file may omit `NODE_ENV` because Vercel injects it. Its absence was not
reported as an operator configuration defect. The preflight itself is implemented
and synthetically tested locally; this comparison does not claim it has passed on
the real production host. No secret values, customer identifiers or sensitive
absolute paths are retained in this document. Historical October 3 configuration
and approvals remain dated evidence in [deployment history](deployment.md).
