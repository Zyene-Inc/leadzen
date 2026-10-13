"use client";
import { HelpTooltip } from "@/components/help-tooltip";
import { SecretInput } from "@/components/secret-input";
import { AiConnection } from "@/components/ai-connection";
import type { Credentials, Settings } from "@/lib/connection-settings";

export function Connections({
  settings,
  onChange,
  credentials,
  onCredentials,
  requireCredentials = false,
  sections = ["ai", "finder", "mailbox"],
  setupMode = false,
  includeSignature = true,
}: {
  settings: Settings;
  onChange: (next: Settings) => void;
  credentials: Credentials;
  onCredentials: (next: Credentials) => void;
  requireCredentials?: boolean;
  sections?: ("ai" | "finder" | "mailbox")[];
  setupMode?: boolean;
  includeSignature?: boolean;
}) {
  const mail = (key: keyof Settings["mailbox"], value: string) =>
    onChange({ ...settings, mailbox: { ...settings.mailbox, [key]: value } });
  const credential = (
    key: "ai" | "smtp" | "mailApi" | "imap" | "bettercontact" | "aiArk",
    value: string,
  ) => onCredentials({ ...credentials, [key]: value });
  const smtp = settings.mailbox.transport === "smtp";
  const ark = settings.lead_finder.provider === "ai_ark";
  const providerName = ark ? "AI Ark" : "BetterContact";
  const removing = ark ? credentials.clearAiArk : credentials.clearBettercontact;
  function transport(value: string) {
    const url =
      value === "resend"
        ? "https://api.resend.com/emails"
        : value === "sendgrid"
          ? "https://api.sendgrid.com/v3/mail/send"
          : value === "zeptomail"
            ? "https://api.zeptomail.com/v1.1/email"
            : "";
    onChange({
      ...settings,
      mailbox: {
        ...settings.mailbox,
        transport: value,
        api_url: url,
        api_key_configured: false,
      },
    });
    onCredentials({ ...credentials, mailApi: "" });
  }
  return (
    <>
      {sections.includes("finder") && (
        <section className="panel settings-card">
          <div className="panel-head">
            <h2 className="panel-title">Lead finding</h2>
            <span className="panel-meta">{providerName}</span>
          </div>
          <p className="settings-help" id="bettercontact-help">
            {setupMode ? (
              "Testing checks your balance. It buys nothing."
            ) : (
              <>
                Not needed for imported contacts. Saving a key costs nothing.
              </>
            )}
          </p>
          <div className="form-grid">
            <label className="wide">Lead provider
              <select className="select" value={settings.lead_finder.provider} onChange={(event) => {
                const provider = event.target.value as Settings["lead_finder"]["provider"];
                onChange({ ...settings, lead_finder: { ...settings.lead_finder, provider,
                  api_key_configured: settings.lead_finder.configured_providers?.[provider] ?? false } });
              }}>
                <option value="bettercontact">BetterContact</option>
                <option value="ai_ark">AI Ark</option>
              </select>
            </label>
            <SecretInput
              label={`${providerName} API key`}
              containerClassName="wide"
              className="input"
              autoComplete="new-password"
              value={ark ? credentials.aiArk ?? "" : credentials.bettercontact}
              onChange={(e) => credential(ark ? "aiArk" : "bettercontact", e.target.value)}
              maxLength={2000}
              disabled={removing}
              aria-describedby="bettercontact-help bettercontact-status"
              placeholder={
                settings.lead_finder?.api_key_configured
                  ? "Blank keeps the saved key"
                  : `Paste your ${providerName} API key`
              }
            />
          </div>
          <p className="settings-help" id="bettercontact-status">
            {removing
              ? "The key will be removed when you save."
              : settings.lead_finder?.api_key_configured
                ? "Key saved. Enter a new one to replace it."
                : "No key saved. You can add it later."}{" "}
            <a
              href={ark ? "https://app.ai-ark.com/" : "https://app.bettercontact.rocks/api_requests"}
              target="_blank"
              rel="noopener noreferrer"
            >
              Get your {providerName} API key
            </a>
          </p>
          {!setupMode && settings.lead_finder?.api_key_configured && (
            <label className="check-row">
              <input
                type="checkbox"
                checked={removing ?? false}
                onChange={(e) =>
                  onCredentials({
                    ...credentials,
                    [ark ? "clearAiArk" : "clearBettercontact"]: e.target.checked,
                    [ark ? "aiArk" : "bettercontact"]: "",
                  })
                }
              />
              Remove the saved {providerName} key when I save
            </label>
          )}
          <p className="settings-help">Only the chosen provider is used. The other key stays saved.{ark && " AI Ark costs 0.5 credits per profile and up to 1 credit per checked email. You see the cost before each search. Daily Autopilot needs BetterContact."}</p>
        </section>
      )}
      {sections.includes("ai") && (
        <AiConnection
          settings={settings}
          onChange={onChange}
          credentials={credentials}
          onCredentials={onCredentials}
          requireCredentials={requireCredentials}
          setupMode={setupMode}
        />
      )}
      {sections.includes("mailbox") && (
        <>
          <section className="panel settings-card">
            <div className="panel-head">
              <h2 className="panel-title">Email sending</h2><HelpTooltip label="Sending provider">Use a verified domain and a provider that allows your email type. Other APIs must accept the Resend format and return an email ID.</HelpTooltip>
            </div>
            <div className="form-grid">
              <label>
                Send through
                <select
                  className="select"
                  value={settings.mailbox.transport}
                  onChange={(e) => transport(e.target.value)}
                >
                  <option value="smtp">SMTP mailbox / relay</option>
                  <option value="resend">
                    Resend API — opted-in recipients
                  </option>
                  <option value="sendgrid">SendGrid API</option>
                  <option value="zeptomail">
                    Zoho ZeptoMail — transactional only
                  </option>
                  <option value="compatible">
                    Resend-compatible email API
                  </option>
                </select>
              </label>
              <label>
                Sending email
                <input
                  className="input"
                  type="email"
                  required
                  value={settings.mailbox.address}
                  onChange={(e) => mail("address", e.target.value)}
                  maxLength={150}
                />
              </label>
              {smtp ? (
                <>
                  <label>
                    SMTP host
                    <input
                      className="input"
                      value={settings.mailbox.smtp_host}
                      onChange={(e) => mail("smtp_host", e.target.value)}
                      required
                      placeholder="smtp.zoho.com"
                    />
                  </label>
                  <div className="secret-field">
                    <label htmlFor="smtp-port">SMTP port</label>
                    <input
                      id="smtp-port"
                      className="input"
                      type="number"
                      value={settings.mailbox.smtp_port ?? "587"}
                      onChange={(e) => mail("smtp_port", e.target.value)}
                      required
                      min={1}
                      max={65535}
                      aria-describedby="smtp-port-help"
                    />
                    <span className="settings-help" id="smtp-port-help">
                      465: TLS · 587 or 2525: STARTTLS
                    </span>
                  </div>
                  <label>
                    SMTP username (optional)
                    <input
                      className="input"
                      value={settings.mailbox.smtp_username}
                      onChange={(e) => mail("smtp_username", e.target.value)}
                      placeholder="Defaults to your sending email"
                      maxLength={320}
                    />
                  </label>
                  <SecretInput
                    label="SMTP app password"
                    className="input"
                    autoComplete="new-password"
                    value={credentials.smtp}
                    onChange={(e) => credential("smtp", e.target.value)}
                    required={
                      requireCredentials &&
                      !settings.mailbox.password_configured
                    }
                    maxLength={2000}
                    placeholder={
                      settings.mailbox.password_configured
                        ? "Blank keeps the saved password"
                        : "Email account password"
                    }
                  />
                </>
              ) : (
                <>
                  <label>
                    Email API URL
                    <input
                      className="input"
                      type="url"
                      value={settings.mailbox.api_url}
                      onChange={(e) => mail("api_url", e.target.value)}
                      required
                      readOnly={
                        settings.mailbox.transport === "resend" ||
                        settings.mailbox.transport === "sendgrid"
                      }
                    />
                  </label>
                  <SecretInput
                    label="Email API key"
                    className="input"
                    autoComplete="new-password"
                    value={credentials.mailApi}
                    onChange={(e) => credential("mailApi", e.target.value)}
                    required={
                      requireCredentials && !settings.mailbox.api_key_configured
                    }
                    maxLength={2000}
                    placeholder={
                      settings.mailbox.api_key_configured
                        ? "Blank keeps the saved key"
                        : "Email provider API key"
                    }
                  />
                </>
              )}
              {includeSignature && <label className="wide">
                Email signature
                <textarea
                  className="input textarea"
                  rows={3}
                  value={settings.mailbox.signature}
                  onChange={(e) => mail("signature", e.target.value)}
                  maxLength={10000}
                />
              </label>}
            </div>
            {settings.mailbox.transport === "resend" && (
              <p className="settings-help">
                Resend needs recipient opt-in. No cold outreach. Record opt-in
                when you add contacts.
              </p>
            )}
            {settings.mailbox.transport === "zeptomail" && (
              <p className="settings-help">
                ZeptoMail is for transactional emails only. Outreach and
                follow-ups are blocked.
              </p>
            )}

          </section>
          <section className="panel settings-card">
            <div className="panel-head">
              <h2 className="panel-title">Reply inbox</h2>
              <HelpTooltip label="Reply inbox">LeadZen reads this inbox to find replies and stop follow-ups.</HelpTooltip>
            </div>
            <div className="form-grid">
              <label>
                IMAP host
                <input
                  className="input"
                  value={settings.mailbox.imap_host}
                  onChange={(e) => mail("imap_host", e.target.value)}
                  placeholder="imap.zoho.com"
                />
              </label>
              <label>
                IMAP port
                <input
                  className="input"
                  type="number"
                  value={settings.mailbox.imap_port ?? "993"}
                  onChange={(e) => mail("imap_port", e.target.value)}
                  min={1}
                  max={65535}
                />
              </label>
              <SecretInput
                label="IMAP app password"
                containerClassName="wide"
                className="input"
                autoComplete="new-password"
                value={credentials.imap}
                onChange={(e) => credential("imap", e.target.value)}
                maxLength={2000}
                placeholder={
                  smtp
                    ? "Blank uses the SMTP password"
                    : settings.mailbox.imap_password_configured
                      ? "Blank keeps the saved password"
                      : "Inbox password"
                }
              />
            </div>
            <p className="settings-help">
              Use your sending email’s inbox. Follow-ups pause if it cannot be read.
            </p>
          </section>
        </>
      )}
    </>
  );
}
