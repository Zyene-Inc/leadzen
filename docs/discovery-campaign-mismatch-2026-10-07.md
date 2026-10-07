# Dental leads outside a restaurant and home-services search — October 7, 2026

## Production observation

In the employee's open LeadZen browser, discovery run
`dbead74b-a79c-4306-826b-08cdd202e53d` showed the saved target:
owners, founders and marketing decision-makers at Restaurants & Hospitality
and Home Services businesses in the United States with 1–10 employees.
It showed 4 of 10 qualified leads saved, all four at dental practices. Their
qualification explanations explicitly acknowledged that dental was outside
the requested industry, but accepted them because dental was considered a
good general fit for Zyene Reviews. Six other profiles were rejected. The
run showed zero profiles discovered and ten evaluated, so this run evaluated
existing candidate backlog rather than newly retrieved profiles. No email
credits were recorded for this run; no messages were sent by this run.
The earlier Chat discovery used a broader saved audience that explicitly
included Dentist and Healthcare & Dental. Its dental results matched that
earlier target; the audience was narrowed before this run.

## Cause

The pinned `openoutfind` qualifier receives the product description and the
campaign target in one model prompt. Its instruction asks whether an industry
is relevant to the product, leaving room for the model to treat broader product
fit as a substitute for the narrower campaign target. The run's saved reasons
show that exact substitution. The finder can surface candidates from the
existing unlabeled backlog; a candidate's appearance in live activity is not
itself a qualification. The pinned BetterContact search adapter also documents
that its provider industry filter is ineffective, so the qualifier has to
enforce the target before saving a lead.

## Correction and verification

`leadzen/discovery_progress.py` now passes an explicit target-precedence rule
to the qualifier: product documentation cannot broaden the target, and explicit
industry, geography, headcount and role restrictions must be met. If a positive
model verdict nevertheless says the lead falls outside the campaign, the
adapter changes it to a rejection before the pinned finder saves the deal or
imports it as a Workspace contact. Focused synthetic regressions were added to
`tests/test_discovery_live.py` for the four mismatch phrasings observed.

Syntax compilation passed for both changed Python files. An isolated execution
of the safeguard passed four mismatch cases and one matching case. Local pytest
startup was slow, but the four targeted Django regression cases eventually
passed (`4 passed, 42 deselected` in `tests/test_discovery_live.py`).

## Release — October 7, 2026

The two-file change passed all nine GitHub PR checks, including the full backend
suite, dashboard checks, browser regression, security checks and Vercel preview.
PR [#6](https://github.com/Zyene-Inc/leadzen/pull/6) was approved and
squash-merged into GitHub `main` at
`60936f74c6fd0747bfc17140ef27c213154a7b9b`. The merged discovery module
has SHA-256
`18da99bc0d13ed5431fb6abe7baa121d0cbd1d981b07285902f2dc5770637b7a`.
The post-merge [`main` workflow](https://github.com/Zyene-Inc/leadzen/actions/runs/37651939591)
also completed successfully, including its backend tests and build.

On the existing Google VM, the two pre-change module copies were backed up in
the root-only `/srv/private/leadzen-discovery-hotfix-20261007/` directory. The
merged module was byte-verified, syntax-checked, and placed in both the live
source tree and installed package. Both live copies match the merged SHA-256.
Only `leadzen.service` was restarted; `leadzen.service` and
`leadzen-followups.service` were active afterward. Authenticated public health
and readiness passed, including database and migration readiness; anonymous
health returned 401. This is a narrow discovery hotfix on the October 6 backend
installation, not a full backend rebuild or migration.

Vercel's ready production deployment `dpl_3yQhgRRMePMtaZRNtNQWbxZ1u1vt`
was assigned to the public `leadzen.zyene.com` alias. Vercel inspection
resolved that alias to the same deployment, and public `/login` returned HTTP
200 with its deployment ID in asset URLs.

The original production run and its four saved dental contacts remain
unchanged. This correction applies to future qualification verdicts; no live
discovery, cleanup, email lookup, provider request, or outbound email was run
as part of deployment. Any pending email-credit approval should be reviewed
against the actual selected lead list.
