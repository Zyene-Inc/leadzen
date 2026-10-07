# MCP connections validation — October 3, 2026

## Before / After / Why

Before, employees could use the portal or its own Chat interface. Settings had no
external assistant connection, and the private dashboard service token could not
safely be handed to an MCP client.

After, Settings includes compact **Claude & ChatGPT** cards with each site's logo,
optional setup steps, official guides, copyable configured MCP URL and real
authenticated connection/disconnect controls. The OAuth consent page identifies
the employee, callback host, permissions and request expiry in New York time.
Sign-in preserves only the validated MCP consent path, with no arbitrary return URL.

Forty typed employee tools reuse canonical Workspace services. Provider actions
create a durable direct-action operation, show the existing portal approval, and
execute once without a model planner loop. Each mutation has a connection-bound
idempotency UUID. Reads and polling do not start providers. Credentials, account
administration and new standing automatic authorization stay in the portal.

This gives employees one set of records and approvals from their preferred
assistant while retaining ownership, pacing, reply/suppression guards and the
platform's fixed America/New_York clock.

## Checked behavior

- OAuth metadata, dynamic public client registration, employee consent and S256
  authorization code exchange; audience/client/callback/PKCE mismatch rejection.
- Hashed opaque access/refresh tokens, expiration, rotation and family revocation
  on replay. Abandoned consent does not appear as a connected app.
- Employee disconnect and password/reset/account changes permanently revoke old
  grants; worker/provider/SMTP/IMAP guards revalidate connection and account access.
- Actual separate control/employee SQLite databases: MCP tokens read only their
  employee's leads, even when local IDs overlap. Workers resolve OAuth grants from
  the control database and deny wrong actors or revoked connections.
- Strict bounded schemas reject actor overrides, external handlers, unbounded
  batches, invented opt-in, foreign timezones and client approval tokens/booleans.
- Saved lead add/update/import/delete, nonsecret settings, sequence draft/pause,
  stored Inbox query, scoped operation polling/cancellation and idempotent replay.
- Approved reply checks preserve campaign contacts in canonical CRM reads and
  relation refreshes. The old process-wide Deal manager exclusion was removed
  from mailbox preparation: AI classification credentials do not select a sender.
  The regression failed before the change and passed afterward; approved sending
  services retain their own recipient guards and reject legacy worker jobs.
- Discovery, paid email enrichment, generation, mailbox check and sending stay
  behind portal review. Synthetic send acceptance occurs once; duplicate dispatch,
  replay, stale setup, expiry and disconnect prevent new effects.
- Existing portal discovery Resume continues only the saved remaining goal with
  its original audience/email scope and approval expiration.
- UI setup/copy/error/loading, authentic connection status, revoke failure and
  repeated submission, consent approve/deny, callback verification and New York
  timestamps. Layout uses existing theme tokens, responsive stacking and native
  focusable controls; setup details remain collapsed.

## Verification evidence

- Final full backend suite: **1,233 passed**, one existing Pydantic AI event-loop
  deprecation warning, `/tmp/leadzen-mcp-backend-verified.log` (333.56 seconds).
- Focused capability and protocol suite: **56 passed** (41 capability cases and
  15 protocol/transport cases), `/tmp/leadzen-mcp-final-focused.log`.
- OAuth/account/invitation suite: **58 passed** (39 OAuth cases, one real database
  scenario, 18 account/invitation regressions), auth agent's final run.
- Extended real database/transport isolation scenario: **1 passed**,
  `/tmp/leadzen-mcp-isolation-final.log`.
- Full dashboard suite after final consent/setup refinements: **1,147 tests across
  20 files passed**, `/tmp/leadzen-mcp-ui-verified.log`.
- TypeScript and Next.js production build passed:
  `/tmp/leadzen-mcp-ui-final-types.log`, `/tmp/leadzen-mcp-build-verified.log`.
- Mailbox, MCP, New York and sending-boundary regressions: **112 passed**,
  `/tmp/leadzen-mcp-mailbox-regression-green.log`.
- Built-in Django checks: zero issues. Migration drift: no changes. Diff
  whitespace check passed.
- React Doctor tracked diff: **100/100**. Full tree: **69/100**, zero errors and
  29 warnings. Existing components account for 28; the new redirect warning is
  a scanner hypothesis in `lib/auth.ts`. Its destination is restricted by
  `safeMcpReturnPath` to `/mcp/connect?request=<opaque handle>`, never an arbitrary
  origin/path, and negative return-path tests pass. It was not suppressed.
- Authenticated synthetic local HTTP check after restart: employee sign-in 200,
  Settings route 200, connection metadata 200 with `available:false` and no public
  endpoint, anonymous MCP 401. The MCP section renders after the client loads
  Settings data; its contents are verified by UI tests, not server HTML alone.
  Local preview migrations include account `0003`.

The broad backend run initially stalled reading cloud-evicted installed sklearn
bytecode (`hidden,compressed,dataless`). Two interrupted attempts are not passing
full-suite evidence. A temporary `PYTHONPYCACHEPREFIX` avoids those files without
modifying installed dependencies. The first completed broad run exposed 13
related failures caused by mailbox preparation hiding campaign contacts. The
regression above reproduced the issue before its fix; the final full run passed
all 1,233 tests. No installed dependency source was changed.

## Limits and release state

Implementation and checks are local. No deployment, real provider spend, live
mailbox operation or real email send was performed. The disposable preview uses
synthetic providers and has no configured public MCP URL.

Browser visual validation remains unavailable under the earlier browser URL policy
restriction; no alternative control path was used to bypass it. Automated UI and
HTTP checks do not certify pixel layout or logo rendering in a real browser.

Hosted Claude/ChatGPT need a reachable HTTPS API and authorized release of the
additive `leadzen_accounts/0003_mcp_oauth` migration plus current source. A real
client OAuth/tool scan has not been performed. In Claude's **OAuth client** setting,
choose **Register automatically**. ChatGPT full write support depends on plan/workspace permissions;
the UI links the current official guides. See [setup](mcp-connections.md).
