"use client";
import { formatNewYorkDateTime } from "@/lib/date-time";
import { NeedsAttention } from "@/components/needs-attention";
import { PageHeading } from "@/components/page-heading";

import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { Icon } from "@/components/icon";
import Link from "next/link";
import type { Account } from "@/lib/auth";
import { useWorkspaceRevision } from "@/lib/workspace-updates";
import { api } from "@/lib/client-api";
import { HomeSummaryPanel, type HomeSummary } from "@/components/home-summary";
import { ThemeToggle } from "@/components/theme-toggle";
import { stateLabel } from "@/lib/format";

type Lead = {
  name: string;
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  company: string;
  title: string;
  state: string;
  outcome: string;
  reason: string;
  email_sent_at: string | null;
  reply_count: number;
};
type Overview = {
  home: HomeSummary;
  ai_ready: boolean;
  transport: string;
  leads: {
    total: number;
    ready: number;
    emailed: number;
    completed: number;
    suppressed: number;
  };
  today: { sent: number; inbound: number };
  mailboxes: {
    address: string;
    daily_limit: number;
    sent_today: number;
    remaining_today: number;
    paused_today: boolean;
    next_send_at: string | null;
  }[];
  activity: {
    accepted: boolean;
    direction: string;
    kind: string;
    to: string;
    from: string;
    subject: string;
    sent_at: string | null;
  }[];
};
type Job = {
  id: string;
  requested_count: number;
  status: string;
  created_at: string;
};

function statusClass(state: string) {
  if (state === "Ready to Email") return "badge ready";
  if (state === "Emailed") return "badge emailed";
  return "badge completed";
}

function formatDate(value: string | null) {
  if (!value) return "Not yet";
  return formatNewYorkDateTime(value, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// Explee-style status card at the top of the Dashboard. Reads saved overview only.
function SendingStatus({ overview }: { overview: Overview }) {
  const boxes = overview.mailboxes ?? [];
  const sent = overview.today?.sent ?? 0;
  const left = boxes.reduce((sum, box) => sum + Math.max(0, box.remaining_today), 0);
  const paused = boxes.some((box) => box.paused_today);
  const state = !boxes.length ? "off" : paused ? "warn" : "on";
  const title = state === "off" ? "No mailbox connected" : paused ? "Sending is paused" : "Sending is on schedule";
  const detail = state === "off"
    ? "Connect a mailbox in Settings to send email."
    : `${sent} sent today, ${left} left today${paused ? " · paused by email provider" : ""}`;
  return (
    <section className="status-card" aria-label="Sending status">
      <span className={`status-dot ${state}`} aria-hidden="true" />
      <div className="status-copy">
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
      <div className="status-actions">
        <Link className="button" href="/settings">View schedule</Link>
        <Link className="button primary" href="/outreach">View emails</Link>
      </div>
    </section>
  );
}

const recentTabs = [
  ["emails", "Latest emails"],
  ["capacity", "Emails left today"],
  ["runs", "Send runs"],
] as const;

export default function Dashboard({ user }: { user: Account }) {
  const workspaceRevision = useWorkspaceRevision();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [query, setQuery] = useState("");
  const [state, setState] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [recent, setRecent] = useState<(typeof recentTabs)[number][0]>("emails");

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const [nextOverview, nextLeads, nextJobs] = await Promise.all([
          api<Overview>("overview", { signal }),
          api<{ items: Lead[]; total: number }>(
            `leads?q=${encodeURIComponent(query)}&state=${encodeURIComponent(state)}`,
            { signal },
          ),
          api<{ items: Job[] }>("jobs", { signal }),
        ]);
        if (signal?.aborted) return;
        setOverview(nextOverview);
        setLeads(nextLeads.items);
        setTotal(nextLeads.total);
        setJobs(nextJobs.items);
        setError("");
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError"))
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to load dashboard",
          );
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [query, state],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, workspaceRevision]);
  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;
    const timer = window.setInterval(async () => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      try {
        await load(controller.signal);
      } finally {
        inFlight = false;
      }
    }, 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [load, workspaceRevision]);

  if (loading && !overview)
    return (
      <div className="shell">
        <Sidebar user={user} active="overview" />
        <main className="main" aria-busy="true" aria-label="Loading workspace">
          <div className="topbar dashboard-topbar">
            <div><h1>{user.workspace_name || "Dashboard"}</h1></div>
            <div className="top-actions"><ThemeToggle /></div>
          </div>
          <div className="loading-layout">
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        </main>
      </div>
    );

  if (!overview)
    return (
      <div className="shell">
        <Sidebar user={user} active="overview" />
        <main className="main">
          <div className="topbar dashboard-topbar">
            <h1>{user.workspace_name || "Dashboard"}</h1>
            <div className="top-actions"><ThemeToggle /></div>
          </div>
          <p className="error" role="alert">
            {error || "Unable to load your workspace."}
          </p>
          <button
            type="button"
            className="button"
            onClick={() => {
              setLoading(true);
              void load();
            }}
          >
            Try again
          </button>
        </main>
      </div>
    );

  return (
    <div className="shell">
      <Sidebar user={user} active="overview" />
      <main className="main">
        <div className="topbar dashboard-topbar">
          <PageHeading
            title={user.workspace_name || "Dashboard"}
            help="Your leads, emails and replies at a glance. Totals include imported contacts."
          />
          <div className="top-actions">
            <button
              type="button"
              className="zy-btn button"
              onClick={() => void load()}
            >
              <Icon name="refresh" />
              Refresh
            </button>
            <ThemeToggle />
          </div>
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <SendingStatus overview={overview} />
        <NeedsAttention />
        <HomeSummaryPanel home={overview.home} onRefresh={load} />
        <div className="section-row">
          <h2 className="section-label">Leads <span className="count-pill">{total}</span></h2>
          <div className="section-actions">
            <div className="search-field">
              <Icon name="search" />
              <input
                className="input"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search name, company or email"
                aria-label="Search leads"
              />
            </div>
            <select
              className="select"
              value={state}
              onChange={(event) => setState(event.target.value)}
              aria-label="Filter leads"
            >
              <option value="all">All stages</option>
              <option value="Ready to Email">Ready to email</option>
              <option value="Emailed">Emailed</option>
              <option value="Completed">Completed</option>
            </select>
            <Link className="button" href="/contacts"><Icon name="contacts" />All leads</Link>
          </div>
        </div>
        <section className="panel home-leads">
          <div
            className="table-wrap"
            role="region"
            aria-label="Leads table"
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>Lead</th>
                  <th>Company</th>
                  <th>State</th>
                  <th>Last email</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr key={lead.id}>
                    <td>
                      <div className="person">
                        {lead.name || [lead.first_name, lead.last_name]
                          .filter(Boolean)
                          .join(" ") || "No name"}
                      </div>
                      <div className="subtext">
                        {lead.email || "No email yet"}
                      </div>
                    </td>
                    <td>
                      <div className="person">
                        {lead.company || "Unknown company"}
                      </div>
                      <div className="subtext">{lead.title || ""}</div>
                    </td>
                    <td>
                      <span className={statusClass(lead.state)}>
                        {lead.state}
                      </span>
                      {lead.reply_count > 0 && (
                        <div className="subtext">
                          {lead.reply_count} {lead.reply_count === 1 ? "reply" : "replies"}
                        </div>
                      )}
                    </td>
                    <td>
                      <div><time dateTime={lead.email_sent_at || undefined}>{formatDate(lead.email_sent_at)}</time></div>
                      <div className="subtext">
                        {lead.reason || "No note"}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {leads.length === 0 && (
              <div className="empty">No leads match.</div>
            )}
          </div>
        </section>
        <div className="section-row">
          <div className="segmented" role="tablist" aria-label="Recent sending">
            {recentTabs.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={recent === id}
                className={recent === id ? "selected" : ""}
                onClick={() => setRecent(id)}
              >
                {label}
                {id === "emails" && <span className="segmented-count">{overview.activity?.length ?? 0}</span>}
              </button>
            ))}
          </div>
          <Link className="text-link" href="/activity">View activity →</Link>
        </div>
        <section className="panel home-recent" role="tabpanel" aria-label={recentTabs.find(([id]) => id === recent)?.[1]}>
          {recent === "emails" && (
            <div className="activity">
              {(overview.activity ?? []).map((item) => (
                <div
                  className="activity-row"
                  key={`${item.sent_at}-${item.from}-${item.to}-${item.subject}`}
                >
                  <div className="activity-dot" />
                  <div>
                    <div className="activity-main">
                      {item.direction === "in"
                        ? `Reply from ${item.from}`
                        : `${item.accepted ? "Sent to" : "Tried to send to"} ${item.to}`}
                    </div>
                    <div className="activity-meta">
                      {item.subject || "No subject"} ·{" "}
                      <time dateTime={item.sent_at || undefined}>{formatDate(item.sent_at)}</time>
                    </div>
                  </div>
                </div>
              ))}
              {!overview.activity?.length && <div className="empty">No activity yet.</div>}
            </div>
          )}
          {recent === "capacity" && (
            <div className="capacity">
              {(overview.mailboxes ?? []).map((box) => (
                <div className="capacity-row" key={box.address}>
                  <div>
                    <div className="capacity-label">{box.address}</div>
                    <div className="subtext">
                      {box.paused_today
                        ? "Paused by email provider"
                        : `${overview.transport === "smtp" ? "SMTP" : overview.transport} connection`}
                    </div>
                  </div>
                  <div className="capacity-value">
                    {box.remaining_today}/{box.daily_limit}
                  </div>
                </div>
              ))}
              {!overview.mailboxes?.length && <div className="empty">No mailbox connected.</div>}
            </div>
          )}
          {recent === "runs" && (
            <div className="activity">
              {jobs.map((job) => (
                <div className="activity-row" key={job.id}>
                  <div>
                    <span className={`badge ${job.status}`}>{stateLabel(job.status)}</span>
                    <p className="settings-help">
                      {job.requested_count} email{job.requested_count === 1 ? "" : "s"} ·{" "}
                      <time dateTime={job.created_at}>{formatDate(job.created_at)}</time>
                    </p>
                  </div>
                </div>
              ))}
              {!jobs.length && <div className="empty">No send runs yet.</div>}
            </div>
          )}
          {!overview.ai_ready && (
            <p className="home-ai-note">
              AI is not connected. <Link href="/settings">Connect AI</Link> or{" "}
              <Link href="/outreach">write by hand</Link>.
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
