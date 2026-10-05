![LeadZen by Zyene](docs/leadzen-logo.svg)

# LeadZen by Zyene

[LeadZen](https://leadzen.zyene.com) is Zyene's private workspace for responsible B2B lead discovery, outreach, and campaign operations. Employees use it to define an audience, find qualified prospects, prepare outreach, and manage approved company mailboxes.

Access is by administrator invitation. LeadZen has no public signup.

## What is in this repository

- Django API, worker, and command-line application
- Next.js dashboard in [`dashboard/`](dashboard/)
- Deployment, operations, and recovery documentation in [`docs/`](docs/)
- GitHub contribution, security, and maintenance guidance

The dashboard shows lead and conversation activity, mailbox capacity, background send jobs, and editable AI and mailbox connections. It supports Groq, OpenAI, Anthropic, Google, Mistral, Cohere, and approved OpenAI-compatible endpoints.

## Architecture

```text
Employee browser → Next.js dashboard → authenticated Django API and worker
                                          ├─ private workspace data
                                          ├─ approved AI and lead-discovery services
                                          └─ connected company mailboxes
```

The browser does not receive provider credentials or access the application database. The API and worker enforce private employee workspaces, sending limits, approval rules, and opt-out handling.

## Local setup

Install this checkout rather than an unrelated package with the same name:

```bash
uv venv
uv pip install -e ".[dev,web]"
.venv/bin/python manage.py migrate --no-input
.venv/bin/python -m leadzen --help
```

Start the Django API and the Next.js dashboard with the instructions in [dashboard/README.md](dashboard/README.md). For a disposable preview that does not send externally, use [local validation](docs/local-validation.md).

## Common commands

```bash
leadzen init              # configure product, audience, model, and mailbox
leadzen find 10           # discover ten qualified leads
leadzen find 10 emails    # resolve verified addresses; provider credits apply
leadzen send 5            # send through the configured mailbox safeguards
leadzen run 5             # find verified leads, then send
leadzen status --json     # report configuration and pipeline state
```

Every command accepts `--db PATH`; `LEADZEN_DB` sets the database path. Installed builds store data in `~/.leadzen`; a source checkout uses `data/`.

## Operations and release information

- [Dashboard and API deployment](docs/dashboard.md)
- [Docker deployment](docs/docker.md)
- [Production release and rollback](docs/production-release.md)
- [Production preflight](docs/production-preflight.md)
- [Production recovery](docs/production-recovery.md)
- [MCP connection setup](docs/mcp-connections.md)

The frontend is deployed separately from the API and worker. A backend release requires the controlled release process, including current preflight and recovery evidence; merging a repository change does not establish backend release readiness.

## Contributing and support

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Use the GitHub issue forms for scrubbed bug reports and product requests. Send suspected vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

For account, product, or integration support, contact [support@zyene.com](mailto:support@zyene.com). See [SUPPORT.md](SUPPORT.md) for the right route.

Repository maintainers follow the [maintenance guide](docs/repository-maintenance.md) to keep documentation, issues, pull requests, and release evidence current.

## License and provenance

This company build retains the GNU GPL terms and third-party authors' rights. See [LICENCE.md](LICENCE.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), [LEGAL_NOTICE.md](LEGAL_NOTICE.md), and [PRIVACY_NOTICE.md](PRIVACY_NOTICE.md).

LeadZen is owned by Zyene and operated at [leadzen.zyene.com](https://leadzen.zyene.com). Zyene Reviews is one Zyene product employees can promote through LeadZen; it is not the platform owner.
