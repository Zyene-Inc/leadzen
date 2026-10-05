![LeadZen by Zyene](docs/leadzen-logo.svg)

# LeadZen by Zyene

LeadZen is Zyene's internal lead discovery and outreach workspace. Describe the
product and target customer, find qualified prospects, review the queue, and send
through a connected company mailbox.

The private web dashboard includes lead and conversation activity, mailbox capacity,
background send jobs, and editable AI and mailbox connections. The AI connection
supports Groq, OpenAI, Anthropic, Google, Mistral, Cohere, and custom
OpenAI-compatible endpoints.

## Local setup

Install this checkout rather than an unrelated package with the same name:

```bash
uv venv
uv pip install -e ".[dev,web]"
.venv/bin/python manage.py migrate --no-input
.venv/bin/python -m leadzen --help
```

Start the Django API and the Next.js dashboard using the instructions in
[dashboard/README.md](dashboard/README.md).

## Commands

```bash
leadzen init              # configure the product, audience, model, and mailbox
leadzen find 10           # discover ten qualified leads
leadzen find 10 emails    # resolve verified addresses; provider credits apply
leadzen send 5            # open five conversations within mailbox safeguards
leadzen run 5             # find verified leads, then send
leadzen status --json     # report configuration and pipeline state
```

Every command accepts `--db PATH`; `LEADZEN_DB` sets the database path.
Installed builds store data in `~/.leadzen`. A source checkout uses `data/`.

## Deployment

Deploy `dashboard/` to Vercel. Run the Python API and worker on your company VM
with persistent SQLite storage. The frontend calls the API through authenticated
server routes. Provider keys and mailbox passwords stay on the server.

- [Dashboard and API deployment](docs/dashboard.md)
- [Docker deployment](docs/docker.md)
- [Manual connection settings](dashboard/README.md)

## Claude and ChatGPT

Settings includes employee-owned MCP connections for Claude and ChatGPT. These
assistants use the existing Workspace records and approval flow. See
[connector setup and release requirements](docs/mcp-connections.md); a configured
public HTTPS API is required for hosted clients.

## Existing installations

The first startup recognizes the previous configuration tables, creates a recovery
copy named `db.before-leadzen.sqlite3`, and renames the application's database
records. Lead IDs, messages, suppressions, and saved credentials are retained.

Use the `leadzen` command, `leadzen.wsgi:application`, and `LEADZEN_*`
environment variables in service definitions. The fixed tool attribution is omitted
from newly composed customer emails; mailbox signatures and opt-out handling remain.

## Development

```bash
.venv/bin/pytest -q
cd dashboard
npm run lint
npm test
npm run build
```

The Python package is `leadzen/`; the web interface is `dashboard/`.
Discovery and sending use the pinned finder and sender libraries.

## License and source provenance

This company build retains the GNU GPL terms and third-party authors' rights.
See [LICENCE.md](LICENCE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The [Legal Notice](LEGAL_NOTICE.md) and [Privacy Notice](PRIVACY_NOTICE.md)
describe the third-party integrations and operator responsibilities.

LeadZen is owned by Zyene and intended for `leadzen.zyene.com`. Zyene Reviews
(`zyenereviews.com`) is one Zyene product employees can promote through LeadZen;
it is not the platform owner. Each employee has a private outreach workspace.

Accounts are created only by an administrator at `/admin`. There is no public
signup. Bootstrap the first administrator's password privately with
`python manage.py bootstrap_admin --email support@zyene.com`. Administrators send
employee invitations through Resend. Employees use their single-use, 48-hour
setup link to create a password, then complete purpose, audience and connections
setup and take the product tour. There is no public signup.

Employees can add or import contacts, record opt-in, write and edit draft
sequences, activate/pause/archive campaigns, and run due emails. Sending respects
mailbox pacing and sending hours. Follow-ups require a readable reply inbox and
stop on replies or opt-outs. Exact reviewed sequences now support approved automatic
follow-ups through an optional service, which remains disabled by default.
See [automatic follow-ups](docs/automatic-followups.md) for scope and operations,
and [local validation](docs/local-validation.md) for test results.

Company support: [support@zyene.com](mailto:support@zyene.com).
