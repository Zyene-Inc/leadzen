"use client";
import { InboxCheck } from "@/components/inbox-check";
import { AskLeadZen } from "@/components/ask-leadzen";
import { PageHeading } from "@/components/page-heading";
import { recordWorkspaceContext, useWorkspaceContext } from "@/lib/workspace-context";
import Link from "next/link";
import { useRef, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { Icon } from "@/components/icon";
import { Avatar } from "@/components/avatar";
import OutreachReview from "@/components/outreach-review";
import { api } from "@/lib/client-api";
import { useStoredData } from "@/lib/use-stored-data";
import { sentTime, type EmailReview } from "@/lib/outreach";
import { formatNewYorkDateTime } from "@/lib/date-time";
import type { Account } from "@/lib/auth";
import { replyLabels, replyLabelDetail, type ReplyLabelName } from "@/lib/reply-labels";
import { plural } from "@/lib/format";

function LabelChip({ value }: { value: ReplyLabel | undefined }) {
  if (!value) return null;
  const detail = replyLabelDetail(value.label, value.return_date, value.action);
  return <span className={`reply-label reply-label-${value.label}`} title={detail || undefined}>{replyLabels[value.label]}{detail && <span className="sr-only">. {detail}</span>}</span>;
}

type ReplyLabel = { label: ReplyLabelName; return_date: string | null; action: "" | "blocked" | "held" } | null;
type ConversationRow = { id: number; name: string; address: string; subject: string; snippet: string; kind: string; last_at: string; count: number; reply_label?: ReplyLabel };
type InboxPage = { items: ConversationRow[]; total: number; limit: number; offset: number };
type ConversationDetail = { id: number; name: string; address: string; can_reply: boolean; reply_blocker: string; total_messages: number; messages: { id: number; direction: string; from: string; to: string; subject: string; body: string; body_truncated: boolean; sent_at: string | null; kind: string; accepted: boolean; reply_label?: ReplyLabel }[] };

function messageAuthor(direction: string, from: string, contact: ConversationDetail) {
  if (direction === "out") return "You";
  if (from && from.toLowerCase() === contact.address.toLowerCase()) return contact.name || from;
  return from || "Unknown sender";
}

// Short list date ("Nov 15"), like a mail client; the thread shows the full time.
const listDate = (value: string | null) => value ? formatNewYorkDateTime(value, { month: "short", day: "numeric" }) : "";
const preview = (body: string) => body.replace(/\s+/g, " ").trim() || "No text saved";

// Earlier messages fold to one line, like a mail client; the latest starts open.
function ThreadMessage({ defaultOpen, author, avatarName, message: m, detail }: { defaultOpen: boolean; author: string; avatarName: string; message: ConversationDetail["messages"][number]; detail: string }) {
  const [open, setOpen] = useState(defaultOpen);
  return <details className="thread-message" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>
      <Avatar name={avatarName} />
      <span className="thread-message-main">
        <span className="thread-message-head"><strong>{author}</strong>{m.from && m.from !== author && <span className="thread-address">{m.from}</span>}<time>{sentTime(m.sent_at)}</time><LabelChip value={m.reply_label} /></span>
        {!open && <span className="thread-preview">{preview(m.body)}</span>}
      </span>
    </summary>
    <div className="thread-message-body">
      <p className="thread-meta">{m.subject || "No subject"} · {m.direction === "out" ? m.accepted ? "Sent" : "Send not confirmed" : m.kind.replaceAll("_", " ") || "Unclassified"}</p>
      {detail && <p className="thread-meta">{detail}</p>}
      <pre className="email-copy">{m.body || "No text saved"}</pre>
      {m.body_truncated && <p className="thread-meta">Cut to the first 12,000 characters.</p>}
    </div>
  </details>;
}

function Conversation({ threadId, close, initialReviewId, actorId, actorName }: { threadId: number; close: () => void; initialReviewId: string | null; actorId: number; actorName: string }) {
  const { data, error, loading, refresh } = useStoredData<ConversationDetail>(`inbox/conversations/${threadId}`, 5000);
  useWorkspaceContext({ currentThreadId: data && !error ? data.id : null, currentDraftId: null, selectedLeadIds: [], currentLeadId: null, workspacePath: data && !error ? `/inbox?thread=${data.id}` : "/inbox" }, actorId);
  const [reviewId, setReviewId] = useState<string | null>(initialReviewId);
  const [actionError, setActionError] = useState("");
  const [busy, setBusyKind] = useState<"" | "manual" | "ai">("");
  const requestIds = useRef({ manual: "", ai: "" });
  const submitting = useRef(false);
  // "manual" opens an empty draft you type yourself (no AI); "ai" asks LeadZen to suggest one.
  // Both go through the same edit and approve steps before anything sends.
  async function start(kind: "manual" | "ai") {
    if (submitting.current || !data?.can_reply) return;
    submitting.current = true; setBusyKind(kind); setActionError("");
    requestIds.current[kind] ||= crypto.randomUUID();
    try {
      const review = await api<EmailReview>("outreach/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ thread_id: threadId, count: 1, request_id: requestIds.current[kind], ...(kind === "manual" ? { manual: true } : {}) }) });
      setReviewId(review.id);
    } catch (caught) { setActionError(caught instanceof Error ? caught.message : kind === "manual" ? "Unable to start a reply" : "Unable to suggest a reply"); }
    finally { submitting.current = false; setBusyKind(""); }
  }
  const last = data ? data.messages.length - 1 : -1;
  return <section className="conversation-detail" aria-label="Conversation">
    <header className="conversation-head">
      <Avatar name={data?.name || data?.address || "?"} />
      <div className="conversation-head-copy"><h2>{data?.name || data?.address || "Saved conversation"}</h2>{data?.name && <p>{data.address}</p>}</div>
      <div className="conversation-head-actions"><AskLeadZen actorId={actorId} context={{ currentThreadId: threadId, workspacePath: `/inbox?thread=${threadId}` }} /><button type="button" className="button ghost conversation-close" aria-label="Back to inbox" title="Back to inbox" onClick={close}><Icon name="close" /></button></div>
    </header>
    {error && <p className="error conversation-notice" role="alert">{error}</p>}
    {!data && <p className="conversation-notice" role="status">{loading ? "Loading conversation…" : "Could not load this conversation."}</p>}
    {data && <>
      <div className="conversation-messages">
        {data.total_messages > data.messages.length && <p className="thread-note">Latest {data.messages.length} of {data.total_messages} messages.</p>}
        {data.messages.map((m, index) => {
          const author = messageAuthor(m.direction, m.from, data);
          const detail = m.reply_label ? replyLabelDetail(m.reply_label.label, m.reply_label.return_date, m.reply_label.action) : "";
          return <ThreadMessage key={m.id} defaultOpen={index === last} author={author} avatarName={author === "You" ? actorName : author} message={m} detail={detail} />;
        })}
      </div>
      <section className="reply-suggestion conversation-composer" aria-labelledby="suggested-reply-title">
        <div className="composer-box">
          <div className="composer-to"><span>To</span><span className="composer-chip">{data.address}</span></div>
          <h3 id="suggested-reply-title">Reply</h3>
          {!data.can_reply && <p className="composer-note" role="status">{data.reply_blocker}</p>}
          {actionError && <p className="error" role="alert">{actionError}</p>}
          {reviewId
            ? <OutreachReview key={reviewId} reviewId={reviewId} workspacePath={`/inbox?thread=${threadId}&review=${reviewId}`} expectedThreadId={threadId} closeLabel="Back to conversation" closed={() => { void recordWorkspaceContext({ currentDraftId: null, workspacePath: `/inbox?thread=${threadId}` }, actorId); setReviewId(null); requestIds.current = { manual: "", ai: "" }; refresh(); }} />
            : <>
              {data.can_reply && <p className="composer-placeholder">Write your own reply, or let LeadZen suggest one. Nothing sends until you approve.</p>}
              <div className="composer-actions">
                <div className="composer-ai"><button type="button" className="button ghost" disabled={!data.can_reply || !!busy} onClick={() => void start("ai")}><Icon name="sparkle" />{busy === "ai" ? "Writing reply…" : "Suggest reply"}</button><span className="composer-note">Uses AI, which may cost money.</span></div>
                <button type="button" className="button primary" disabled={!data.can_reply || !!busy} onClick={() => void start("manual")}>{busy === "manual" ? "Opening…" : "Write reply"}</button>
              </div>
            </>}
        </div>
      </section>
    </>}
  </section>;
}

export default function Inbox({ user, initialThreadId = null, initialReviewId = null }: { user: Account; initialThreadId?: number | null; initialReviewId?: string | null }) {
  const [query, setQuery] = useState("");
  const [label, setLabel] = useState<ReplyLabelName | "">("");
  const [offset, setOffset] = useState(0);
  const [threadId, setThreadId] = useState<number | null>(initialThreadId);
  useWorkspaceContext(threadId ? {} : { currentThreadId: null, currentDraftId: null, selectedLeadIds: [], currentLeadId: null, workspacePath: "/inbox" }, user.id);
  const { data, loading, error, refresh } = useStoredData<InboxPage>(`inbox/conversations?q=${encodeURIComponent(query)}&label=${label}&offset=${offset}`, 5000);
  return <div className="shell"><Sidebar user={user} active="inbox" /><main className="main main-inbox"><header className="topbar"><PageHeading title="Inbox" help="Read replies and answer them." /><div className="top-actions"><Link className="button" href="/inbox/messages">All messages</Link></div></header>
    <InboxCheck refreshed={refresh} />
    {error && <p className="error" role="alert">{error}</p>}
    <div className={`conversation-layout ${threadId ? "has-conversation" : ""}`}><section className="conversation-list" aria-label="Inbox conversations">
      <div className="inbox-filters"><select className="select" aria-label="Filter by reply label" value={label} onChange={(e) => { setLabel(e.target.value as ReplyLabelName | ""); setOffset(0); }}><option value="">All replies</option>{(Object.keys(replyLabels) as ReplyLabelName[]).map((key) => <option key={key} value={key}>{replyLabels[key]}</option>)}</select><div className="search-field"><Icon name="search" /><input className="input" aria-label="Search conversations" placeholder="Search by name, company or email" maxLength={200} value={query} onChange={(e) => { setQuery(e.target.value); setOffset(0); }} /></div></div>
      {loading && !data ? <p className="inbox-list-empty" role="status">Loading conversations…</p> : !data?.items.length ? <div className="inbox-list-empty"><span className="empty-icon" aria-hidden="true"><Icon name="inbox" /></span><p>{label ? `No conversations labelled ${replyLabels[label].toLowerCase()}.` : query ? "No conversations match your search." : "No replies yet. Choose Check for replies."}</p></div> : <ul className="conversation-cards">{data.items.map((c) => <li key={c.id}><button type="button" className="conversation-row" aria-pressed={threadId === c.id} onClick={() => setThreadId(c.id)}>
        <Avatar name={c.name || c.address} />
        <span className="conversation-row-body">
          <span className="conversation-row-top"><strong>{c.name || c.address}</strong>{c.count > 1 && <span className="conversation-count" aria-label={plural(c.count, "message")}>{c.count}</span>}</span>
          <span className="conversation-row-meta">{c.name ? c.address : ""}{c.name && c.subject ? " · " : ""}{c.subject || (c.name ? "" : "No subject")}</span>
          <span className="conversation-row-snippet">{c.snippet || "No saved text"}</span>
          <span className="conversation-row-foot"><time dateTime={c.last_at}>{listDate(c.last_at)}</time><LabelChip value={c.reply_label} /></span>
        </span>
      </button></li>)}</ul>}
      {data && <div className="records-pagination inbox-pagination"><span className="muted">{plural(data.total, "conversation")}</span><div className="top-actions"><button className="button ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - data.limit))}>Previous</button><button className="button ghost" disabled={offset + data.limit >= data.total} onClick={() => setOffset(offset + data.limit)}>Next</button></div></div>}
    </section>{threadId ? <Conversation key={threadId} threadId={threadId} actorId={user.id} actorName={user.name || user.email} initialReviewId={threadId === initialThreadId ? initialReviewId : null} close={() => setThreadId(null)} /> : <section className="conversation-empty"><div><span className="empty-icon" aria-hidden="true"><Icon name="inbox" /></span><h2>No conversation selected</h2><p>Pick a contact from the list to read the thread and reply inline.</p></div></section>}</div>
  </main></div>;
}
