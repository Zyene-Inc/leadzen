"use client";
import { PageHeading } from "@/components/page-heading";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Sidebar } from "@/components/sidebar";
import { Icon } from "@/components/icon";
import type { Account } from "@/lib/auth";
import { api } from "@/lib/client-api";

type DiscoverySetup = {
  max_count: number;
  max_email_count?: number;
  provider_name?: string;
  profile_budget_per_lead?: number;
  target: string;
  ready: boolean;
  blockers: string[];
  revision: string;
  active_run: {
    thread_id: string;
    status: string;
    discovery_id: string | null;
  } | null;
};

function DiscoveryContext({
  setup,
  loading,
}: {
  setup: DiscoverySetup | null;
  loading: boolean;
}) {
  return (
    <>
      <section className="discovery-target" aria-label="Your target">
        <p className="eyebrow">Your target</p>
        {loading ? (
          <div className="skeleton" aria-label="Loading saved target" />
        ) : (
          <p>
            {setup?.target ||
              "Set your target first."}
          </p>
        )}
      </section>
      {setup && !setup.ready && (
        <div className="discovery-notice" role="status">
          <strong>Finish setup first</strong>
          <ul>
            {setup.blockers.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <Link className="text-link" href="/settings">
            Open Settings
          </Link>{" "}
          ·{" "}
          <Link className="text-link" href="/onboarding">
            Purpose & setup
          </Link>
        </div>
      )}
      {setup?.active_run && (
        <div className="discovery-notice" role="status">
          A task is already{" "}
          {setup.active_run.status.replaceAll("_", " ")}.{" "}
          <Link
            className="text-link"
            href={
              setup.active_run.discovery_id
                ? `/find-leads/${setup.active_run.discovery_id}`
                : `/chat/${setup.active_run.thread_id}`
            }
          >
            Open or stop it
          </Link>{" "}
          to start a new one.
        </div>
      )}
    </>
  );
}

type DiscoveryChoices = {
  providerName: string;
  profileBudget: number;
  quantity: string;
  count: number;
  maximum: number;
  valid: boolean;
  emails: boolean;
  busy: boolean;
};

function DiscoveryOptions({
  providerName,
  profileBudget,
  quantity,
  count,
  maximum,
  valid,
  emails,
  busy,
  setQuantity,
  setEmails,
}: DiscoveryChoices & {
  setQuantity: (value: string) => void;
  setEmails: (value: boolean) => void;
}) {
  return (
    <fieldset className="discovery-options" disabled={busy}>
      <legend className="sr-only">Discovery choices</legend>
      <label className="discovery-label" htmlFor="discovery-count">
        How many leads?
      </label>
      <div className="discovery-counter">
        <button
          className="button"
          type="button"
          aria-label="Decrease lead count"
          disabled={!Number.isInteger(count) || count <= 1}
          onClick={() => setQuantity(String(Math.min(count - 1, maximum)))}
        >
          −
        </button>
        <input
          id="discovery-count"
          className="input"
          type="number"
          inputMode="numeric"
          min={1}
          max={maximum}
          step={1}
          required
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          aria-invalid={!valid}
          aria-describedby="discovery-count-help"
        />
        <button
          className="button"
          type="button"
          aria-label="Increase lead count"
          disabled={!valid || count >= maximum}
          onClick={() => setQuantity(String(count + 1))}
        >
          +
        </button>
      </div>
      <p
        id="discovery-count-help"
        className={valid ? "settings-help" : "error"}
      >
        1–{maximum} per run.
      </p>
      <fieldset className="discovery-email-options">
        <legend className="discovery-label">Email addresses</legend>
        <label className={`discovery-choice${!emails ? " selected" : ""}`}>
          <input
            type="radio"
            name="email-lookup"
            checked={!emails}
            onChange={() => setEmails(false)}
          />
          <span>
            <strong>Don’t find emails</strong>
            <span>{profileBudget ? "Paid search, no emails" : "Free discovery"}</span>
          </span>
        </label>
        <label className={`discovery-choice${emails ? " selected" : ""}`}>
          <input
            type="radio"
            name="email-lookup"
            checked={emails}
            onChange={() => setEmails(true)}
          />
          <span>
            <strong>Find verified emails</strong>
            <span>
              {valid
                ? `Up to ${count} ${providerName} credit${count === 1 ? "" : "s"}`
                : "Pick a count to see the cost"}
            </span>
          </span>
        </label>
      </fieldset>
    </fieldset>
  );
}

function DiscoveryReview({
  providerName,
  profileBudget,
  count,
  valid,
  emails,
  busy,
  canStart,
}: Pick<DiscoveryChoices, "count" | "valid" | "emails" | "busy" | "providerName" | "profileBudget"> & {
  canStart: boolean;
}) {
  const credits = count * (profileBudget + (emails ? 1 : 0));
  return (
    <section className="discovery-review" aria-label="Discovery cost preview">
      <p className="eyebrow">Check before you start</p>
      <div aria-live="polite" aria-atomic="true">
        <h2>
          {valid
            ? `Finding ${count} lead${count === 1 ? "" : "s"}`
            : "Pick a valid count"}
        </h2>
        <dl className="discovery-cost">
          <dt>{profileBudget ? `Max ${providerName} cost (search + emails)` : `${providerName} email cost`}</dt>
          <dd>
            {!valid
              ? "Not estimated"
              : `${credits ? "Up to " : ""}${credits} credit${credits === 1 ? "" : "s"}`}
          </dd>
        </dl>
        <p className="settings-help">
          {emails
            ? "Stops at your email limit. Some people may have no email."
            : "No emails will be bought."}
        </p>
        {profileBudget > 0 && <p className="settings-help">AI Ark charges 0.5 credits per profile, even if it does not fit. Searches up to {count * 2} profiles for up to {count} credits, plus email credits if chosen. You may get fewer leads.</p>}
      </div>
      <p className="discovery-safety">
        <Icon name="check" />
        No outreach emails will be sent.
      </p>
      <p className="settings-help">
        AI use may cost extra.
      </p>
      <button
        className="button primary discovery-start"
        type="submit"
        disabled={!canStart}
      >
        {busy && <span className="operation-status-dot" aria-hidden="true" />}
        {busy ? "Starting…" : "Start finding"}
      </button>
      <p className="settings-help">
        {profileBudget
          ? `Starting approves only these choices and the ${providerName} credit limit above.`
          : "Starting approves only these choices and the credit limit above."}
      </p>
    </section>
  );
}

export default function FindLeads({ user }: { user: Account }) {
  const router = useRouter();
  const [setup, setSetup] = useState<DiscoverySetup | null>(null);
  const [quantity, setQuantity] = useState("3");
  const [emails, setEmails] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const submitting = useRef(false);
  const request = useRef<{ selection: string; id: string } | null>(null);
  const count = Number(quantity);
  const maximum = (emails ? setup?.max_email_count : setup?.max_count) ?? 25;
  const providerName = setup?.provider_name ?? "BetterContact";
  const profileBudget = setup?.profile_budget_per_lead ?? 0;
  const valid = Number.isInteger(count) && count >= 1 && count <= maximum;
  const credits = count * (profileBudget + (emails ? 1 : 0));

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void api<DiscoverySetup>("discovery", { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setSetup(value);
      })
      .catch((caught) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to load discovery setup",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [revision]);

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      submitting.current ||
      loading ||
      !valid ||
      !setup?.ready ||
      setup.active_run
    )
      return;
    submitting.current = true;
    setBusy(true);
    setError("");
    const selection = JSON.stringify([count, emails, setup.revision]);
    if (request.current?.selection !== selection)
      request.current = { selection, id: crypto.randomUUID() };
    try {
      const result = await api<{ run: { id: string } }>("discovery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          count,
          emails,
          estimated_credits: credits,
          revision: setup.revision,
          request_id: request.current.id,
        }),
      });
      // Same durable worker and history as chat, but no model can alter the choices.
      router.push(`/find-leads/${result.run.id}`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to start discovery",
      );
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <Sidebar user={user} active="find-leads" />
      <main className="main">
        <header className="topbar">
          <PageHeading title="Find leads" help="Find people who fit your target. Watch each result live." />
          <Link className="button" href="/target">
            Edit target
          </Link>
        </header>
        <div className="discovery-page">
          <DiscoveryContext setup={setup} loading={loading} />
          <form className="discovery-form" onSubmit={start} aria-busy={busy}>
            <DiscoveryOptions
              providerName={providerName}
              profileBudget={profileBudget}
              quantity={quantity}
              count={count}
              maximum={maximum}
              valid={valid}
              emails={emails}
              busy={busy}
              setQuantity={setQuantity}
              setEmails={setEmails}
            />
            <DiscoveryReview
              providerName={providerName}
              profileBudget={profileBudget}
              count={count}
              valid={valid}
              emails={emails}
              busy={busy}
              canStart={
                !busy &&
                !loading &&
                valid &&
                !!setup?.ready &&
                !setup.active_run
              }
            />
          </form>
          {error && (
            <div className="error discovery-error" role="alert">
              <p>{error}</p>
              <button
                className="button"
                type="button"
                disabled={busy || loading}
                onClick={() => setRevision((value) => value + 1)}
              >
                Refresh setup
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
