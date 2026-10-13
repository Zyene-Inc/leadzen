"use client";
import { useState } from "react";
import Link from "next/link";
import { Sidebar } from "@/components/sidebar";
import { PageHeading } from "@/components/page-heading";
import { HelpText } from "@/components/help-tooltip";
import type { Account } from "@/lib/auth";
import { useStoredData } from "@/lib/use-stored-data";

type Step = { step: number; subject: string; sent: number; replies: number; reply_rate: number | null };
type CampaignResult = { id: string; name: string; status: string; recipients: number; contacted: number; sent: number; replied: number; reply_rate: number | null; bounced: number; opted_out: number; steps: Step[]; estimated: boolean };
export type Results = {
  period: string;
  overview: { sent: number; contacted: number; replied: number; reply_rate: number | null; bounced: number; bounce_rate: number | null; opted_out: number };
  trend: { date: string; sent: number; replies: number }[];
  campaigns: CampaignResult[];
  best_campaign: { id: string; name: string; reply_rate: number; contacted: number } | null;
  best_message: (Step & { campaign_id: string; campaign: string }) | null;
  min_sample: number;
};

const periods = [["7", "7 days"], ["30", "30 days"], ["90", "90 days"], ["all", "All time"]] as const;
export const percent = (value: number | null) => value === null ? "—" : `${Math.round(value * 1000) / 10}%`;
const stepName = (step: number) => step === 0 ? "First email" : `Follow-up ${step}`;
const day = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** One series, its own scale. Sent and replies differ by an order of magnitude. */
function Bars({ label, points, field, tone }: { label: string; points: Results["trend"]; field: "sent" | "replies"; tone: "ink" | "soft" }) {
  const [hover, setHover] = useState<number | null>(null);
  // A period switch changes the number of bars; never point at a bar that no longer exists.
  const shown = hover !== null && hover < points.length ? hover : null;
  const max = Math.max(1, ...points.map((p) => p[field]));
  const width = 600, height = 72, gap = points.length > 45 ? 1 : 2;
  const bar = width / points.length;
  return <figure className="results-bars" onMouseLeave={() => setHover(null)}>
    <figcaption><span>{label}</span><strong>{points.reduce((sum, p) => sum + p[field], 0)}</strong></figcaption>
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={`${label} per day`}>
      <line x1="0" x2={width} y1={height - 0.5} y2={height - 0.5} className="results-axis" />
      {points.map((p, i) => {
        const h = p[field] ? Math.max(3, (p[field] / max) * (height - 4)) : 0;
        return <g key={p.date} onMouseEnter={() => setHover(i)}>
          <rect x={i * bar} y={0} width={bar} height={height} fill="transparent" />
          {h > 0 && <rect x={i * bar + gap / 2} y={height - h} width={Math.max(1, bar - gap)} height={h} rx={Math.min(3, bar / 3)} className={`results-bar ${tone}${shown === i ? " hover" : ""}`} />}
        </g>;
      })}
    </svg>
    {shown !== null && <p className="results-tip" style={{ left: `${Math.min(88, Math.max(4, ((shown + 0.5) / points.length) * 100))}%` }}>{day(points[shown].date)} · {points[shown][field]} {field === "sent" ? "sent" : points[shown][field] === 1 ? "reply" : "replies"}</p>}
  </figure>;
}

function Trend({ points }: { points: Results["trend"] }) {
  if (!points.some((p) => p.sent || p.replies)) return <p className="empty">No emails sent in this period.</p>;
  return <div className="results-trend">
    <Bars label="Emails sent" points={points} field="sent" tone="soft" />
    <Bars label="New replies" points={points} field="replies" tone="ink" />
    <div className="results-dates"><span>{day(points[0].date)}</span><span>{day(points[points.length - 1].date)}</span></div>
    <details className="results-table-toggle"><summary>Show as table</summary>
      <div className="table-wrap"><table><thead><tr><th>Day</th><th>Sent</th><th>Replies</th></tr></thead>
        <tbody>{points.filter((p) => p.sent || p.replies).map((p) => <tr key={p.date}><td>{day(p.date)}</td><td>{p.sent}</td><td>{p.replies}</td></tr>)}</tbody></table></div>
    </details>
  </div>;
}

function CampaignRow({ item }: { item: CampaignResult }) {
  return <details className="results-campaign">
    <summary>
      <span className="results-campaign-name"><strong>{item.name}</strong><small>{item.contacted} of {item.recipients} emailed{item.estimated ? " · older sends estimated" : ""}</small></span>
      <span className="results-rate"><strong>{percent(item.reply_rate)}</strong><small>{item.replied} {item.replied === 1 ? "reply" : "replies"}</small></span>
      <span className="results-minor">{item.bounced} bounced · {item.opted_out} opted out</span>
    </summary>
    <div className="table-wrap"><table>
      <thead><tr><th>Email</th><th>Subject</th><th>Sent</th><th>Replies</th><th>Reply rate</th></tr></thead>
      <tbody>{item.steps.map((s) => <tr key={s.step}><td>{stepName(s.step)}</td><td className="results-subject">{s.subject}</td><td>{s.sent}</td><td>{s.replies}</td><td>{percent(s.reply_rate)}</td></tr>)}</tbody>
    </table></div>
    <Link className="text-link" href={`/outreach?campaign=${item.id}`}>Open campaign →</Link>
  </details>;
}

export default function ResultsPage({ user }: { user: Account }) {
  const [period, setPeriod] = useState("30");
  const { data, error, loading } = useStoredData<Results>(`results?period=${period}`);
  const o = data?.overview;
  const tiles = o ? [
    ["Reply rate", percent(o.reply_rate), `${o.replied} of ${o.contacted} people replied`],
    ["Emails sent", String(o.sent), "Accepted by your mail provider"],
    ["People emailed", String(o.contacted), "First emailed in this period"],
    ["Bounced", String(o.bounced), o.bounce_rate === null ? "No sends yet" : `${percent(o.bounce_rate)} of sends`],
    ["Opted out", String(o.opted_out), "Asked to stop"],
  ] : [];
  return <div className="shell"><Sidebar user={user} active="results" /><main className="main">
    <header className="topbar"><PageHeading title="Results" help="How your emails are doing. Replies matter most." />
      <div className="results-periods" role="group" aria-label="Time period">{periods.map(([key, label]) => <button key={key} type="button" className={`button ${period === key ? "selected" : "ghost"}`} aria-pressed={period === key} onClick={() => setPeriod(key)}>{label}</button>)}</div>
    </header>
    {error && <p className="error" role="alert">{error}</p>}
    {!error && (loading || (!!data && data.period !== period)) && <p className="empty" role="status">Loading results…</p>}
    {/* Never show one period's numbers under another period's button. */}
    {data && o && data.period === period && <>
      <section className="results-tiles" aria-label="Summary">{tiles.map(([label, value, note], i) => <div key={label} className={`results-tile${i === 0 ? " lead" : ""}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>)}</section>
      <section className="results-highlights">
        <div className="panel results-highlight"><span>Best campaign</span>{data.best_campaign ? <><strong>{data.best_campaign.name}</strong><small>{percent(data.best_campaign.reply_rate)} reply rate · {data.best_campaign.contacted} people</small></> : <small>Shows once a campaign has emailed {data.min_sample} people.</small>}</div>
        <div className="panel results-highlight"><span>Best message</span>{data.best_message ? <><strong>{data.best_message.subject || "No subject"}</strong><small>{stepName(data.best_message.step)} in {data.best_message.campaign} · {percent(data.best_message.reply_rate)} reply rate</small></> : <small>Shows once a message has gone to {data.min_sample} people.</small>}</div>
      </section>
      <section className="panel results-section"><div className="panel-head"><h2 className="panel-title">Sent and replies</h2><span className="panel-meta">{data.period === "all" ? "Last 90 days" : `Last ${data.period} days`} · New York time</span></div><Trend points={data.trend} /></section>
      <section className="panel results-section"><div className="panel-head"><h2 className="panel-title">By campaign</h2><HelpText label="How replies are counted">A reply counts for the last email that person got before replying. Bounces and opt-outs are shown so you can spot list or message problems.</HelpText></div>
        {data.campaigns.length ? data.campaigns.map((item) => <CampaignRow key={item.id} item={item} />) : <p className="empty">No campaign emails in this period. <Link className="text-link" href="/outreach">Start outreach</Link></p>}
      </section>
    </>}
  </main></div>;
}
