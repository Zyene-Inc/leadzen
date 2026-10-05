"use client";
import { recordWorkspaceContext, useWorkspaceContext } from "@/lib/workspace-context";
import { useEffect, useRef, useState, type RefObject } from "react";
import EmailPreview from "@/components/email-preview";
import { api } from "@/lib/client-api";
import { useStoredData } from "@/lib/use-stored-data";
import { sentTime, type EmailReview } from "@/lib/outreach";

function FinalConfirmation({ review, cancel, started }: { review: EmailReview; cancel: () => void; started: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef("");
  const submitting = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  async function confirm() {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    requestId.current ||= crypto.randomUUID();
    try {
      await api("jobs/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ review_id: review.id, count: review.requested_count, revision: review.revision, request_id: requestId.current }) });
      started();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to start approved outreach"); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <section className="outreach-confirm" aria-labelledby="final-send-title">
    <h3 ref={heading} tabIndex={-1} id="final-send-title">Send {review.kind === "reply" ? "this reply" : `emails to ${review.requested_count} ${review.requested_count === 1 ? "person" : "people"}`}?</h3>
    <p>This action sends real emails from {review.from_address}. Only the approved messages above are included.</p>
    <p className="settings-help">{review.note}</p>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="card-actions"><button className="button" disabled={busy} onClick={cancel}>No, go back</button><button className="button primary" disabled={busy} onClick={() => void confirm()}>{busy ? "Starting…" : review.kind === "reply" ? "Yes, send this reply" : "Yes, start outreach"}</button></div>
  </section>;
}

function Progress({ review, stop }: { review: EmailReview; stop: () => void }) {
  const running = ["queued", "running"].includes(review.status);
  const generating = review.status === "generating";
  const names: Record<string, string> = { accepted: "Email accepted by provider", pending: running ? "Waiting for sending interval, window or capacity" : "Not sent; new review required", sending: "Sending attempt in progress", review: "Uncertain or failed attempt; do not automatically retry", cancelled: "Cancelled; not sent" };
  return <section className="panel outreach-progress" aria-labelledby="outreach-progress-title">
    <h2 id="outreach-progress-title">{generating ? "Preparing drafts" : running ? "Outreach Running" : `Outreach ${review.status}`}</h2>
    <p role="status">{review.accepted} / {review.requested_count} {review.kind === "reply" ? "replies accepted" : "conversations opened"}</p>
    <progress value={review.accepted} max={review.requested_count} aria-label="Emails accepted by provider" />
    <ul className="outreach-progress-list">{review.drafts.map((d) => <li key={d.id}><span aria-hidden="true">{d.state === "accepted" ? "✓" : d.state === "review" ? "!" : "○"}</span><div><strong>{d.name}</strong><p>{names[d.state] || d.state}{d.accepted_at ? ` · ${sentTime(d.accepted_at)}` : ""}</p></div></li>)}</ul>
    <p className="settings-help">Acceptance is not proof of delivery or inbox placement. No automatic follow-up is scheduled.</p>
    {running && <button className="button danger" onClick={stop}>Stop outreach</button>}
    {generating && <button className="button" onClick={stop}>Cancel draft generation</button>}
  </section>;
}

function reviewReady(data: EmailReview) {
  return data.status === "draft" && !data.stale && data.drafts.length > 0 && data.drafts.every((d) => d.approved && d.state === "pending");
}

function ReviewDrafts({ data, update, begin, cancel, startRef, workspacePath }: { data: EmailReview; update: (data: EmailReview) => void; begin: () => void; cancel: () => void; startRef: RefObject<HTMLButtonElement | null>; workspacePath?: string }) {
  const ready = reviewReady(data);
  return <>{data.drafts.map((d) => <EmailPreview key={d.id} draft={d} review={data} update={update} workspacePath={workspacePath} />)}
    <div className="card-actions"><button className="button" onClick={cancel}>Cancel review</button><button ref={startRef} className="button primary" disabled={!ready} onClick={begin}>{data.kind === "reply" ? "Review & Send" : "Review & send"}</button></div>
    {!ready && <p className="settings-help">Approve every message above to enable final confirmation.</p>}</>;
}

export default function OutreachReview({ reviewId, closed, closeLabel = "Back to outreach", workspacePath, expectedThreadId }: { reviewId: string; closed?: () => void; closeLabel?: string; workspacePath?: string; expectedThreadId?: number }) {
  const { data, setData, loading, error, refresh } = useStoredData<EmailReview>(`outreach/reviews/${reviewId}`, 2000);
  const wrongConversation = !!data && expectedThreadId !== undefined && (data.kind !== "reply" || data.thread_id !== expectedThreadId);
  useWorkspaceContext(data && !wrongConversation ? { currentDraftId: data.drafts.length === 1 ? data.drafts[0].id : null, currentLeadId: null, selectedLeadIds: [], workspacePath: workspacePath || `/outreach?review=${reviewId}` } : {}, data?.actor_id);
  const [confirming, setConfirming] = useState(false);
  const [actionError, setActionError] = useState("");
  const startButton = useRef<HTMLButtonElement>(null);
  async function cancelReview() {
    try { setData(await api<EmailReview>(`outreach/reviews/${reviewId}`, { method: "DELETE" })); setActionError(""); }
    catch (caught) { setActionError(caught instanceof Error ? caught.message : "Unable to cancel this review"); }
  }
  if (!data) return <section className="panel outreach-progress"><p role="status">{loading ? "Loading saved email review…" : error}</p><button className="button" onClick={refresh}>Refresh review</button></section>;
  if (wrongConversation) return <section className="panel"><p className="error" role="alert">This saved reply belongs to a different conversation.</p>{closed && <button className="button" onClick={closed}>{closeLabel}</button>}</section>;
  const ready = reviewReady(data);
  const draftMode = data.status === "draft";
  return <section className="outreach-review" aria-label="Saved email review">
    <div className="section-heading"><div><p className="eyebrow">Human review</p><h2>Email Preview</h2><p className="settings-help">From {data.from_address}. Review each exact message before approving.</p></div><button className="button" onClick={refresh}>Refresh review</button></div>
    {(error || actionError) && <p className="error" role="alert">{error || actionError}</p>}
    {data.stale && <p className="error" role="alert">The saved setup, contact or inbox changed. This review cannot send; create a fresh review.</p>}
    {!draftMode && <Progress review={data} stop={() => void cancelReview()} />}
    {draftMode && <ReviewDrafts data={data} update={setData} begin={() => setConfirming(true)} cancel={() => void cancelReview()} startRef={startButton} workspacePath={workspacePath} />}
    {confirming && draftMode && ready && <FinalConfirmation key={data.revision} review={data} cancel={() => { setConfirming(false); startButton.current?.focus(); }} started={refresh} />}
    {closed && !["queued", "running", "generating"].includes(data.status) && <button className="button" onClick={() => { void recordWorkspaceContext({ currentDraftId: null, workspacePath: workspacePath || "/outreach" }, data.actor_id); closed(); }}>{closeLabel}</button>}
  </section>;
}
