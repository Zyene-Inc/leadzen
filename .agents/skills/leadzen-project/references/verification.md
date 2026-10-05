# Verification and operations

Use `.venv/bin/python` and `.venv/bin/pytest` from the repository root. Run dashboard
commands from `dashboard/`. `npm run lint` is currently a TypeScript check, not a
general ESLint scan. Read the installed Next.js docs under
`dashboard/node_modules/next/dist/docs/` before using version-sensitive APIs.

## Choose checks by behavior

| Change | Useful coverage |
| --- | --- |
| Tools, ownership, approvals, canonical context | `tests/test_chat.py`, `test_chat_workspace.py`, `test_chat_ai.py` |
| Discovery / progress | `tests/test_discovery.py`, `test_discovery_live.py`, `test_activity.py` |
| Sending / suppression / follow-ups | `tests/test_reviewed_outreach.py`, `test_campaigns.py`, `test_automatic_followups.py`, `test_lead_crm.py`, `test_lead_timeline.py` |
| Accounts / configuration | `tests/test_accounts*.py`, `test_setup_wizard.py`, `test_workspace_settings.py`, `test_runtime_settings.py` |
| Chat presentation / streaming / shared refresh | `dashboard/tests/chat-presentation.test.tsx`, `chat-experience.test.tsx`; locate related protocol tests with `rg --files dashboard/tests` |

For an application change, run the relevant regression tests; broad integration or
release work warrants full suites. Run dashboard `npm test`, `npm run lint`, and
`npm run build` as applicable, plus `git diff --check`. Avoid repeatedly running
everything without a new change/failure. If a user asks for repeated testing, report
exact scopes and repetitions rather than claiming all production buttons were tested.

React Doctor's tracked diff can miss this project's untracked components. When
using it, inspect the full tree as well and review findings rather than suppressing
them for a score. Report warnings honestly. Browser checks should cover real
interaction behavior, responsive layout, keyboard/focus, reduced motion and themes.
Use the environment's permitted browser tools; do not require one vendor's tool
name in another agent host. Keep desktop/mobile screenshots as evidence, with
synthetic records or redacted private data.

## Disposable local preview

Read `tests/scenarios/local_preview.py` before launching. It scrubs provider
environment, uses a generated fixture encryption key, seeds local accounts,
migrates its disposable databases and replaces provider actions with synthetic
adapters. It exercises the actual application persistence/approval/stream paths.
Do not connect this preview to a production database or real credentials.

Check ports first. In a backend terminal from the repository root:

```sh
LEADZEN_PREVIEW_DIR=$(mktemp -d /tmp/leadzen-preview.XXXXXX) .venv/bin/python tests/scenarios/local_preview.py
```

In a frontend terminal from `dashboard/`:

```sh
LEADZEN_API_URL=http://127.0.0.1:8000 LEADZEN_API_TOKEN=synthetic-local-dashboard-token LEADZEN_DASHBOARD_PUBLIC_URL=http://localhost:3001 npm run dev -- --port 3001 --hostname 127.0.0.1
```

Use the fixture login from the script. Never overwrite a production/admin access
file with demo credentials. Inspect before reusing an older preview database and
retain its fixture key. Do not start a second server on an occupied port or kill
unrelated processes. Stop the identified preview dev server before a build if
generated Next.js types conflict; never delete source to fix generated cache issues.
Restore it afterward when delivering a preview.

Synthetic success does not validate real keys, billing, SMTP/IMAP behavior, delivery
or inbox placement. Fresh user approval is required for those external checks.

## Authorized release only

Read `docs/deployment.md` and inspect current release scripts before acting. The
documented platform is Vercel frontend plus an existing Google VM backend with
persistent SQLite/workspace data. Do not replace this architecture or create paid
resources as a routine fix. A frontend deploy alone cannot apply backend migrations.

Prepare a concrete reviewed release from the entire intended dirty-source snapshot,
including untracked source/assets; never assume a git commit includes the work.
Preserve live credentials and the stable encryption key. Stop intake/scheduler and
drain relevant workers before schema changes or release recovery backups. Back up
the control DB, initialized employee DBs, matching environment/key, source and service
units. Apply **all current migrations**, not a stale hard-coded last number, to
control and employee databases. A Settings database export is only one workspace,
not full-server recovery.

Do not restart delivery automatically after a release hold; inspect the release
procedure and obtain the required fresh action authorization. Document deployed
snapshot, migration results, health/auth checks and rollback artifacts without
copying secrets. Never infer current scheduler health from the enabled flag.
Historical deployment approval does not authorize the next release, and deployment
does not authorize email tests or paid enrichment.
