"use client";

import { useEffect, useRef, useState } from "react";
import { scheduleSummary, windowSchedule, type SendingWindow } from "@/lib/sending-schedule";
import { api } from "@/lib/client-api";

type Email = { step: number; subject: string; body: string; delay_days?: number };
type Preview = { window?: SendingWindow; automatic_window?: SendingWindow; from_address: string; revision: string; note: string; automatic_available: boolean; delay_basis: string; timezone: string; recipients: (Email & { id: number; email: string; followups: Email[] })[] };

export default function CampaignSendReview({ campaignId, count, close, sent }: { campaignId: string; count: number; close: () => void; sent: () => Promise<void> }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [queued, setQueued] = useState(false);
  const [automatic, setAutomatic] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const submitting = useRef(false);
  const request = useRef<{ revision: string; id: string } | null>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setPreview(null); setError("");
    void api<Preview>(`campaigns/${campaignId}/preview?count=${count}`, { signal: controller.signal }).then((data) => { if (!controller.signal.aborted) setPreview(data); }).catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Unable to review emails"); });
    return () => controller.abort();
  }, [campaignId, count, refresh]);
  async function confirm() {
    if (!preview?.recipients.length || submitting.current || queued) return;
    submitting.current = true; setBusy(true); setError("");
    const selection = `${preview.revision}:${automatic}`;
    if (request.current?.revision !== selection) request.current = { revision: selection, id: crypto.randomUUID() };
    try {
      await api(`campaigns/${campaignId}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ count, revision: preview.revision, request_id: request.current.id, automatic_followups: automatic }) });
      setQueued(true);
      await sent();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to queue emails"); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <section className="live-email-review" aria-labelledby={`campaign-send-title-${campaignId}`} onKeyDown={(event) => { if (event.key === "Escape" && !busy) close(); }}>
    <h3 ref={heading} id={`campaign-send-title-${campaignId}`} tabIndex={-1}>Confirm outreach</h3>
    <p>Review the exact recipients and messages below. Confirming queues real emails.</p>
    {!preview && !error && <p role="status">Loading saved email previews…</p>}
    {preview && <>
      <p className="settings-help">From {preview.from_address}. Up to {preview.recipients.length} due email{preview.recipients.length === 1 ? "" : "s"} in this run.</p>
      {preview.window && <p className="settings-help">Sending schedule: {scheduleSummary(windowSchedule(preview.window))}. Mailbox capacity and pacing apply.</p>}
      {preview.recipients.map((recipient) => <div className="sequence-step" key={recipient.id}><p className="panel-meta">To {recipient.email} · Email {recipient.step}</p><strong>{recipient.subject}</strong><pre>{recipient.body}</pre></div>)}
      {!preview.recipients.length && <p>No eligible emails are due yet. Check dates, replies, suppression and recipient permission.</p>}
      {preview.recipients.some((recipient) => recipient.followups.length > 0) && <>
        <label className="check-row"><input type="checkbox" checked={automatic} disabled={busy || queued || !preview.automatic_available} onChange={(event) => setAutomatic(event.target.checked)} /> Approve automatic follow-ups for these recipients</label>
        {!preview.automatic_available && <p className="settings-help">Automatic follow-ups are unavailable. You can return here to review each follow-up when it is due.</p>}
        {automatic && preview.recipients.map((recipient) => <div key={`future-${recipient.id}`}>
          {recipient.followups.map((email) => <div className="sequence-step" key={email.step}><p className="panel-meta">To {recipient.email} · Email {email.step} · {email.delay_days} {preview.delay_basis === "working_days" ? "working" : "calendar"} days after the previous send</p><strong>{email.subject}</strong><pre>{email.body}</pre></div>)}
        </div>)}
        {automatic && <p className="settings-help">Approve only the displayed sequence, valid for up to one year. Follow-ups use {preview.automatic_window || preview.window ? scheduleSummary(windowSchedule((preview.automatic_window ?? preview.window)!)) : "the sending schedule in Settings"}. Pause or archive the campaign, stop a lead, or record an opt-out to stop sending. Changes to content, identity, connections or sending schedule require a new approval.</p>}
      </>}
      <p className="settings-help">Sending respects mailbox limits, hours and pacing. Replies and opt-outs stop follow-ups. Provider acceptance does not guarantee delivery.</p>
    </>}
    {error && <p className="error" role="alert">{error}</p>}
    {queued && <p className="success" role="status">Outreach queued. Your Outreach list shows delivery progress.</p>}
    <div className="card-actions">
      <button className="button" disabled={busy} onClick={close}>{queued ? "Close" : "Cancel"}</button>
      {!queued && <button className="button primary" disabled={busy || !preview?.recipients.length} onClick={confirm}>{busy ? "Queuing…" : automatic ? "Approve sequence" : "Confirm & send"}</button>}
      {error && !queued && <button className="button" disabled={busy} onClick={() => { setAutomatic(false); setRefresh((value) => value + 1); }}>Refresh review</button>}
    </div>
  </section>;
}
