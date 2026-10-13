"use client";
import { formatNewYorkDateTime } from "@/lib/date-time";
import { HelpTooltip } from "@/components/help-tooltip";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/icon";
import { api } from "@/lib/client-api";
import type { Audience } from "@/lib/setup-wizard";

export type HomeSummary = {
  operator_name: string;
  metrics: {
    found: number;
    qualified: number;
    with_email: number;
    contacted: number;
    replies: number;
  };
  credits: {
    provider_name?: string;
    configured: boolean;
    balance: number | null;
    checked_at: string | null;
    synthetic: boolean;
  };
  target: { summary: string; audience: Audience | null; country_name: string; place?: string };
  recent_activity: {
    id: number;
    name: string;
    status: "qualified" | "rejected" | "excluded";
    reason: string;
    at: string;
  }[];
};

const metrics = [
  ["found", "People found", "Everyone found, including people who did not fit"],
  ["qualified", "Qualified", "People who match your target"],
  ["with_email", "With email", "Qualified people with an email address"],
  ["contacted", "Emailed", "People you have emailed, all time"],
  ["replies", "Replies", "People who wrote back, all time"],
] as const;

const numberFormatter = new Intl.NumberFormat();
const timestamp = (value: string) => formatNewYorkDateTime(value, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function CreditBalance({
  credits,
  onRefresh,
}: {
  credits: HomeSummary["credits"];
  onRefresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      // Reuse the bounded, authenticated account probe. No lead lookup or send.
      await api("onboarding/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "discovery" }),
      });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not check credits",
      );
    } finally {
      await onRefresh();
      setBusy(false);
    }
  }
  return (
    <section className="home-credit-bar" aria-label={`${credits.provider_name ?? "BetterContact"} credits`}>
      <div>
        <div className="home-credit-value">
          {credits.provider_name ?? "BetterContact"} credits <HelpTooltip label="Provider credits">Checking your balance is free. It does not buy anything.</HelpTooltip>{" "}
          <strong>
            {credits.balance === null
              ? "Not checked"
              : numberFormatter.format(credits.balance)}
          </strong>
        </div>
        <p className="settings-help">
          {!credits.configured
            ? `Connect ${credits.provider_name ?? "BetterContact"} to find leads.`
            : credits.checked_at
              ? `${credits.synthetic ? "Sample data. " : ""}Checked ${timestamp(credits.checked_at)}.`
              : "Check to see your balance."}
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
      {credits.configured ? (
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => void refresh()}
        >
          <Icon name="refresh" />
          {busy ? "Checking…" : "Check credits"}
        </button>
      ) : (
        <Link className="button" href="/settings">
          Connect {credits.provider_name ?? "BetterContact"}
        </Link>
      )}
    </section>
  );
}

export function HomeSummaryPanel({
  home,
  onRefresh,
}: {
  home: HomeSummary;
  onRefresh: () => Promise<void>;
}) {
  const audience = home.target.audience;
  return (
    <>
      <section className="zy-stats metrics home-metrics" aria-label="Outreach totals">
        {metrics.map(([key, label, note]) => (
          <div className="zy-stat metric" key={key}>
            <div className="zy-stat-title metric-label">{label}<HelpTooltip label={label}>{note}</HelpTooltip></div>
            <div className="zy-stat-value metric-value">
              {numberFormatter.format(home.metrics[key])}
            </div>
          </div>
        ))}
      </section>
      <CreditBalance credits={home.credits} onRefresh={onRefresh} />
      <div className="home-panels">
        <section className="zy-card panel home-target">
          <div className="panel-head">
            <h2 className="panel-title">Your target</h2>
            <Link className="button" href="/target">
              Edit target
            </Link>
          </div>
          <div className="home-target-body">
            {audience ? (
              <>
                <h3>{audience.industry?.replace(/\s+/g, " ").trim()}</h3>
                <p className="home-target-location">
                  {home.target.place || home.target.country_name}
                  {audience.company_size !== "any"
                    ? ` · ${audience.company_size} employees`
                    : " · Any company size"}
                </p>
                <ul className="home-target-roles" aria-label="Target roles">
                  {audience.roles.map((role) => (
                    <li key={role}>{role}</li>
                  ))}
                </ul>
                <details className="home-target-details">
                  <summary>Full target</summary>
                  <p>{home.target.summary}</p>
                </details>
              </>
            ) : (
              <p>
                {home.target.summary ||
                  "Pick an industry, country and roles to start."}
              </p>
            )}
            <div className="home-next-action">
              <Link
                className="button primary"
                href={home.target.summary ? "/find-leads" : "/target"}
              >
                <Icon name="search" />
                {home.target.summary ? "Find more leads" : "Set your target"}
              </Link>
              <HelpTooltip label="Finding leads">You see the count and credit cost before you start. Finding emails is optional.</HelpTooltip>
            </div>
          </div>
        </section>
        <section className="zy-card panel">
          <div className="panel-head">
            <div>
              <h2 className="panel-title">Latest decisions</h2>
            </div>
          </div>
          <div className="activity home-decisions" role="region" aria-label="Recent qualification decisions" tabIndex={0}>
            {home.recent_activity.map((item) => (
              <div className="activity-row" key={item.id}>
                <span className={`home-verdict ${item.status}`}>
                  <Icon
                    name={item.status === "qualified" ? "check" : "close"}
                  />
                </span>
                <div>
                  <div className="activity-main">
                    {item.name}{" "}
                    <span className="home-verdict-label">{item.status}</span>
                  </div>
                  <time className="activity-meta" dateTime={item.at}>
                    {timestamp(item.at)}
                  </time>
                  {item.reason && (
                    <details className="home-reason">
                      <summary>Why {item.status}?</summary>
                      <p>{item.reason}</p>
                    </details>
                  )}
                </div>
              </div>
            ))}
            {!home.recent_activity.length && (
              <div className="empty">
                <p>No decisions yet.</p>
                <p>Find leads to see who fits and why.</p>
              </div>
            )}
          </div>
          <div className="home-activity-footer">
            <Link href="/contacts">All leads</Link>
            <Link href="/inbox">Replies</Link>
          </div>
        </section>
      </div>
    </>
  );
}
