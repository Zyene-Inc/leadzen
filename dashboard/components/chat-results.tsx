"use client";
import { formatNewYorkDateTime } from "@/lib/date-time";
import Link from "next/link";
import { useMemo } from "react";
import { Icon } from "@/components/icon";
import { ChatDiscoveryCard } from "@/components/chat-discovery-card";
import type { DiscoveryProgress } from "@/lib/discovery";
import type { Approval, ChatMessage } from "@/lib/chat";
import { workspaceLink } from "@/lib/chat";

function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          !!item && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}
function text(value: unknown) {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : "";
}

function resultKey(item: Record<string, unknown>) {
  return text(item.id) || text(item.email) || JSON.stringify(item);
}
const toolNames: Record<string, string> = {
  get_workspace_status: "Workspace status", get_workspace_context: "Workspace context",
  get_target: "Audience", update_target: "Audience updated", find_leads: "Lead discovery",
  stop_discovery: "Discovery stopped", list_leads: "Leads", get_lead: "Lead details",
  find_work_emails: "Email lookup", get_credit_usage: "Credits", create_drafts: "Email drafts",
  get_draft: "Email draft", update_draft: "Draft updated", regenerate_draft: "Draft rewritten",
  send_email: "Email send", send_emails: "Email sending", sync_mailbox: "Mailbox sync",
  list_replies: "Replies", get_thread: "Conversation", draft_reply: "Reply draft", send_reply: "Reply send",
  suppress_contact: "Contact suppressed", unsuppress_contact: "Suppression removed", get_activity: "Activity",
};

export function ToolResult({ message, discovery, onCommand }: { message: ChatMessage; discovery?: DiscoveryProgress; onCommand?: (prompt: string) => void }) {
  const result = message.data.result ?? {};
  const items = rows(result.items);
  const drafts = rows(result.drafts);
  const run = result.discovery as DiscoveryProgress | undefined;
  const live = result.status === "running" && ["find_leads", "find_work_emails"].includes(message.data.tool || "") ? discovery : undefined;
  if (live || (run && message.data.tool !== "find_work_emails")) return <ChatDiscoveryCard data={(live || run)!} />;
  const draftTool = ["create_drafts", "get_draft", "update_draft", "regenerate_draft", "draft_reply", "send_email", "send_emails", "send_reply"].includes(message.data.tool || "");
  if (draftTool && drafts.length) return <section className="chat-tool chat-drafts" aria-label="Email drafts"><h3>{message.content}</h3>
    {drafts.map((draft) => <article className="chat-result-row" key={resultKey(draft)}><div className="email-preview-head"><strong>{text(draft.name)}</strong><span className="badge">{draft.state === "accepted" ? "Accepted by provider" : "Draft · not sent"}</span></div><p>From: {text(result.from_address)}<br />To: {text(draft.to)}</p><strong>{text(draft.subject)}</strong><pre className="email-copy">{text(draft.preview_body) || text(draft.body)}</pre><div className="card-actions"><Link className="text-link" href={workspaceLink(result.workspaceUrl) || "/sending"}>Open in Workspace →</Link>{draft.state === "pending" && onCommand && <button className="button" onClick={() => onCommand(`Send draft ${text(draft.id)}. Show the exact message for confirmation first.`)}>Review sending</button>}</div></article>)}
    {!!result.note && <p className="settings-help">{text(result.note)}</p>}
  </section>;
  const isContacts = message.data.tool === "list_leads";
  const running = result.status === "running";
  const stopped = result.status === "stopped";
  return (
    <details
      className={`chat-tool${result.error ? " tool-error" : running ? " tool-running" : stopped ? " tool-stopped" : ""}`}
      open={!!result.error || stopped || ["draft_campaign", "get_lead", "list_leads", "list_replies", "find_work_emails", "get_thread"].includes(message.data.tool || "")}
    >
      <summary>
        <Icon name={result.error ? "help" : running ? "refresh" : stopped ? "stop" : "check"} />
        <span>{message.content}</span>
        <span className="tool-label">
          {running ? "In progress" : stopped ? "Stopped" : toolNames[message.data.tool || ""] || "Workspace action"}
        </span>
      </summary>
      <div className="chat-tool-content">
        {!!result.error && <p className="error">{text(result.error)}</p>}
        {isContacts && items.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Contact</th>
                  <th>Company</th>
                  <th>Email</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={resultKey(item)}>
                    <td><Link className="text-link" href={`/contacts/${text(item.id)}`}>{text(item.name)}</Link>{!!item.title && <small>{text(item.title)}</small>}{!!item.reason && <p>{text(item.reason)}</p>}</td>
                    <td>{text(item.company)}</td>
                    <td>{text(item.email) || "Not verified"}</td>
                    <td>{text(item.state)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : items.length > 0 ? (
          items.map((item) => (
            <div className="chat-result-row" key={resultKey(item)}>
              <strong>{text(item.name) || text(item.subject)}</strong>
              <span>{text(item.from) || text(item.status)}</span>
              {!!item.body && <p>{text(item.body)}</p>}
              {!!item.email && <p>{text(item.email)} · {text(item.email_status)}</p>}
              {!item.email && message.data.tool === "find_work_emails" && <p>No verified email found</p>}
              {!!workspaceLink(item.workspaceUrl) && <Link className="text-link" href={workspaceLink(item.workspaceUrl)!}>Open in Workspace →</Link>}
              {!!item.threadId && onCommand && <button className="button" onClick={() => onCommand(`Draft a reply to conversation ${text(item.threadId)}. Do not send.`)}>Draft reply</button>}
            </div>
          ))
        ) : null}
        {!items.length && !result.error && (
          <dl className="chat-facts">
            {Object.entries(result)
              .filter(
                ([key, value]) =>
                  key !== "steps" &&
                  key !== "recipients" &&
                  key !== "items" &&
                  key !== "workspaceUrl" &&
                  key !== "status" &&
                  (typeof value === "string" ||
                    typeof value === "number" ||
                    typeof value === "boolean"),
              )
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>
                    {typeof value === "boolean"
                      ? value
                        ? "Yes"
                        : "No"
                      : text(value)}
                  </dd>
                </div>
              ))}
          </dl>
        )}
        {!!result.name && message.data.tool === "get_lead" && <div className="chat-result-row"><strong>{text(result.name)}</strong><span>{text(result.title)} · {text(result.company)}</span><p>{text(result.reason)}</p></div>}
        {!!result.credits && typeof result.credits === "object" && <p>Credits actually used: {text((result.credits as Record<string, unknown>).used) || "Awaiting provider report"}</p>}
        {!!result.steps && <Sequence steps={result.steps} />}
        <Link
          className="text-link"
          href={
            workspaceLink(result.workspaceUrl) || (message.data.tool?.includes("campaign")
              ? "/campaigns"
              : message.data.tool === "connections"
                ? "/settings"
                : "/contacts")
          }
        >
          Open in workspace →
        </Link>
      </div>
    </details>
  );
}

function Sequence({ steps }: { steps: unknown }) {
  return (
    <div className="chat-sequence">
      {rows(steps).map((step, index) => (
        <div key={JSON.stringify(step)}>
          <span className="eyebrow">
            Email {index + 1}
            {index > 0 ? ` · Wait ${text(step.delay_days)} days` : ""}
          </span>
          <strong>{text(step.subject)}</strong>
          <p>{text(step.body)}</p>
        </div>
      ))}
    </div>
  );
}

export function ApprovalCard({
  approval,
  expiresAt,
  busy,
  onApprove,
}: {
  approval: Approval;
  expiresAt: string | null;
  busy: boolean;
  onApprove: (approved: boolean) => void;
}) {
  const preview = approval.preview;
  const expiration = useMemo(() => expiresAt ? formatNewYorkDateTime(expiresAt, { hour: "numeric", minute: "2-digit" }) : "", [expiresAt]);
  return (
    <section className="chat-approval" aria-label="Action approval">
      <div className="approval-heading">
        <span className="approval-dot" />
        <span>YOUR APPROVAL NEEDED</span>
      </div>
      <h2>{approval.summary}</h2>
      <div className="approval-limits">
        <span>
          Up to <strong>{approval.credits}</strong> lead credits
        </span>
        <span>
          Up to <strong>{approval.emails}</strong> emails
        </span>
      </div>
      {approval.tool === "find_work_emails" && <p>Selected leads: {rows(preview.recipients).length}</p>}
      {!!preview.audience && (
        <p>
          <strong>Audience:</strong> {text(preview.audience)}
        </p>
      )}
      {!!preview.from_address && (
        <p>
          <strong>Sender:</strong> {text(preview.from_address)}
        </p>
      )}
      {!!preview.recipients && (
        <div className="approval-recipients">
          <strong>Exact recipients</strong>
          {rows(preview.recipients).map((recipient) => (
            <details open key={resultKey(recipient)}>
              <summary>
                {text(recipient.name) || text(recipient.email)}{recipient.name && recipient.email ? ` · ${text(recipient.email)}` : ""}
              </summary>
              <strong>{text(recipient.subject)}</strong>
              <p className="chat-message-text">{text(recipient.body)}</p>
            </details>
          ))}
        </div>
      )}
      {!!preview.steps && <Sequence steps={preview.steps} />}
      {!!preview.note && <p className="muted">{text(preview.note)}</p>}
      <p className="muted">
        Model and discovery calls can incur separate provider charges. This
        approval covers only this action
        {expiresAt
          ? ` and expires at ${expiration}`
          : ""}
        .
      </p>
      <div className="approval-actions">
        <button
          className="button primary"
          type="button"
          disabled={busy}
          onClick={() => onApprove(true)}
        >
          {busy ? "Updating…" : approval.tool === "find_work_emails" ? "Get emails" : ["send_email", "send_emails", "send_reply"].includes(approval.tool) ? "Confirm send" : "Approve this action"}
        </button>
        <button
          className="button"
          type="button"
          disabled={busy}
          onClick={() => onApprove(false)}
        >
          Cancel
        </button>
      </div>
    </section>
  );
}
