"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/client-api";
import type { CheckKind } from "@/lib/setup-wizard";
import { checkedDate, type WorkspaceSettings } from "@/lib/workspace-settings";

const testDetails: Record<CheckKind, string> = {
  ai: "Sends one short AI request with your saved key. Your AI provider may charge for it.",
  discovery:
    "Checks your lead provider balance with your saved key. Buys nothing.",
  mailbox:
    "Signs in to your saved email account. Sends nothing and reads no emails.",
};
function isConfigured(kind: CheckKind, data: WorkspaceSettings) {
  if (kind === "ai") return data.llm.enabled && data.llm.api_key_configured;
  if (kind === "discovery") return data.lead_finder.api_key_configured;
  return Boolean(
    data.mailbox.address &&
    (data.mailbox.password_configured || data.mailbox.api_key_configured),
  );
}
export function SettingsTest({
  kind,
  data,
  disabled,
  saved,
}: {
  kind: CheckKind;
  data: WorkspaceSettings;
  disabled: boolean;
  saved: (data: WorkspaceSettings) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const submitting = useRef(false);
  const button = useRef<HTMLButtonElement>(null);
  const previouslyOpen = useRef(false);
  useEffect(() => {
    if (!busy) {
      if (previouslyOpen.current && !open) button.current?.focus();
      previouslyOpen.current = open;
    }
  }, [open, busy]);
  const check = data.workspace.checks[kind];
  const configured = isConfigured(kind, data);
  function close() {
    setOpen(false);
    setError("");
  }
  async function test() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("onboarding/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind }),
      });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not run the test",
      );
      submitting.current = false;
      setBusy(false);
      return;
    }
    try {
      saved(await api<WorkspaceSettings>("settings"));
      close();
    } catch {
      // The test itself passed; only the follow-up refresh failed.
      setOpen(false);
      setNotice("Test passed. Reload to see the new status.");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="central-settings-test">
      <div className="central-test-status">
        <span
          className={check.connected ? "connected" : ""}
          role={busy ? "status" : undefined}
          aria-live={busy ? "polite" : undefined}
        >
          {busy
            ? "Testing…"
            : check.connected
              ? "Connected ✓"
              : configured
                ? "Not tested"
                : "Not set up"}
        </span>
        {check.tested_at && (
          <span>
            Checked <time dateTime={check.tested_at}>{checkedDate(check.tested_at)}</time>
            {check.synthetic ? " · Local preview" : ""}
          </span>
        )}
      </div>
      <button
        ref={button}
        className="button"
        type="button"
        disabled={disabled || !configured || busy}
        aria-expanded={open}
        onClick={() => {
          setError("");
          setNotice("");
          setOpen(!open);
        }}
      >
        Test
      </button>
      {notice && (
        <p className="settings-help" role="status">
          {notice}
        </p>
      )}
      {open && (
        <div className="central-test-confirm">
          <p>{testDetails[kind]}</p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div className="central-settings-actions">
            <button
              className="button"
              type="button"
              disabled={busy}
              onClick={close}
            >
              Cancel test
            </button>
            <button
              className="button primary"
              type="button"
              disabled={busy || disabled}
              onClick={() => void test()}
            >
              {busy ? "Testing…" : "Confirm test"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
