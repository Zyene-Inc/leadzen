"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/icon";
import { SuppressionForm } from "@/components/suppression-form";
import { api } from "@/lib/client-api";
import { formatTimelineDate, type Contact, type OutreachTimeline, type TimelineEntry } from "@/lib/leads";
import { scheduleSummary } from "@/lib/sending-schedule";
import { LEADZEN_TIME_ZONE_LABEL } from "@/lib/date-time";

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const complete = entry.status === "accepted" || entry.status === "received";
  const date = formatTimelineDate(entry.at);
  const status: Record<string, string> = { due: "Needs review", scheduled: "Scheduled", estimated: "Estimated", draft: "Draft", paused: "Paused", unconfirmed: "Not confirmed" };
  return <li className={`timeline-entry ${complete ? "timeline-complete" : ""}`}>
    <div className="timeline-date">{entry.at ? <time dateTime={entry.at} title={date.time}>{date.date}</time> : date.date}</div>
    <span className="timeline-marker" aria-hidden="true">{complete ? <Icon name="check" /> : <span />}</span>
    <div className="timeline-copy"><strong>{entry.label}</strong>{status[entry.status] && <span className="timeline-state">{status[entry.status]}</span>}{entry.subject && <p>{entry.subject}</p>}</div>
  </li>;
}

const stoppedMessages: Record<string, string> = {
  reply: "Follow-ups stopped: they replied. Continue in Inbox.",
  suppressed: "Do Not Contact. Future emails are blocked.",
  inbound: "Follow-ups stopped: a message came in. See Inbox.",
  completed: "Sequence finished. History is kept.",
};

function TimelineControls({ lead, timeline, load }: { lead: Contact; timeline: OutreachTimeline; load: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const submitting = useRef(false);
  const stopButton = useRef<HTMLButtonElement>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  const noticeElement = useRef<HTMLParagraphElement>(null);
  async function stop() {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      await api(`contacts/${lead.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stop: true }) });
      setConfirming(false); setNotice("Sequence stopped. History kept.");
      await load();
      noticeElement.current?.focus();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to stop the sequence"); }
    finally { submitting.current = false; setBusy(false); }
  }
  function closeSuppression() { setAdding(false); addButton.current?.focus(); }
  return <>
    {notice && <p ref={noticeElement} className="success" role="status" tabIndex={-1}>{notice}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="card-actions">
      {timeline.can_stop && <button ref={stopButton} className="button" disabled={busy} onClick={() => setConfirming(true)} aria-expanded={confirming}><Icon name="stop" />Stop sequence</button>}
      {lead.email && !timeline.suppression && <button ref={addButton} className="button" disabled={busy} onClick={() => setAdding(true)} aria-expanded={adding}>Block this email</button>}
      {lead.reply_count > 0 && <Link className="button" href="/inbox">Open Inbox</Link>}
      <Link className="text-link" href="/suppression">Do Not Contact list</Link>
    </div>
    {confirming && <div className="timeline-confirm" role="group" aria-label="Stop sequence confirmation"><p>Stop future emails to {lead.name}? Sent emails and history stay.</p><div className="card-actions"><button className="button" disabled={busy} onClick={() => { setConfirming(false); stopButton.current?.focus(); }}>Cancel</button><button className="button primary" disabled={busy} onClick={() => void stop()}>{busy ? "Stopping…" : "Confirm stop"}</button></div></div>}
    {adding && <SuppressionForm fixedEmail={lead.email} cancel={closeSuppression} saved={async (created) => { closeSuppression(); setNotice(created ? "Added to Do Not Contact." : "Already blocked. Original reason and date kept."); await load(); noticeElement.current?.focus(); }} />}
  </>;
}

function TimelineSequence({ sequence, blocked }: { sequence: OutreachTimeline["sequences"][number]; blocked: boolean }) {
  const status = sequence.status === "pending" ? sequence.campaign_status : sequence.status === "review" ? "Needs review" : sequence.status;
  return <div className="timeline-sequence">
    <h3>{sequence.name}<span className="timeline-state">{status}</span></h3>
    {sequence.steps.length > 0 && <><ol className="timeline-list">{sequence.steps.map((entry) => <TimelineRow key={entry.id} entry={entry} />)}</ol><p className="settings-help">Times in {LEADZEN_TIME_ZONE_LABEL}. {sequence.automatic ? `Approved follow-ups send when the scheduler is on, within ${sequence.sending_schedule ? scheduleSummary(sequence.sending_schedule) : "your sending hours in Settings"}.` : "Review each follow-up in Outreach."} Later dates are estimates.</p></>}
    {sequence.status === "review" && !blocked && <p className="settings-help">Last send needs review. It won’t retry on its own.</p>}
  </div>;
}

export function LeadTimeline({ lead, load }: { lead: Contact; load: () => Promise<void> }) {
  const timeline = lead.timeline;
  if (!timeline) return null;
  return <section className="panel settings-card lead-timeline" aria-labelledby="outreach-timeline-title">
    <div className="timeline-heading"><h2 id="outreach-timeline-title">Outreach timeline</h2><button className="button ghost" onClick={() => void load()} aria-label="Refresh outreach timeline"><Icon name="refresh" />Refresh</button></div>
    {timeline.events.length ? <ol className="timeline-list">{timeline.events.map((entry) => <TimelineRow key={entry.id} entry={entry} />)}</ol> : <p className="settings-help">No emails or replies yet.</p>}
    {timeline.events.length > 0 && <p className="settings-help">Times in {LEADZEN_TIME_ZONE_LABEL}. Accepted does not mean delivered.</p>}
    {timeline.history_truncated && <p className="settings-help">Showing the latest 100. See Inbox for all.</p>}
    {timeline.blocked_reason && <p className="timeline-stopped" role="status">{stoppedMessages[timeline.blocked_reason]}</p>}
    {timeline.sequences.map((sequence) => <TimelineSequence key={sequence.id} sequence={sequence} blocked={!!timeline.blocked_reason} />)}
    {!timeline.sequences.length && !timeline.blocked_reason && <p className="settings-help">No sequence for this lead yet.</p>}
    {timeline.suppression && <p className="settings-help">Reason: {timeline.suppression.reason || "No reason recorded"}. Added {formatTimelineDate(timeline.suppression.at).date}.</p>}
    <TimelineControls lead={lead} timeline={timeline} load={load} />
  </section>;
}
