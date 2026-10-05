"use client";
import { HelpTooltip } from "@/components/help-tooltip";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { ChatResponse } from "@/components/chat-response";
import { conversationWorkspaceVersion, notifyWorkspaceUpdated } from "@/lib/workspace-updates";
import { Sidebar } from "@/components/sidebar";
import { ChatRename } from "@/components/chat-rename";
import { Icon, type IconName } from "@/components/icon";
import { ChatHistory } from "@/components/chat-history";
import { ApprovalCard, ToolResult } from "@/components/chat-results";
import { streamConversation } from "@/lib/chat-stream";
import { flushWorkspaceContext } from "@/lib/workspace-context";
import { api } from "@/lib/client-api";
import { activeRun, currentRunDiscovery, type ChatRun, type ChatThread, type Conversation } from "@/lib/chat";
import type { Account } from "@/lib/auth";
import type { Settings } from "@/lib/connection-settings";
import { ChatLiveActivity } from "@/components/chat-live-activity";

const suggestions: {
  icon: IconName;
  title: string;
  detail: string;
  prompt: string;
}[] = [
  {
    icon: "contacts",
    title: "Find the right leads",
    detail: "Discover prospects for your product",
    prompt:
      "Find 5 qualified leads matching my saved audience. Do not buy email addresses.",
  },
  {
    icon: "campaigns",
    title: "Draft a sequence",
    detail: "Personalized emails, ready for review",
    prompt:
      "Draft outreach for the selected leads, or ask me to choose if none are selected. Do not send.",
  },
  {
    icon: "chat",
    title: "Review replies",
    detail: "See who responded and what to do next",
    prompt:
      "Did anyone reply? Check saved replies and offer to sync my mailbox for fresh replies. Do not send.",
  },
  {
    icon: "overview",
    title: "Check my workspace",
    detail: "Connections, leads, and outreach status",
    prompt:
      "Check my connections and workspace. What is ready, and what should I do next?",
  },
];
const jsonBody = (body: unknown) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function useChat(threadId?: string, initialPrompt = "") {
  const router = useRouter();
  const [history, setHistory] = useState<ChatThread[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [prompt, setPrompt] = useState(initialPrompt);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connectionNotice, setConnectionNotice] = useState("");
  const [submittedPrompt, setSubmittedPrompt] = useState("");
  const composer = useRef<HTMLTextAreaElement>(null);
  const submitting = useRef(false);
  const contextEpoch = useRef(0);
  const workspaceVersion = useRef("");
  const retryRequest = useRef<{
    content: string;
    id: string;
    threadId?: string;
  } | null>(null);
  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      const epoch = contextEpoch.current;
      const [threads, config, detail] = await Promise.all([
        api<{ items: ChatThread[] }>("chat/threads", { signal }),
        api<Settings>("settings", { signal }),
        threadId
          ? api<Conversation>(`chat/threads/${threadId}`, { signal })
          : Promise.resolve(null),
      ]);
      if (signal?.aborted || epoch !== contextEpoch.current) return;
      setHistory(threads.items);
      setSettings(config);
      setConversation(detail);
      setConnectionNotice("");
    },
    [threadId],
  );
  useEffect(() => {
    const controller = new AbortController();
    contextEpoch.current += 1;
    void refresh(controller.signal)
      .catch((caught) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error ? caught.message : "Could not load chat",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => { controller.abort(); contextEpoch.current += 1; };
  }, [refresh]);
  const currentConversation = conversation?.id === threadId ? conversation : null;
  useEffect(() => {
    if (!currentConversation) return;
    const version = conversationWorkspaceVersion(currentConversation);
    if (workspaceVersion.current !== version) {
      workspaceVersion.current = version;
      notifyWorkspaceUpdated();
    }
  }, [currentConversation]);
  const run = currentConversation?.run;
  const pending = activeRun(run);
  const streaming = !!run && ["queued", "running"].includes(run.status);
  const aiReady =
    !!settings?.llm.enabled &&
    !!settings.llm.api_key_configured &&
    !!settings.llm.model;
  useEffect(() => {
    if (!threadId || !streaming) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function connect() {
      try {
        await streamConversation(threadId!, (snapshot) => {
          if (!controller.signal.aborted) {
            setConnectionNotice("");
            setConversation(snapshot);
          }
        }, controller.signal);
      } catch (caught) {
        if (!controller.signal.aborted) {
          try {
            await refresh(controller.signal);
            if (!controller.signal.aborted) setConnectionNotice("");
          } catch {
            if (!controller.signal.aborted) setConnectionNotice(caught instanceof Error ? caught.message : "Live connection interrupted; refreshing saved progress.");
          }
        }
      }
      if (!controller.signal.aborted) timer = setTimeout(() => void connect(), 1000);
    }
    void connect();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [threadId, run?.id, streaming, refresh]);
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = prompt.trim();
    if (!content || !aiReady || pending || submitting.current) return;
    submitting.current = true;
    const epoch = contextEpoch.current;
    setBusy(true);
    setError("");
    setNotice("");
    setConnectionNotice("");
    setSubmittedPrompt(content);
    setPrompt("");
    const request =
      retryRequest.current?.content === content
        ? retryRequest.current
        : { content, id: crypto.randomUUID(), threadId };
    retryRequest.current = request;
    let accepted = false;
    try {
      await flushWorkspaceContext();
      const id =
        request.threadId ??
        (await api<ChatThread>("chat/threads", jsonBody({}))).id;
      request.threadId = id;
      const result = await api<{ run: ChatRun }>(
        `chat/threads/${id}/messages`,
        jsonBody({ content, request_id: request.id }),
      );
      accepted = true;
      retryRequest.current = null;
      if (epoch !== contextEpoch.current) return;
      if (threadId && result.run) setConversation((current) => current ? { ...current, run: result.run } : current);
      if (!threadId) router.push(`/chat/${id}`);
      else {
        await refresh();
        setSubmittedPrompt("");
      }
    } catch (caught) {
      if (epoch !== contextEpoch.current) return;
      setSubmittedPrompt("");
      if (!accepted) setPrompt(content);
      setError(
        accepted ? "Your message was received. Saved progress could not refresh; reload this conversation to continue." : caught instanceof Error ? caught.message : "Message could not be sent",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function approve(approved: boolean) {
    if (!run?.approval || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await api(
        `chat/runs/${run.id}/approval`,
        jsonBody({ approved, action_id: run.approval.id }),
      );
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Approval could not be updated",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function stop() {
    if (!run || busy) return;
    setBusy(true);
    setError("");
    try {
      await api(`chat/runs/${run.id}/cancel`, jsonBody({}));
      await refresh();
      setNotice(
        "Stop requested. Completed work stays in Workspace; the current action may finish before the task stops.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not stop task",
      );
    } finally {
      setBusy(false);
    }
  }
  async function rename(title: string) {
    if (!threadId || pending || submitting.current || !title.trim()) return false;
    submitting.current = true; setBusy(true); setError("");
    try {
      await api(`chat/threads/${threadId}`, { ...jsonBody({ title: title.trim() }), method: "PUT" });
      await refresh();
      return true;
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not rename conversation"); return false; }
    finally { submitting.current = false; setBusy(false); }
  }
  async function deleteChat(id: string) {
    await api(`chat/threads/${id}`, { method: "DELETE" });
    setHistory((items) => items.filter((item) => item.id !== id));
    if (id === threadId) router.replace("/chat");
  }
  async function archive() {
    if (!threadId || pending) return;
    setBusy(true);
    setError("");
    try {
      await api(`chat/threads/${threadId}`, {
        ...jsonBody({ archived: true }),
        method: "PUT",
      });
      router.push("/chat");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not archive chat",
      );
      setBusy(false);
    }
  }
  return {
    history,
    conversation: currentConversation,
    settings,
    prompt,
    setPrompt,
    loading,
    busy,
    error,
    notice: connectionNotice || notice,
    submittedPrompt,
    composer,
    run,
    pending,
    aiReady,
    send,
    approve,
    stop,
    archive,
    deleteChat,
    rename,
  };
}

type ChatProps = {
  user: Account;
  threadId?: string;
  initialPrompt?: string;
};

export default function Chat(props: ChatProps) {
  return <ChatScreen key={`${props.user.id}:${props.threadId || "new-chat"}`} {...props} />;
}

function ChatScreen({
  user,
  threadId,
  initialPrompt = "",
}: ChatProps) {
  const {
    history,
    conversation,
    settings,
    prompt,
    setPrompt,
    loading,
    busy,
    error,
    notice,
    submittedPrompt,
    composer,
    run,
    pending,
    aiReady,
    send,
    approve,
    stop,
    archive,
    deleteChat,
    rename,
  } = useChat(threadId, initialPrompt);
  const isHome = !threadId;
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const scroll = useRef<HTMLDivElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const jumpingToLatest = useRef(false);
  const userScrollIntent = useRef(false);
  const [showJump, setShowJump] = useState(false);
  useEffect(() => {
    const viewport = scroll.current;
    if (viewport && followLatest.current && !jumpingToLatest.current) viewport.scrollTop = viewport.scrollHeight;
  }, [conversation, submittedPrompt, loading]);
  const transcriptVisible = !isHome || !!submittedPrompt;
  useEffect(() => {
    const viewport = scroll.current;
    if (!viewport || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (followLatest.current && !jumpingToLatest.current) viewport.scrollTop = viewport.scrollHeight;
    });
    observer.observe(viewport);
    if (transcript.current) observer.observe(transcript.current);
    return () => observer.disconnect();
  }, [loading, transcriptVisible]);
  useEffect(() => {
    const textarea = composer.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(160, Math.max(40, textarea.scrollHeight))}px`;
  }, [prompt, composer]);
  function trackScroll() {
    const viewport = scroll.current;
    if (!viewport) return;
    const nearBottom = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop < 80;
    if (jumpingToLatest.current && !nearBottom) return;
    jumpingToLatest.current = false;
    if (followLatest.current && !userScrollIntent.current) {
      if (!nearBottom) viewport.scrollTop = viewport.scrollHeight;
      return;
    }
    followLatest.current = nearBottom;
    setShowJump(!followLatest.current);
  }
  function beginUserScroll() {
    userScrollIntent.current = true;
    interruptJump();
  }
  function interruptJump() {
    if (!jumpingToLatest.current) return;
    jumpingToLatest.current = false;
    const viewport = scroll.current;
    if (viewport) viewport.scrollTo({ top: viewport.scrollTop, behavior: "instant" });
    trackScroll();
  }
  function finishJump() {
    if (jumpingToLatest.current) {
      jumpingToLatest.current = false;
      const viewport = scroll.current;
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
    }
    trackScroll();
    userScrollIntent.current = false;
  }
  function jumpToLatest() {
    const viewport = scroll.current;
    if (!viewport) return;
    followLatest.current = true;
    userScrollIntent.current = false;
    setShowJump(false);
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    jumpingToLatest.current = !reducedMotion;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: reducedMotion ? "instant" : "smooth" });
  }
  return (
    <div className="shell chat-shell">
      <Sidebar
        user={user}
        active="chat"
        chatNavigation={<ChatHistory items={history} selected={threadId} onDelete={deleteChat} />}
      />
      <main className="chat-main">
        <header className="chat-topbar">
          <div>
            <div className="page-title-row"><h1>{isHome ? "Outreach orchestrator" : (conversation?.title ?? "Conversation")}</h1><HelpTooltip label="Working in Chat">Ask LeadZen to find leads, prepare drafts or review replies. Chat and Workspace share your records. Purchases, mailbox access and sending require confirmation.</HelpTooltip></div>
          </div>
          <div className="chat-topbar-actions">
            <Link className="button ghost" href="/settings"><Icon name="settings" /> Settings</Link>
            {!isHome && <button type="button" className="button ghost" disabled={pending || busy} onClick={() => { setTitle(conversation?.title || ""); setRenaming(true); }}>Rename</button>}
            {!isHome && <button type="button" className="button ghost" onClick={archive} disabled={pending || busy}>Archive</button>}
          </div>
        </header>
        {renaming && <ChatRename title={title} busy={busy} change={setTitle} save={rename} close={() => setRenaming(false)} />}
        <div className={`chat-stage${isHome ? " chat-stage-home" : ""}`}>
          <div className="chat-scroll" ref={scroll} onScroll={trackScroll} onScrollEnd={finishJump} onWheel={beginUserScroll} onTouchStart={beginUserScroll} onPointerDown={(event) => { if (event.target === event.currentTarget) beginUserScroll(); }} onKeyDown={(event) => { if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", "Tab", " "].includes(event.key)) beginUserScroll(); }} role="region" aria-label="Conversation scroll area" tabIndex={0}>
            {loading ? <p className="muted" role="status">Loading your workspace…</p> : <>
              {isHome && <div className="chat-welcome">
                <div className="chat-welcome-mark" aria-hidden="true"><Icon name="chat" /></div>
                <p className="eyebrow">LeadZen by Zyene</p>
                <h2>Hello, {user.name.split(" ")[0] || "there"}.</h2>
                <p>What would you like to work on?</p>
              </div>}
              {!aiReady && <div className="chat-connection-notice">
                <Icon name="settings" />
                <div><strong>Connect your AI provider to start</strong><p>Choose a model, API key, and compatible Base URL in <Link className="text-link" href="/settings">Connections</Link>. Keep credentials out of chat.</p></div>
              </div>}
              {conversation?.context && <p className="chat-context" role="status">
                {conversation.context.workspaceName}
                {!!conversation.context.selectedLeadIds?.length && ` · ${conversation.context.selectedLeadIds.length} selected leads`}
                {conversation.context.currentLeadId && ` · ${conversation.context.referencedLeads.find((lead) => lead.id === conversation.context?.currentLeadId)?.name || "Current lead"}`}
                {conversation.context.currentDraftId && " · Active draft"}
              </p>}
              {transcriptVisible && <div className="chat-transcript" ref={transcript} aria-label="Conversation messages">
                {conversation?.messages.map((message, index) => message.role === "tool" ? (
                  conversation.run && !message.data.result?.error && index > conversation.messages.findLastIndex(item => item.role === "user") && (
                    message.data.result?.status === "running" || (
                      message.data.tool === "find_leads" && currentRunDiscovery(conversation) &&
                      !!message.data.result?.discovery
                    )
                  ) ? null :
                  <ToolResult key={message.id} message={message} discovery={conversation?.discovery} onCommand={(text) => { setPrompt(text); composer.current?.focus(); }} />
                ) : (
                  <article key={message.id} className={`chat-message ${message.role}${message.data.streaming ? " is-streaming" : ""}`}>
                    <div className="chat-message-author">{message.role === "approval" ? "Approval recorded" : message.role === "user" ? user.name || "You" : "LeadZen"}</div>
                    {message.role === "assistant" ? <ChatResponse content={message.content} streaming={!!message.data.streaming} /> : <div className="chat-message-text">{message.content}</div>}
                  </article>
                ))}
                {submittedPrompt && <article className="chat-message user chat-submit-preview">
                  <div className="chat-message-author">{user.name || "You"}</div>
                  <div className="chat-message-text">{submittedPrompt}</div>
                  <span className="chat-work-detail" role="status">Submitting your request…</span>
                </article>}
                {conversation && <ChatLiveActivity conversation={conversation} />}
                {run?.approval && <ApprovalCard approval={run.approval} expiresAt={run.approval_expires_at} busy={busy} onApprove={(value) => void approve(value)} />}
                {run?.status === "failed" && <p className="chat-status-note">Task failed. Review the message above before retrying.</p>}
                {run?.status === "cancelled" && <p className="chat-status-note">Task stopped. Completed results are saved in Workspace.</p>}
              </div>}
              {isHome && !submittedPrompt && <>
                <div className="chat-suggestions">
                  {suggestions.map((suggestion) => <button type="button" key={suggestion.title} onClick={() => { setPrompt(suggestion.prompt); composer.current?.focus(); }} disabled={loading || !aiReady}>
                    <Icon name={suggestion.icon} /><span><strong>{suggestion.title}</strong><span>{suggestion.detail}</span></span><span aria-hidden="true">↗</span>
                  </button>)}
                </div>
                <div className="chat-home-footer"><span>Use your own connections</span><span>Review before sending</span><Link className="text-link" href="/tour">Explore the workspace →</Link></div>
              </>}
            </>}
          </div>
          <div className="chat-composer-dock">
            {showJump && <button type="button" className="button chat-jump-latest" onClick={jumpToLatest}>Jump to latest ↓</button>}
            {error && <div className="error" role="alert">{error}</div>}
            {notice && <div className="chat-status-note" role="status">{notice}</div>}
            <form className="chat-composer" data-tour="chat-composer" onSubmit={(event) => { followLatest.current = true; setShowJump(false); void send(event); }}>
              <label className="sr-only" htmlFor="chat-prompt">Message LeadZen</label>
              <textarea
                id="chat-prompt"
                ref={composer}
                value={prompt}
                maxLength={4000}
                rows={1}
                placeholder={pending ? "Write your next message while LeadZen works…" : "Ask LeadZen to find leads, draft outreach, or review replies…"}
                disabled={loading || !aiReady || busy}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                    event.preventDefault();
                    if (!pending) event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div className="composer-footer">
                <span>{settings?.llm.model || "Connect a model"}{settings?.llm.provider ? ` · ${settings.llm.provider.replaceAll("_", " ")}` : ""}</span>
                {pending ? <button className="button" type="button" onClick={stop} disabled={busy || run?.cancel_requested}><Icon name="stop" />{run?.cancel_requested ? "Stopping…" : "Stop task"}</button> : <button className="button primary composer-send" type="submit" aria-label="Send message" disabled={loading || busy || !aiReady || !prompt.trim()}><Icon name="send" /></button>}
              </div>
            </form>
            <p className="chat-disclaimer">Review recipients and copy before approving. Drafting never sends.</p>
          </div>
        </div>
      </main>
    </div>
  );
}
