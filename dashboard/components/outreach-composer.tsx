"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { api } from "@/lib/client-api";
import type { Contact } from "@/lib/leads";
import type { Campaign, SequenceStep } from "@/lib/campaign";
import type { Conversation } from "@/lib/chat";
import { activeRun } from "@/lib/chat";
import { useStoredData } from "@/lib/use-stored-data";
import { useWorkspaceContext } from "@/lib/workspace-context";
import { HelpText } from "@/components/help-tooltip";
import { AskLeadZen } from "@/components/ask-leadzen";
import CampaignSendReview from "@/components/campaign-send-review";

type EditableStep = SequenceStep & { key: string };
const editableSteps = (steps: SequenceStep[]): EditableStep[] => steps.map((step) => ({ ...step, key: crypto.randomUUID() }));
const blankStep = (delay_days = 0): EditableStep => ({ key: crypto.randomUUID(), subject: "", body: "", delay_days });
const post = (body: unknown, method = "POST") => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function Preparation({ threadId, done, cancel }: { threadId: string; done: (campaign: Campaign) => void; cancel: () => void }) {
  const { data, error, refresh } = useStoredData<Conversation>(`chat/threads/${threadId}`, 1500);
  const handled = useRef(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState("");
  useEffect(() => {
    if (!data || activeRun(data.run) || handled.current) return;
    const result = [...data.messages].reverse().find((m) => m.data.tool === "draft_campaign" && typeof m.data.result?.id === "string")?.data.result;
    if (result) { handled.current = true; done(result as Campaign); }
  }, [data, done]);
  async function stop() {
    if (!data?.run || stopping) return;
    setStopping(true); setStopError("");
    try { await api(`chat/runs/${data.run.id}/cancel`, post({})); refresh(); }
    catch (caught) { setStopError(caught instanceof Error ? caught.message : "Could not stop preparation"); }
    finally { setStopping(false); }
  }
  const running = activeRun(data?.run);
  return <section className="panel settings-card" aria-live="polite"><h2>Preparing your draft</h2><p>{running ? "LeadZen is using your saved offer and selected leads." : "Review the assistant’s result or return to your drafts."}</p><p className="settings-help">AI charges may apply. Sending and paid lookups require separate approval.</p>{(error || stopError) && <p className="error" role="alert">{error || stopError}</p>}{data?.run?.status === "awaiting_approval" && <p role="status">The assistant needs your input. Review its request in Chat; no action has been approved here.</p>}<div className="card-actions"><Link className="button" href={`/chat/${threadId}`}>View activity</Link>{running ? <button className="button" disabled={stopping} onClick={() => void stop()}>Stop preparation</button> : <button className="button" onClick={cancel}>Back to outreach</button>}</div></section>;
}

export function OutreachComposer({ actorId, initialSelection, existing, aiReady, close, saved }: { actorId: number; initialSelection: number[]; existing?: Campaign; aiReady: boolean; close: () => void; saved: () => void }) {
  const [stage, setStage] = useState(existing ? 2 : 1);
  const [selected, setSelected] = useState(existing ? existing.recipients.map((r) => r.id) : initialSelection);
  const selectedIds = new Set(selected);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const { data: contacts, error: contactsError, loading } = useStoredData<{ items: Contact[]; total: number; limit: number }>(`leads?state=Ready%20to%20Email&limit=50&offset=${offset}&q=${encodeURIComponent(search)}`);
  const [name, setName] = useState(existing?.name || "New outreach");
  const [category, setCategory] = useState(existing?.category || "outreach");
  const [steps, setSteps] = useState<EditableStep[]>(() => existing ? editableSteps(existing.steps) : [blankStep()]);
  const [offer, setOffer] = useState({ target: existing?.target || "", product: existing?.product || "", booking_link: existing?.booking_link || "", signature: existing?.signature || "", delay_basis: existing?.delay_basis || "working_days" });
  const [confirmed, setConfirmed] = useState(false);
  const [draft, setDraft] = useState<Campaign | undefined>(existing);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const generation = useRef<{ selection: string; thread: string; request: string } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, [stage]);
  useWorkspaceContext({ selectedLeadIds: selected, currentCampaignId: draft?.id || null, currentDraftId: null, currentLeadId: null, currentThreadId: null, workspacePath: "/outreach" }, actorId);
  async function prepareAI() {
    if (lock.current || !selected.length || selected.length > 25) return;
    lock.current = true; setBusy(true); setError("");
    try {
      const selection = [...selected].sort((a, b) => a - b).join(",");
      if (generation.current?.selection !== selection) {
        const thread = await api<{ id: string }>("chat/threads", post({}));
        generation.current = { selection, thread: thread.id, request: crypto.randomUUID() };
      }
      const request = generation.current;
      await api(`chat/threads/${request.thread}/messages`, post({ request_id: request.request, content: `Prepare one draft campaign for exactly these Workspace lead IDs: ${selection}. Use my saved product, target, signature and booking link. Write one concise initial message using supported personalization tags. No follow-ups yet. Create the draft with draft_campaign and finish. Do not send, activate, sync a mailbox, discover leads or buy emails.`, context: { selectedLeadIds: selected, currentCampaignId: null, currentLeadId: null, currentDraftId: null, currentThreadId: null, workspacePath: "/outreach" } }));
      setThreadId(request.thread);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not prepare drafts. Check saved outreach before retrying."); }
    finally { lock.current = false; setBusy(false); }
  }
  function adopt(item: Campaign) {
    setDraft(item); setName(item.name); setCategory(item.category); setSteps(editableSteps(item.steps)); setSelected(item.recipients.map((r) => r.id));
    setOffer({ target: item.target, product: item.product, booking_link: item.booking_link, signature: item.signature, delay_basis: item.delay_basis });
    setThreadId(null); setStage(2); saved();
  }
  async function persistDraft() {
    if (lock.current) throw new Error("Please wait for the current save.");
    if (!selected.length || !name.trim() || steps.some((step, index) => !step.subject.trim() || !step.body.trim() || (index > 0 && (!Number.isInteger(step.delay_days) || step.delay_days < 1 || step.delay_days > 90)))) throw new Error("Add a name, subject and message, with follow-up delays of 1–90 days.");
    lock.current = true; setBusy(true); setError("");
    try {
      const result = await api<Campaign>(draft ? `campaigns/${draft.id}` : "campaigns", post({ name, category, steps: steps.map(({ subject, body, delay_days }) => ({ subject, body, delay_days })), contact_ids: selected, ...offer }, draft ? "PUT" : "POST"));
      setDraft(result); saved();
      return result;
    } finally { lock.current = false; setBusy(false); }
  }
  async function save(event?: FormEvent) {
    event?.preventDefault();
    if (lock.current) return;
    try { await persistDraft(); if (event) setStage(3); else close(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not save your draft"); }
  }
  function updateStep(index: number, changes: Partial<SequenceStep>) { setSteps((current) => current.map((step, i) => i === index ? { ...step, ...changes } : step)); }
  if (threadId) return <Preparation threadId={threadId} done={adopt} cancel={() => { saved(); close(); }} />;
  return <section className="outreach-composer" aria-label="Create outreach">
    <ol className="outreach-steps" aria-label="Outreach steps">{["Select leads", "Review messages", "Confirm outreach"].map((label, i) => <li key={label} aria-current={stage === i + 1 ? "step" : undefined}><span>{i + 1}</span>{label}</li>)}</ol>
    <div className="section-heading"><h2 ref={heading} tabIndex={-1}>{stage === 1 ? "Who would you like to contact?" : stage === 2 ? "Make the message yours" : "Ready for your approval"}</h2><button className="button ghost" disabled={busy} onClick={() => { if (stage !== 2 || window.confirm("Close this editor? Unsaved changes will be lost; saved drafts remain in Outreach.")) close(); }}>{draft ? "Close editor" : "Cancel"}</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {stage === 1 && <section className="panel settings-card">
      <div className="filters"><input className="input" aria-label="Search ready leads" placeholder="Search name, company or email" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} /><strong>{selected.length} selected</strong>{selected.length > 0 && <button className="button ghost" onClick={() => setSelected([])}>Clear selection</button>}</div>
      {contactsError && <p className="error" role="alert">{contactsError}</p>}
      <div className="contact-picker">{contacts?.items.filter((c) => c.email).map((c) => <label className="check-row" key={c.id}><input type="checkbox" checked={selectedIds.has(c.id)} disabled={busy || (!selectedIds.has(c.id) && selected.length >= 25)} onChange={(e) => setSelected(e.target.checked ? [...selected, c.id] : selected.filter((id) => id !== c.id))} /><span><strong>{c.name || c.email}</strong><small>{c.company ? `${c.company} · ` : ""}{c.email}</small></span></label>)}</div>
      {loading && !contacts && <p role="status">Loading leads…</p>}{contacts && !contacts.items.length && <p className="empty">No ready leads match. <Link className="text-link" href="/contacts">Find or add leads</Link></p>}{contacts && contacts.items.length > 0 && !contacts.items.some((c) => c.email) && <p className="empty">None of the ready leads have a resolved email yet. <Link className="text-link" href="/contacts">Find each lead’s work email from the Leads page</Link>, or add contacts with emails.</p>}
      {contacts && contacts.total > contacts.limit && <div className="records-pagination"><span>{offset + 1}–{Math.min(offset + contacts.limit, contacts.total)} of {contacts.total}</span><div className="top-actions"><button className="button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - contacts.limit))}>Previous</button><button className="button" disabled={offset + contacts.limit >= contacts.total} onClick={() => setOffset(offset + contacts.limit)}>Next</button></div></div>}
      <p className="settings-help">Select up to 25 leads. Eligibility and permissions are checked again before sending.</p>
      <div className="card-actions"><button className="button primary" disabled={busy || !selected.length || selected.length > 25} onClick={() => aiReady ? void prepareAI() : setStage(2)}>{busy ? "Preparing…" : "Prepare drafts"}</button>{aiReady && <button className="button" disabled={busy || !selected.length || selected.length > 25} onClick={() => setStage(2)}>Write myself</button>}</div>
      <p className="settings-help">{aiReady ? "Prepare drafts uses your AI provider; AI charges may apply. No emails are sent." : "Write your message in the next step. Connect AI in Settings for assisted drafting."}</p>
    </section>}
    {stage === 2 && <form onSubmit={save}><fieldset disabled={busy} className="outreach-fields">
      <section className="panel settings-card"><div className="form-grid"><label className="wide">Outreach name<input className="input" required maxLength={160} value={name} onChange={(e) => setName(e.target.value)} /></label></div><p className="settings-help">{selected.length} selected recipients{draft ? ` · ${draft.from_address}` : ""}</p>
        <details><summary>Offer & sending details</summary><div className="form-grid"><label>Email type<select className="select" value={category} disabled={!!draft} onChange={(e) => { setCategory(e.target.value); if (e.target.value === "transactional") setSteps((current) => current.slice(0, 1)); }}><option value="outreach">Outreach</option><option value="opted_in">Opted-in campaign</option><option value="transactional">Transactional notification</option></select></label>{(["target", "product", "booking_link", "signature"] as const).map((key) => <label key={key} className="wide">{({ target: "Target", product: "Product", booking_link: "Booking link", signature: "Signature" })[key]}<textarea className="input" rows={2} value={offer[key]} maxLength={key === "booking_link" ? 500 : 2000} onChange={(e) => setOffer({ ...offer, [key]: e.target.value })} /></label>)}</div></details>
        <HelpText label="Personalize your message">Use {"{{first_name}}, {{last_name}}, {{company}}, {{sender_name}} or {{booking_link}}. The final review shows each recipient’s rendered message, signature and opt-out text."}</HelpText>
      </section>
      {steps.map((step, index) => <section className="panel settings-card" key={step.key}><div className="panel-head"><h3>{index ? `Follow-up ${index}` : "First email"}</h3>{index > 0 && <button className="button ghost" type="button" onClick={() => setSteps((current) => current.filter((_, i) => i !== index))}>Remove follow-up {index}</button>}</div><div className="form-grid">{index > 0 && <label>Days after the previous email<input className="input" type="number" min={1} max={90} required value={step.delay_days || ""} onChange={(e) => { if (e.target.value === "") { updateStep(index, { delay_days: 0 }); return; } const days = e.target.valueAsNumber; if (Number.isInteger(days) && days >= 1 && days <= 90) updateStep(index, { delay_days: days }); }} /></label>}<label className="wide">Subject<input className="input" required maxLength={200} value={step.subject} onChange={(e) => updateStep(index, { subject: e.target.value })} /></label><label className="wide">Message<textarea className="input textarea" rows={6} required maxLength={10000} value={step.body} onChange={(e) => updateStep(index, { body: e.target.value })} /></label></div></section>)}
      <section className="panel settings-card"><div className="section-heading"><div><h3>Follow-ups</h3><p className="settings-help">{steps.length === 1 ? "Off · Send the first email only." : `${steps.length - 1} follow-up${steps.length > 2 ? "s" : ""} · Review timing and approve automation in the next step.`}</p></div><button className="button" type="button" aria-pressed={steps.length > 1} disabled={category === "transactional"} onClick={() => setSteps((current) => current.length > 1 ? current.slice(0, 1) : [...current, blankStep(3)])}>{steps.length > 1 ? "Turn off follow-ups" : "Add follow-ups"}</button></div>{steps.length > 1 && <div className="form-grid"><label>Count delays in<select className="select" value={offer.delay_basis} onChange={(e) => setOffer({ ...offer, delay_basis: e.target.value })}><option value="working_days">Working days (Mon–Fri)</option><option value="calendar_days">Calendar days</option></select></label>{steps.length < 3 && <button className="button" type="button" onClick={() => setSteps([...steps, blankStep(5)])}>Add second follow-up</button>}</div>}</section>
      <div className="card-actions">{!draft && <button className="button" type="button" onClick={() => setStage(1)}>Back to leads</button>}<button className="button primary" type="submit">{busy ? "Saving…" : "Review & send"}</button><button className="button" type="button" onClick={() => void save()}>Save for later</button><AskLeadZen actorId={actorId} beforeOpen={async () => { const result = await persistDraft(); return { currentCampaignId: result.id, workspacePath: `/outreach?campaign=${result.id}` }; }} context={{ selectedLeadIds: selected, currentCampaignId: draft?.id || null, workspacePath: "/outreach" }} /></div>
    </fieldset></form>}
    {stage === 3 && draft && <CampaignSendReview campaignId={draft.id} count={Math.min(25, selected.length)} close={() => confirmed ? close() : setStage(2)} sent={async () => { setConfirmed(true); saved(); }} />}
  </section>;
}
