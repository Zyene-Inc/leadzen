# Running LeadZen by Zyene with Docker

Build the company image from this checkout:

```bash
docker build -f compose/leadzen/Dockerfile -t leadzen:local .
```

The build context excludes private environment files, runtime databases and
backups, installed dependencies, caches and generated builds. Source, migrations,
package metadata, legal notices and placeholder environment examples remain
available. Provide real credentials and persistent storage when running the image.

Run a bounded discovery job with persistent storage and the provider variables
in a private environment file:

```bash
docker run --rm --env-file .env -v /srv/leadzen/data:/app/data leadzen:local 10 emails > leads.csv
```

The image sets `LEADZEN_DB=/app/data/db.sqlite3`. The number is the goal,
and `emails` opts into paid address enrichment. Without an explicit number,
the container discovers one qualified lead. The environment file supplies
`OPENOUTFIND_*` and `OUTSEND_*` variables consumed by the provider libraries.

For the internal dashboard API:

```bash
docker run --rm --env-file .env -p 127.0.0.1:8000:8000 \
  -v /srv/leadzen/data:/app/data leadzen:local gunicorn \
  --bind 0.0.0.0:8000 leadzen.wsgi:application
```

Keep the API behind HTTPS and persist the data directory. Configure
the variables listed in [production audit](production-readiness-audit-2026-10-04.md).
The current WSGI preflight requires `LEADZEN_ENV=production`, absolute
`LEADZEN_DB` and `LEADZEN_WORKSPACE_ROOT` paths, `LEADZEN_SETTINGS_KEY`,
`LEADZEN_SECRET_KEY`, `LEADZEN_DASHBOARD_TOKEN`, explicit
`LEADZEN_ALLOWED_HOSTS`, an HTTPS `LEADZEN_PUBLIC_URL`, and explicit HTTPS
`LEADZEN_DASHBOARD_ORIGINS` including that public origin. Preserve the stable
encryption key and keep environment files private.
The default entrypoint drops privileges before Gunicorn starts; retain it.
Deploy the Next.js frontend from `dashboard/` to Vercel.
Its production configuration requires the HTTPS `LEADZEN_API_URL`, matching
server-only `LEADZEN_API_TOKEN`, and exact HTTPS `LEADZEN_DASHBOARD_PUBLIC_URL`.

Before starting the current API against existing data, stop intake and all
workers, create matched source/environment/key/control/workspace recovery
backups, and apply every migration to the control and initialized employee
databases. The current migration leaves are `leadzen_config.0019_discoverylookup_source_index`
and `leadzen_accounts.0004_accountprofile_tour_state`. The new private
`/api/ready` checks control-database/schema readiness with the dashboard bearer
token; `/api/health` reports process liveness. Employee schemas, scheduler health
and providers require separate verification. These endpoints and requirements
describe current source, not a verified live deployment.

The Compose file `local.yml` builds the same image. `make build`,
`make up`, `make logs`, and `make stop` operate that local service.
For a one-off job, use the `app` service explicitly:

```bash
docker compose -f local.yml run --rm --env-from-file .env app 10 emails > leads.csv
```

Compose's `--env-file` option supplies variable interpolation; it does not pass
every provider variable into this service. `--env-from-file` supplies the job's
container environment. The paid `emails` example requires explicit authorization.

Historical configuration-table upgrades create a SQLite recovery copy on first
startup; they do not replace the reviewed Django migration and full-server
backup procedure above. Schedule bounded CLI jobs using a systemd timer or your
existing scheduler.
