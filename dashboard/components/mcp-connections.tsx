"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
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

export type MCPSetupProblem = {
  setting: string;
  problem: string;
  example: string;
};

export type MCPConnectionsData = {
  endpoint: string | null;
  available: boolean;
  reason: string | null;
  setup?: MCPSetupProblem[];
  connections: MCPConnection[];
};

type Step = { title: string; body: ReactNode; url?: string; link?: { href: string; label: string } };

type Provider = {
  id: "claude" | "chatgpt";
  name: string;
  domain: string;
  guide: string;
  availability: string;
  steps: Step[];
};

// Labels follow the official guides (Claude custom connectors and OpenAI's
// "Connecting custom MCP servers in ChatGPT", checked November 4, 2026).
const providers: Provider[] = [
  {
    id: "claude",
    name: "Claude",
    domain: "claude.ai",
    guide: "https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp",
    availability: "Works on Claude web and desktop for Free, Pro, Max, Team and Enterprise. Free allows one custom connector. On Team or Enterprise, an owner adds LeadZen once in Organization settings → Connectors → Add → Custom → Web; then each employee finds it in Customize → Connectors, selects Connect and continues at step 4.",
    steps: [
      {
        title: "Open Claude connectors",
        body: <>In Claude, go to <b>Customize → Connectors</b>, select <b>+ Add</b>, then <b>Add custom connector</b>.</>,
        link: { href: "https://claude.ai/customize/connectors", label: "Open Claude connectors" },
      },
      {
        title: "Name it and paste the server URL",
        body: <>Enter the name <b>LeadZen</b>. Copy the URL below into <b>Remote MCP server URL</b>, then select <b>Continue</b>.</>,
        url: "Remote MCP server URL",
      },
      {
        title: "Choose sign-in settings",
        body: <>Under <b>Authentication</b>, choose <b>Sign in now</b>. Under <b>OAuth client</b>, choose <b>Register automatically</b>. No client ID, secret or request headers are needed. Select <b>Add</b>.</>,
      },
      {
        title: "Approve in LeadZen",
        body: <>A LeadZen page opens. Sign in if asked. Check that it says <b>Claude wants access</b>, your email is shown and the assistant callback is a Claude address, then select <b>Connect</b>. You return to Claude.</>,
      },
      {
        title: "Turn it on in a chat",
        body: <>In a conversation, select <b>+ → Connectors</b> and switch on <b>LeadZen</b>. Try “Show my newest leads.”</>,
      },
      {
        title: "Check it here",
        body: <>Select <b>Refresh</b> under Connected apps below. Claude appears with the time it connected.</>,
      },
    ],
  },
  {
    id: "chatgpt",
    name: "ChatGPT",
    domain: "chatgpt.com",
    guide: "https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt",
    availability: "Full access needs ChatGPT Business, Enterprise or Edu on the web; it is not available in the mobile apps. On Business, only admins and owners can add LeadZen. On Enterprise or Edu, admins can let selected members add it. Pro can connect with read-only access.",
    steps: [
      {
        title: "Open ChatGPT Plugins",
        body: <>On chatgpt.com, open <b>Plugins</b>, select <b>+</b>, then <b>Add custom MCP server</b>. If you can’t, ask your ChatGPT admin to add and publish LeadZen, then continue at step 5.</>,
        link: { href: "https://chatgpt.com/plugins", label: "Open ChatGPT Plugins" },
      },
      {
        title: "Name it and paste the server URL",
        body: <>Enter the name <b>LeadZen</b>. Under <b>Connection</b>, paste the URL below.</>,
        url: "MCP server URL",
      },
      {
        title: "Choose OAuth and create",
        body: <>For authentication, choose <b>OAuth</b>. LeadZen registers ChatGPT automatically, so no client ID or secret is needed. Check <b>I understand and want to continue</b>, then select <b>Create as a plugin</b>.</>,
      },
      {
        title: "Approve in LeadZen",
        body: <>A LeadZen page opens. Sign in if asked. Check that it says <b>ChatGPT wants access</b>, your email is shown and the assistant callback is a ChatGPT or OpenAI address, then select <b>Connect</b>. Back in ChatGPT, review the LeadZen tools it found.</>,
      },
      {
        title: "Use it in a chat",
        body: <>Start a new conversation, type <b>@</b> and select <b>LeadZen</b>. To share it with your team, a ChatGPT admin publishes it from <b>Admin console → Plugins → Manage Legacy Apps → Drafts → Publish</b>. Teammates then find it in <b>Settings → Plugins</b> and each approves their own LeadZen account.</>,
      },
      {
        title: "Check it here",
        body: <>Select <b>Refresh</b> under Connected apps below. ChatGPT appears with the time it connected.</>,
      },
    ],
  },
];

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

function selectContents(element: HTMLElement | null) {
  const selection = element ? window.getSelection() : null;
  if (!element || !selection) return;
  const range = document.createRange();
  range.selectNodeContents(element);
  selection.removeAllRanges();
  selection.addRange(range);
}

function ServerURL({ id, label, endpoint, onCopy }: { id: string; label: string; endpoint: string; onCopy: () => Promise<boolean> }) {
  const [copied, setCopied] = useState(false);
  const value = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);
  return (
    <div className={styles.server}>
      <span className={styles.serverLabel} id={`${id}-label`}>{label}</span>
      <div className={styles.serverControl}>
        {/* Wrapping text keeps the whole URL visible on phones, unlike a one-line input. */}
        <code ref={value} id={id} className={styles.serverValue} role="textbox" aria-readonly="true" aria-labelledby={`${id}-label`} tabIndex={0} onFocus={(event) => selectContents(event.currentTarget)}>{endpoint}</code>
        <button className="button" type="button" aria-label={`Copy ${label}`} onClick={() => {
          void onCopy().then((done) => {
            setCopied(done);
            // Leave the URL selected beside the button so it can be copied manually.
            if (!done) selectContents(value.current);
          });
        }}>{copied ? "Copied" : "Copy URL"}</button>
      </div>
    </div>
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
  const setup = Array.isArray(data?.setup) ? data.setup : [];

  async function copy(destination?: string) {
    if (!endpoint) return false;
    setActionError("");
    try {
      await navigator.clipboard.writeText(endpoint);
      setNotice(destination ? `Server URL copied. Paste it into ${destination}.` : "Server URL copied.");
      return true;
    } catch {
      setActionError("Could not copy. The URL is selected; copy it manually.");
      return false;
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
          <HelpTooltip label="MCP connections">Lets Claude or ChatGPT use your LeadZen workspace. Each employee connects on their own. No one can see another employee’s records or keys.</HelpTooltip>
        </div>
        <span className={styles.protocol}>MCP</span>
      </div>
      <p className={styles.description}>Use your workspace from Claude or ChatGPT. Choose Set up for step-by-step instructions.</p>
      <p className={styles.approval}>Sending and paid actions still need approval in LeadZen.</p>

      {loading && !data && <p className={styles.status} role="status">Loading connections…</p>}
      {error && <div className="error" role="alert">{error} <button className="button" type="button" onClick={refresh}>Try again</button></div>}
      {actionError && <div className="error" role="alert">{actionError}</div>}
      {notice && <p className={styles.notice} role="status">{notice}</p>}

      {data && (endpoint
        ? <ServerURL id="mcp-server-url" label="Server URL" endpoint={endpoint} onCopy={() => copy()} />
        : <div className={styles.blocker} role="status" aria-labelledby="mcp-blocker-title">
          <h3 id="mcp-blocker-title">Not ready to connect yet</h3>
          <p>{data.reason || "LeadZen’s server address for Claude and ChatGPT is not set up yet."} Setup steps appear here once it is.</p>
          {setup.length > 0 && <>
            <p className={styles.blockerLead}>For your LeadZen admin, on the API server:</p>
            <ul>{setup.map((item) => (
              <li key={item.setting}><code>{item.setting}</code> {item.problem}. Set it to <code>{item.example}</code></li>
            ))}</ul>
            <p>Then restart the LeadZen API and select Check again.</p>
          </>}
          <button className="button" type="button" onClick={refresh} disabled={loading}>Check again</button>
        </div>)}

      <div className={styles.providers}>
        {providers.map((provider) => (
          <div key={provider.id} className={`${styles.provider} ${open === provider.id ? styles.providerOpen : ""}`}>
            <div className={styles.providerHeading}>
              <CompanyLogo name={provider.name} domain={provider.domain} />
              <h3>{provider.name}</h3>
              <button className="button" type="button" aria-expanded={open === provider.id} aria-controls={`mcp-setup-${provider.id}`} aria-label={`Set up ${provider.name}`} onClick={() => setOpen(open === provider.id ? null : provider.id)}>{open === provider.id ? "Close" : "Set up"}</button>
            </div>
            {open === provider.id && (
              <div id={`mcp-setup-${provider.id}`} className={styles.setup}>
                {endpoint ? <ol className={styles.steps}>{provider.steps.map((step) => (
                  <li key={step.title}>
                    <strong>{step.title}</strong>
                    <p>{step.body}</p>
                    {step.url && <ServerURL id={`mcp-server-url-${provider.id}`} label={step.url} endpoint={endpoint} onCopy={() => copy(provider.name)} />}
                    {step.link && <a className={styles.stepLink} href={step.link.href} target="_blank" rel="noopener noreferrer">{step.link.label} <span aria-hidden="true">↗</span></a>}
                  </li>
                ))}</ol> : <p className={styles.waiting}>{data ? "Steps appear once your admin finishes the server setup above." : "Loading setup steps…"}</p>}
                <p className={styles.availability}>{provider.availability}</p>
                <a href={provider.guide} target="_blank" rel="noopener noreferrer">{provider.name} setup guide <span aria-hidden="true">↗</span></a>
              </div>
            )}
          </div>
        ))}
      </div>

      {data && <div className={styles.connections}>
        <div className={styles.connectionTitle}><h3>Connected apps</h3><button className="button ghost" type="button" onClick={refresh} disabled={loading || busy !== null}>Refresh</button></div>
        {connections.length === 0 ? <p className={styles.status}>No apps connected yet. After you approve in LeadZen, select Refresh.</p> : connections.map((connection) => (
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
