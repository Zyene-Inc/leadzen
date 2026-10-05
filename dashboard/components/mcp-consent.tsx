"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { WorkspacePage } from "@/components/workspace-records";
import type { Account } from "@/lib/auth";
import { api } from "@/lib/client-api";
import { formatNewYorkDateTime } from "@/lib/date-time";
import { returnToMcpClient, validatedMcpRedirect } from "@/lib/mcp-redirect";
import styles from "@/components/mcp-connections.module.css";

export type MCPConsentData = {
  request: string;
  clientName: string;
  redirectHost: string;
  scopes: string[];
  expiresAt: string;
};

const permissions: Record<string, string> = {
  "leadzen:read": "Read your leads, outreach, inbox and workspace settings.",
  "leadzen:write": "Manage your leads, drafts, outreach and nonsecret settings.",
  offline_access: "Keep this connection active until you disconnect it or access expires.",
};

export default function MCPConsent({ user, request }: { user: Account; request: string }) {
  const [data, setData] = useState<MCPConsentData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const inFlight = useRef(false);
  useEffect(() => {
    setData(null);
    if (!/^[A-Za-z0-9_-]{16,256}$/.test(request)) {
      setError("This connection request is missing or invalid. Start again from your assistant.");
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void api<MCPConsentData>(`mcp/authorize?request=${encodeURIComponent(request)}`, { signal: controller.signal })
      .then((next) => {
        if (!controller.signal.aborted) setData(next);
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Could not review this connection. Start again from your assistant.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [request, revision]);

  async function decide(decision: "approve" | "deny") {
    if (!data || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ redirectUrl: string }>("mcp/authorize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: data.request, decision }),
      });
      const destination = validatedMcpRedirect(result.redirectUrl, data.redirectHost);
      if (!destination) throw new Error("The assistant callback could not be verified. Start a new connection from your assistant.");
      returnToMcpClient(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not complete this connection. Try again.");
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <WorkspacePage user={user} active="settings" title="Connect your assistant" description="Review access to your own LeadZen workspace before connecting." actions={<Link className="button" href="/settings#mcp-connections">Back to Settings</Link>}>
      <section className={styles.consent} aria-labelledby="mcp-consent-title" aria-busy={loading || busy}>
        <h2 id="mcp-consent-title">{data ? `${data.clientName} wants access` : "Review connection"}</h2>
        {loading && <p role="status">Loading connection request…</p>}
        {error && <div className="error" role="alert">{error}{!data && request && <button className="button" type="button" onClick={() => setRevision((value) => value + 1)}>Try again</button>}</div>}
        {data && <>
          <p>Only connect if you started this request in your assistant and recognize the callback below.</p>
          <dl className={styles.consentDetails}>
            <dt>LeadZen account</dt><dd>{user.email}</dd>
            <dt>Assistant callback</dt><dd>{data.redirectHost}</dd>
            <dt>Request expires</dt><dd><time dateTime={data.expiresAt}>{formatNewYorkDateTime(data.expiresAt)}</time> · New York time</dd>
          </dl>
          <ul>{data.scopes.map((scope) => <li key={scope}>{permissions[scope] || scope}</li>)}</ul>
          <p className={styles.consentNote}>This allows access to your employee workspace. Paid actions and email sending still require a separate approval in LeadZen. You can disconnect this app in Settings at any time.</p>
          <div className={styles.consentActions}>
            <button className="button" type="button" disabled={busy} onClick={() => { void decide("deny"); }}>Deny access</button>
            <button className="button primary" type="button" disabled={busy} onClick={() => { void decide("approve"); }}>{busy ? "Returning to assistant…" : "Connect"}</button>
          </div>
        </>}
      </section>
    </WorkspacePage>
  );
}
