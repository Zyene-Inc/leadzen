"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/client-api";
import { checkedDate } from "@/lib/workspace-settings";

type HealthStatus = "pass" | "fail" | "unknown";
type HealthCheck = {
  key: "spf" | "dkim" | "dmarc" | "mx";
  label: string;
  status: HealthStatus;
  message: string;
  steps: string[];
  fix: { type: string; host: string; value: string } | null;
  record: string;
};
export type DomainHealthResult = {
  domain: string;
  state: "passing" | "failing" | "unknown";
  summary: string;
  checks: HealthCheck[];
  checked_at: string;
};

const statusText: Record<HealthStatus, string> = {
  pass: "OK",
  fail: "Fix needed",
  unknown: "Not verified",
};

export function DomainHealth({
  address,
  disabled,
}: {
  address: string;
  disabled: boolean;
}) {
  const [result, setResult] = useState<DomainHealthResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = useRef(false);
  const domain = address.includes("@") ? address.split("@").pop() : "";
  async function run() {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setError("");
    try {
      setResult(
        await api<DomainHealthResult>("settings/domain-health", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not check the domain",
      );
    } finally {
      running.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="central-settings-test domain-health">
      <div className="central-test-status">
        <span role={busy ? "status" : undefined} aria-live="polite">
          {busy
            ? "Checking DNS…"
            : result
              ? result.summary
              : domain
                ? `Domain health for ${domain}`
                : "Domain health"}
        </span>
        {result && !busy && (
          <span>
            Checked{" "}
            <time dateTime={result.checked_at}>
              {checkedDate(result.checked_at)}
            </time>
          </span>
        )}
      </div>
      <button
        className="button"
        type="button"
        disabled={disabled || busy || !domain}
        onClick={() => void run()}
        title="Reads public DNS records. Sends nothing."
      >
        {result ? "Check again" : "Check domain"}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && result.checks.length > 0 && (
        <ul className="domain-health-list" aria-label={`DNS records for ${result.domain}`}>
          {result.checks.map((check) => (
            <li key={check.key} className={`domain-health-item ${check.status}`}>
              <div className="domain-health-head">
                <strong>{check.label}</strong>
                <span className="domain-health-status">
                  {statusText[check.status]}
                </span>
              </div>
              <p>{check.message}</p>
              {check.status !== "pass" && check.steps.length > 0 && (
                <details>
                  <summary>How to fix</summary>
                  <ol>
                    {check.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                  {check.fix && (
                    <dl className="domain-health-fix">
                      <dt>Type</dt>
                      <dd>{check.fix.type}</dd>
                      <dt>Host</dt>
                      <dd>
                        <code>{check.fix.host}</code>
                      </dd>
                      <dt>Value</dt>
                      <dd>
                        <code>{check.fix.value}</code>
                      </dd>
                    </dl>
                  )}
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
