# Internal dashboard deployment

The dashboard is split into two services on purpose:

```text
Vercel / Next.js dashboard  ->  HTTPS + bearer token  ->  GCE / Django API + worker
                                                               |
                                                               +-- SQLite database
                                                               +-- Zoho SMTP/IMAP
                                                               +-- BetterContact + Groq
```

The browser never receives provider credentials and never opens the SQLite file. The
Next.js server proxies dashboard requests to the API, while the API starts a separate
worker for sends. The worker applies the normal LeadZen by Zyene pacing, capacity checks,
and a filesystem lock before doing any work.

## API VM

Install the project with the web extra and migrate the database:

```bash
uv pip install -e ".[web]"
python manage.py migrate --no-input
```

Required environment variables on the VM:

```dotenv
LEADZEN_DB=/srv/leadzen/data/db.sqlite3
LEADZEN_DASHBOARD_TOKEN=use-a-long-random-token
LEADZEN_DASHBOARD_ORIGINS=https://your-dashboard.vercel.app
LEADZEN_ALLOWED_HOSTS=api.yourcompany.com
```

Set `LEADZEN_SETTINGS_KEY` to a privately generated Fernet key and retain it with
your encrypted backups. Each employee enters their mailbox and AI credentials in
onboarding. Workers receive only that employee's workspace settings. Back up the
control database and the entire adjacent `workspaces/` directory consistently.

Run the API behind an HTTPS reverse proxy:

```bash
gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 2 --timeout 120 leadzen.wsgi:application
```

Only expose the reverse proxy publicly. Do not expose port 8000 directly. Restrict the
API endpoint using its service token and per-user sessions. CORS is not access
control. Rotate any previously exposed service token before enabling login.

## Vercel dashboard

Deploy the `dashboard/` directory as its own Vercel project. Set these server-side
environment variables in Vercel:

```dotenv
LEADZEN_API_URL=https://api.yourcompany.com
LEADZEN_API_TOKEN=the-same-token-as-the-vm
```

Production refuses a non-HTTPS API URL. Use `leadzen.zyene.com` for the frontend.
There is no shared dashboard password or public signup. Bootstrap the first account
on the VM using the private terminal password prompt:

```bash
python manage.py bootstrap_admin --email support@zyene.com
```

Administrators create employee accounts at `/admin` by entering a name and work
email. Resend delivers a single-use setup link, valid for 48 hours. Employees
create their own password, sign in, complete onboarding and take the product
tour. The admin can resend invitations or initiate a password reset via email.
Disabling, deleting or resetting an account revokes its sessions. Deletion
retains workspace history, and self-deletion is refused.

Invitation sending needs `LEADZEN_RESEND_API_KEY`, `LEADZEN_PUBLIC_URL` and
`LEADZEN_INVITATION_FROM` on the **backend only**. The invitation sender must use
a verified Resend domain. This platform-level key is never exposed to employees
or inherited by their outreach workers. Employee email/AI credentials are
encrypted separately in each private workspace.

Employees can configure BetterContact in onboarding's **Lead discovery** step or
at **Connections → Lead finding** (`/settings`). Only a saved-key presence flag
is returned to the browser. Blank input preserves the existing key; replacement
and explicit removal are supported. Keys are stored in the workspace's encrypted
credentials and exported as `OPENOUTFIND_BETTERCONTACT_API_KEY` only inside its
authorized worker/CLI process. Saving does not validate against the provider,
spend credits, start lead discovery, or send emails. BetterContact is optional
for employees who add/import their own contacts. The existing Overview run
sends stored leads; adding the key does not turn that button into a new search.

Deploy the backend before the frontend for this setting. No additional Vercel
environment variable is required for the key. The six-step onboarding release
requires migration **0009** on the control and every employee database. Existing CLI keys
are moved into encrypted storage on the next successful connection save; the
old plaintext BetterContact field is cleared atomically with that write.

**Workspace → Find Leads** (`/find-leads`) provides a structured discovery form.
It defaults to three qualified leads with no email lookup and a visible **0-credit**
BetterContact email estimate. Verified-email lookup shows **up to N credits** before
Start Finding. AI usage is separate. That button approves only the displayed
count, email choice and credit limit, starts one existing discovery worker action,
and opens its saved progress/results in Chat. It does not send outreach emails.
Both free and verified discovery require the employee's BetterContact connection,
AI configuration and completed product/target/identity setup. Changed setup,
concurrent tasks and duplicate submissions cannot silently change or repeat the
approved action. This form adds no migration or environment variable; the matching
backend `/api/discovery` must be released before the dashboard in a future rollout.

Known provider hosts are approved by default. Additional trusted AI and mail
hosts can be configured with `LEADZEN_LLM_HOSTS` and `LEADZEN_MAIL_HOSTS`
(comma-separated exact hostnames). Only approve hosts you trust: workers connect
to them and transmit the employee's configured credentials. AI URLs require
HTTPS; SMTP 465 uses verified implicit TLS, SMTP 587/2525 use STARTTLS, and IMAP
993 uses verified TLS.

Chat normally uses the provider adapter's structured tool output. If a tested
OpenAI-compatible gateway buffers tool arguments but streams JSON text, the backend
can opt in exact hosts through `LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS` (comma-separated
hostnames). This preserves final Decision validation and all action approvals; it
does not approve new network hosts. Validate each selected model before enabling
it. The installed Cohere adapter falls back to a validated completed answer because
it has no streaming implementation. See the [provider validation and remaining
limitations](provider-streaming-validation-2026-10-04.md).

## Six-step employee setup

First-time employees are redirected to `/onboarding` after signing in. The
wizard saves public answers as employees continue and resumes at the first
unfinished step. Already-onboarded employees can review or update the setup.

1. **AI provider:** provider, model, approved base URL and API key. **Test
   connection** makes one short model request (up to 256 output tokens, no tools
   or retries). Usage charges may apply. Groq GPT-OSS uses low reasoning effort.
   AI can be explicitly skipped for manual campaigns.
2. **Lead discovery:** BetterContact key and an explicit account-only connection
   test. It retrieves `credits_left` without a profile search or enrichment;
   zero credits is valid, a missing/invalid balance is not replaced with a guess.
   The guide distinguishes free profile discovery from standard verified work
   emails (1 credit), with provider-plan/catch-all caveats. Manual contacts can
   explicitly skip this step's connection requirement.
3. **Your identity:** employee name, operator email and country. An email-looking
   name is rejected. These details are separate from both the login identity
   and sending mailbox; updating them never changes the login email.
4. **Sending mailbox:** SMTP or the existing supported email APIs, plus IMAP
   reply access. The paid-US Zoho preset is `smtppro.zoho.com:465` and
   `imappro.zoho.com:993`; account/data-center details remain editable. SMTP is
   authenticated, IMAP is authenticated and INBOX selected read-only. No mail
   is sent or fetched. API senders show only IMAP verified / sending API saved,
   **not** SMTP or API-delivery success.
5. **Product / offer:** outreach purpose, workspace, product name, description
   and optional HTTPS booking link.
6. **Target audience:** industry, country, employee count, roles (including
   custom roles), seniority and additional instructions. A deterministic preview
   must be reviewed and authorization confirmed. These are discovery/AI
   qualification instructions, not a guarantee that all prospects match.

Only successfully tested credentials are saved by a connection test. Saves in
Connections remain a separate, untested configuration path. The server records
private HMAC receipts tied to the exact tested connection and credentials,
valid for 24 hours. Changed settings require retesting; failed retests discard
old success. Tests are serialized per workspace and limited to 30 per kind per
employee per 15 minutes. A result cannot overwrite settings changed in another
tab or survive account revocation. Completing the wizard revalidates all six
steps and writes the offer/target to the existing outreach engine's SiteConfig.
The first completed setup opens an interactive product tour over the real
workspace. Fourteen steps wait for actual controls, click outcomes and rendered
routes/forms. Active progress, completion and Skip persist on the employee account;
refresh resumes the current step, and Settings → Take Product Tour restarts a
completed/skipped tour. Unrelated navigation pauses the guide rather than pulling
the employee back. Account migration `0004_accountprofile_tour_state` is required;
see [tour validation](product-tour-validation-2026-10-04.md) for tested behavior and
the outstanding browser visual review.

All typed secrets have accessible eye toggles. Saved keys/passwords and receipt
fingerprints are never returned to the browser. There are no new Vercel
environment variables; retain the existing stable `LEADZEN_SETTINGS_KEY` and
the approved provider-host settings. See [local test evidence](local-validation.md).

`LEADZEN_EMAIL_HOSTS` approves exact hostnames for custom Resend-compatible
HTTPS email APIs. Resend is restricted to opted-in recipients; ZeptoMail to
single transactional notifications. A SMTP connection is not an exception to
the selected provider's acceptable-use rules. API sending does not provide an
inbox: connect IMAP separately for replies and follow-ups.

Campaign sequences have up to five steps. Employees explicitly run due emails
again after the follow-up delay; there is no automatic scheduler. Uncertain
delivery stays in review and is not silently retried. Job results appear on
Overview, and provider acceptance does not imply inbox delivery.

Before upgrading, stop active jobs and take a consistent SQLite backup. Install
the new wheel, migrate the control database, and migrate existing workspace
databases before restarting the API. Legacy CLI leads remain in the control
database and are not automatically assigned to employee workspaces.

## Local development

See `dashboard/README.md`. The API can run with `python manage.py runserver` locally and
the dashboard with `npm run dev` from `dashboard/`.
