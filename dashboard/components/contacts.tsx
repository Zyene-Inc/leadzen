"use client";
import { AskLeadZen } from "@/components/ask-leadzen";
import { useRouter } from "next/navigation";
import { recordWorkspaceContext, flushWorkspaceContext, useWorkspaceContext } from "@/lib/workspace-context";
import { PageHeading } from "@/components/page-heading";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Sidebar } from "@/components/sidebar";
import { Avatar } from "@/components/avatar";
import { Icon } from "@/components/icon";
import type { Account } from "@/lib/auth";
import { useWorkspaceRevision } from "@/lib/workspace-updates";
import { api } from "@/lib/client-api";
import { emailLabel, leadFilters, leadStatus, type Contact } from "@/lib/leads";
import { LeadLinks } from "@/components/lead-links";

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
      "Use unique column headers, an email column, and 1–100 contacts",
    );
  return rows.map((values) => {
    if (values.length !== headers.length)
      throw new Error("CSV column counts do not match");
    const result = Object.fromEntries(
      headers.map((key, i) => [key, values[i]]),
    );
    return { ...result, opted_in: result.opted_in?.toLowerCase() === "true" };
  });
}

export default function Contacts({ user }: { user: Account }) {
  const router = useRouter();
  const [selected, setSelected] = useState<number[]>([]);
  const selectedIds = new Set(selected);
  const [importOpen, setImportOpen] = useState(false);
  useWorkspaceContext({ selectedLeadIds: selected, currentLeadId: null, currentDraftId: null, currentThreadId: null, currentCampaignId: null, workspacePath: "/contacts" }, user.id);
  async function prepareOutreach() {
    setBusy(true); setError("");
    try {
      await recordWorkspaceContext({ selectedLeadIds: selected, currentLeadId: null, currentDraftId: null, currentThreadId: null, currentCampaignId: null, workspacePath: "/outreach" }, user.id);
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
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    return api<{ items: Contact[]; total: number }>(
        `leads?limit=50&offset=${offset}&q=${encodeURIComponent(query)}&stage=${stage}`,
        { signal },
      ).then((value) => {
      if (signal?.aborted) return;
      setItems(value.items);
      setTotal(value.total);
      setLoadError("");
    }).catch((caught) => {
      if (signal?.aborted) return;
      setLoadError(
        caught instanceof Error ? caught.message : "Unable to load contacts",
      );
    }).finally(() => {
      // An obsolete search must not clear the next search's loading state.
      // All request errors are handled above, including aborted requests.
      if (signal?.aborted) return;
      setLoading(false);
    });
  }, [query, offset, stage]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, workspaceRevision]);
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
  function importCsv() {
    try {
      void mutate(
        "contacts",
        "POST",
        { contacts: csvRows(csv) },
        "Contacts imported.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid CSV");
    }
  }
  return (
    <div className="shell">
      <Sidebar user={user} active="contacts" />
      <main className="main">
        <div className="topbar">
          <PageHeading title="Leads" help="Review qualified people, find work emails when needed, and track conversations." />
          <div className="top-actions"><Link className="button primary" href="/find-leads">Find leads</Link><button className="button" aria-expanded={importOpen} aria-controls="lead-import" onClick={() => setImportOpen(!importOpen)}>Import</button>
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
                  Opt-in record
                  <input
                    className="input"
                    name="consent_note"
                    defaultValue={editing?.consent_note ?? ""}
                    maxLength={500}
                    placeholder="When and how they asked to receive emails"
                  />
                </label>
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  name="opted_in"
                  defaultChecked={editing?.opted_in ?? false}
                />
                This person explicitly opted in to receive our emails.
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
        <details id="lead-import" className="panel import-panel" open={importOpen} onToggle={(event) => setImportOpen(event.currentTarget.open)}>
          <summary>Import CSV</summary>
          <p className="settings-help">
            Columns: email, first_name, last_name, company, title, opted_in
            (true/false), consent_note. Up to 100 contacts per import; duplicate
            emails are rejected.
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
              onClick={importCsv}
            >
              Import contacts
            </button>
          </div>
        </details>
        {selected.length > 0 && <div className="selection-toolbar"><strong>{selected.length} selected</strong><button className="button primary" disabled={busy} onClick={() => void prepareOutreach()}>Prepare outreach</button><AskLeadZen actorId={user.id} context={{ selectedLeadIds: selected, workspacePath: "/contacts" }} /><button className="button ghost" onClick={() => setSelected([])}>Clear</button></div>}
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
                placeholder="Search name, company, title or email"
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
                  <th><span className="sr-only">Select lead</span></th><th>Lead</th>
                  <th>Company</th>
                  <th>Status / email</th>
                  <th>Manage</th>
                </tr>
              </thead>
              <tbody>
                {!loading && items.map((item) => (
                  <tr key={item.id}><td><input type="checkbox" aria-label={`Select ${item.name || item.email}`} checked={selectedIds.has(item.id)} disabled={!selectedIds.has(item.id) && (selected.length >= 25 || !item.email || item.state !== "Ready to Email")} onChange={(e) => setSelected(e.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id))} /></td>
                    <td>
                      <div className="person-cell">
                        <Avatar
                          name={item.name}
                        />
                        <div>
                          <div className="person">
                            <Link className="text-link" href={`/contacts/${item.id}`}>{item.name}</Link>
                          </div>
                          <div className="subtext">{item.title || "Title not recorded"}</div>
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
                      <div className="subtext">
                        {item.opted_in
                          ? "Opt-in recorded"
                          : "No opt-in recorded"}
                      </div>
                      {item.state === "Completed" && <div className="subtext">Outreach stopped</div>}
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
                        <button
                          type="button"
                          className="button ghost"
                          disabled={busy || item.state === "Completed"}
                          onClick={() =>
                            void mutate(
                              `contacts/${item.id}`,
                              "PUT",
                              { stop: true },
                              "Outreach stopped; history retained.",
                            )
                          }
                        >
                          Stop
                        </button>
                        <button
                          type="button"
                          className="button ghost danger-button"
                          disabled={busy || !item.email}
                          onClick={() => {
                            if (
                              window.confirm(
                                `Record an opt-out for ${item.email} and block future emails?`,
                              )
                            )
                              void mutate(
                                `contacts/${item.id}`,
                                "PUT",
                                { suppress: true },
                                "Contact suppressed. Future emails are blocked.",
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
                          Delete
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
                            Remove {item.name} from Leads and stop queued
                            outreach? Email history and opt-out records are
                            kept.
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
                                  "Contact deleted from Contacts. Queued outreach stopped; history and opt-outs retained.",
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
                {query || stage !== "all" ? "No leads match this search and filter. Try All or a different search." : <>No leads yet. <Link className="text-link" href="/find-leads">Find leads</Link>, add a contact, or import a CSV to begin.</>}
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
