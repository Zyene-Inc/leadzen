"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/icon";
import type { ChatThread } from "@/lib/chat";
import { formatNewYorkDateTime, newYorkDayKey } from "@/lib/date-time";

export function ChatHistory({
  items,
  selected,
  onDelete,
}: {
  items: ChatThread[];
  selected?: string;
  onDelete?: (id: string) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [deleting, setDeleting] = useState<ChatThread | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const submitting = useRef(false);
  useEffect(() => {
    if (deleting) dialog.current?.showModal();
    else if (dialog.current?.open) dialog.current.close();
  }, [deleting]);
  function close() {
    if (submitting.current) return;
    setDeleting(null); setError(""); opener.current?.focus();
  }
  async function remove() {
    if (!deleting || !onDelete || submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      await onDelete(deleting.id);
      setDeleting(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not delete this chat. Please retry."); }
    finally { submitting.current = false; setBusy(false); }
  }
  const groups = useMemo(() => {
    const today = Date.parse(newYorkDayKey(new Date()));
    return ["Last 7 days", "Last 30 days", "Older"].map((label, index) => ({
      label,
      items: items.filter((item) => {
        const days = Math.max(
          0,
          (today - Date.parse(newYorkDayKey(item.updated_at))) / 86400000,
        );
        return (
          (index === 0
            ? days < 7
            : index === 1
              ? days >= 7 && days < 30
              : days >= 30) &&
          item.title.toLowerCase().includes(query.toLowerCase())
        );
      }).map((item) => ({ ...item, dateLabel: formatNewYorkDateTime(item.updated_at, { month: "short", day: "numeric" }) })),
    }));
  }, [items, query]);
  return (
    <nav className="chat-history" aria-label="Chat conversations">
      <div className="chat-history-controls">
        <label className="chat-filter">
          <Icon name="search" />
          <input
            aria-label="Filter chats"
            placeholder="Filter chats"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <Link
          href="/chat"
          className="button ghost"
          aria-label="New chat"
          title="New chat"
        >
          <Icon name="plus" />
        </Link>
      </div>
      {groups.map(
        (group) =>
          group.items.length > 0 && (
            <section key={group.label} className="chat-history-group">
              <h2>{group.label}</h2>
              {group.items.map((item) => (
                <div className={`chat-history-row${item.id === selected ? " selected" : ""}`} key={item.id}>
                <Link
                  className={`chat-history-item${item.id === selected ? " selected" : ""}`}
                  key={item.id}
                  href={`/chat/${item.id}`}
                  aria-current={selected === item.id ? "page" : undefined}
                >
                  <span>{item.title}</span>
                  <time dateTime={item.updated_at}>
                    {item.dateLabel}
                  </time>
                </Link>
                {onDelete && <button type="button" className="button ghost chat-history-delete" aria-label={`Delete chat: ${item.title}`} title="Delete chat" onClick={(event) => { opener.current = event.currentTarget; setError(""); setDeleting(item); }}><Icon name="trash" /></button>}
                </div>
              ))}
            </section>
          ),
      )}
      {!items.length && (
        <p className="history-empty">Your conversations will appear here.</p>
      )}
      {!!items.length && !groups.some((g) => g.items.length) && (
        <p className="history-empty">No matching conversations.</p>
      )}
      <dialog ref={dialog} className="zy-modal chat-delete-dialog" aria-labelledby="delete-chat-title" aria-describedby="delete-chat-description" onCancel={(event) => { event.preventDefault(); close(); }}>
        <div className="zy-modal-box">
          <h2 id="delete-chat-title">Delete chat?</h2>
          <p className="chat-delete-name">{deleting?.title}</p>
          <p id="delete-chat-description">This conversation will be removed from your history. Leads, drafts, campaigns, and outreach records stay in Workspace.</p>
          {error && <p role="alert" className="error">{error}</p>}
          <form method="dialog" className="zy-modal-action" onSubmit={(event) => { event.preventDefault(); close(); }}>
            <button className="button" type="submit" disabled={busy} autoFocus>Cancel</button>
            <button className="button danger-button" type="button" disabled={busy} onClick={() => void remove()}>{busy ? "Deleting…" : "Delete chat"}</button>
          </form>
        </div>
      </dialog>
    </nav>
  );
}
