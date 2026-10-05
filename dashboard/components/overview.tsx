"use client";
import { formatNewYorkDateTime, newYorkHour } from "@/lib/date-time";
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

function greeting(name: string) {
  const hour = newYorkHour(new Date());
  const period = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  const firstName = name.trim().split(/\s+/)[0];
  return `Good ${period}${firstName ? `, ${firstName}` : ""}`;
}

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
            <div><p className="eyebrow">{user.workspace_name} / Dashboard</p><h1>Your workspace</h1></div>
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
            <h1>Your workspace</h1>
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
            title={greeting(overview.home.operator_name || user.name)}
            eyebrow={user.workspace_name}
            help="Find the right people. See who is qualified, contacted and replying. Workspace totals cover all saved targets, including imported contacts."
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
        <NeedsAttention />
        <HomeSummaryPanel home={overview.home} onRefresh={load} />
        <div className="layout-grid">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">Lead queue</h2>
                <div className="panel-meta">
                  {total} leads match the current view
                </div>
              </div>
              <span className="panel-meta">Updated live</span>
            </div>
            <div className="filters">
              <div className="search-field">
                <Icon name="search" />
                <input
                  className="input"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search person, company, or email"
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
            </div>
            <div
              className="table-wrap"
              role="region"
              aria-label="Lead queue table"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Company</th>
                    <th>Stage</th>
                    <th>Last touch</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id}>
                      <td>
                        <div className="person">
                          {lead.name || [lead.first_name, lead.last_name]
                            .filter(Boolean)
                            .join(" ") || "Unnamed lead"}
                        </div>
                        <div className="subtext">
                          {lead.email || "No email resolved"}
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
                            {lead.reply_count} reply
                          </div>
                        )}
                      </td>
                      <td>
                        <div><time dateTime={lead.email_sent_at || undefined}>{formatDate(lead.email_sent_at)}</time></div>
                        <div className="subtext">
                          {lead.reason || "No qualification note"}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {leads.length === 0 && (
                <div className="empty">No leads match this view.</div>
              )}
            </div>
          </section>
          <div className="right-stack">
            <section className="panel send-box">
              <div className="panel-title">AI-assisted outreach</div>
              <p>
                Preview, edit and approve each message, then confirm the exact
                recipients. Mailbox pacing and daily safeguards stay on the server.
              </p>
              <div className="send-controls">
                <Link className="button primary" href="/outreach">Review outreach</Link>
              </div>
              {!overview?.ai_ready && (
                <p>
                  AI is not connected.{" "}
                  <Link href="/outreach">Prepare outreach</Link> or{" "}
                  <Link href="/settings">connect an AI provider</Link>.
                </p>
              )}
            </section>
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2 className="panel-title">Mailbox capacity</h2>
                  <div className="panel-meta">Measured sending headroom</div>
                </div>
              </div>
              <div className="capacity">
                {overview?.mailboxes.map((box) => (
                  <div className="capacity-row" key={box.address}>
                    <div>
                      <div className="capacity-label">{box.address}</div>
                      <div className="subtext">
                        {box.paused_today
                          ? "Paused by provider response"
                          : `${overview?.transport === "smtp" ? "SMTP" : overview?.transport} connection`}
                      </div>
                    </div>
                    <div className="capacity-value">
                      {box.remaining_today}/{box.daily_limit}
                    </div>
                  </div>
                )) ?? <div className="empty">No mailbox connected.</div>}
                {overview?.mailboxes.length === 0 && (
                  <div className="empty">No mailbox connected.</div>
                )}
              </div>
            </section>
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2 className="panel-title">Mailbox activity</h2>
                  <div className="panel-meta">Latest mailbox events</div>
                </div>
              </div>
              <div className="activity">
                {overview?.activity.map((item) => (
                  <div
                    className="activity-row"
                    key={`${item.sent_at}-${item.from}-${item.to}-${item.subject}`}
                  >
                    <div className="activity-dot" />
                    <div>
                      <div className="activity-main">
                        {item.direction === "in"
                          ? `Reply from ${item.from}`
                          : `${item.accepted ? "Accepted by provider for" : "Send attempt to"} ${item.to}`}
                      </div>
                      <div className="activity-meta">
                        {item.subject || "No subject"} ·{" "}
                        <time dateTime={item.sent_at || undefined}>{formatDate(item.sent_at)}</time>
                      </div>
                    </div>
                  </div>
                )) ?? <div className="empty">No activity yet.</div>}
                {overview?.activity.length === 0 && (
                  <div className="empty">No activity yet.</div>
                )}
              </div>
            </section>
          </div>
        </div>
        <section className="panel job-panel">
          <div className="panel-head">
            <h2 className="panel-title">Outreach runs</h2>
            <Link className="text-link" href="/activity">View activity →</Link>
          </div>
          <div className="activity">
            {jobs.map((job) => (
              <div className="activity-row" key={job.id}>
                <span className="activity-dot" />
                <div>
                  <span className={`badge ${job.status}`}>{job.status}</span>
                  <p className="settings-help">
                    Requested: {job.requested_count} email{job.requested_count === 1 ? "" : "s"} ·{" "}
                    <time dateTime={job.created_at}>{formatDate(job.created_at)}</time>
                  </p>
                </div>
              </div>
            ))}
            {!jobs.length && <div className="empty">No outreach runs yet.</div>}
          </div>
        </section>
      </main>
    </div>
  );
}
