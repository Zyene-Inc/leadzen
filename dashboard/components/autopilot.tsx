"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/client-api";
import { useStoredData } from "@/lib/use-stored-data";
import { HelpTooltip } from "@/components/help-tooltip";
import { defaultSendingSchedule, NEW_YORK_TIMEZONE, NEW_YORK_TIMEZONE_LABEL, normalizeSendingSchedule, scheduleDayLabel, scheduleSummary, scheduleTime, type SendingSchedule } from "@/lib/sending-schedule";
import { formatNewYorkDateTime } from "@/lib/date-time";

type Scope = {
  timezone: string; daily_contacts: number; monthly_contacts: number;
  daily_credits: number; monthly_credits: number; daily_ai_requests: number;
  monthly_ai_requests: number; authorization_days: number; followup_days: number[]; tone: string; sending_schedule?: SendingSchedule;
};
type State = {
  setup: { revision: string; blockers: string[]; target: string; product: string; sender: string; signature: string; booking_link: string; service_enabled: boolean; sending_schedule?: SendingSchedule };
  policy: { id: string; enabled: boolean; scope: Scope; expires_at: string; expires_on?: string; expired?: boolean; heartbeat_stale?: boolean; next_start: string | null; heartbeat_at: string | null; issue: string; setup_changed: boolean } | null;
  runs: { id: string; workday: string; phase: string; contacts: number; accepted: number; reserved_credits: number; ai_requests: number; issue: string; campaign_ids: string[]; discovery_ids?: string[] }[];
};
const defaults: Scope = { timezone: NEW_YORK_TIMEZONE, daily_contacts: 10, monthly_contacts: 200, daily_credits: 10, monthly_credits: 200,
  daily_ai_requests: 60, monthly_ai_requests: 1200, authorization_days: 30, followup_days: [3, 5], tone: "Brief, professional and helpful" };
const fields = [
  ["daily_contacts", "New contacts / day", 25], ["monthly_contacts", "New contacts / month", 500],
  ["daily_credits", "Email credits / day", 25], ["monthly_credits", "Email credits / month", 500],
  ["daily_ai_requests", "AI requests / day", 200], ["monthly_ai_requests", "AI requests / month", 4000],
  ["authorization_days", "Authorize for (days)", 90],
] as const;
const phases: Record<string, string> = { scheduled: "Scheduled", finding: "Finding leads", enriching: "Finding verified emails", drafting: "Writing messages", validating: "Checking messages", sending: "Sending", completed: "Initial outreach complete", needs_attention: "Needs attention", stopped: "Stopped" };

function initialScope(data: State): Scope {
  const schedule = normalizeSendingSchedule(data.setup.sending_schedule ?? data.policy?.scope.sending_schedule ?? defaultSendingSchedule());
  return { ...defaults, ...data.policy?.scope, timezone: NEW_YORK_TIMEZONE, sending_schedule: schedule };
}
function numericInput(raw: string) {
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}
const followupSlots = [{ id: "first", index: 0 }, { id: "second", index: 1 }];

function policyStartLabel(scope: Scope) {
  const schedule = scope.sending_schedule;
  return schedule
    ? `${scheduleDayLabel(schedule.days)} · Starts ${scheduleTime(schedule.start)} · ${NEW_YORK_TIMEZONE_LABEL}`
    : `Weekdays · Starts 10 AM · ${NEW_YORK_TIMEZONE_LABEL}`;
}

function AutopilotSetup({ data, close, saved }: { data: State; close: () => void; saved: () => void }) {
  const review = data.setup;
  const [scope, setScope] = useState<Scope>(() => initialScope(data));
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const requestId = useRef({ id: "", body: "" });
  const heading = useRef<HTMLHeadingElement>(null);
  const schedule = scope.sending_schedule ?? defaultSendingSchedule();
  useEffect(() => { heading.current?.focus(); }, []);
  async function enable(event: React.FormEvent) {
    event.preventDefault();
    if (lock.current || !accepted) return;
    lock.current = true; setBusy(true); setError("");
    const body = JSON.stringify({ ...scope, enabled: true, authorize_automatic_outreach: true, revision: review.revision });
    if (requestId.current.body !== body) requestId.current = { id: crypto.randomUUID(), body };
    try {
      await api("autopilot", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...JSON.parse(body), request_id: requestId.current.id }) });
      saved(); close();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not enable Autopilot"); }
    finally { lock.current = false; setBusy(false); }
  }
  return <form className="autopilot-setup" onSubmit={enable} onKeyDown={(event) => { if (event.key === "Escape" && !busy) { event.preventDefault(); close(); } }}>
    <h3 ref={heading} tabIndex={-1}>Set up daily outreach</h3>
    <p className="settings-help">{scheduleSummary(schedule)}. Discovery starts at {scheduleTime(schedule.start)}; sending is paced until {scheduleTime(schedule.end)}. Holidays are included; unsent first emails expire that day. <Link className="text-link" href="/settings#sending-hours">Edit schedule in Settings</Link></p>
    <div className="autopilot-facts"><p><strong>From</strong> {review.sender || "No mailbox connected"}</p><p><strong>Audience</strong> {review.target || "Set your audience in Settings"}</p><details><summary>Offer, signature & booking link</summary><pre>{review.product}</pre><pre>{review.signature}</pre><p>{review.booking_link || "No booking link"}</p></details></div>
    <div className="form-grid">
      {fields.map(([key, label, max]) => <label key={key}>{label}<input type="number" required min={1} max={max} value={scope[key] || ""} onChange={(event) => setScope({ ...scope, [key]: numericInput(event.target.value) })} /></label>)}
    </div>
    <label>Writing guidance<textarea maxLength={500} required value={scope.tone} onChange={(event) => setScope({ ...scope, tone: event.target.value })} /></label>
    <label className="checkbox-label"><input type="checkbox" checked={scope.followup_days.length > 0} onChange={(event) => setScope({ ...scope, followup_days: event.target.checked ? [3, 5] : [] })} />Add follow-ups</label>
    {!!scope.followup_days.length && <><div className="form-grid">{followupSlots.slice(0, scope.followup_days.length).map(({ id, index }) => <label key={id}>Follow-up {index + 1}: sending days after previous email<input type="number" required min={1} max={30} value={scope.followup_days[index] || ""} onChange={(event) => setScope({ ...scope, followup_days: scope.followup_days.map((value, position) => position === index ? numericInput(event.target.value) : value) })} /></label>)}</div><HelpTooltip label="Follow-up timing">Counts only your selected sending days. For a Saturday-only schedule, one sending day means the next Saturday.</HelpTooltip></>}
    <p className="settings-help">AI requests and email lookups can incur provider charges. These are request and credit caps, not a currency spending limit. Reservations count even if a provider response is lost. Follow-ups stop on any recorded reply or opt-out; inbox failures hold sending.</p>
    <label className="checkbox-label"><input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />I authorize recurring discovery, paid email lookups, AI drafting, inbox checks, and automatic sending{scope.followup_days.length ? " including follow-ups" : ""} on this schedule and within these limits, without daily review.</label>
    {!!review.blockers.length && <ul className="error">{review.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>}
    {error && <p role="alert" className="error">{error}</p>}
    <div className="card-actions"><button type="submit" className="button primary" disabled={busy || !accepted || !!review.blockers.length}>{busy ? "Enabling…" : "Enable automatic outreach"}</button><button type="button" className="button" disabled={busy} onClick={close}>Cancel</button></div>
  </form>;
}

export function Autopilot() {
  const { data, error: loadError, refresh } = useStoredData<State>("autopilot", 10000);
  const [editing, setEditing] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const policy = data?.policy;
  const on = !!policy?.enabled;
  async function turnOff() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try { await api("autopilot", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: false }) }); refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not stop Autopilot"); }
    finally { lock.current = false; setBusy(false); }
  }
  return <section className="panel settings-card autopilot-card" aria-label="Daily Autopilot">
    <div className="panel-head"><div><div className="autopilot-title"><h2>Daily Autopilot</h2><HelpTooltip label="About Daily Autopilot">Finds new matching leads, verifies emails, writes personal messages and sends within your approved limits. Turning it off stops pending automatic work. Emails already accepted cannot be recalled.</HelpTooltip></div><p className="panel-meta">{on ? policyStartLabel(policy.scope) : "Find leads, write messages and send automatically."}</p></div><button ref={toggle} className={`button ${on ? "primary" : ""}`} role="switch" aria-label="Daily Autopilot" aria-checked={on} disabled={!data || busy} onClick={() => { if (on) void turnOff(); else if (!editing) setEditing(data); }}>{busy ? "Stopping…" : on ? "On" : "Off"}</button></div>
    {(error || loadError) && <p className="error" role="alert">{error || loadError}</p>}
    {data && !data.setup.service_enabled && <p className="settings-help">Automatic execution is disabled on the server. Your administrator must enable the Autopilot service before it can run.</p>}
    {on && policy && <PolicyStatus policy={policy} serviceEnabled={!!data?.setup.service_enabled} />}
    {editing && <AutopilotSetup data={editing} saved={refresh} close={() => { setEditing(null); toggle.current?.focus(); }} />}
    {data && <RunHistory runs={data.runs} />}
  </section>;
}


function PolicyStatus({ policy, serviceEnabled }: { policy: NonNullable<State["policy"]>; serviceEnabled: boolean }) {
  return <>
    <p className="settings-help">Up to {policy.scope.daily_contacts} new contacts/day · {policy.scope.followup_days.length} follow-ups · authorization ends {formatNewYorkDateTime(policy.expires_at, { dateStyle: "medium" })}</p>
    {policy.expired && <p className="error" role="status">Authorization expired. Turn off and review a new authorization.</p>}
    {policy.setup_changed && <p className="error" role="status">Setup changed. Turn off and review a new authorization.</p>}
    {policy.issue && <p className="error" role="status">{policy.issue}</p>}
    {policy.heartbeat_stale && serviceEnabled && <p className="error" role="status">Worker heartbeat unavailable or delayed. Check with your administrator.</p>}
    {policy.next_start && <p className="panel-meta">Next scheduled start: {formatNewYorkDateTime(policy.next_start)} · {NEW_YORK_TIMEZONE_LABEL}</p>}
    <details><summary>Authorized limits</summary><p className="settings-help">{policy.scope.daily_credits} email credits/day, {policy.scope.monthly_credits}/month · {policy.scope.daily_ai_requests} AI requests/day, {policy.scope.monthly_ai_requests}/month · {policy.scope.monthly_contacts} new contacts/month. Planned batches reserve contact capacity.</p></details>
  </>;
}

function RunHistory({ runs }: { runs: State["runs"] }) {
  const latest = runs[0];
  if (!latest) return null;
  return <details className="autopilot-results"><summary>{latest.workday} · {phases[latest.phase] || latest.phase} · {latest.accepted} emails accepted</summary>{runs.map((run) => <div key={run.id} className="sequence-step"><strong>{run.workday} · {phases[run.phase] || run.phase}</strong><p className="panel-meta">{run.contacts} contacts · {run.accepted} emails accepted · {run.reserved_credits} credits reserved · {run.ai_requests} AI requests</p>{run.issue && <p className="error">{run.issue}</p>}{run.discovery_ids?.map((id) => <Link className="button ghost" key={id} href={`/find-leads/${id}`}>View discovery</Link>)}{run.campaign_ids.map((id) => <Link className="button ghost" key={id} href={`/outreach?campaign=${id}`}>View messages & status</Link>)}</div>)}</details>;
}
