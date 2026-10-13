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
import OutreachReview from "@/components/outreach-review";
import { transientError } from "@/lib/api-errors";
import { leadStatus, type Contact } from "@/lib/leads";
import { EmailConfirmation } from "@/components/work-email-confirm";

const active = new Set(["queued", "running", "paused"]);

function EmailOutcome({ lead }: { lead: Contact }) {
  if (lead.email_status === "verified") return <p className="success" role="status">✓ Email verified{lead.lookup?.synthetic ? " (synthetic preview)" : ""}</p>;
  const messages: Partial<Record<Contact["email_status"], string>> = {
    catch_all_safe: "Safe catch-all address. Not verified one by one.",
    pending: lead.lookup?.status === "paused" ? "Search paused. Resume or stop it in activity." : "Finding work email…",
    not_found: "No email found.",
    review: "Search didn’t finish. Check activity before trying again. Paid searches never retry on their own.",
  };
  return messages[lead.email_status] ? <p className="settings-help" role="status">{messages[lead.email_status]}</p> : null;
}

function LookupUsage({ lookup }: { lookup: NonNullable<Contact["lookup"]> }) {
  if (lookup.credits_used === null) return <p className="settings-help">{lookup.provider_name ?? "BetterContact"} credits used: not reported yet.</p>;
  const label = lookup.credits_used === 1 ? "credit" : "credits";
  return <p className="settings-help">{lookup.credits_used} {lookup.provider_name ?? "BetterContact"} {label} used{lookup.synthetic ? " (synthetic preview only)" : ""}.</p>;
}

function WorkEmail({ lead, load }: { lead: Contact; load: () => Promise<void> }) {
  const [reviewing, setReviewing] = useState(false);
  const [draftReview, setDraftReview] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [draftError, setDraftError] = useState("");
  const draftRequest = useRef("");
  const opener = useRef<HTMLButtonElement>(null);
  const canDraft = !!lead.email && !["suppressed", "contacted", "replied"].includes(lead.crm_status);
  async function draftEmail() {
    if (drafting) return;
    setDrafting(true); setDraftError("");
    draftRequest.current ||= crypto.randomUUID();
    try {
      // One personal first email, reviewed before anything is sent. No Chat involved.
      const review = await api<{ id: string }>("outreach/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ count: 1, lead_ids: [lead.id], request_id: draftRequest.current }) });
      setDraftReview(review.id);
    } catch (caught) { setDraftError(caught instanceof Error ? caught.message : "Could not draft an email"); draftRequest.current = ""; }
    finally { setDrafting(false); }
  }
  const lookup = lead.lookup;
  function close() { setReviewing(false); opener.current?.focus(); }
  return <section className="panel settings-card" aria-labelledby="lead-contact-title">
    <h2 id="lead-contact-title">Contact</h2>
    <p className="eyebrow">Work email</p>
    <p className="lead-email-address">{lead.email || (lookup ? "No email yet" : "Not searched yet")}</p>
    <EmailOutcome lead={lead} />
    {lookup && <LookupUsage lookup={lookup} />}
    <div className="card-actions">
      {!lead.email && !active.has(lookup?.status ?? "") && <button ref={opener} className="button primary" onClick={() => setReviewing(true)} aria-expanded={reviewing} aria-controls={reviewing ? "work-email-confirm" : undefined}>Find work email</button>}
      {lookup?.run_id && <Link className="button" href={`/find-leads/${lookup.run_id}`}>View progress</Link>}
      {lead.email && <Link className="button primary" href={`/outreach?lead=${lead.id}`}>Prepare outreach</Link>}
      {canDraft && !draftReview && <button className="button" disabled={drafting} onClick={() => void draftEmail()}>{drafting ? "Drafting…" : "Draft email"}</button>}
    </div>
    {draftError && <p className="error" role="alert">{draftError}</p>}
    {draftReview && <OutreachReview key={draftReview} reviewId={draftReview} workspacePath={`/contacts/${lead.id}`} closeLabel="Back to lead" closed={() => { setDraftReview(null); draftRequest.current = ""; void load(); }} />}
    {reviewing && <EmailConfirmation contactId={lead.id} close={close} started={load} />}
    <p className="settings-help">An email is not permission to send. Opt-outs, blocks and your approval are checked first.</p>
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
    } catch (caught) {
      // Keep the loaded contact through transient poll/refresh failures; a denial or another contact clears it.
      if (!signal?.aborted) { setLead((current) => transientError(caught) && current?.id === contactId ? current : null); setError(caught instanceof Error ? caught.message : "Unable to load lead"); }
    }
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
      <header className="topbar lead-detail-head"><div><p className="eyebrow">Your workspace / Leads</p><h1>{lead.name}</h1><p className="lede">{lead.title || "No title"}<br />{lead.company || "No company"}</p><LeadLinks linkedin={lead.linkedin_url} website={lead.website} /></div><div className="top-actions"><span className={`badge crm-${lead.crm_status}`}>{leadStatus(lead.crm_status)}</span><AskLeadZen actorId={user.id} context={{ currentLeadId: lead.id, workspacePath: `/contacts/${lead.id}` }} /></div></header>
      <div className="lead-detail-grid">
        <section className="panel settings-card"><h2>{lead.qualified ? "Why this lead" : "Lead fit"}</h2><p className="lead-reason">{lead.reason}</p><p className="settings-help">{lead.qualified ? "From the original lead search." : "Not marked as a fit."}</p>
          {lead.profile_text && <details><summary>Profile notes</summary><p className="lead-reason">{lead.profile_text}</p></details>}
          <p className="settings-help">{lead.reply_count} {lead.reply_count === 1 ? "reply" : "replies"}.{lead.opted_in ? " Opted in." : ""} {lead.consent_note}</p>
        </section>
        <WorkEmail lead={lead} load={load} />
      </div>
      <LeadTimeline lead={lead} load={load} />
    </>}
  </main></div>;
}
