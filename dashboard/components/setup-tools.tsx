"use client";
import { Connections } from "@/components/connections";
import { SetupMailboxPreset } from "@/components/setup-mailbox";
import { SetupConnectionCheck } from "@/components/setup-connection-check";
import type { Credentials, Settings } from "@/lib/connection-settings";
import type { CheckKind, Wizard } from "@/lib/setup-wizard";

const kinds: Record<number, CheckKind> = {
  1: "ai",
  2: "discovery",
  4: "mailbox",
};
const sections = { ai: "ai", discovery: "finder", mailbox: "mailbox" } as const;
export function SetupTools({
  step,
  settings,
  credentials,
  checks,
  discoveryEnabled,
  testing,
  onSettings,
  onCredentials,
  onDiscovery,
  onTest,
}: {
  step: number;
  settings: Settings;
  credentials: Credentials;
  checks: Wizard["checks"];
  discoveryEnabled: boolean;
  testing: boolean;
  onSettings: (settings: Settings) => void;
  onCredentials: (credentials: Credentials) => void;
  onDiscovery: (enabled: boolean) => void;
  onTest: (kind: CheckKind) => void;
}) {
  const kind = kinds[step];
  const showCheck =
    kind === "ai"
      ? settings.llm.enabled
      : kind === "discovery"
        ? discoveryEnabled
        : true;
  return (
    <>
      {kind === "mailbox" && (
        <SetupMailboxPreset settings={settings} onChange={onSettings} />
      )}
      {kind === "discovery" && (
        <label className="setup-manual-choice">
          <input
            type="checkbox"
            checked={!discoveryEnabled}
            onChange={(event) => onDiscovery(!event.target.checked)}
          />
          I’ll add contacts myself for now
        </label>
      )}
      {(kind !== "discovery" || discoveryEnabled) && (
        <Connections
          settings={settings}
          credentials={credentials}
          onChange={onSettings}
          onCredentials={onCredentials}
          sections={[sections[kind]]}
          setupMode
        />
      )}
      {kind === "discovery" && (
        <div className="setup-credit-guide">
          <div>
            <strong>Finding people</strong>
            <span>{settings.lead_finder.provider === "ai_ark" ? "0.5 credits per returned profile" : "Free"}</span>
          </div>
          <div>
            <strong>Checked work email</strong>
            <span>1 credit per checked email</span>
          </div>
          <p>
            Emails are optional. Costs may vary by your provider’s plan.
          </p>
        </div>
      )}
      {showCheck && (
        <SetupConnectionCheck
          kind={kind}
          check={checks[kind]}
          busy={testing}
          onTest={() => onTest(kind)}
          model={`${settings.llm.provider}:${settings.llm.model}`}
        />
      )}
      {kind === "ai" && !settings.llm.enabled && (
        <p className="setup-note">
          Manual campaigns work without AI. Finding leads and Chat need AI.
        </p>
      )}
    </>
  );
}
