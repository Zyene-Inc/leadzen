"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/client-api";

export function SuppressionForm({ fixedEmail, cancel, saved }: {
  fixedEmail?: string;
  cancel: () => void;
  saved: (created: boolean) => void | Promise<void>;
}) {
  const emailInput = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { emailInput.current?.focus(); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    const values = new FormData(event.currentTarget);
    submitting.current = true; setBusy(true); setError("");
    try {
      const result = await api<{ created: boolean }>("suppression", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: fixedEmail ?? values.get("email"), reason: values.get("reason") }),
      });
      await saved(result.created);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to suppress this address");
    } finally { submitting.current = false; setBusy(false); }
  }
  return <form className="suppression-form" onSubmit={submit} aria-label="Add to suppression list">
    <h3>Block future emails to this address</h3>
    <div className="suppression-fields">
      <label>Email address<input ref={emailInput} className="input" name="email" type="email" required maxLength={150} defaultValue={fixedEmail} readOnly={!!fixedEmail} autoComplete="off" /></label>
      <label>Reason<select className="input" name="reason" defaultValue="Manually suppressed">
        <option>Manually suppressed</option><option>Opted out</option>
      </select></label>
    </div>
    <p className="settings-help">This permanently blocks future emails in your workspace, including after the lead is imported again. Existing history is retained.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="card-actions">
      <button className="button" type="button" disabled={busy} onClick={cancel}>Cancel</button>
      <button className="button primary" type="submit" disabled={busy}>{busy ? "Adding…" : "Confirm suppression"}</button>
    </div>
  </form>;
}
