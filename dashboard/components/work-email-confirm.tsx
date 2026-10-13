"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/client-api";

type Review = { eligible: boolean; reason: string; revision: string; name: string; provider_name?: string };
export function EmailConfirmation({ contactId, close, started }: { contactId: number; close: () => void; started: () => Promise<void> }) {
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const submitting = useRef(false);
  const request = useRef<{ revision: string; id: string } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setReview(null); setError("");
    void api<Review>(`contacts/${contactId}/email`, { signal: controller.signal }).then((value) => {
      if (!controller.signal.aborted) setReview(value);
    }).catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Unable to review lookup"); });
    return () => controller.abort();
  }, [contactId, refresh]);
  async function confirm() {
    if (!review?.eligible || submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    if (request.current?.revision !== review.revision) request.current = { revision: review.revision, id: crypto.randomUUID() };
    try {
      await api(`contacts/${contactId}/email`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision: review.revision, request_id: request.current.id, estimated_credits: 1 }) });
      await started();
      close();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start lookup");
    } finally { submitting.current = false; setBusy(false); }
  }
  return <section className="live-email-review" aria-labelledby="work-email-confirm">
    <h3 ref={heading} id="work-email-confirm" tabIndex={-1}>Find this person’s work email?</h3>
    <p>Uses up to <strong>1 {review?.provider_name ?? "lead-provider"} credit</strong>. No emails are sent. AI charges may apply.</p>
    {!review && !error && <p role="status">Checking…</p>}
    {review && <p className="settings-help">{review.eligible ? `Search for ${review.name}’s email. A match is not guaranteed.` : review.reason}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="card-actions">
      <button className="button" disabled={busy} onClick={close}>Cancel</button>
      <button className="button primary" disabled={!review?.eligible || busy} onClick={confirm}>{busy ? "Starting…" : "Find email"}</button>
      {error && <button className="button" disabled={busy} onClick={() => setRefresh((value) => value + 1)}>Check again</button>}
    </div>
  </section>;
}


type BulkReview = { items: { id: number; name: string; eligible: boolean; reason: string }[]; eligible_ids: number[]; blocker: string; estimated_credits: number; provider_name: string; revision: string };

/** Leads page bulk action: one lookup task for the selected leads that are eligible. */
export function BulkEmailConfirmation({ contactIds, close, started }: { contactIds: number[]; close: () => void; started: (runId: string, count: number) => void }) {
  const [review, setReview] = useState<BulkReview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const request = useRef<{ key: string; id: string } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const ids = [...contactIds].sort((a, b) => a - b).join(",");
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setReview(null); setError("");
    void api<BulkReview>(`contacts/emails?ids=${ids}`, { signal: controller.signal }).then((value) => {
      if (!controller.signal.aborted) setReview(value);
    }).catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Unable to review lookup"); });
    return () => controller.abort();
  }, [ids]);
  async function confirm() {
    if (!review || !review.eligible_ids.length || review.blocker || submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      // Approve exactly the eligible leads the employee saw; ineligible ones are left out.
      const final = review.eligible_ids.length === review.items.length ? review : await api<BulkReview>(`contacts/emails?ids=${review.eligible_ids.join(",")}`);
      if (final.eligible_ids.join(",") !== review.eligible_ids.join(",") || final.blocker) throw new Error(final.blocker || "The selected leads changed. Review again.");
      const key = `${final.revision}:${final.eligible_ids.join(",")}`;
      if (request.current?.key !== key) request.current = { key, id: crypto.randomUUID() };
      const result = await api<{ run: { id: string } }>("contacts/emails", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ contact_ids: final.eligible_ids, revision: final.revision, request_id: request.current.id, estimated_credits: final.eligible_ids.length }) });
      started(result.run.id, final.eligible_ids.length);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start lookup");
    } finally { submitting.current = false; setBusy(false); }
  }
  const skipped = review?.items.filter((item) => !item.eligible) ?? [];
  const count = review?.eligible_ids.length ?? 0;
  return <section className="live-email-review" aria-labelledby="bulk-email-confirm">
    <h3 ref={heading} id="bulk-email-confirm" tabIndex={-1}>Find work emails?</h3>
    {!review && !error && <p role="status">Checking…</p>}
    {review && <p>{count ? <>Search {count} lead{count === 1 ? "" : "s"}. Uses up to <strong>{count} {review.provider_name} credit{count === 1 ? "" : "s"}</strong>. No emails are sent.</> : "None of these leads can be searched."}</p>}
    {review?.blocker && <p className="error" role="alert">{review.blocker}</p>}
    {skipped.length > 0 && <details><summary>{skipped.length} skipped</summary><ul className="settings-help">{skipped.map((item) => <li key={item.id}>{item.name}: {item.reason}</li>)}</ul></details>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="card-actions">
      <button className="button" disabled={busy} onClick={close}>Cancel</button>
      <button className="button primary" disabled={!count || !!review?.blocker || busy} onClick={() => void confirm()}>{busy ? "Starting…" : `Find ${count || ""} email${count === 1 ? "" : "s"}`.replace("  ", " ")}</button>
    </div>
  </section>;
}
