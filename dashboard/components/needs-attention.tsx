"use client";
import Link from "next/link";
import { useStoredData } from "@/lib/use-stored-data";
import { HelpTooltip } from "@/components/help-tooltip";
export function NeedsAttention() {
  const { data, error, loading, refresh } = useStoredData<{ items: { id: string; label: string; detail: string; href: string }[] }>("attention", 10000);
  return <section className="panel needs-attention" aria-busy={loading && !data} aria-labelledby="attention-title"><div className="panel-head" data-tour="home-attention"><h2 id="attention-title">Needs you</h2><HelpTooltip label="About your attention list">Drafts to approve, replies to answer and sending problems.</HelpTooltip></div>
    {error ? <p className="error" role="alert">Could not load your to-dos. <button className="button ghost" onClick={refresh}>Retry</button></p> : loading && !data ? <p role="status">Loading…</p> : !data?.items.length ? <p className="settings-help">All clear. <Link className="text-link" href="/contacts">See your leads</Link></p> : <ul className="attention-list">{data.items.map((item) => <li key={item.id}><Link className="attention-row" href={item.href}><span><strong>{item.label}</strong><small>{item.detail}</small></span><span aria-hidden="true">→</span></Link></li>)}</ul>}
  </section>;
}
