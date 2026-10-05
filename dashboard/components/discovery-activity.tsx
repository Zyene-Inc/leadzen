"use client";
import { formatNewYorkDateTime } from "@/lib/date-time";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { Icon } from "@/components/icon";
import {
  candidateWorkspaceLink,
  currentDiscoveryActivity,
  currentDiscoverySearch,
  discoveryActivityLabels,
  findingActive,
  profileLink,
  type Candidate,
  type DiscoveryEvent,
  type DiscoveryProgress,
} from "@/lib/discovery";

function eventTime(createdAt: string) {
  const date = new Date(createdAt);
  return Number.isNaN(date.getTime()) ? "" : formatNewYorkDateTime(date, { hour: "2-digit", minute: "2-digit" });
}

export function DiscoveryCurrentActivity({ data }: { data: DiscoveryProgress }) {
  const active = findingActive(data.status) && !data.pause_requested && !data.stop_requested;
  const latest = data.current_activity || data.events.at(-1);
  return (
    <div className="discovery-current" data-active={active} data-status={data.status}>
      <span className="operation-status-dot" aria-hidden="true" />
      <div>
        <p className="discovery-current-label" role="status" aria-atomic="true">
          {currentDiscoveryActivity(data)}
        </p>
        <p className="discovery-current-search">{currentDiscoverySearch(data)}</p>
      </div>
      {latest && (
        <time className="discovery-current-update" dateTime={latest.created_at}>
          {eventTime(latest.created_at)}
        </time>
      )}
    </div>
  );
}

function CandidateLinks({ candidate }: { candidate: Partial<Candidate> }) {
  const workspace = candidateWorkspaceLink(candidate);
  const profile = profileLink(candidate.profile_url);
  if (!workspace && !profile) return null;
  return (
    <div className="discovery-person-links">
      {workspace && <Link className="text-link" href={workspace}>Open in Workspace →</Link>}
      {profile && (
        <a className="text-link" href={profile} target="_blank" rel="noopener noreferrer">
          View profile ↗
        </a>
      )}
    </div>
  );
}

export function DiscoveryActivityItem({ event, fresh = false }: { event: DiscoveryEvent; fresh?: boolean }) {
  const { kind, data } = event;
  const verdict = kind === "qualified" || kind === "rejected";
  const candidate = verdict || kind === "discovered" || kind === "evaluating";
  const priorVerdict = data.outcome === "qualified" || data.outcome === "rejected";
  return (
    <li className="live-event discovery-event" data-kind={kind} data-new={fresh}>
      <span className={`live-event-icon ${verdict ? kind : ""}`} aria-hidden="true">
        <Icon name={kind === "qualified" ? "check" : kind === "rejected" ? "close" : kind === "evaluating" ? "activity" : kind === "discovered" ? "contacts" : "search"} />
      </span>
      <div className="live-event-body">
        <div className="live-event-heading">
          <strong className={verdict ? `live-verdict ${kind}` : ""}>
            {discoveryActivityLabels[kind] || kind.replaceAll("_", " ")}
          </strong>
          <time className="discovery-event-time" dateTime={event.created_at}>
            {eventTime(event.created_at)}
          </time>
        </div>
        {candidate && data.name && <h3 className="discovery-person-heading">{data.name}</h3>}
        {candidate && [data.title, data.company].some(Boolean) && (
          <p className="discovery-person-meta">{[data.title, data.company].filter(Boolean).join(" · ")}</p>
        )}
        {verdict && (
          <p className="live-reason discovery-person-reason">
            <span>{kind === "qualified" ? "Why qualified:" : "Why rejected:"}</span>{" "}
            {data.reason || "No qualification reason was recorded."}
          </p>
        )}
        {kind === "discovered" && (
          <p className="settings-help">
            Returned by the profile search. {priorVerdict
              ? `A ${data.outcome} verdict was already recorded.`
              : "Qualification is still pending."}
          </p>
        )}
        {kind === "evaluating" && (
          <p className="settings-help">
            {priorVerdict
              ? "Checking this profile again against your target. A new verdict has not been recorded for this check."
              : "Checking this profile against your target. A verdict has not been recorded yet."}
          </p>
        )}
        {kind === "searching" && data.filters && (
          <p className="discovery-person-meta">{Object.entries(data.filters).map(([key, value]) => `${key}: ${value}`).join(" · ")}</p>
        )}
        {kind === "search_completed" && typeof data.profiles_returned === "number" && (
          <p>{data.profiles_returned} profile{data.profiles_returned === 1 ? "" : "s"} returned · qualification determines which fit your target</p>
        )}
        {data.message && <p className="settings-help">{data.message}</p>}
        {candidate && <CandidateLinks candidate={data} />}
      </div>
    </li>
  );
}

export function DiscoveryActivityFeed({ events, visible = 18 }: { events: DiscoveryEvent[]; visible?: number }) {
  const seen = useRef<Set<number> | null>(null);
  const fresh = new Set(seen.current ? events.filter((event) => !seen.current!.has(event.id)).map((event) => event.id) : []);
  useEffect(() => { seen.current = new Set(events.map((event) => event.id)); }, [events]);
  const latest = [...events].reverse();
  return (
    <>
      <ol className="discovery-activity-list">
        {latest.slice(0, visible).map((event) => <DiscoveryActivityItem key={event.id} event={event} fresh={fresh.has(event.id)} />)}
      </ol>
      {latest.length > visible && (
        <details className="discovery-details">
          <summary>Earlier activity ({latest.length - visible})</summary>
          <ol className="discovery-activity-list">
            {latest.slice(visible).map((event) => <DiscoveryActivityItem key={event.id} event={event} />)}
          </ol>
        </details>
      )}
    </>
  );
}

export function DiscoveryCandidateRow({ candidate, fresh = false }: { candidate: Candidate; fresh?: boolean }) {
  const decided = candidate.outcome === "qualified" || candidate.outcome === "rejected";
  return (
    <article className="discovery-candidate-row" data-outcome={candidate.outcome} data-new={fresh}>
      <div className="discovery-candidate-heading">
        <strong>{candidate.name}</strong>
        <span className={`badge ${candidate.outcome === "qualified" ? "crm-qualified" : candidate.outcome === "rejected" ? "crm-rejected" : ""}`}>
          {decided ? candidate.outcome === "qualified" ? "Qualified" : "Rejected" : "Not evaluated yet"}
        </span>
      </div>
      <p className="discovery-person-meta">{[candidate.title, candidate.company].filter(Boolean).join(" · ")}</p>
      {decided && (
        <p className="discovery-person-reason">
          <span>{candidate.outcome === "qualified" ? "Why qualified:" : "Why rejected:"}</span>{" "}
          {candidate.reason || "No qualification reason was recorded."}
        </p>
      )}
      {candidate.email && <p className="discovery-person-meta">{candidate.email}</p>}
      <CandidateLinks candidate={candidate} />
    </article>
  );
}

export function DiscoveryCandidateList({ candidates, label }: { candidates: Candidate[]; label?: string }) {
  const seen = useRef<Set<string> | null>(null);
  const identity = (candidate: Candidate) => `${candidate.id}:${candidate.outcome}`;
  const fresh = new Set(seen.current ? candidates.filter((candidate) => !seen.current!.has(identity(candidate))).map(identity) : []);
  useEffect(() => { seen.current = new Set(candidates.map(identity)); }, [candidates]);
  return (
    <div className="discovery-candidate-list" aria-label={label}>
      {candidates.map((candidate) => <DiscoveryCandidateRow key={candidate.id} candidate={candidate} fresh={fresh.has(identity(candidate))} />)}
    </div>
  );
}
