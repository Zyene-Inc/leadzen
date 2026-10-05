"use client";
import Link from "next/link";
import { DiscoveryActivityFeed, DiscoveryCandidateList, DiscoveryCurrentActivity } from "@/components/discovery-activity";
import { recentDiscoveryCandidates, statusLabel, type DiscoveryProgress } from "@/lib/discovery";

export function ChatDiscoveryCard({ data }: { data: DiscoveryProgress }) {
  const candidates = recentDiscoveryCandidates(data);
  const remaining = data.counts.awaiting_evaluation;
  return (
    <section className="zy-card chat-operation chat-discovery" aria-label="Discovery progress">
      <div className="email-preview-head">
        <h3>{data.goal.unit === "emails" ? "Finding work emails" : "Finding leads"}</h3>
        <span className={`badge ${data.status}`}>{statusLabel(data)}</span>
      </div>
      <DiscoveryCurrentActivity data={data} />
      <div className="live-progress-heading">
        <strong>{data.counts.produced} / {data.goal.count}</strong>
        <span>{data.goal.unit === "emails" ? "verified email results" : "qualified leads saved"}</span>
      </div>
      <progress className="live-progress" aria-label="Discovery goal" value={Math.min(data.counts.produced, data.goal.count)} max={data.goal.count} />
      <dl className="chat-facts discovery-card-facts">
        <div><dt>Discovered</dt><dd>{data.counts.discovered}</dd></div>
        <div><dt>Qualified</dt><dd>{data.counts.qualified}</dd></div>
        <div><dt>Evaluated</dt><dd>{data.counts.evaluated}</dd></div>
        <div><dt>Rejected</dt><dd>{data.counts.rejected}</dd></div>
        <div><dt>Email credits used</dt><dd>{data.credits.used === null ? "Awaiting provider report" : data.credits.used}</dd></div>
      </dl>
      {typeof remaining === "number" && remaining > 0 && <p className="settings-help">{remaining} discovered {remaining === 1 ? "profile has" : "profiles have"} not received a qualification verdict yet.</p>}
      {candidates.length > 0 && (
        <DiscoveryCandidateList candidates={candidates} label="Recent discovery candidates" />
      )}
      <details className="discovery-details">
        <summary>View activity{data.events.length ? ` (${data.events.length})` : ""}</summary>
        {data.events.length ? <DiscoveryActivityFeed events={data.events} visible={12} /> : (
          <p className="settings-help">The first discovery action has not been recorded yet.</p>
        )}
      </details>
      <Link className="text-link" href={`/find-leads/${data.id}`}>View all in Workspace →</Link>
    </section>
  );
}
