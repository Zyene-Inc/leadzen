"use client";
import { HelpTooltip } from "@/components/help-tooltip";
import { SecretInput } from "@/components/secret-input";
import type { Credentials, Settings } from "@/lib/connection-settings";

export function AiConnection({
  settings,
  onChange,
  credentials,
  onCredentials,
  requireCredentials,
  setupMode,
}: {
  settings: Settings;
  onChange: (settings: Settings) => void;
  credentials: Credentials;
  onCredentials: (credentials: Credentials) => void;
  requireCredentials: boolean;
  setupMode: boolean;
}) {
  const llm = (key: keyof Settings["llm"], value: string | boolean) => {
    const next = { ...settings.llm, [key]: value };
    if (key === "enabled" && value === true) {
      next.provider = next.provider || "groq";
      if (!next.model && next.provider === "groq")
        next.model = "openai/gpt-oss-120b";
    }
    onChange({ ...settings, llm: next });
  };
  const credential = (key: keyof Credentials, value: string) =>
    onCredentials({ ...credentials, [key]: value });
  return (
    <section className="panel settings-card">
      <div className="panel-head">
        <h2 className="panel-title">AI connection</h2>
        <HelpTooltip label="AI connection">Use AI to qualify leads and draft messages. Manual campaigns work without it. Saved keys are never displayed.</HelpTooltip>
      </div>
      <label className="check-row">
        <input
          type="checkbox"
          checked={settings.llm.enabled}
          onChange={(e) => llm("enabled", e.target.checked)}
        />
        Use AI for discovery and automated outreach
      </label>
      {settings.llm.enabled && (
        <div className="form-grid">
          <label>
            Provider
            <select
              className="select"
              value={settings.llm.provider}
              onChange={(e) => llm("provider", e.target.value)}
            >
              {[
                "groq",
                "openai",
                "anthropic",
                "google",
                "mistral",
                "cohere",
                "openai_compatible",
              ].map((provider) => (
                <option key={provider} value={provider}>
                  {provider === "openai_compatible"
                    ? "OpenAI-compatible"
                    : provider}
                </option>
              ))}
            </select>
          </label>
          <label>
            Model
            <input
              className="input"
              value={settings.llm.model}
              onChange={(e) => llm("model", e.target.value)}
              required
              maxLength={200}
            />
          </label>
          <SecretInput
            label="AI API key"
            className="input"
            autoComplete="new-password"
            value={credentials.ai}
            onChange={(e) => credential("ai", e.target.value)}
            required={requireCredentials && !settings.llm.api_key_configured}
            maxLength={2000}
            placeholder={
              settings.llm.api_key_configured
                ? "Blank keeps the saved key"
                : "Provider API key"
            }
          />
          <label>
            AI base URL
            <input
              className="input"
              type="url"
              value={settings.llm.base_url}
              onChange={(e) => llm("base_url", e.target.value)}
              required={settings.llm.provider === "openai_compatible"}
              placeholder="https://api.example.com/v1"
            />
          </label>
        </div>
      )}
      <p className="settings-help">
        Custom endpoints need administrator approval.{" "}
        {setupMode &&
          "Testing sends one short request to your model; provider usage charges may apply."}
      </p>
    </section>
  );
}
