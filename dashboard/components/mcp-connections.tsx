"use client";

import { useRef, useState } from "react";
import { HelpTooltip } from "@/components/help-tooltip";
import { api } from "@/lib/client-api";
import { formatNewYorkDateTime } from "@/lib/date-time";
import { useStoredData } from "@/lib/use-stored-data";
import styles from "@/components/mcp-connections.module.css";

export type MCPConnection = {
  id: string;
  clientName: string;
  createdAt: string;
  lastUsedAt: string | null;
};

export type MCPConnectionsData = {
  endpoint: string | null;
  available: boolean;
  reason: string | null;
  connections: MCPConnection[];
};

const providers = [
  {
    id: "claude",
    name: "Claude",
    domain: "claude.ai",
    guide: "https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp",
    steps: [
      "Open Claude → Customize → Connectors → Add custom connector.",
      "Name it LeadZen, paste the server URL and use OAuth. Under OAuth client, choose Register automatically.",
      "Sign in to LeadZen, review access and connect. Enable LeadZen in your conversation.",
    ],
    availability: "On Team or Enterprise, your organization owner adds the connector first. Availability depends on your Claude plan.",
  },
  {
    id: "chatgpt",
    name: "ChatGPT",
    domain: "chatgpt.com",
    guide: "https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt",
    steps: [
      "Ask your ChatGPT workspace admin to enable developer mode and create a custom app in Apps.",
      "Name it LeadZen, paste the server URL and choose OAuth. Sign in to LeadZen to review access.",
      "Scan the tools, create the app and select LeadZen in your chat. Your admin can publish it for the team.",
    ],
    availability: "Full tools require ChatGPT Business, Enterprise or Edu on web with workspace permission. Pro supports read/fetch access only.",
  },
] as const;

function CompanyLogo({ name, domain }: { name: string; domain: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className={styles.logoUnavailable}>Logo unavailable</span>;
  return (
    // Company Logo Fetcher skill: use the actual site's favicon, never an invented brand mark.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      className={styles.logo}
      src={`https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://${domain}&size=256`}
      alt={`${name} logo`}
      width={32}
      height={32}
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

export function MCPConnections() {
  const { data, setData, error, loading, refresh } = useStoredData<MCPConnectionsData>("mcp/connections");
  const [open, setOpen] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const inFlight = useRef(false);
  const connections = Array.isArray(data?.connections) ? data.connections : [];
  const endpoint = data?.available && data.endpoint ? data.endpoint : null;

  async function copy() {
    if (!endpoint) return;
    setActionError("");
    try {
      await navigator.clipboard.writeText(endpoint);
      setNotice("Server URL copied.");
    } catch {
      setActionError("Could not copy the URL. Select the server URL and copy it manually.");
    }
  }

  async function disconnect(connection: MCPConnection) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(connection.id);
    setActionError("");
    setNotice("");
    try {
      const result = await api<{ revoked: boolean }>("mcp/connections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connectionId: connection.id }),
      });
      if (result.revoked !== true) throw new Error("This app is still connected. Try disconnecting again.");
      if (data) setData({ ...data, connections: connections.filter((item) => item.id !== connection.id) });
      setConfirm(null);
      setNotice(`${connection.clientName} disconnected.`);
      refresh();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not disconnect this app. Try again.");
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  return (
    <section className={`central-settings-section ${styles.section}`} id="mcp-connections" aria-labelledby="mcp-title">
      <div className={styles.heading}>
        <div className="central-settings-label">
          <h2 id="mcp-title">Claude &amp; ChatGPT</h2>
          <HelpTooltip label="MCP connections">MCP lets an assistant use your existing LeadZen workspace. Each employee signs in separately. Your connections never expose another employee’s records or provider secrets.</HelpTooltip>
        </div>
        <span className={styles.protocol}>MCP</span>
      </div>
      <p className={styles.description}>Use your workspace from Claude or ChatGPT.</p>
      <p className={styles.approval}>Sending and paid actions still need approval in LeadZen.</p>

      {loading && !data && <p className={styles.status} role="status">Loading connections…</p>}
      {error && <div className="error" role="alert">{error} <button className="button" type="button" onClick={refresh}>Try again</button></div>}
      {actionError && <div className="error" role="alert">{actionError}</div>}
      {notice && <p className={styles.notice} role="status">{notice}</p>}

      <div className={styles.providers}>
        {providers.map((provider) => (
          <div key={provider.id} className={styles.provider}>
            <div className={styles.providerHeading}>
              <CompanyLogo name={provider.name} domain={provider.domain} />
              <h3>{provider.name}</h3>
              <button className="button" type="button" aria-expanded={open === provider.id} aria-controls={`mcp-setup-${provider.id}`} aria-label={`Set up ${provider.name}`} onClick={() => setOpen(open === provider.id ? null : provider.id)}>{open === provider.id ? "Close" : "Set up"}</button>
            </div>
            {open === provider.id && (
              <div id={`mcp-setup-${provider.id}`} className={styles.setup}>
                <ol>{provider.steps.map((step) => <li key={step}>{step}</li>)}</ol>
                <p className={styles.availability}>{provider.availability}</p>
                <a href={provider.guide} target="_blank" rel="noopener noreferrer">{provider.name} setup guide <span aria-hidden="true">↗</span></a>
              </div>
            )}
          </div>
        ))}
      </div>

      {data && (endpoint ? (
        <div className={styles.server}>
          <label htmlFor="mcp-server-url">Server URL</label>
          <div className={styles.serverControl}>
            <input id="mcp-server-url" className="input" readOnly value={endpoint} onFocus={(event) => event.target.select()} spellCheck={false} />
            <button className="button" type="button" onClick={() => { void copy(); }}>Copy URL</button>
          </div>
        </div>
      ) : <p className={styles.blocker} role="status">{data.reason || "Connectors need a public HTTPS server. Ask your administrator to finish setup."}</p>)}

      {data && <div className={styles.connections}>
        <div className={styles.connectionTitle}><h3>Connected apps</h3><button className="button ghost" type="button" onClick={refresh} disabled={loading || busy !== null}>Refresh connections</button></div>
        {connections.length === 0 ? <p className={styles.status}>No apps connected yet. Connect from Claude or ChatGPT to get started.</p> : connections.map((connection) => (
          <div className={styles.connection} key={connection.id}>
            <div className={styles.connectionInfo}>
              <strong>{connection.clientName}</strong>
              <p>{connection.lastUsedAt ? <>Last used <time dateTime={connection.lastUsedAt}>{formatNewYorkDateTime(connection.lastUsedAt)}</time></> : <>Connected <time dateTime={connection.createdAt}>{formatNewYorkDateTime(connection.createdAt)}</time></>} · New York time</p>
              {confirm === connection.id && <p>Disconnect this app? Its access stops immediately.</p>}
            </div>
            <div className={styles.actions}>
              {confirm === connection.id ? <>
                <button className="button" type="button" disabled={busy !== null} onClick={() => setConfirm(null)}>Cancel</button>
                <button className="button danger-button" type="button" disabled={busy !== null} onClick={() => { void disconnect(connection); }}>{busy === connection.id ? "Disconnecting…" : "Confirm disconnect"}</button>
              </> : <button className="button" type="button" aria-label={`Disconnect ${connection.clientName}`} disabled={busy !== null} onClick={() => setConfirm(connection.id)}>Disconnect</button>}
            </div>
          </div>
        ))}
      </div>}
    </section>
  );
}
