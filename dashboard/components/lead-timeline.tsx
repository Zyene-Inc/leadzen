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
  const status: Record<string, string> = { due: "Awaiting review", scheduled: "Scheduled follow-up", estimated: "Estimated", draft: "Draft", paused: "Paused", unconfirmed: "Acceptance not recorded" };
  return <li className={`timeline-entry ${complete ? "timeline-complete" : ""}`}>
    <div className="timeline-date">{entry.at ? <time dateTime={entry.at} title={date.time}>{date.date}</time> : date.date}</div>
    <span className="timeline-marker" aria-hidden="true">{complete ? <Icon name="check" /> : <span />}</span>
    <div className="timeline-copy"><strong>{entry.label}</strong>{status[entry.status] && <span className="timeline-state">{status[entry.status]}</span>}{entry.subject && <p>{entry.subject}</p>}</div>
  </li>;
}

const stoppedMessages: Record<string, string> = {
  reply: "Follow-ups stopped after this reply. Continue the conversation in Inbox.",
  suppressed: "Do Not Contact. Future emails to this address are blocked.",
  inbound: "Follow-ups stopped because an inbound message is recorded. Review it in Inbox.",
  completed: "Outreach sequence ended. Email and conversation history are retained.",
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
      setConfirming(false); setNotice("Sequence stopped. History retained.");
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
      {timeline.can_stop && <button ref={stopButton} className="button" disabled={busy} onClick={() => setConfirming(true)} aria-expanded={confirming}><Icon name="stop" />Stop Sequence</button>}
      {lead.email && !timeline.suppression && <button ref={addButton} className="button" disabled={busy} onClick={() => setAdding(true)} aria-expanded={adding}>Add to suppression list</button>}
      {lead.reply_count > 0 && <Link className="button" href="/inbox">Open Inbox</Link>}
      <Link className="text-link" href="/suppression">Do Not Contact list</Link>
    </div>
    {confirming && <div className="timeline-confirm" role="group" aria-label="Stop Sequence confirmation"><p>Stop future outreach to {lead.name}? Accepted emails and conversation history will remain.</p><div className="card-actions"><button className="button" disabled={busy} onClick={() => { setConfirming(false); stopButton.current?.focus(); }}>Cancel</button><button className="button primary" disabled={busy} onClick={() => void stop()}>{busy ? "Stopping…" : "Confirm stop"}</button></div></div>}
    {adding && <SuppressionForm fixedEmail={lead.email} cancel={closeSuppression} saved={async (created) => { closeSuppression(); setNotice(created ? "Address added to Do Not Contact." : "This address is already suppressed; its original reason and date are retained."); await load(); noticeElement.current?.focus(); }} />}
  </>;
}

function TimelineSequence({ sequence, blocked }: { sequence: OutreachTimeline["sequences"][number]; blocked: boolean }) {
  const status = sequence.status === "pending" ? sequence.campaign_status : sequence.status === "review" ? "Needs review" : sequence.status;
  return <div className="timeline-sequence">
    <h3>{sequence.name}<span className="timeline-state">{status}</span></h3>
    {sequence.steps.length > 0 && <><ol className="timeline-list">{sequence.steps.map((entry) => <TimelineRow key={entry.id} entry={entry} />)}</ol><p className="settings-help">Dates use {LEADZEN_TIME_ZONE_LABEL}. {sequence.automatic ? `Approved follow-ups run while the scheduler is enabled, within ${sequence.sending_schedule ? scheduleSummary(sequence.sending_schedule) : "your sending hours in Settings"}.` : "Follow-ups require review in Outreach."} Later dates are estimates until the preceding email is accepted.</p></>}
    {sequence.status === "review" && !blocked && <p className="settings-help">The last attempt needs review. No automatic retry will occur.</p>}
  </div>;
}

export function LeadTimeline({ lead, load }: { lead: Contact; load: () => Promise<void> }) {
  const timeline = lead.timeline;
  if (!timeline) return null;
  return <section className="panel settings-card lead-timeline" aria-labelledby="outreach-timeline-title">
    <div className="timeline-heading"><h2 id="outreach-timeline-title">Outreach timeline</h2><button className="button ghost" onClick={() => void load()} aria-label="Refresh outreach timeline"><Icon name="refresh" />Refresh</button></div>
    {timeline.events.length ? <ol className="timeline-list">{timeline.events.map((entry) => <TimelineRow key={entry.id} entry={entry} />)}</ol> : <p className="settings-help">No recorded emails or replies yet.</p>}
    {timeline.events.length > 0 && <p className="settings-help">Recorded event dates use {LEADZEN_TIME_ZONE_LABEL}. Email acceptance does not confirm delivery.</p>}
    {timeline.history_truncated && <p className="settings-help">Showing the latest 100 events. Full conversations are available in Inbox.</p>}
    {timeline.blocked_reason && <p className="timeline-stopped" role="status">{stoppedMessages[timeline.blocked_reason]}</p>}
    {timeline.sequences.map((sequence) => <TimelineSequence key={sequence.id} sequence={sequence} blocked={!!timeline.blocked_reason} />)}
    {!timeline.sequences.length && !timeline.blocked_reason && <p className="settings-help">No campaign sequence is saved for this lead. No follow-up dates are scheduled here.</p>}
    {timeline.suppression && <p className="settings-help">Reason: {timeline.suppression.reason || "No reason recorded"}. Added {formatTimelineDate(timeline.suppression.at).date}.</p>}
    <TimelineControls lead={lead} timeline={timeline} load={load} />
  </section>;
}
