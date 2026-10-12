"use client";
import { formatNewYorkDateTime } from "@/lib/date-time";
import { PageHeading } from "@/components/page-heading";

import { useRef, useState, type ReactNode } from "react";
import { Sidebar } from "@/components/sidebar";
import { Icon } from "@/components/icon";
import type { Account } from "@/lib/auth";
import { useStoredData } from "@/lib/use-stored-data";
import { SuppressionForm } from "@/components/suppression-form";
import { InboxCheck } from "@/components/inbox-check";
import { api } from "@/lib/client-api";

type PageData<T> = { items: T[]; total: number; limit: number; offset: number };
type InboxMessage = {
  id: number;
  from: string;
  subject: string;
  kind: string;
  sent_at: string | null;
  body: string;
  body_truncated: boolean;
};
type Suppressed = {
  id: number;
  email: string;
  reason: string;
  suppressed_at: string;
  removable?: boolean;
};
const classifications: Record<string, string> = {
  human_reply: "Human reply",
  auto_reply: "Auto-reply",
  bounce: "Bounce",
  opt_out: "Opt-out",
  unrelated: "Unrelated",
  "": "Unclassified",
};

const dateLabel = (at: string | null) =>
  at ? formatNewYorkDateTime(at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "No timestamp";

export function WorkspacePage({
  user,
  active,
  title,
  description,
  actions,
  children,
}: {
  user: Account;
  active: string;
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="shell">
      <Sidebar user={user} active={active} />
      <main className="main">
        <header className="topbar">
          <PageHeading title={title} help={description} />
          <div className="top-actions">{actions}</div>
        </header>
        {children}
      </main>
    </div>
  );
}

function Refresh({
  loading,
  onClick,
}: {
  loading: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="button"
      type="button"
      disabled={loading}
      onClick={onClick}
    >
      <Icon name="refresh" />
      Refresh
    </button>
  );
}

function Pagination({
  data,
  onPage,
}: {
  data: { total: number; offset: number; limit: number };
  onPage: (offset: number) => void;
}) {
  return (
    <div className="records-pagination">
      <span className="muted">
        {data.total
          ? `${data.offset + 1}–${Math.min(data.offset + data.limit, data.total)} of ${data.total}`
          : "0 results"}
      </span>
      <div className="top-actions">
        <button
          className="button"
          type="button"
          disabled={data.offset === 0}
          onClick={() => onPage(Math.max(0, data.offset - data.limit))}
        >
          Previous
        </button>
        <button
          className="button"
          type="button"
          disabled={data.offset + data.limit >= data.total}
          onClick={() => onPage(data.offset + data.limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function Inbox({ user }: { user: Account }) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [offset, setOffset] = useState(0);
  const { data, loading, error: savedError, refresh } = useStoredData<
    PageData<InboxMessage>
  >(
    `inbox?q=${encodeURIComponent(query)}&kind=${encodeURIComponent(kind)}&offset=${offset}`,
  );
  const error = loading ? "" : savedError;
  return (
    <WorkspacePage
      user={user}
      active="inbox"
      title="Inbox"
      description="Read stored inbound messages, including human replies, bounces and opt-outs. Refresh reloads saved messages; checking your mailbox for new replies is a separate approved action."
      actions={
        <>
          <Refresh loading={loading} onClick={refresh} />
        </>
      }
    >
      <InboxCheck refreshed={refresh} />
      <section className="panel">
        <div className="filters">
          <div className="search-field">
            <Icon name="search" />
            <input
              className="input"
              aria-label="Search inbox"
              placeholder="Search sender, subject or message"
              maxLength={200}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOffset(0);
              }}
            />
          </div>
          <select
            className="select"
            aria-label="Filter inbox"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setOffset(0);
            }}
          >
            <option value="all">All messages</option>
            {Object.entries(classifications).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {error ? (
          <p className="error records-notice" role="alert">
            {error} Use Refresh to retry.
          </p>
        ) : loading ? (
          <p className="empty" role="status">
            Loading inbox…
          </p>
        ) : (
          data && (
            <>
              <div className="inbox-list">
                {data.items.map((message) => (
                  <details key={message.id} className="inbox-message">
                    <summary>
                      <div className="inbox-message-heading">
                        <strong>{message.from || "Unknown sender"}</strong>
                        <span className="badge">
                          {classifications[message.kind] || "Unclassified"}
                        </span>
                        <time dateTime={message.sent_at || undefined}>
                          {dateLabel(message.sent_at)}
                        </time>
                      </div>
                      <div className="inbox-subject">
                        {message.subject || "No subject"}
                      </div>
                    </summary>
                    <div className="inbox-body">
                      {message.body ||
                        "No plain-text content was stored for this message."}
                    </div>
                    {message.body_truncated && (
                      <p className="settings-help records-notice">
                        Showing the first 12,000 characters. Read the full
                        message in your mailbox.
                      </p>
                    )}
                  </details>
                ))}
                {!data.items.length && (
                  <div className="empty">
                    {query || kind !== "all"
                      ? "No messages match this view."
                      : "No messages saved yet. Use Check for replies above after connecting your reply inbox in Settings."}
                  </div>
                )}
              </div>
              <Pagination data={data} onPage={setOffset} />
            </>
          )
        )}
      </section>
    </WorkspacePage>
  );
}

export function Suppression({ user }: { user: Account }) {
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");
  const [removing, setRemoving] = useState<number | null>(null);
  const [removeError, setRemoveError] = useState("");
  const [busy, setBusy] = useState(false);
  const addButton = useRef<HTMLButtonElement>(null);
  async function removeBlock(row: Suppressed) {
    if (busy) return;
    setBusy(true); setRemoveError(""); setNotice("");
    try {
      // The server re-checks: opt-outs, unsubscribes and bounces can never be removed.
      const result = await api<{ note: string }>(`suppression/${row.id}`, { method: "DELETE" });
      setRemoving(null); setNotice(`${row.email}: ${result.note}`); refresh();
    } catch (caught) { setRemoveError(caught instanceof Error ? caught.message : "Could not remove this block"); }
    finally { setBusy(false); }
  }
  const { data, loading, error: savedError, refresh } = useStoredData<PageData<Suppressed>>(
    `suppression?q=${encodeURIComponent(query)}&offset=${offset}`,
  );
  const error = loading ? "" : savedError;
  return (
    <WorkspacePage
      user={user}
      active="suppression"
      title="Do Not Contact"
      description="Addresses blocked from outreach in your workspace. Opt-outs remain protected even if a contact is deleted or imported again."
      actions={<><button ref={addButton} className="button primary" onClick={() => setAdding(true)} aria-expanded={adding}>Add to suppression list</button><Refresh loading={loading} onClick={refresh} /></>}
    >
      {adding && <SuppressionForm cancel={() => { setAdding(false); addButton.current?.focus(); }} saved={(created) => { setAdding(false); setQuery(""); setOffset(0); refresh(); setNotice(created ? "Address added. Future emails are blocked." : "Already on the list. The original reason and date are retained."); addButton.current?.focus(); }} />}
      {notice && <p className="success records-notice" role="status">{notice}</p>}
      <section className="panel">
        <div className="filters">
          <div className="search-field">
            <Icon name="search" />
            <input
              className="input"
              aria-label="Search suppression"
              placeholder="Search email…"
              maxLength={200}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOffset(0);
              }}
            />
          </div>
        </div>
        {error ? (
          <p className="error records-notice" role="alert">
            {error} Use Refresh to retry.
          </p>
        ) : loading ? (
          <p className="empty" role="status">
            Loading suppression list…
          </p>
        ) : (
          data && (
            <>
              <div
                role="region"
                aria-label="Suppressed addresses"
              >
                <ul className="suppression-list">
                    {data.items.map((row) => (
                      <li key={row.id}>
                        <p className="suppression-address">{row.email}</p>
                        <dl>
                          <div><dt>Reason</dt><dd>{row.reason || "No reason recorded"}</dd></div>
                          <div><dt>Date</dt><dd><time dateTime={row.suppressed_at}>{dateLabel(row.suppressed_at)}</time></dd></div>
                        </dl>
                        {row.removable ? (removing === row.id
                          ? <div className="card-actions" role="group" aria-label={`Remove block for ${row.email}`}>
                              <span>Allow future outreach to {row.email}? Stopped sequences stay stopped.</span>
                              <button className="button" disabled={busy} onClick={() => { setRemoving(null); setRemoveError(""); }}>Cancel</button>
                              <button className="button primary" disabled={busy} onClick={() => void removeBlock(row)}>{busy ? "Removing…" : "Confirm remove"}</button>
                            </div>
                          : <button className="button ghost" onClick={() => { setRemoving(row.id); setRemoveError(""); }}>Remove block</button>)
                          : <p className="settings-help">Opt-out protected: cannot be removed.</p>}
                        {removing === row.id && removeError && <p className="error" role="alert">{removeError}</p>}
                      </li>
                    ))}
                </ul>
                {!data.items.length && (
                  <div className="empty">
                    {query
                      ? "No suppressed addresses match this search."
                      : "No suppressed addresses yet. Future opt-outs will appear here."}
                  </div>
                )}
              </div>
              <Pagination data={data} onPage={setOffset} />
            </>
          )
        )}
      </section>
    </WorkspacePage>
  );
}
