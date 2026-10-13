"use client";
import { AskLeadZen } from "@/components/ask-leadzen";
import { useRouter } from "next/navigation";
import { recordWorkspaceContext, flushWorkspaceContext, useWorkspaceContext } from "@/lib/workspace-context";
import { PageHeading } from "@/components/page-heading";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Sidebar } from "@/components/sidebar";
import { Avatar } from "@/components/avatar";
import { Icon } from "@/components/icon";
import type { Account } from "@/lib/auth";
import { useWorkspaceRevision } from "@/lib/workspace-updates";
import { api } from "@/lib/client-api";
import { emailLabel, leadFilters, leadStatus, type Contact } from "@/lib/leads";
import { LeadLinks } from "@/components/lead-links";
import { BulkEmailConfirmation, EmailConfirmation } from "@/components/work-email-confirm";

type Summary = { all: number; email_found: number; needs_email: number; contacted: number; replied: number };
const canEmail = (item: Contact) => !!item.email && item.state === "Ready to Email";
const canLookUp = (item: Contact) => !item.email && item.qualified && item.email_status === "not_requested" && item.state === "Ready to Email";

type ImportRow = { row: number; email: string; reason: string };
type ImportReport = { ids: number[]; created: number; restored: number; do_not_contact: number; skipped: ImportRow[]; duplicates: ImportRow[]; failed: ImportRow[]; summary: string };

function csvRows(source: string) {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (char === '"') {
      if (quoted && source[i + 1] === '"') {
        cell += '"';
        i++;
      } else quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && source[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some((v) => v.trim())) rows.push(row);
      row = [];
      cell = "";
    } else cell += char;
  }
  if (quoted) throw new Error("CSV contains an unclosed quoted field");
  row.push(cell);
  if (row.some((v) => v.trim())) rows.push(row);
  const headers =
    rows.shift()?.map((value) => value.trim().replace(/^\uFEFF/, "")) ?? [];
  if (
    !headers.includes("email") ||
    headers.length !== new Set(headers).size ||
    rows.length > 100 ||
    rows.length < 1
  )
    throw new Error(
      "Add an email column, unique headers and 1–100 rows",
    );
  return rows.map((values) => {
    if (values.length !== headers.length)
      throw new Error("Every row needs the same number of columns");
    const result = Object.fromEntries(
      headers.map((key, i) => [key, values[i]]),
    );
    return { ...result, opted_in: result.opted_in?.toLowerCase() === "true" };
  });
}

export default function Contacts({ user }: { user: Account }) {
  const router = useRouter();
  // Keep each selected lead's row so the toolbar works across pages and filters.
  const [picked, setPicked] = useState<Map<number, Contact>>(new Map());
  const selected = useMemo(() => [...picked.keys()], [picked]);
  const selectedIds = new Set(selected);
  const ready = [...picked.values()].filter(canEmail);
  const needEmail = [...picked.values()].filter((item) => !item.email);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [lookupFor, setLookupFor] = useState<number | null>(null);
  const [bulkLookup, setBulkLookup] = useState(false);
  const [lookupRun, setLookupRun] = useState("");
  function toggle(item: Contact, on: boolean) {
    setPicked((current) => { const next = new Map(current); if (on) next.set(item.id, item); else next.delete(item.id); return next; });
  }
  const [importOpen, setImportOpen] = useState(false);
  useWorkspaceContext({ selectedLeadIds: selected, currentLeadId: null, currentDraftId: null, currentThreadId: null, currentCampaignId: null, workspacePath: "/contacts" }, user.id);
  async function prepareOutreach() {
    setBusy(true); setError("");
    try {
      await recordWorkspaceContext({ selectedLeadIds: ready.map((item) => item.id), currentLeadId: null, currentDraftId: null, currentThreadId: null, currentCampaignId: null, workspacePath: "/outreach" }, user.id);
      await flushWorkspaceContext(); router.push("/outreach");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not select leads"); }
    finally { setBusy(false); }
  }
  const workspaceRevision = useWorkspaceRevision();
  const [items, setItems] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState("all");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Contact | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [csv, setCsv] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const latest = useRef(0);
  const load = useCallback((signal?: AbortSignal, background = false) => {
    // Background refreshes keep rows (and anything open in them) on screen,
    // and only the newest request may apply its result.
    const request = ++latest.current;
    if (!background) setLoading(true);
    return api<{ items: Contact[]; total: number; summary?: Summary }>(
        `leads?limit=50&offset=${offset}&q=${encodeURIComponent(query)}&stage=${stage}`,
        { signal },
      ).then((value) => {
      if (signal?.aborted || request !== latest.current) return;
      setItems(value.items);
      // Selected leads follow their latest saved state (email found, stopped, edited).
      const fresh = new Map(value.items.map((item) => [item.id, item]));
      setPicked((current) => [...current.keys()].some((id) => fresh.has(id)) ? new Map([...current].map(([id, item]) => [id, fresh.get(id) ?? item])) : current);
      setTotal(value.total);
      if (value.summary) setSummary(value.summary);
      setLoadError("");
    }).catch((caught) => {
      if (signal?.aborted || request !== latest.current) return;
      setLoadError(
        caught instanceof Error ? caught.message : "Unable to load contacts",
      );
    }).finally(() => {
      // An obsolete search must not clear the next search's loading state.
      // All request errors are handled above, including aborted requests.
      if (signal?.aborted || request !== latest.current) return;
      setLoading(false);
    });
  }, [query, offset, stage]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, workspaceRevision]);
  // Refresh while a work-email lookup runs so results appear without navigation.
  // Poll while any lookup is pending, plus a short grace period right after starting
  // one (the server may not mark rows pending yet). Never poll indefinitely.
  const [lookupStartedAt, setLookupStartedAt] = useState(0);
  const pending = items.some((item) => item.email_status === "pending");
  const [graceOver, setGraceOver] = useState(true);
  useEffect(() => {
    if (!lookupStartedAt) return;
    setGraceOver(false);
    const timer = window.setTimeout(() => setGraceOver(true), 20000);
    return () => window.clearTimeout(timer);
  }, [lookupStartedAt]);
  const lookingUp = pending || !graceOver;
  useEffect(() => {
    if (!lookingUp) return;
    let inFlight = false;
    const timer = window.setInterval(() => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      void load(undefined, true).finally(() => { inFlight = false; });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [lookingUp, load]);
  async function mutate(
    path: string,
    method: string,
    body: object,
    message: string,
  ) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setNotice(message);
      setShowForm(false);
      setEditing(null);
      setDeleting(null);
      setCsv("");
      // Removing the last row on a later page returns to the preceding page.
      if (method === "DELETE" && items.length === 1 && offset > 0)
        setOffset(Math.max(0, offset - 50));
      else await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to save contacts",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    await mutate(
      editing ? `contacts/${editing.id}` : "contacts",
      editing ? "PUT" : "POST",
      {
        ...Object.fromEntries(fields),
        opted_in: fields.get("opted_in") === "on",
      },
      "Contact saved.",
    );
  }
  async function importCsv() {
    let contacts: Record<string, unknown>[];
    try { contacts = csvRows(csv); } catch (caught) { setError(caught instanceof Error ? caught.message : "Invalid CSV"); return; }
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError(""); setNotice(""); setReport(null);
    try {
      // Each row is handled on its own; the server reports every skipped or failed row.
      const result = await api<ImportReport>("contacts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ contacts }) });
      setReport(result); setNotice(`Import done: ${result.summary ?? ""}`);
      if (result.ids?.length) { setCsv(""); await load(); }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to import contacts");
    } finally { submitting.current = false; setBusy(false); }
  }
  return (
    <div className="shell">
      <Sidebar user={user} active="contacts" />
      <main className="main">
        <div className="topbar">
          <PageHeading title="Leads" help="People to contact. Find their email, then reach out." />
          <div className="top-actions"><Link className="button primary" href="/find-leads">Find leads</Link><button className="button" aria-expanded={importOpen} aria-controls={importOpen ? "lead-import" : undefined} onClick={() => setImportOpen(!importOpen)}>Import</button>
          <button
            type="button"
            className="button"
            data-tour={showForm ? "contact-close" : "contact-add"}
            aria-expanded={showForm}
            aria-controls={showForm ? "contact-form" : undefined}
            disabled={busy}
            onClick={() => {
              setEditing(null);
              setShowForm(!showForm);
            }}
          >
            <Icon name={showForm ? "close" : "plus"} />
            {showForm ? "Close form" : "Add contact"}
          </button></div>
        </div>
        {summary && <p className="lead-summary" aria-label="Lead counts"><strong>{summary.all}</strong> lead{summary.all === 1 ? "" : "s"} · <strong>{summary.email_found}</strong> with email · <strong>{summary.needs_email}</strong> need email · <strong>{summary.contacted}</strong> contacted · <strong>{summary.replied}</strong> replied</p>}
        {(error || loadError) && (
          <div className="error" role="alert">
            {error || loadError}
          </div>
        )}
        {notice && (
          <div className="success" role="status">
            {notice}
          </div>
        )}
        {showForm && (
          <section className="panel settings-card" id="contact-form" data-tour="contact-form">
            <div className="panel-head">
              <h2 className="panel-title">
                {editing ? "Edit contact" : "Add contact"}
              </h2>
            </div>
            <form key={editing?.id ?? "new"} onSubmit={save}>
              <div className="form-grid">
                {(
                  [
                    ["email", "Email"],
                    ["first_name", "First name"],
                    ["last_name", "Last name"],
                    ["company", "Company"],
                    ["title", "Job title"],
                    ["website", "Website"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      className="input"
                      data-tour={key === "email" ? "contact-email" : undefined}
                      name={key}
                      defaultValue={editing?.[key] ?? ""}
                      type={key === "email" ? "email" : "text"}
                      readOnly={key === "email" && Boolean(editing)}
                      required={key === "email" && !editing}
                      maxLength={key === "website" ? 500 : key === "email" ? 150 : key === "first_name" || key === "last_name" ? 100 : 200}
                    />
                  </label>
                ))}
                <label className="wide">
                  Profile notes
                  <textarea
                    className="input textarea"
                    name="profile_text"
                    rows={3}
                    defaultValue={editing?.profile_text ?? ""}
                    maxLength={10000}
                  />
                </label>
                <label className="wide">
                  Opt-in note
                  <input
                    className="input"
                    name="consent_note"
                    defaultValue={editing?.consent_note ?? ""}
                    maxLength={500}
                    placeholder="When and how they opted in"
                  />
                </label>
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  name="opted_in"
                  defaultChecked={editing?.opted_in ?? false}
                />
                They opted in to our emails.
              </label>
              <div className="card-actions">
                <button
                  type="submit"
                  className="button primary"
                  disabled={busy}
                >
                  Save contact
                </button>
                <button
                  className="button"
                  type="button"
                  disabled={busy}
                  onClick={() => setShowForm(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </section>
        )}
        {importOpen && <details id="lead-import" className="panel import-panel" open={importOpen} onToggle={(event) => setImportOpen(event.currentTarget.open)}>
          <summary>Import CSV</summary>
          <p className="settings-help">
            Up to 100 rows. Columns: email (required), first_name, last_name,
            company, title, opted_in (true/false), consent_note.
          </p>
          <p className="settings-help">
            Bad rows and repeats are skipped. Deleted contacts come back. Do
            Not Contact emails stay blocked.
          </p>
          <textarea
            className="input textarea"
            rows={5}
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            aria-label="CSV contacts"
            maxLength={60000}
            placeholder="email,first_name,company\nada@example.com,Ada,Example"
          />
          <div className="card-actions">
            <button
              type="button"
              className="button"
              disabled={busy || !csv.trim()}
              onClick={() => void importCsv()}
            >
              Import contacts
            </button>
          </div>
          {report && [...(report.failed ?? []), ...(report.duplicates ?? []), ...(report.skipped ?? [])].length > 0 && (
            <div className="import-report" aria-label="Rows not imported">
              <strong>Rows not imported</strong>
              <ul>{[...report.failed.map((r) => ({ ...r, kind: "Failed" })), ...report.duplicates.map((r) => ({ ...r, kind: "Repeated" })), ...report.skipped.map((r) => ({ ...r, kind: "Skipped" }))]
                .sort((a, b) => a.row - b.row)
                .map((r) => <li key={`${r.kind}-${r.row}`}>Row {r.row}{r.email ? ` · ${r.email}` : ""}: {r.kind}. {r.reason}</li>)}</ul>
            </div>
          )}
        </details>}
        {lookupRun && <div className="success" role="status">{pending || !graceOver ? "Finding emails. Results show here." : "Email lookup finished."} <Link className="text-link" href={`/find-leads/${lookupRun}`}>View progress</Link> <button className="button ghost" onClick={() => setLookupRun("")}>Dismiss</button></div>}
        {selected.length > 0 && <div className="selection-toolbar"><strong>{selected.length} selected</strong>
          {needEmail.length > 0 && <button className="button" disabled={busy || bulkLookup} onClick={() => setBulkLookup(true)}>Find emails ({needEmail.length})</button>}
          <button className="button primary" disabled={busy || !ready.length} title={ready.length ? undefined : "Find emails first"} onClick={() => void prepareOutreach()}>Prepare outreach{ready.length && ready.length !== selected.length ? ` (${ready.length})` : ""}</button>
          <AskLeadZen actorId={user.id} context={{ selectedLeadIds: selected, workspacePath: "/contacts" }} /><button className="button ghost" onClick={() => { setPicked(new Map()); setBulkLookup(false); }}>Clear</button>
          {!ready.length && <span className="settings-help">Find emails first to reach out.</span>}
        </div>}
        {bulkLookup && needEmail.length > 0 && <BulkEmailConfirmation key={needEmail.map((item) => item.id).join(",")} contactIds={needEmail.map((item) => item.id)} close={() => setBulkLookup(false)} started={(runId) => { setBulkLookup(false); setPicked((current) => new Map([...current].filter(([, item]) => !!item.email))); setLookupRun(runId); setLookupStartedAt(Date.now()); void load(); }} />}
        <section className="panel">
          <div className="filters">
            <div className="search-field">
              <Icon name="search" />
              <input
                className="input"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setOffset(0);
                }}
                aria-label="Search leads"
                placeholder="Search name, company or email"
                maxLength={200}
              />
            </div>
          </div>
          <div className="lead-filter-list" role="group" aria-label="Filter leads">
            {leadFilters.map(([key, label]) => <button key={key} type="button" className={`button ${stage === key ? "selected" : "ghost"}`} aria-pressed={stage === key} onClick={() => { setStage(key); setOffset(0); }}>
              {label}
            </button>)}
          </div>
          <div
            className="table-wrap"
            role="region"
            aria-label="Leads table"
            aria-busy={loading}
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th><input type="checkbox" aria-label="Select leads on this page" title="Select up to 25 leads" checked={!!items.length && items.some((item) => selectedIds.has(item.id))} disabled={loading || !items.length} onChange={() => {
                    const anyOnPage = items.some((item) => selectedIds.has(item.id));
                    const next = new Map(picked);
                    if (anyOnPage) items.forEach((item) => next.delete(item.id));
                    else for (const item of items) if (next.size < 25) next.set(item.id, item);
                    if (!anyOnPage && items.length + picked.size > 25) setNotice("Selected 25 leads. That is the most for one action.");
                    setPicked(next);
                  }} /></th><th>Lead</th>
                  <th>Company</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {!loading && items.map((item) => (
                  <tr key={item.id}><td><input type="checkbox" aria-label={`Select ${item.name || item.email}`} checked={selectedIds.has(item.id)} disabled={!selectedIds.has(item.id) && selected.length >= 25} onChange={(e) => toggle(item, e.target.checked)} /></td>
                    <td>
                      <div className="person-cell">
                        <Avatar
                          name={item.name}
                        />
                        <div>
                          <div className="person">
                            <Link className="text-link" href={`/contacts/${item.id}`}>{item.name}</Link>
                          </div>
                          <div className="subtext">{item.title || "No title"}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      {item.company}
                      <LeadLinks linkedin={item.linkedin_url} website={item.website} />
                    </td>
                    <td>
                      <span
                        className={`badge crm-${item.crm_status}`}
                      >
                        {leadStatus(item.crm_status)}
                      </span>
                      <div className="subtext">
                        {emailLabel(item)}
                      </div>
                      {item.opted_in && <div className="subtext">Opted in</div>}
                      {item.state === "Completed" && <div className="subtext">Outreach stopped</div>}
                      {canLookUp(item) && lookupFor !== item.id && <button type="button" className="button small" disabled={busy} aria-expanded={false} onClick={() => setLookupFor(item.id)}>Find email</button>}
                      {lookupFor === item.id && <EmailConfirmation contactId={item.id} close={() => setLookupFor(null)} started={async () => { setLookupFor(null); setLookupStartedAt(Date.now()); await load(); }} />}
                    </td>
                    <td>
                      <div className="row-actions">
                        <Link className="button ghost" href={`/contacts/${item.id}`} aria-label={`View ${item.name}`}>View</Link>
                        <button
                          type="button"
                          className="button ghost"
                          disabled={busy}
                          onClick={() => {
                            setEditing(item);
                            setShowForm(true);
                          }}
                        >
                          Edit
                        </button>
                        {(item.state === "Ready to Email" ||
                          item.state === "Emailed") && (
                          <button
                            type="button"
                            className="button ghost"
                            disabled={busy}
                            onClick={() =>
                              void mutate(
                                `contacts/${item.id}`,
                                "PUT",
                                { stop: true },
                                "Outreach stopped. History kept.",
                              )
                            }
                          >
                            Stop
                          </button>
                        )}
                        <button
                          type="button"
                          className="button ghost danger-button"
                          disabled={busy || !item.email}
                          onClick={() => {
                            if (
                              window.confirm(
                                `Opt out ${item.email}? All future emails will be blocked.`,
                              )
                            )
                              void mutate(
                                `contacts/${item.id}`,
                                "PUT",
                                { suppress: true },
                                "Opted out. Future emails are blocked.",
                              );
                          }}
                        >
                          Opt out
                        </button>
                        <button
                          type="button"
                          className="button ghost danger-button"
                          disabled={busy}
                          aria-label={`Delete ${item.name}`}
                          title="Delete"
                          aria-expanded={deleting === item.id}
                          aria-controls={
                            deleting === item.id
                              ? `delete-contact-${item.id}`
                              : undefined
                          }
                          onClick={() =>
                            setDeleting(deleting === item.id ? null : item.id)
                          }
                        >
                          <Icon name="trash" />
                        </button>
                      </div>
                      {deleting === item.id && (
                        <div
                          className="contact-delete-confirm"
                          id={`delete-contact-${item.id}`}
                          role="group"
                          aria-label={`Confirm deletion of ${item.name}`}
                        >
                          <p>
                            Delete {item.name}? Queued emails stop. History
                            and opt-outs are kept.
                          </p>
                          <div className="row-actions">
                            <button
                              type="button"
                              className="button danger-button"
                              disabled={busy}
                              onClick={() =>
                                void mutate(
                                  `contacts/${item.id}`,
                                  "DELETE",
                                  {},
                                  "Contact deleted. Queued emails stopped.",
                                )
                              }
                            >
                              {busy ? "Deleting…" : "Delete contact"}
                            </button>
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              onClick={() => setDeleting(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading && <div className="empty" role="status">Loading leads…</div>}
            {!loading && !items.length && (
              <div className="empty">
                {query || stage !== "all" ? "No leads match. Try All or another search." : <>No leads yet. <Link className="text-link" href="/find-leads">Find leads</Link>, add one, or import a CSV.</>}
              </div>
            )}
          </div>
          <div className="card-actions">
            <button
              type="button"
              className="button"
              disabled={offset === 0}
              onClick={() => setOffset(offset - 50)}
            >
              Previous
            </button>
            <span className="panel-meta">
              {total ? offset + 1 : 0}–{Math.min(offset + 50, total)} of {total}
            </span>
            <button
              type="button"
              className="button"
              disabled={offset + 50 >= total}
              onClick={() => setOffset(offset + 50)}
            >
              Next
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
