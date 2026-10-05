"use client";
import { Icon } from "@/components/icon";
import type { CheckKind, ConnectionCheck } from "@/lib/setup-wizard";

export function SetupConnectionCheck({
  kind,
  check,
  model,
  busy,
  onTest,
}: {
  kind: CheckKind;
  check?: ConnectionCheck;
  model: string;
  busy: boolean;
  onTest: () => void;
}) {
  const label = kind === "mailbox" ? "Test mailbox" : "Test connection";
  return (
    <div className="setup-connection-check">
      <button
        type="button"
        className="button secondary"
        onClick={onTest}
        disabled={busy}
      >
        {busy ? "Testing…" : label}
      </button>
      <div
        role="status"
        aria-live="polite"
        className={
          check?.connected ? "setup-check-success" : "setup-check-pending"
        }
      >
        {check?.connected ? (
          <>
            <Icon name="check" />
            <div>
              {kind === "ai" && (
                <>
                  <strong>Connected — the model answered</strong>
                  <span>{model}</span>
                </>
              )}
              {kind === "discovery" && (
                <>
                  <strong>Connected</strong>
                  <span>
                    Credits available: {check.credits ?? "Not returned"}
                  </span>
                </>
              )}
              {kind === "mailbox" && (
                <>
                  <strong>
                    {check.smtp
                      ? "SMTP connected · IMAP connected"
                      : "IMAP connected"}
                  </strong>
                  <span>
                    {check.smtp
                      ? "Ready to send, subject to consent and sending rules. No test email was sent."
                      : "Sending API credentials saved. Delivery was not tested; no email was sent."}
                  </span>
                </>
              )}
              {check.synthetic && (
                <span className="setup-synthetic">
                  Synthetic local test — no external provider calls
                </span>
              )}
            </div>
          </>
        ) : (
          <span>Not tested for these settings. Test before continuing.</span>
        )}
      </div>
    </div>
  );
}
