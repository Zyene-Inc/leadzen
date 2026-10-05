# Credential disposition and key recovery

The October 4 review retained a redacted, per-location disposition in
`docs/production-credential-disposition-2026-10-04.json`: 43 real or unresolved
historical locations, plus three separately classified scanner false positives.
Reusable credentials, captured sessions and Google Chromium build identifiers
require their provider/account owners' classification. Ownership and revocation
are currently UNVERIFIED. No questionable credential was used against a provider.

For each disposition, use its service, historical file/line/commit and recognized
field names to identify the owner privately. Ask that owner to inspect the
administrative console using their existing legitimate login; do not paste or
probe the exposed credential. Record whether it is a public identifier, revoked
historical secret, or still reusable credential, and retain a redacted receipt.
For reusable secrets/sessions, prepare an exact owner-authorized revocation and
replacement action, terminate exposed sessions, update the matching private
service configuration, and verify the administrative revocation record. A current
source deletion, new key elsewhere or history cleanup does not revoke old material.
Do not rewrite Git history or rotate live credentials through these local tools.

The stable `LEADZEN_SETTINGS_KEY` has a separate recovery requirement. It decrypts
existing employee settings, invitations and mailbox passwords. Preserve it with
the complete matched recovery set and restrict access; do not replace it as a
generic response to unrelated historical findings. Any actual exposure or key
change needs an explicitly approved compatibility, complete re-encryption and
recovery procedure proven on isolated copies first. Preserve the stable signing
key separately for matching authentication recovery.

Current-source Gitleaks uses full redaction and excludes private environments,
databases, logs and captured historical pages from the release artifact. The
pinned CI scanner checks current source and newly introduced historical material;
manual whole-history scanning retains the historical gate rather than suppressing
it. A clean current scan does not close historical credential disposition.

Production logging is restricted to safe fixed categories and aggregate request
outcomes. Regression tests exercise tokens, authorization codes, cookies,
passwords, provider exceptions and personal data. Existing legacy logs/storage
must be inspected through authorized counts-only checks. Nested or malformed
mailbox storage blocks preflight with fixed codes; remediation of existing data
requires an approved private recovery-aware operation, never silent key or row
rewriting. Do not upload private scanner input, recovered configuration or logs.
