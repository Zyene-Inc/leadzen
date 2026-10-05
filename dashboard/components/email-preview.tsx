"use client";
import { AskLeadZen } from "@/components/ask-leadzen";
import { recordWorkspaceContext } from "@/lib/workspace-context";
import { useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/client-api";
import type { EmailDraft, EmailReview } from "@/lib/outreach";

export default function EmailPreview({ draft, review, update, workspacePath }: { draft: EmailDraft; review: EmailReview; update: (value: EmailReview) => void; workspacePath?: string }) {
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  const editButton = useRef<HTMLButtonElement>(null);
  const available = review.status === "draft" && draft.state === "pending" && !review.stale;
  async function act(action: string) {
    if (submitting.current || !available) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      const data = await api<EmailReview>(`outreach/reviews/${review.id}/drafts/${draft.id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, revision: draft.revision, subject, body }) });
      update(data); setEditing(false);
      if (action === "edit") editButton.current?.focus();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to update the draft"); }
    finally { submitting.current = false; setBusy(false); }
  }
  function save(event: FormEvent) { event.preventDefault(); void act("edit"); }
  return <article className="email-preview" aria-labelledby={`draft-${draft.id}`} aria-busy={busy} onFocusCapture={() => { void recordWorkspaceContext({ currentDraftId: draft.id, workspacePath: workspacePath || `/sending?review=${review.id}` }, review.actor_id); }}>
    <div className="email-preview-head"><h3 id={`draft-${draft.id}`}>{draft.name}</h3><span className={`badge ${draft.approved ? "ready" : "completed"}`}>{draft.approved ? "Approved" : "Needs review"}</span></div>
    <p className="settings-help">To: {draft.to}</p>
    {editing ? <form onSubmit={save}>
      <label className="field"><span>Subject</span><input className="input" maxLength={200} required value={subject} disabled={review.kind === "reply" || busy} onChange={(e) => setSubject(e.target.value)} /></label>
      <label className="field"><span>Message</span><textarea className="input email-editor" autoFocus maxLength={10000} required disabled={busy} value={body} onChange={(e) => setBody(e.target.value)} /></label>
      <p className="settings-help">Your saved signature and opt-out stay in the final preview. Saving clears approval.</p>
      <div className="card-actions"><button className="button" type="button" disabled={busy} onClick={() => { setEditing(false); editButton.current?.focus(); }}>Cancel edit</button><button type="submit" className="button primary" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button></div>
    </form> : <><p><strong>Subject:</strong> {draft.subject}</p><pre className="email-copy">{draft.preview_body}</pre><div className="card-actions">
      <button type="button" className="button" disabled={!available || busy} onClick={() => void act("regenerate")}>{busy ? "Working…" : "Regenerate"}</button>
      <button ref={editButton} type="button" className="button" disabled={!available || busy} onClick={() => { setSubject(draft.subject); setBody(draft.body); setEditing(true); }}>Edit</button>
      <button type="button" className="button primary" disabled={!available || busy || draft.approved} onClick={() => void act("approve")}>{draft.approved ? "Approved" : "Approve"}</button>
    </div></>}
    {review.actor_id && <AskLeadZen actorId={review.actor_id} context={{ currentDraftId: draft.id, workspacePath: workspacePath || `/outreach?review=${review.id}` }} />}
    <p className="settings-help">Regenerate uses your connected AI provider and may incur AI charges. Approve saves your review only; it does not send.</p>
    {error && <p className="error" role="alert">{error}</p>}
  </article>;
}
