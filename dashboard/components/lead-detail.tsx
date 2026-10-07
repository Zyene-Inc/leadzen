"use client";
import { AskLeadZen } from "@/components/ask-leadzen";
import { useWorkspaceContext } from "@/lib/workspace-context";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Sidebar } from "@/components/sidebar";
import { LeadLinks } from "@/components/lead-links";
import { LeadTimeline } from "@/components/lead-timeline";
import type { Account } from "@/lib/auth";
import { useWorkspaceRevision } from "@/lib/workspace-updates";
import { api } from "@/lib/client-api";
import { leadStatus, type Contact } from "@/lib/leads";

type Review = { eligible: boolean; reason: string; revision: string; name: string; provider_name?: string };
const active = new Set(["queued", "running", "paused"]);

function EmailConfirmation({ contactId, close, started }: { contactId: number; close: () => void; started: () => Promise<void> }) {
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
    <p>This may use <strong>1 {review?.provider_name ?? "lead-provider"} credit</strong>. No other profiles will be searched and no emails will be sent. AI-provider charges may apply separately.</p>
    {!review && !error && <p role="status">Reviewing the saved profile…</p>}
    {review && <p className="settings-help">{review.eligible ? `Find an email for ${review.name}. An address is not guaranteed; actual usage will be shown when the provider reports it.` : review.reason}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="card-actions">
      <button className="button" disabled={busy} onClick={close}>Cancel</button>
      <button className="button primary" disabled={!review?.eligible || busy} onClick={confirm}>{busy ? "Starting…" : "Find Email"}</button>
      {error && <button className="button" disabled={busy} onClick={() => setRefresh((value) => value + 1)}>Refresh review</button>}
    </div>
  </section>;
}

function EmailOutcome({ lead }: { lead: Contact }) {
  if (lead.email_status === "verified") return <p className="success" role="status">✓ Verified email found{lead.lookup?.synthetic ? " (synthetic preview)" : ""}</p>;
  const messages: Partial<Record<Contact["email_status"], string>> = {
    catch_all_safe: "Provider reports a safe catch-all address. This is not an individually verified mailbox.",
    pending: lead.lookup?.status === "paused" ? "Lookup paused. Resume or stop it in live activity." : "Work-email lookup in progress…",
    not_found: "The provider completed the lookup without a usable email.",
    review: "The lookup did not finish with a usable result. Review the saved activity before trying again. Uncertain purchases are not automatically repeated.",
  };
  return messages[lead.email_status] ? <p className="settings-help" role="status">{messages[lead.email_status]}</p> : null;
}

function LookupUsage({ lookup }: { lookup: NonNullable<Contact["lookup"]> }) {
  if (lookup.credits_used === null) return <p className="settings-help">{lookup.provider_name ?? "BetterContact"} credit usage has not been reported.</p>;
  const label = lookup.credits_used === 1 ? "credit" : "credits";
  return <p className="settings-help">{lookup.credits_used} {lookup.provider_name ?? "BetterContact"} {label} used{lookup.synthetic ? " (synthetic preview only)" : ""}.</p>;
}

function WorkEmail({ lead, load }: { lead: Contact; load: () => Promise<void> }) {
  const [reviewing, setReviewing] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const lookup = lead.lookup;
  function close() { setReviewing(false); opener.current?.focus(); }
  return <section className="panel settings-card" aria-labelledby="lead-contact-title">
    <h2 id="lead-contact-title">Contact</h2>
    <p className="eyebrow">Work email</p>
    <p className="lead-email-address">{lead.email || (lookup ? "No saved email yet" : "Not yet requested")}</p>
    <EmailOutcome lead={lead} />
    {lookup && <LookupUsage lookup={lookup} />}
    <div className="card-actions">
      {!lead.email && !active.has(lookup?.status ?? "") && <button ref={opener} className="button primary" onClick={() => setReviewing(true)} aria-expanded={reviewing} aria-controls={reviewing ? "work-email-confirm" : undefined}>Find Work Email</button>}
      {lookup?.run_id && <Link className="button" href={`/find-leads/${lookup.run_id}`}>View lookup activity</Link>}
      {lead.email && <Link className="button primary" href={`/outreach?lead=${lead.id}`}>Prepare outreach</Link>}
    </div>
    {reviewing && <EmailConfirmation contactId={lead.id} close={close} started={load} />}
    <p className="settings-help">An email address is not permission to send. Consent, suppression, provider policy and send approval are checked separately.</p>
  </section>;
}

export default function LeadDetail({ user, contactId }: { user: Account; contactId: number }) {
  const workspaceRevision = useWorkspaceRevision();
  const [lead, setLead] = useState<Contact | null>(null);
  const [error, setError] = useState("");
  useWorkspaceContext({ currentLeadId: lead?.id ?? null, selectedLeadIds: [], currentDraftId: null, currentThreadId: null, workspacePath: lead ? `/contacts/${lead.id}` : "/contacts" }, user.id);
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const value = await api<Contact>(`contacts/${contactId}`, { signal });
      if (!signal?.aborted) { setLead(value); setError(""); }
    } catch (caught) { if (!signal?.aborted) { setLead(null); setError(caught instanceof Error ? caught.message : "Unable to load lead"); } }
  }, [contactId]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, workspaceRevision]);
  useEffect(() => {
    if (!active.has(lead?.lookup?.status ?? "")) return;
    const controller = new AbortController();
    let inFlight = false;
    const timer = window.setInterval(() => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      void load(controller.signal).finally(() => { inFlight = false; });
    }, 1500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [lead?.lookup?.status, load]);
  return <div className="shell"><Sidebar user={user} active="contacts" /><main className="main">
    <Link className="text-link" href="/contacts">← Back to Leads</Link>
    {error && <div className="error" role="alert">{error}</div>}
    {!lead && !error && <div className="empty" role="status">Loading lead…</div>}
    {lead && <>
      <header className="topbar lead-detail-head"><div><p className="eyebrow">Your workspace / Leads</p><h1>{lead.name}</h1><p className="lede">{lead.title || "Title not recorded"}<br />{lead.company || "Company not recorded"}</p><LeadLinks linkedin={lead.linkedin_url} website={lead.website} /></div><div className="top-actions"><span className={`badge crm-${lead.crm_status}`}>{leadStatus(lead.crm_status)}</span><AskLeadZen actorId={user.id} context={{ currentLeadId: lead.id, workspacePath: `/contacts/${lead.id}` }} /></div></header>
      <div className="lead-detail-grid">
        <section className="panel settings-card"><h2>{lead.qualified ? "Why LeadZen selected this person" : "Qualification record"}</h2><p className="lead-reason">{lead.reason}</p><p className="settings-help">{lead.qualified ? "Based on the saved discovery qualification, not a new AI assessment." : "This contact has no current qualified discovery decision."}</p>
          {lead.profile_text && <details><summary>Profile notes</summary><p className="lead-reason">{lead.profile_text}</p></details>}
          <p className="settings-help">{lead.reply_count} {lead.reply_count === 1 ? "reply" : "replies"} recorded. {lead.opted_in ? "Opt-in recorded." : "No opt-in recorded."} {lead.consent_note}</p>
        </section>
        <WorkEmail lead={lead} load={load} />
      </div>
      <LeadTimeline lead={lead} load={load} />
    </>}
  </main></div>;
}
