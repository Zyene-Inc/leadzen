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
    configured: boolean;
    balance: number | null;
    checked_at: string | null;
    synthetic: boolean;
  };
  target: { summary: string; audience: Audience | null; country_name: string };
  recent_activity: {
    id: number;
    name: string;
    status: "qualified" | "rejected" | "excluded";
    reason: string;
    at: string;
  }[];
};

const metrics = [
  ["found", "People found", "Discovered profiles, including unqualified"],
  ["qualified", "Qualified leads", "Profiles accepted by the qualifier"],
  ["with_email", "With email", "Qualified profiles with an address"],
  ["contacted", "Contacted", "Unique addresses accepted by the provider"],
  ["replies", "Replies", "People with a stored human reply"],
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
    <section className="home-credit-bar" aria-label="BetterContact credits">
      <div>
        <div className="home-credit-value">
          BetterContact credits <HelpTooltip label="BetterContact credits">Check your saved balance. Checking credits does not buy profiles or email addresses.</HelpTooltip>{" "}
          <strong>
            {credits.balance === null
              ? "Not checked"
              : numberFormatter.format(credits.balance)}
          </strong>
        </div>
        <p className="settings-help">
          {!credits.configured
            ? "Connect BetterContact to discover leads."
            : credits.checked_at
              ? `${credits.synthetic ? "Synthetic preview. " : ""}Checked ${timestamp(credits.checked_at)}.`
              : "Check credits to retrieve your balance."}
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
          Connect BetterContact
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
            <h2 className="panel-title">Current target</h2>
            <Link className="button" href="/target">
              Edit Target
            </Link>
          </div>
          <div className="home-target-body">
            {audience ? (
              <>
                <h3>{audience.industry}</h3>
                <p className="home-target-location">
                  {home.target.country_name}
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
                  <summary>Full targeting instructions</summary>
                  <p>{home.target.summary}</p>
                </details>
              </>
            ) : (
              <p>
                {home.target.summary ||
                  "Choose an industry, country and decision-makers to guide your first search."}
              </p>
            )}
            <div className="home-next-action">
              <Link
                className="button primary"
                href={home.target.summary ? "/find-leads" : "/target"}
              >
                <Icon name="search" />
                {home.target.summary ? "Find More Leads" : "Set your target"}
              </Link>
              <HelpTooltip label="Finding leads">Review the lead count and email-credit estimate before starting. Email lookup stays optional.</HelpTooltip>
            </div>
          </div>
        </section>
        <section className="zy-card panel">
          <div className="panel-head">
            <div>
              <h2 className="panel-title">Recent activity</h2>
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
                <p>No qualification activity yet.</p>
                <p>Start a search to see who matches your target and why.</p>
              </div>
            )}
          </div>
          <div className="home-activity-footer">
            <Link href="/contacts">Manage contacts</Link>
            <Link href="/inbox">Review replies</Link>
          </div>
        </section>
      </div>
    </>
  );
}
