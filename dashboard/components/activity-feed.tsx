"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/icon";
import { WorkspacePage } from "@/components/workspace-records";
import type { Account } from "@/lib/auth";
import { useStoredData } from "@/lib/use-stored-data";
import { activityTime, type ActivityEvent } from "@/lib/activity";
import { formatNewYorkDateTime, LEADZEN_TIME_ZONE_LABEL, newYorkDayKey } from "@/lib/date-time";

type ActivityData = { items: ActivityEvent[]; limit: number };
type LogData = {
  items: {
    id: string;
    label: string;
    at: string;
    output: string;
    truncated: boolean;
    unavailable: boolean;
  }[];
};

function groupEvents(events: ActivityEvent[]) {
  const now = new Date();
  const today = newYorkDayKey(now);
  const yesterday = newYorkDayKey(now, -1);
  const groups = new Map<string, { label: string; events: ActivityEvent[] }>();
  for (const event of events) {
    const key = newYorkDayKey(event.at);
    if (!groups.has(key)) {
      const label = key === today ? "Today"
        : key === yesterday ? "Yesterday" : formatNewYorkDateTime(event.at, { month: "short", day: "numeric", year: "numeric" });
      groups.set(key, { label, events: [] });
    }
    groups.get(key)!.events.push(event);
  }
  return Array.from(groups, ([key, group]) => ({ key, ...group }));
}

function ActivityRow({ event }: { event: ActivityEvent }) {
  const time = activityTime(event.at);
  const content = <>
    <p className="workspace-event-title">{event.title}</p>
    {event.detail && <p className="workspace-event-detail">{event.detail}</p>}
  </>;
  return (
    <li className="workspace-event">
      <time dateTime={event.at} title={time.timestamp}>
        {time.clock}
      </time>
      <span className={`workspace-event-icon state-${event.kind}`} aria-hidden="true">
        <Icon name={event.kind === "success" ? "check" : event.kind === "rejected" ? "close" : "activity"} />
      </span>
      {event.href ? <Link className="workspace-event-copy" href={event.href}>{content}</Link>
        : <div className="workspace-event-copy">{content}</div>}
    </li>
  );
}

function ActivityList({ data }: { data: ActivityData }) {
  if (!data.items.length) {
    return <p className="empty">No activity yet. Lead decisions, discovery results and email events will appear here.</p>;
  }
  return (
    <div className="workspace-activity-feed">
      <p className="workspace-activity-note">Latest {data.limit} saved events · {LEADZEN_TIME_ZONE_LABEL}</p>
      {groupEvents(data.items).map((group) => (
        <section className="workspace-activity-day" key={group.key} aria-label={group.label}>
          <h2>{group.label}</h2>
          <ol>{group.events.map((event) => <ActivityRow key={event.id} event={event} />)}</ol>
        </section>
      ))}
    </div>
  );
}

function DeveloperLogs({ close }: { close: () => void }) {
  const { data, loading, error, refresh } = useStoredData<LogData>("activity/logs");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return (
    <section id="developer-logs" className="panel workspace-developer-logs" aria-labelledby="developer-logs-title">
      <div className="panel-head">
        <h2 id="developer-logs-title" className="panel-title" tabIndex={-1} ref={heading}>Developer Logs</h2>
        <div className="top-actions">
          <button className="button" type="button" disabled={loading} onClick={refresh}>Refresh logs</button>
          <button className="button" type="button" onClick={close}>Close logs</button>
        </div>
      </div>
      <p className="settings-help workspace-logs-note">Saved worker output and the latest log tails. Authentication details are removed.</p>
      {error && <p className="error records-notice" role="alert">{error}</p>}
      {loading && !data && <p className="empty" role="status">Loading developer logs…</p>}
      {!loading && !error && !data?.items.length && <p className="empty">No developer logs have been recorded yet.</p>}
      {data?.items.map((log) => (
        <article className="workspace-log" key={log.id} aria-label={log.label}>
          <div className="workspace-log-heading">
            <h3>{log.label}</h3>
            <time dateTime={log.at}>{activityTime(log.at).timestamp}</time>
          </div>
          {log.output ? <pre tabIndex={0} aria-label={`${log.label} output`}>{log.output}</pre> : <p className="settings-help">No worker output recorded.</p>}
          {log.truncated && <p className="settings-help">Showing the latest portion of this log.</p>}
          {log.unavailable && <p className="settings-help">The worker log file is unavailable.</p>}
        </article>
      ))}
    </section>
  );
}

export function Activity({ user }: { user: Account }) {
  const { data, loading, error, refresh } = useStoredData<ActivityData>("activity");
  const [logsOpen, setLogsOpen] = useState(false);
  const logsButton = useRef<HTMLButtonElement>(null);
  function closeLogs() {
    setLogsOpen(false);
    logsButton.current?.focus();
  }
  return (
    <WorkspacePage user={user} active="activity" title="Activity"
      description="Lead decisions, discovery results and email events, newest first."
      actions={(
        <>
          <button className="button" type="button" ref={logsButton} aria-expanded={logsOpen} aria-controls="developer-logs" onClick={() => setLogsOpen((open) => !open)}>Developer Logs</button>
          <button className="button" type="button" disabled={loading} onClick={refresh}><Icon name="refresh" />Refresh</button>
        </>
      )}
    >
      <section className="panel" aria-label="Workspace activity">
        {error ? <p className="error records-notice" role="alert">{error} Use Refresh to retry.</p>
          : loading && !data ? <p className="empty" role="status">Loading activity…</p>
          : data && <ActivityList data={data} />}
      </section>
      {logsOpen && <DeveloperLogs close={closeLogs} />}
    </WorkspacePage>
  );
}
