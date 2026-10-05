# Enabled integration release gate

Local transport/OAuth/provider tests use synthetic responses, exact employee
ownership and the application's real approval/STOP/dedup/uncertain-operation
guards. These do not prove current provider credentials, inbox delivery, billing,
sender verification, provider quotas or genuine external MCP-client compatibility.
The release policy must enumerate enabled features. A disabled policy feature is
excluded scope, not a new application kill switch; automation also requires the
actual environment gates and standing employee authorization.

Prepared live checks require fresh approval of the exact account and action:

| Feature | Smallest prepared check | Remaining required input/authorization |
| --- | --- | --- |
| Invitation email | One invitation to an operator-selected controlled address; set up once and verify reuse rejection. No retries of an ambiguous Resend acceptance. | Exact recipient, verified sender, one-send approval and private current credential. |
| Mail transport | One approved synthetic plain-text message to an operator-controlled inbox, followed by one bounded IMAP/read check and receipt reconciliation. | Exact sender/recipient and subject, one-send approval, current mailbox app credential and provider receipt. |
| AI | One synthetic prompt without customer data, maximum 256 input and 64 output tokens, maximum cost USD 0.01. | Exact provider/model/employee, credential, spending approval and model-specific price/limit validation before action. |
| Enrichment | One selected operator-owned public professional profile, maximum one credit; collect the existing operation if acceptance is uncertain. | Exact canonical selected profile, authorized owner, one-credit approval and current provider quota. |
| MCP | Genuine client consent to a disposable employee; read-only contact list, one refresh, revoke in portal, then prove old access/refresh fail. No tools that send or spend. | Exact client/account, configured trusted HTTPS endpoint and explicit test consent. |

No destination, provider or client action in this table has been authorized or
performed by preparing it. Fill the exact inputs privately and record only safe
aggregate results and provider receipt categories. A failed/unknown external
operation stays held until acceptance or usage is reconciled. Never turn on broad
scheduling, blindly resend, buy again or substitute customer data for these tests.
