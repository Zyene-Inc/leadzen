# Repository maintenance

This guide keeps the public LeadZen repository clear, accurate, and safe to use.

## Every pull request

1. Use a focused branch and complete the pull request template.
2. Confirm required GitHub checks and reviewer approval are complete before merging.
3. Record migration, configuration, release, privacy, and security effects in the pull request.
4. Use synthetic or scrubbed data in source code, screenshots, issues, pull requests, and logs.
5. Delete the source branch after the pull request is merged, unless it is an intentional long-lived release branch.

## Weekly

1. Triage open issues and pull requests: label, assign, close duplicates, and request missing reproduction steps.
2. Review failed, cancelled, or skipped checks. A cancelled check needs a clear rerun or explanation before it is treated as complete.
3. Check that repository links, the README, support address, and public About section still describe the active product.
4. Confirm that merged temporary branches are removed. `main` is the normal long-lived branch.

## Monthly

1. Review dependency, security, and platform updates through a normal pull request. Do not enable automated branch creation without an owner decision.
2. Review repository access, branch protections, GitHub Actions permissions, and the list of organization owners with the responsible administrator.
3. Review the issue forms, pull request template, security contact, and support links.
4. Refresh documentation that describes product behavior, integrations, deployments, or operator procedures.

## Release responsibility

A merged pull request may publish the frontend through the connected deployment service. Before treating a production release as complete, verify the deployment status and the intended environment.

The backend is released separately. Follow [production release and rollback](production-release.md), including maintenance controls, current preflight evidence, backup and recovery checks, and the final operator approval. Never treat a GitHub merge as proof that the backend is current or ready.

## Information handling

Never place credentials, access tokens, employee records, customer data, real mailbox content, production database exports, or private infrastructure details in this repository, issues, pull requests, Actions logs, or screenshots. Report suspected vulnerabilities according to [SECURITY.md](../SECURITY.md).
