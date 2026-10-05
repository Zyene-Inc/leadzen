"use client";
import { InboxCheck } from "@/components/inbox-check";
import { AskLeadZen } from "@/components/ask-leadzen";
import { PageHeading } from "@/components/page-heading";
import { recordWorkspaceContext, useWorkspaceContext } from "@/lib/workspace-context";
import Link from "next/link";
import { useRef, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import OutreachReview from "@/components/outreach-review";
import { api } from "@/lib/client-api";
import { useStoredData } from "@/lib/use-stored-data";
import { sentTime, type EmailReview } from "@/lib/outreach";
import type { Account } from "@/lib/auth";

type ConversationRow = { id: number; name: string; address: string; subject: string; snippet: string; kind: string; last_at: string; count: number };
type InboxPage = { items: ConversationRow[]; total: number; limit: number; offset: number };
type ConversationDetail = { id: number; name: string; address: string; can_reply: boolean; reply_blocker: string; total_messages: number; messages: { id: number; direction: string; from: string; to: string; subject: string; body: string; body_truncated: boolean; sent_at: string | null; kind: string; accepted: boolean }[] };

function messageAuthor(direction: string, from: string, contact: ConversationDetail) {
  if (direction === "out") return "You";
  if (from && from.toLowerCase() === contact.address.toLowerCase()) return contact.name || from;
  return from || "Unknown sender";
}

function Conversation({ threadId, close, initialReviewId, actorId }: { threadId: number; close: () => void; initialReviewId: string | null; actorId: number }) {
  const { data, error, loading, refresh } = useStoredData<ConversationDetail>(`inbox/conversations/${threadId}`, 5000);
  useWorkspaceContext({ currentThreadId: data && !error ? data.id : null, currentDraftId: null, selectedLeadIds: [], currentLeadId: null, workspacePath: data && !error ? `/inbox?thread=${data.id}` : "/inbox" }, actorId);
  const [reviewId, setReviewId] = useState<string | null>(initialReviewId);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const requestId = useRef("");
  const submitting = useRef(false);
  async function suggest() {
    if (submitting.current || !data?.can_reply) return;
    submitting.current = true; setBusy(true); setActionError("");
    requestId.current ||= crypto.randomUUID();
    try {
      const review = await api<EmailReview>("outreach/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ thread_id: threadId, count: 1, request_id: requestId.current }) });
      setReviewId(review.id);
    } catch (caught) { setActionError(caught instanceof Error ? caught.message : "Unable to suggest a reply"); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <section className="conversation-detail" aria-label="Conversation">
    <div className="section-heading"><div><p className="eyebrow">Conversation</p><h2>{data?.name || "Saved conversation"}</h2><p className="settings-help">{data?.address}</p></div><div className="top-actions"><AskLeadZen actorId={actorId} context={{ currentThreadId: threadId, workspacePath: `/inbox?thread=${threadId}` }} /><button className="button" onClick={close}>Back to inbox</button></div></div>
    {error && <p className="error" role="alert">{error}</p>}
    {!data && <p role="status">{loading ? "Loading conversation…" : "Unable to load this conversation."}</p>}
    {data && <><div className="conversation-messages">
      {data.total_messages > data.messages.length && <p className="settings-help">Showing the latest {data.messages.length} of {data.total_messages} saved messages.</p>}
      {data.messages.map((m) => <article key={m.id} className="conversation-message"><div className="email-preview-head"><strong>{messageAuthor(m.direction, m.from, data)}</strong><time>{sentTime(m.sent_at)}</time></div><p className="settings-help">{m.subject} · {m.direction === "out" ? m.accepted ? "Accepted by provider" : "Send attempt, not confirmed" : m.kind.replaceAll("_", " ") || "Unclassified"}</p><pre className="email-copy">{m.body || "No saved plain-text content"}</pre>{m.body_truncated && <p className="settings-help">This saved message is shortened to 12000 characters.</p>}</article>)}
    </div><section className="reply-suggestion" aria-labelledby="suggested-reply-title"><h3 id="suggested-reply-title">AI Suggested Reply</h3><p className="settings-help">AI charges may apply. Review the suggestion before approving a send.</p>{!data.can_reply && <p role="status">{data.reply_blocker}</p>}{actionError && <p className="error" role="alert">{actionError}</p>}{!reviewId && <button className="button" disabled={!data.can_reply || busy} onClick={() => void suggest()}>{busy ? "Drafting suggestion…" : "Suggest reply"}</button>}{reviewId && <OutreachReview key={reviewId} reviewId={reviewId} workspacePath={`/inbox?thread=${threadId}&review=${reviewId}`} expectedThreadId={threadId} closeLabel="Back to conversation" closed={() => { void recordWorkspaceContext({ currentDraftId: null, workspacePath: `/inbox?thread=${threadId}` }, actorId); setReviewId(null); requestId.current = ""; refresh(); }} />}</section></>}
  </section>;
}

export default function Inbox({ user, initialThreadId = null, initialReviewId = null }: { user: Account; initialThreadId?: number | null; initialReviewId?: string | null }) {
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [threadId, setThreadId] = useState<number | null>(initialThreadId);
  useWorkspaceContext(threadId ? {} : { currentThreadId: null, currentDraftId: null, selectedLeadIds: [], currentLeadId: null, workspacePath: "/inbox" }, user.id);
  const { data, loading, error, refresh } = useStoredData<InboxPage>(`inbox/conversations?q=${encodeURIComponent(query)}&offset=${offset}`, 5000);
  return <div className="shell"><Sidebar user={user} active="inbox" /><main className="main"><header className="topbar"><PageHeading title="Inbox" help="Read saved conversations and review replies before sending." /><div className="top-actions"><Link className="button" href="/inbox/messages">All stored messages</Link></div></header>
    <InboxCheck refreshed={refresh} />
    {error && <p className="error" role="alert">{error}</p>}
    <div className={`conversation-layout ${threadId ? "has-conversation" : ""}`}><section className="panel conversation-list" aria-label="Inbox conversations"><div className="filters"><input className="input" aria-label="Search conversations" placeholder="Search person or message" maxLength={200} value={query} onChange={(e) => { setQuery(e.target.value); setOffset(0); }} /></div>
      {loading && !data ? <p className="empty" role="status">Loading conversations…</p> : !data?.items.length ? <p className="empty">No replies saved yet. Choose Check for replies to check your connected inbox.</p> : <ul>{data.items.map((c) => <li key={c.id}><button className="conversation-row" aria-pressed={threadId === c.id} onClick={() => setThreadId(c.id)}><div className="email-preview-head"><strong>{c.name || c.address}</strong><time>{sentTime(c.last_at)}</time></div><span>{c.subject || "No subject"}</span><p>{c.snippet || "No saved text"}</p><small>{c.count} messages</small></button></li>)}</ul>}
      {data && <div className="records-pagination"><span className="muted">{data.total} conversations</span><div className="top-actions"><button className="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - data.limit))}>Previous</button><button className="button" disabled={offset + data.limit >= data.total} onClick={() => setOffset(offset + data.limit)}>Next</button></div></div>}
    </section>{threadId ? <Conversation key={threadId} threadId={threadId} actorId={user.id} initialReviewId={threadId === initialThreadId ? initialReviewId : null} close={() => setThreadId(null)} /> : <section className="conversation-empty"><h2>Your conversations, in one place</h2><p>Select a conversation to read its history and prepare a reply.</p></section>}</div>
  </main></div>;
}
