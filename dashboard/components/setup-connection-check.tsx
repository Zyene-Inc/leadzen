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
  const label = kind === "mailbox" ? "Test email account" : "Test connection";
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
                  <strong>Connected. The AI answered.</strong>
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
                      ? "Ready to send. No test email was sent."
                      : "Sending key saved. Sending was not tested. No email was sent."}
                  </span>
                </>
              )}
              {check.synthetic && (
                <span className="setup-synthetic">
                  Local test only. No outside calls.
                </span>
              )}
            </div>
          </>
        ) : (
          <span>Not tested yet. Test before you continue.</span>
        )}
      </div>
    </div>
  );
}
