"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/icon";
import { DiscoveryActivityFeed } from "@/components/discovery-activity";
import { currentRunDiscovery, type ChatRun, type Conversation } from "@/lib/chat";
import { currentDiscoveryActivity, type DiscoveryProgress } from "@/lib/discovery";

const terminalLabels: Record<string, string> = {
  succeeded: "Task complete", completed: "Task complete", failed: "Task needs attention",
  cancelled: "Task stopped", stopped: "Task stopped", paused: "Task paused", awaiting_approval: "Approval needed",
};
function activityLabel(run: ChatRun, active: boolean, discovery: DiscoveryProgress | undefined, tool: string | undefined, writing: boolean) {
  if (run.approval) return "Approval needed";
  if (!active) return terminalLabels[run.status] || "Task status unavailable";
  if (run.cancel_requested) return "Stopping task";
  if (run.status === "queued") return "Waiting to start";
  if (discovery && tool) return currentDiscoveryActivity(discovery);
  return tool || (writing ? "Writing a response" : "Working on your request");
}
function actionState(result: Record<string, unknown> | undefined, active: boolean) {
  if (result?.error || result?.status === "failed") return "Needs attention";
  if (result?.status === "running") return active ? "In progress" : "Not confirmed complete";
  if (["stopped", "cancelled"].includes(String(result?.status))) return "Stopped";
  return "Recorded";
}

function RunElapsed({ run, active }: { run: ChatRun; active: boolean }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!active || !run.created_at) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, run.id, run.created_at]);
  const start = Date.parse(run.created_at || "");
  const end = active ? now : Date.parse(run.finished_at || "");
  if (!Number.isFinite(start) || end === null || !Number.isFinite(end)) return null;
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  const duration = seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return <span className="chat-live-elapsed" title="Elapsed since request, including any waits" aria-label={`Elapsed since request, including waits: ${duration}`}>{duration}</span>;
}

export function ChatLiveActivity({ conversation }: { conversation: Conversation }) {
  const run = conversation.run;
  if (!run) return null;
  // Keep expansion/timing scoped to one request, including when another run starts.
  return <RunActivity key={run.id} conversation={conversation} run={run} />;
}

function RunActivity({ conversation, run }: { conversation: Conversation; run: ChatRun }) {
  const [expanded, setExpanded] = useState(false);
  const active = ["queued", "running"].includes(run.status) && !run.approval;
  const currentMessages = conversation.messages.slice(conversation.messages.findLastIndex(message => message.role === "user") + 1);
  const actions = currentMessages.filter(message => message.role === "tool");
  const tool = actions.findLast(message => message.data.result?.status === "running");
  const writing = currentMessages.some(message => message.role === "assistant" && message.data.streaming);
  // A conversation can contain older discovery runs. Never borrow their counts.
  const discovery = currentRunDiscovery(conversation);
  const completed = actions.filter(message => {
    const result = message.data.result;
    return result && !result.error && !["running", "failed", "stopped", "cancelled"].includes(String(result.status));
  }).length;
  const label = activityLabel(run, active, discovery, tool?.content, writing);
  const detail = discovery
    ? `${discovery.counts.discovered} profiles found · ${discovery.counts.produced} / ${discovery.goal.count} ${discovery.goal.unit === "emails" ? "email results" : "qualified leads"} · ${discovery.counts.evaluated} evaluated`
    : completed ? `${completed} ${completed === 1 ? "action" : "actions"} completed`
    : active ? "Using your connected model and Workspace" : "View recorded activity";
  return (
    <section className="chat-live-activity" aria-label="Task activity" data-active={active} data-status={run.status}>
      <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
        <summary className="chat-live-summary" aria-label={`${label}. ${detail}. ${expanded ? "Hide" : "View"} activity`}>
          <span className="chat-live-symbol" aria-hidden="true">
            {active ? <span className="chat-work-motion"><span /><span /><span /></span>
              : <Icon name={run.status === "succeeded" ? "check" : run.status === "failed" || run.approval ? "help" : "stop"} />}
          </span>
          <span className="chat-live-copy"><strong role="status" aria-live="polite" aria-atomic="true">{label}</strong><span>{detail}</span></span>
          <RunElapsed run={run} active={active} />
          <span className="chat-live-toggle">{expanded ? "Hide activity" : "View activity"}<span aria-hidden="true">{expanded ? "⌃" : "⌄"}</span></span>
        </summary>
        {expanded && <div className="chat-live-body" role="region" aria-label="Recorded task activity" tabIndex={0}>
          {run.cancel_requested && active && <p>Waiting for the current action to finish. Saved results are kept.</p>}
          {discovery?.synthetic && <p>Synthetic preview · no external calls or real credits used.</p>}
          {discovery && <p>Email credits used: {discovery.credits.used === null ? "Awaiting provider report" : discovery.credits.used}</p>}
          {actions.length > 0 && <ol className="chat-live-actions">{actions.map(action => {
            return <li key={action.id}><span>{action.content}</span><small>{actionState(action.data.result, active)}</small></li>;
          })}</ol>}
          {discovery?.events.length ? <DiscoveryActivityFeed events={discovery.events} visible={6} />
            : !actions.length && <p>{active ? "Waiting for the next recorded update." : "No tool actions were recorded for this request."}</p>}
        </div>}
      </details>
      {discovery && <div className="chat-live-footer">
        {(discovery.credits.approved > 0 || discovery.credits.used === null) && <span className="chat-live-credit">Email credits: {discovery.credits.used === null ? "Awaiting provider report" : `${discovery.credits.used} used`} · {discovery.credits.approved} approved</span>}
        <Link className="text-link" href={`/find-leads/${discovery.id}`}>{active ? "Open live discovery" : "View saved results"} →</Link><Link className="text-link" href="/contacts">Open leads →</Link>
      </div>}
    </section>
  );
}
