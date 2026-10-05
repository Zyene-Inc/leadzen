"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/client-api";
import type { ChatRun } from "@/lib/chat";

type Check = { thread_id: string; run: ChatRun };
export function InboxCheck({ refreshed }: { refreshed: () => void }) {
  const [check, setCheck] = useState<Check | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const request = useRef<string>("");
  const opener = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const refreshRef = useRef(refreshed);
  useEffect(() => { refreshRef.current = refreshed; }, [refreshed]);
  useEffect(() => {
    const controller = new AbortController();
    void api<{ check: Check | null }>("inbox/check", { signal: controller.signal }).then((result) => {
      if (!controller.signal.aborted) setCheck(result.check || null);
    }).catch((caught) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Could not restore your last inbox check");
    }).finally(() => { if (!controller.signal.aborted) setRestoring(false); });
    return () => controller.abort();
  }, []);
  useEffect(() => { if (check?.run.status === "awaiting_approval") heading.current?.focus(); }, [check?.run.status]);
  useEffect(() => {
    if (!check || !["queued", "running"].includes(check.run.status)) return;
    const controller = new AbortController();
    let inFlight = false;
    const timer = window.setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const run = await api<ChatRun>(`chat/runs/${check.run.id}`, { signal: controller.signal });
        if (!controller.signal.aborted) { setCheck((current) => current?.run.id === run.id ? { ...current, run } : current); setError(""); if (run.status === "succeeded") refreshRef.current(); }
      } catch (caught) { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Could not check task status"); }
      finally { inFlight = false; }
    }, 1500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [check]);
  async function act(approved?: boolean) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try {
      if (approved === undefined) {
        request.current ||= crypto.randomUUID();
        setCheck(await api<Check>("inbox/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: request.current }) }));
      } else if (check?.run.approval) {
        const run = await api<ChatRun>(`chat/runs/${check.run.id}/approval`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action_id: check.run.approval.id, approved }) });
        if (!approved) { setCheck(null); request.current = ""; opener.current?.focus(); } else setCheck((current) => current?.run.id === run.id ? { ...current, run } : current);
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not check replies"); }
    finally { lock.current = false; setBusy(false); }
  }
  const running = !!check && ["queued", "running"].includes(check.run.status);
  const waiting = check?.run.status === "awaiting_approval";
  return <section className="inbox-check">
    <button ref={opener} data-tour="inbox-replies" className="button primary" disabled={restoring || busy || running || waiting} onClick={() => { if (check) { request.current = ""; setCheck(null); } void act(); }}>{busy ? "Please wait…" : running ? "Checking replies…" : "Check for replies"}</button>
    {waiting && <section className="outreach-confirm" aria-label="Approve inbox access" onKeyDown={(e) => { if (e.key === "Escape" && !busy) void act(false); }}><h2 ref={heading} tabIndex={-1}>Check your connected inbox?</h2><p>Read replies from {String(check.run.approval?.preview.from_address || "your mailbox")} and classify them using AI. AI charges may apply. No emails will be sent.</p>{error && <p className="error" role="alert">{error}</p>}<div className="card-actions"><button className="button" disabled={busy} onClick={() => void act(false)}>Cancel</button><button className="button primary" disabled={busy} onClick={() => void act(true)}>Approve & check replies</button></div></section>}
    {!waiting && error && <p className="error" role="alert">{error}</p>}
    {check && !waiting && <p role="status">{check.run.status === "succeeded" ? "Reply check complete. Inbox is up to date with this check." : running ? "Checking your mailbox. You can keep working." : "The check did not finish. Review the saved result before retrying."} <Link className="text-link" href={`/chat/${check.thread_id}`}>View result</Link></p>}
  </section>;
}
