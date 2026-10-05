# LeadZen by Zyene dashboard

This is the private Vercel frontend for the LeadZen by Zyene worker. It does not contain
mailbox, LLM, or BetterContact credentials. The browser talks to same-origin Next.js
proxy routes; those routes call the private Django API on the worker VM.

## Local development

Use a supported Node.js LTS release: Node 22.12 or newer in the 22.x series,
or Node 24.x. The test runner requires these versions; CI uses Node 22.

1. Start the API from the repository root:

   ```bash
   LEADZEN_DASHBOARD_TOKEN=dev-api-token \
   LEADZEN_DASHBOARD_ORIGINS=http://localhost:3000 \
   python manage.py migrate
   LEADZEN_DASHBOARD_TOKEN=dev-api-token \
   LEADZEN_DASHBOARD_ORIGINS=http://localhost:3000 \
   python manage.py runserver 127.0.0.1:8000
   ```

2. Install and start the dashboard:

   ```bash
   cd dashboard
   cp .env.example .env.local
   # Set LEADZEN_API_URL=http://127.0.0.1:8000,
   # LEADZEN_API_TOKEN=dev-api-token.
   npm ci
   npm run dev
   ```

3. Create the first administrator using the private terminal prompt:
   `python manage.py bootstrap_admin --email support@zyene.com`.
   Open `http://localhost:3000` and sign in. Create employee accounts at `/admin`.

For a disposable local preview with a mail catcher and **no external sending**,
use the commands and synthetic accounts in [`docs/local-validation.md`](../docs/local-validation.md).

## Deployment shape

- Deploy this `dashboard/` directory as a Vercel project.
- Set `LEADZEN_API_URL` to the HTTPS API URL on the worker VM.
- Set `LEADZEN_API_TOKEN` to the same long random token as the VM.
- Accounts and revocable sessions are managed by the API; no shared password is used.
- Set `LEADZEN_DASHBOARD_ORIGINS` on the VM to the exact Vercel origin.
- In production, including Vercel and a standalone server behind a TLS proxy, set the server-only
  `LEADZEN_DASHBOARD_PUBLIC_URL` to the exact public HTTPS origin, such as
  `https://leadzen.example.com`. This lets origin checks validate browser requests
  against the public URL when Next.js sees an internal address. Paths, queries,
  fragments and embedded credentials are rejected. Incoming forwarded-host headers
  do not choose the allowed origin. Production mutations fail closed when this is unset.
- Set `LEADZEN_SETTINGS_KEY` only on the VM. Generate it with
  `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
  This key encrypts mailbox passwords, AI API keys and BetterContact keys entered
  through onboarding or `/settings`. BetterContact is configured under
  **Connections → Lead finding**, not in a Vercel environment variable.
- Run the Django API behind HTTPS with `gunicorn leadzen.wsgi:application`.
- Configure the backend-only `LEADZEN_RESEND_API_KEY`, `LEADZEN_INVITATION_FROM`
  (a verified Resend sender) and `LEADZEN_PUBLIC_URL=https://leadzen.zyene.com`.
  Keep these out of `NEXT_PUBLIC_*` variables and the frontend environment.

The Settings page intentionally refuses to save credentials until the VM has
`LEADZEN_SETTINGS_KEY`. Configure HTTPS before entering real credentials; the
current public-IP HTTP smoke endpoint is for health checks only.

The VM is still the only place allowed to run a send job. The API rejects concurrent
jobs, validates the remaining daily mailbox capacity, persists job state, and takes a
filesystem lock before starting the sender.
