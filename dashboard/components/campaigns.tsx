"use client";
import { Autopilot } from "@/components/autopilot";
import { useRef, useState } from "react";
import Link from "next/link";
import { Sidebar } from "@/components/sidebar";
import { PageHeading } from "@/components/page-heading";
import { HelpText } from "@/components/help-tooltip";
import { OutreachComposer } from "@/components/outreach-composer";
import OutreachReview from "@/components/outreach-review";
import CampaignSendReview from "@/components/campaign-send-review";
import { AskLeadZen } from "@/components/ask-leadzen";
import { useWorkspaceContext } from "@/lib/workspace-context";
import { useStoredData } from "@/lib/use-stored-data";
import { api } from "@/lib/client-api";
import type { Account } from "@/lib/auth";
import type { Campaign } from "@/lib/campaign";
import type { OutreachSetup } from "@/lib/outreach";
import { sentTime } from "@/lib/outreach";
import { scheduleDayLabel, scheduleHours, scheduleSummary, windowSchedule } from "@/lib/sending-schedule";
import { LEADZEN_TIME_ZONE_LABEL } from "@/lib/date-time";

function OutreachItem({ item, actorId, edit, refresh, initiallyOpen }: { item: Campaign; actorId: number; edit: () => void; refresh: () => void; initiallyOpen: boolean }) {
  const opener = useRef<HTMLButtonElement>(null);
  const lock = useRef(false);
  const [reviewing, setReviewing] = useState(initiallyOpen && item.status !== "draft" && !item.autopilot);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function change(method: string, body: object) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try { await api(`campaigns/${item.id}`, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); setReviewing(false); refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not update outreach"); }
    finally { lock.current = false; setBusy(false); }
  }
  const stepCount = item.autopilot ? Math.max(0, ...item.recipients.map((r) => r.personal_steps?.length || 0)) : item.steps.length;
  return <article className="panel settings-card outreach-item"><div className="panel-head"><div><h3>{item.name}</h3><p className="panel-meta">{item.total} recipients · {item.sent} contacted · {stepCount > 1 ? `${stepCount - 1} follow-ups` : "One email"}</p></div><span className={`badge ${item.status}`}>{item.status === "draft" ? "Needs review" : item.status}</span></div>
    {item.automatic_followups && <p className="settings-help">Automatic follow-ups approved · {item.sending_schedule ? scheduleSummary(item.sending_schedule) : "Sending hours follow Settings"}</p>}{item.followup_issue && <p className="error" role="status">{item.followup_issue}</p>}{error && <p className="error" role="alert">{error}</p>}
    {item.autopilot && <p className="settings-help">Authorized by Daily Autopilot. Personal messages are saved for each recipient.</p>}
    {item.status !== "archived" && <div className="card-actions">{!item.autopilot && <button ref={opener} className="button primary" disabled={busy} onClick={() => item.status === "draft" ? edit() : setReviewing(!reviewing)}>{item.status === "draft" ? "Review draft" : item.status === "paused" ? "Review & resume" : "Review next emails"}</button>}{item.autopilot && item.status === "paused" && <button className="button" disabled={busy} onClick={() => void change("PUT", { status: "active" })}>Resume automatic outreach</button>}{item.status === "active" && <button className="button" disabled={busy} onClick={() => void change("PUT", { status: "paused" })}>Pause outreach</button>}<button className="button ghost" disabled={busy} onClick={() => { if (window.confirm(`Stop and archive “${item.name}”? Emails already accepted cannot be recalled.`)) void change("DELETE", {}); }}>Stop & archive</button><AskLeadZen actorId={actorId} context={{ currentCampaignId: item.id, workspacePath: `/outreach?campaign=${item.id}` }} /></div>}
    {reviewing && <CampaignSendReview campaignId={item.id} count={Math.min(25, item.total)} close={() => { setReviewing(false); opener.current?.focus(); }} sent={async () => refresh()} />}
    <details className="sequence-details" open={item.autopilot && initiallyOpen ? true : undefined}><summary>Messages & recipient status</summary>{item.steps.map((step, index) => <div className="sequence-step" key={`${item.id}-${index}-${step.subject}`}><strong>{index ? `Follow-up ${index} · ${step.delay_days} ${item.delay_basis === "working_days" ? "working" : "calendar"} days later` : "First email"}: {step.subject}</strong><pre>{step.body}</pre></div>)}{item.recipients.map((r) => <p className="panel-meta" key={r.id}>{r.email} · {r.status} · {r.next_step} accepted{r.next_send_at ? ` · Next: ${sentTime(r.next_send_at)}` : ""}{r.personal_steps?.map((step, index) => <span className="autopilot-message" key={index}><strong>{index ? `Follow-up ${index} · ${step.delay_days} working days later` : "First email"}: {step.subject}</strong><span>{step.body}</span></span>)}</p>)}{item.total > item.recipients.length && <p className="settings-help">Showing the first {item.recipients.length} of {item.total} recipients.</p>}</details>
  </article>;
}

const noSelection: number[] = [];
export default function Outreach({ user, initialSelection = noSelection, initialReviewId = null, initialCampaignId = null }: { user: Account; initialSelection?: number[]; initialReviewId?: string | null; initialCampaignId?: string | null }) {
  const campaigns = useStoredData<{ items: Campaign[] }>("campaigns", 5000);
  const setup = useStoredData<OutreachSetup>("outreach", 5000);
  const jobs = useStoredData<{ items: { id: string; status: string; requested_count: number; kind: string; output: string }[] }>("jobs", 5000);
  const [creating, setCreating] = useState(initialSelection.length > 0 && !initialReviewId && !initialCampaignId);
  const [editing, setEditing] = useState<Campaign | undefined>();
  const [reviewId, setReviewId] = useState(initialReviewId);
  useWorkspaceContext(!creating && !reviewId ? { workspacePath: "/outreach", selectedLeadIds: [], currentLeadId: null, currentDraftId: null, currentThreadId: null, currentCampaignId: null } : {}, user.id);
  const [filter, setFilter] = useState("open");
  const [openedInitial, setOpenedInitial] = useState(false);
  const initial = campaigns.data?.items.find((c) => c.id === initialCampaignId);
  // Resolve a linked record once; subsequent polls never overwrite employee edits or filters.
  if (!openedInitial && initial) {
    setOpenedInitial(true);
    if (initial.status === "archived") setFilter("all");
    if (initial.status === "draft" && !initial.autopilot) { setEditing(initial); setCreating(true); }
  }
  function refresh() { campaigns.refresh(); setup.refresh(); jobs.refresh(); }
  const items = campaigns.data?.items.filter((c) => filter === "all" || (filter === "draft" ? c.status === "draft" : c.status !== "archived")) || [];
  return <div className="shell"><Sidebar user={user} active="outreach" /><main className="main"><header className="topbar" data-tour={creating || reviewId ? "outreach-flow" : undefined}><PageHeading title="Outreach" help="Select leads, review their messages and confirm sending. Drafts, follow-ups and delivery progress live here." /><div className="top-actions"><button className="button" onClick={refresh}>Refresh</button>{!creating && !reviewId && <button className="button primary" data-tour="outreach-flow" onClick={() => { setEditing(undefined); setCreating(true); }}>New outreach</button>}</div></header>
    {(campaigns.error || setup.error || jobs.error) && <p className="error" role="alert">{campaigns.error || setup.error || jobs.error}</p>}
    {creating ? <OutreachComposer key={editing?.id || "new"} actorId={user.id} initialSelection={initialSelection} existing={editing} aiReady={!!setup.data?.ai_ready} close={() => { setCreating(false); setEditing(undefined); refresh(); }} saved={refresh} /> : reviewId ? <OutreachReview reviewId={reviewId} workspacePath={`/outreach?review=${reviewId}`} closeLabel="Back to outreach" closed={() => { setReviewId(null); refresh(); }} /> : <>
      <Autopilot />
      {setup.data && <div className="outreach-summary"><div><span className="muted">Sending from</span><strong>{setup.data.from_address || "Connect a mailbox in Settings"}</strong></div><div><span className="muted">Available today</span><strong>{setup.data.remaining_today} conversations</strong></div><div><span className="muted">Sending hours</span><strong>{scheduleHours(windowSchedule(setup.data.window))}</strong><small>{scheduleDayLabel(windowSchedule(setup.data.window).days)} · {LEADZEN_TIME_ZONE_LABEL}</small><Link className="text-link" href="/settings#sending-hours">Edit hours</Link></div></div>}
      {jobs.data?.items.some((j) => ["queued", "running", "failed"].includes(j.status)) && <section className="panel settings-card"><h2>Delivery activity</h2>{jobs.data.items.filter((j) => ["queued", "running", "failed"].includes(j.status)).slice(0, 5).map((job) => <div className="attention-row" key={job.id}><span>{job.requested_count} emails <span className="badge">{job.status}</span></span><details><summary>View result</summary><p className="settings-help">{job.output || "Waiting for the worker’s next update."}</p></details></div>)}<HelpText label="What these states mean">Queued messages may wait for sending hours or pacing. Provider acceptance does not guarantee delivery. Uncertain attempts require review and are never automatically retried.</HelpText></section>}
      <div className="section-heading"><h2>Your outreach</h2><div className="top-actions" role="group" aria-label="Filter outreach">{[["open", "Open"], ["draft", "Needs review"], ["all", "All"]].map(([value, label]) => <button key={value} className={`button ${filter === value ? "selected" : "ghost"}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div></div>
      {setup.data?.reviews.filter((r) => filter === "all" || (filter === "draft" ? r.status === "draft" : ["draft", "generating", "queued", "running", "failed"].includes(r.status))).map((r) => <button className="review-list-button panel" key={r.id} onClick={() => setReviewId(r.id)}><span><strong>{r.kind === "reply" ? "Reply draft" : `${r.count} personal messages`}</strong><small>{sentTime(r.created_at)}</small></span><span className="badge">{r.status === "draft" ? "Needs review" : r.status}</span></button>)}
      <div className="campaign-list">{items.map((item) => <OutreachItem key={item.id} item={item} actorId={user.id} refresh={refresh} initiallyOpen={item.id === initialCampaignId} edit={() => { setEditing(item); setCreating(true); }} />)}</div>
      {campaigns.loading && !campaigns.data && <p role="status">Loading outreach…</p>}{campaigns.data && !items.length && !setup.data?.reviews.length && <section className="empty"><h2>{filter === "draft" ? "No drafts waiting" : "Start a conversation"}</h2><p>Select leads and prepare your first message. Add follow-ups only when you need them.</p><button className="button primary" onClick={() => { setEditing(undefined); setCreating(true); }}>Select leads</button></section>}
    </>}
  </main></div>;
}
