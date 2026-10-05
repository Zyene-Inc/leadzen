# LeadZen by Zyene development instructions

Start with [AGENTS.md](AGENTS.md) and the repository's
[LeadZen project skill](.agents/skills/leadzen-project/SKILL.md).
They route to maintained project context and task-specific skills shared by Codex,
Claude, and other coding agents. Dated handoffs are historical evidence; current
user instructions and verified code take precedence over stale implementation notes.

- Use `.venv/bin/python` for Python commands.
- Preserve uncommitted user work.
- Keep provider credentials on the API server and out of browser responses.
- Run the relevant Python tests and the dashboard type check/build after changes.
- Commits use single-line messages with no co-author trailer.
- Do not write memory files.

## Architecture

`leadzen/` hosts the Django registry, configuration, CLI, private API, and
background worker. `dashboard/` is the Vercel Next.js interface. The finder
and sender remain installed dependencies pinned in `pyproject.toml`; their
provider environment interfaces are `OPENOUTFIND_*` and `OUTSEND_*`.

The dashboard connects to the API using `LEADZEN_API_URL` and
`LEADZEN_API_TOKEN`. The API uses `LEADZEN_DASHBOARD_TOKEN`,
`LEADZEN_DB`, and `LEADZEN_SETTINGS_KEY`.

The config app label is `leadzen_config`. `leadzen/upgrade.py` is the
one-time migration of historical config tables and migration records. It creates a
SQLite backup before renaming and preserves data. Do not remove recovery support
until existing installs have been upgraded.

`leadzen/branding.py` centralizes the product identity and suppresses the
sender library's tool attribution. Configure it at Django app startup so workers
and clean installs behave the same way. Do not modify installed site-packages.

## Commands

```bash
uv pip install -e ".[dev,web]"
.venv/bin/python manage.py migrate --no-input
.venv/bin/python -m leadzen --help
.venv/bin/pytest -q
cd dashboard
npm run lint
npm run build
```

The CLI skill in `skills/find-leads/SKILL.md` must stay aligned with command
changes. Retain the GPL license and third-party source attribution. Do not publish
packages to public registries or push source upstream as part of routine dashboard
deployment.
