# Claude and ChatGPT connections

LeadZen exposes a remote MCP endpoint over the existing employee Workspace. It
does not create another CRM. Settings → **Claude & ChatGPT** provides each site's
logo, connector setup steps, a copyable server URL, and the employee's authenticated
connections with disconnect controls.

## Employee flow

Settings → **Claude & ChatGPT** → **Set up** shows numbered steps for each
assistant, with the server URL and a copy button inside the paste step.

1. Copy the server URL from LeadZen Settings.
2. Claude: **Customize → Connectors → + Add → Add custom connector**, name
   **LeadZen**, paste it into **Remote MCP server URL**, **Continue**. Choose
   **Authentication: Sign in now** and **OAuth client: Register automatically**;
   LeadZen supports dynamic registration, not Claude's published identity. On
   Team/Enterprise an owner adds it once under **Organization settings →
   Connectors → Add → Custom → Web**, then each employee selects **Connect**.
   ChatGPT: **Plugins → + → Add custom MCP server**, name **LeadZen**, paste the
   URL under **Connection**, choose OAuth, accept the risk warning and select
   **Create as a plugin**. A ChatGPT admin publishes it for the workspace.
3. The assistant opens `/mcp/connect`. Sign in to LeadZen and review the account,
   assistant callback host and requested access.
4. Connect, then enable LeadZen in the conversation (Claude: **+ → Connectors**;
   ChatGPT: type **@** and select LeadZen). Settings → **Refresh** under
   Connected apps lists the new grant.
5. Ask for saved leads, inbox messages, outreach, drafts, target or workspace
   settings. Mutations take a new `requestId` UUID. Repeating the same UUID and
   arguments returns the saved operation instead of repeating the action.
6. For discovery, enrichment, AI drafting, mailbox sync or sending, open the
   returned `portalUrl`. LeadZen presents the exact action for employee approval.
   `get_operation` reads its recorded state and result without restarting it.
7. Disconnect from Settings to revoke the grant. New requests and queued/running
   external actions recheck access, including immediately before transport bytes.

Imported profiles, lead notes and inbound emails remain untrusted content. An
assistant cannot turn their text into authority to send, buy email addresses,
restore an opt-out or enable Autopilot. Credentials, account administration,
provider tests, backups and new recurring authorizations stay in the portal.

## Supported capabilities

The static registry in `leadzen/mcp/tools.py` supplies 40 strictly typed tools:

- Workspace status/context, lead search/details, add/edit/import/delete contacts.
- Discovery and selected verified email lookup, stored credit usage and stop.
- Personal draft creation/read/edit/revision and exact initial/reply send requests.
- Stored sequence create/list/detail/pause and one bounded due-send request.
- Stored Inbox replies/conversations, reply check and reply drafting.
- Nonsecret settings read/update, lead target, Autopilot state/pause, activity,
  suppression and portal-reviewed removal of manual suppression.
- Poll or cancel an operation owned by the same employee and connection.

Automatic follow-up and Autopilot standing authorization remain an explicit portal
review. Scheduling and all employee-facing times use **America/New_York**, including
automatic daylight-saving changes. Standard shared suppression, reply, pacing,
allowance and sending-window checks remain enforced at the actual send.

## Server configuration and release requirements

Backend-only configuration:

```dotenv
LEADZEN_PUBLIC_URL=https://your-dashboard-host
LEADZEN_MCP_PUBLIC_URL=https://your-api-host/mcp
```

The MCP resource, OAuth endpoints and discovery metadata must all reach the same
API host over HTTPS. Use the existing API deployment, not the dashboard's private
`/api/proxy` path. Keep the service token and provider secrets server-side. Reverse
proxies must pass Authorization, Origin, Accept and MCP-Protocol-Version headers
without caching OAuth/MCP responses. Do not require the private dashboard service
token on these public OAuth routes: they enforce their own employee OAuth tokens.

Routes include `/mcp`, `/.well-known/oauth-protected-resource/mcp`,
`/.well-known/oauth-authorization-server`, and `/mcp/oauth/{register,authorize,token,revoke}`.
Transport uses stateless Streamable HTTP with JSON responses; operations are durable
background jobs rather than long HTTP requests. Supported protocol revisions are
2025-03-26, 2025-06-18 and 2025-11-25. Unauthenticated access gets a Bearer metadata
challenge. Origin, body size, tool schemas, task count and request rates are bounded.

Apply all current migrations, including `leadzen_accounts/0003_mcp_oauth`, to the
control DB and initialized employee DBs as the existing release procedure requires.
OAuth models stay in the control DB. Authorization code exchange requires S256 PKCE,
the exact registered callback and resource. Tokens are opaque; only hashes persist.
Access tokens expire after 15 minutes; optional `offline_access` supplies rotating
refresh tokens. Replay revokes the grant. Password changes, reset invitations,
account disable/delete and employee disconnect permanently revoke existing grants.

Public client registration is bounded and makes no network requests for arbitrary
client metadata. Consent shows the untrusted app name and registered callback host;
the employee must recognize their initiated request before connecting.

No valid MCP public URL means Settings shows **Not ready to connect yet** instead
of setup steps. `GET /api/mcp/connections` returns `setup`: each blocking backend
setting name, the problem and a corrected public URL (never secret values). The
common mistake is an origin without the path: `LEADZEN_MCP_PUBLIC_URL` must be
exactly `https://<api-host>/mcp`. The October 8, 2026 production record set it to
`https://leadzen-api.zyene.com`, which fails this check; the fix is
`https://leadzen-api.zyene.com/mcp` in the active `/etc/leadzen-*.env`, followed
by an API restart (an owner-approved production change). The disposable localhost preview can show the UI but hosted
Claude/ChatGPT cannot connect directly to that localhost server. An authorized
HTTPS rollout and real client connection test are required before claiming live
compatibility or availability.

## Client availability

Claude custom connector availability and organization setup depend on its plan.
See the [official Claude guide](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).

Full read/write custom MCP apps currently require ChatGPT Business, Enterprise or
Edu on web and the appropriate workspace permissions. Pro supports read/fetch
connections. See [OpenAI's current guide](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).
Client plans and interface labels may change; the Settings help links to these
guides rather than implying that LeadZen can enable a third-party subscription.

Implementation follows the [MCP transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
and [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization).
