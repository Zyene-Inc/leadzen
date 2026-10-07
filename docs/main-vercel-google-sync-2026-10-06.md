# Main, Vercel, and Google backend sync — October 6, 2026

## Completed

- Zyene GitHub repository has only `main`, at `f1d8cfe314ba84dd7b9e59592fba0b721e63e0d4` when checked. Complete application release-input comparison found no newer local runtime source; local differences were older README, CI, and risk-decision content, one browser assertion, one backend test variation, and repository templates.
- [Main CI run 37505054023](https://github.com/Zyene-Inc/leadzen/actions/runs/37505054023) completed successfully: backend test, Node 22/24 dashboard, browser, build, image security, and secrets jobs all passed.
- Vercel deployment `dpl_E14WyTSQh5W4bKtUPtUKYTPYsoAL` is READY for main and is assigned to `leadzen.zyene.com`. Public `/login` returned HTTP 200 with this deployment ID in asset URLs.
- Main source was captured as a linux/amd64 candidate at `/Users/ashishdikonda/Desktop/Openoutreach/leadzen-main-release-f1d8cfe-20261006`. Its source SHA-256 is `2754d2cdddca10e3bed26b822a343f1a20dc1895a3274d6119a11d81cb4cf892`. The source archive and manifest were uploaded and byte-verified under the VM's root-only `/srv/private/leadzen-staged-f1d8cfe-20261006/`. The VM service does not use this staged candidate.
- The live Google API and follow-up units reported active. Both live databases returned `ok` for SQLite quick checks. The previously deployed deleted-employee invitation hotfix remains present and its authenticated API health check passed earlier on October 6.

## Full Google backend release remains blocked

The VM runs the October 3 source baseline plus the invitation hotfix. The control and employee databases are at accounts migration 0002 and configuration migration 0014; main includes accounts 0004 and configuration 0019. The live process and `/etc/leadzen.env` both lack `LEADZEN_ENV` and `LEADZEN_SECRET_KEY`, which current WSGI requires. The current matched recovery and independent backup paths, deployed release manifest, and new release/preflight modules are absent on the VM.

The staged source is a preparation step only. Applying it now would require a controlled release: reconcile and preserve configuration, establish a complete matched and independently held recovery set for both databases, stop and drain writers, apply and verify all migrations, build and validate the runtime, and pass the remaining release gates in `docs/production-release.md`. No backend migration or full source replacement was performed in this sync check. No real email or paid provider action was triggered.
