# Contributing to LeadZen

Thank you for improving LeadZen. This repository supports a private employee workspace, so changes must protect employee data, provider credentials, mailbox safeguards, and outreach approvals.

## Before you start

- Read the relevant documentation in [`docs/`](docs/) and the dashboard guide in [`dashboard/README.md`](dashboard/README.md).
- Use a focused branch and pull request for each change.
- Do not include API keys, passwords, access tokens, customer data, real email addresses, mailbox contents, production exports, or screenshots containing them.
- Do not send email, contact providers, spend provider credits, or deploy while testing a change unless the operator has specifically approved that action.

## Local development

Set up the application with the commands in the [README](README.md#local-setup). The dashboard and API have separate local setup instructions in [`dashboard/README.md`](dashboard/README.md).

Use synthetic data for local checks. When a change affects behavior, run the checks for the area you changed and describe the result in the pull request. Update user, operations, or security documentation when the change affects those areas.

## Pull requests

1. Explain the user or operator problem being addressed.
2. Keep the change scoped and document migrations, configuration, release, data, privacy, or security effects.
3. Complete the pull request template with the checks you ran.
4. Wait for required checks and review before merging to `main`.

The default branch is protected. Do not commit directly to `main`, force-push shared branches, or bypass review and required checks.

## Reporting problems

Use the [bug report form](../../issues/new/choose) for reproducible product or repository problems, after removing sensitive information. Use the [feature request form](../../issues/new/choose) to describe a user problem and proposed outcome.

For a suspected security issue, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Conduct

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
