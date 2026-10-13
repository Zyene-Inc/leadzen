"use client";
import { formatNewYorkDateTime } from "@/lib/date-time";
import { PageHeading } from "@/components/page-heading";
import { useWorkspaceContext } from "@/lib/workspace-context";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { Icon } from "@/components/icon";
import DiscoveryEmailReview from "@/components/discovery-email-review";
import { DiscoveryActivityFeed, DiscoveryCandidateList, DiscoveryCurrentActivity, DiscoverySearchScope } from "@/components/discovery-activity";
import { api } from "@/lib/client-api";
import type { Account } from "@/lib/auth";
import {
  approvedBudget,
  creditLabel,
  findingActive,
  candidateWorkspaceLink,
  recentDiscoveryCandidates,
  profileLink,
  summaryTitle,
  summaryNote,
  statusLabel,
  type DiscoveryProgress,
} from "@/lib/discovery";

function useProgress(runId: string) {
  const [data, setData] = useState<DiscoveryProgress | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    function load() {
      void api<DiscoveryProgress>(`discovery/${runId}`, {
        signal: controller.signal,
      })
        .then((response) => {
          if (controller.signal.aborted) return;
          setData({
            ...response,
            events: response.events.map((event) => ({
              ...event,
              display_time: formatNewYorkDateTime(event.created_at, { hour: "2-digit", minute: "2-digit" }),
            })),
          });
          setError("");
          if (findingActive(response.status)) timer = setTimeout(load, 1500);
        })
        .catch((caught) => {
          if (!controller.signal.aborted) {
            setError(
              caught instanceof Error
                ? caught.message
                : "Unable to load discovery progress",
            );
            // A dropped connection must not silently freeze a running discovery screen.
            timer = setTimeout(load, 3000);
          }
        });
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId, revision]);
  return { data, error, refresh: () => setRevision((value) => value + 1) };
}

function Profile({ value }: { value: string | undefined }) {
  const href = profileLink(value);
  return href ? (
    <a
      className="text-link live-profile"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      View profile ↗
    </a>
  ) : null;
}

function ResultTable({ data }: { data: DiscoveryProgress }) {
  const leads = data.leads;
  const candidates = recentDiscoveryCandidates(data, 100);
  return (
    <section
      id="discovery-results"
      className="live-results"
      aria-labelledby="results-title"
      tabIndex={-1}
    >
      <div className="live-section-heading">
        <h2 id="results-title">Qualified leads</h2>
        <Link className="text-link" href="/contacts">
          All leads →
        </Link>
      </div>
      {!leads.length ? (
        <p className="settings-help">
          Qualified people show up here as they are found.
        </p>
      ) : (
        <div
          className="table-wrap"
          role="region"
          aria-label="Qualified leads table"
          tabIndex={0}
        >
          <table>
            <caption className="sr-only">
              Qualified people from this run
            </caption>
            <thead>
              <tr>
                <th scope="col">Person</th>
                <th scope="col">Why they fit</th>
                <th scope="col">Email</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td>
                    {candidateWorkspaceLink(lead) ? (
                      <Link className="text-link" href={candidateWorkspaceLink(lead)!}>{lead.name}</Link>
                    ) : <strong>{lead.name}</strong>}
                    <p className="settings-help">{lead.title}</p>
                    <p className="settings-help">{lead.company}</p>
                    <Profile value={lead.profile_url} />
                  </td>
                  <td className="live-table-reason">
                    {lead.reason || "No reason saved"}
                  </td>
                  <td>{lead.email || "Not found yet"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {candidates.length > 0 && (
        <details className="discovery-details discovery-candidate-history">
          <summary>Everyone found ({candidates.length})</summary>
          <p className="settings-help">Includes people who did not fit or are not checked yet.</p>
          <DiscoveryCandidateList candidates={candidates} />
        </details>
      )}
    </section>
  );
}

function FailurePanel({ data }: { data: DiscoveryProgress }) {
  const last = data.current_activity ?? null;
  const activity =
    last && last.data
      ? `It stopped while checking ${last.data.name || "a profile"}${
          last.data.company ? ` at ${last.data.company}` : ""
        }.`
      : "It stopped while checking a profile.";
  return (
    <section className="discovery-notice" aria-labelledby="failure-title">
      <h3 id="failure-title">This run failed</h3>
      <p>
        {activity} Check the{" "}
        <Link className="text-link" href={`/chat/${data.thread_id}`}>
          run transcript
        </Link>{" "}
        for the reason. Check Settings before you try again.
      </p>
    </section>
  );
}

function ProgressSummary({ data }: { data: DiscoveryProgress }) {
  const stats = [
    ["Found", data.counts.discovered],
    ["Checked", data.counts.evaluated],
    ["Qualified", data.counts.qualified],
    ["Rejected", data.counts.rejected],
  ] as const;
  return (
    <section className="zy-card live-summary" aria-labelledby="progress-title">
      <div className="live-summary-top">
        <h2 id="progress-title">{summaryTitle(data)}</h2>
        <span className={`badge ${data.status}`}>{statusLabel(data)}</span>
      </div>
      <div
        className="live-progress-heading"
        aria-live="polite"
        aria-atomic="true"
      >
        <strong>
          {data.counts.produced} / {data.goal.count}
        </strong>
        <span>
          {data.goal.unit === "emails"
            ? "emails found"
            : "leads saved"}
        </span>
      </div>
      <progress
        className="live-progress"
        aria-label="Saved results toward requested goal"
        value={Math.min(data.counts.produced, data.goal.count)}
        max={data.goal.count}
      />
      <dl className="live-statistics">
        {stats.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value.toLocaleString()}</dd>
          </div>
        ))}
        <div>
          <dt>{creditLabel(data)} used</dt>
          <dd>
            {data.credits.used === null ? "Waiting for count" : data.credits.used}
          </dd>
        </div>
      </dl>
      <DiscoverySearchScope scope={data.search_scope} />
      {data.credits.used === null && (
        <p className="settings-help">
          {data.credits.reported} credits confirmed so far. More may still be
          charged; this is not a free result.
        </p>
      )}
      <p className="settings-help">{summaryNote(data)}</p>
      {typeof data.counts.awaiting_evaluation === "number" && data.counts.awaiting_evaluation > 0 && (
        <p className="settings-help">
          {data.counts.awaiting_evaluation} {data.counts.awaiting_evaluation === 1 ? "person is" : "people are"} not checked yet.
        </p>
      )}
      <p className="settings-help">
        {approvedBudget(data)} AI use is extra. This run sends no emails.
      </p>
    </section>
  );
}

function RunControls({
  data,
  refresh,
}: {
  data: DiscoveryProgress;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  async function control(action: string) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await api(`discovery/${data.id}/${action}`, { method: "POST" });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to change this run",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
      refresh();
    }
  }
  const active = findingActive(data.status);
  const expired =
    !data.approval_expires_at ||
    Date.parse(data.approval_expires_at) <= Date.now();
  if (!active && data.status !== "paused") return null;
  return (
    <div className="live-controls">
      <div className="live-actions">
        {active && (
          <button
            className="button"
            disabled={busy || data.pause_requested || data.stop_requested}
            onClick={() => control("pause")}
          >
            {data.pause_requested ? "Pausing…" : "Pause"}
          </button>
        )}
        {data.status === "paused" && (
          <button
            className="button primary"
            disabled={busy || expired}
            onClick={() => control("resume")}
          >
            Resume
          </button>
        )}
        <button
          className="button"
          disabled={busy || data.stop_requested}
          onClick={() => control("stop")}
        >
          <Icon name="stop" />
          {data.stop_requested ? "Stopping…" : "Stop"}
        </button>
      </div>
      <p className="settings-help">
        {expired && data.status === "paused"
          ? "Approval expired. Stop this run and start a new search."
          : "Pause and Stop take effect after the current step. Paid lookups already sent cannot be undone."}
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function FinishedActions({ data }: { data: DiscoveryProgress }) {
  const [review, setReview] = useState(false);
  if (findingActive(data.status) || data.status === "paused") return null;
  return (
    <>
      <div className="live-actions live-finished-actions">
        <a className="button primary" href="#discovery-results">
          See leads
        </a>
        {data.goal.unit === "leads" && data.counts.produced > 0 && (
          <button
            className="button"
            onClick={() => setReview(true)}
            disabled={review}
          >
            Find emails
          </button>
        )}
        <Link className="button" href="/find-leads">
          Find more
        </Link>
      </div>
      {review && (
        <DiscoveryEmailReview runId={data.id} close={() => setReview(false)} />
      )}
    </>
  );
}

export default function DiscoveryLive({
  user,
  runId,
}: {
  user: Account;
  runId: string;
}) {
  const { data, error, refresh } = useProgress(runId);
  useWorkspaceContext({ currentRunId: data && !error ? data.id : null, workspacePath: data && !error ? `/find-leads/${data.id}` : "/find-leads" }, user.id);
  return (
    <div className="shell">
      <Sidebar user={user} active="find-leads" />
      <main className="main">
        <header className="topbar">
          <PageHeading title="Finding leads" help="See who fits, why, and the credits used. Leads save as they arrive." />
          {data && (
            <Link className="button" href={`/chat/${data.thread_id}`}>
              View transcript
            </Link>
          )}
        </header>
        <div className="discovery-live-page">
          {error && (
            <div className="discovery-notice" role="alert">
              <p>{error}</p>
              <button className="button" onClick={refresh}>
                Refresh
              </button>
            </div>
          )}
          {!data && !error && (
            <p role="status">Loading…</p>
          )}
          {data && (
            <>
              {data.synthetic && (
                <p className="discovery-notice">
                  Sample data only. No real credits used.
                </p>
              )}
              <ProgressSummary data={data} />
              {data.status === "failed" && <FailurePanel data={data} />}
              <DiscoveryCurrentActivity data={data} />
              <RunControls data={data} refresh={refresh} />
              <FinishedActions key={data.id} data={data} />
              <section className="discovery-target">
                <p className="eyebrow">Target</p>
                <p>{data.target}</p>
              </section>
              <div className="live-detail-grid">
                <section
                  className="live-activity"
                  aria-labelledby="activity-title"
                >
                  <div className="live-section-heading">
                    <h2 id="activity-title">Live steps</h2>
                    <span className="settings-help">Latest first · {data.events.length} saved events</span>
                  </div>
                  {data.events.length ? (
                    <DiscoveryActivityFeed events={data.events} />
                  ) : (
                    <p className="settings-help">
                      Waiting for the first step…
                    </p>
                  )}
                </section>
                <ResultTable data={data} />
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
