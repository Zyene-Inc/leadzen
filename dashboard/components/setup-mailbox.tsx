"use client";
import { HelpText } from "@/components/help-tooltip";
import type { Settings } from "@/lib/connection-settings";

const presets = [
  [
    "zoho",
    "Zoho Mail — paid organization (US)",
    "smtppro.zoho.com",
    "imappro.zoho.com",
    "465",
  ],
  [
    "gmail",
    "Gmail / Google Workspace",
    "smtp.gmail.com",
    "imap.gmail.com",
    "465",
  ],
  [
    "microsoft",
    "Microsoft 365",
    "smtp.office365.com",
    "outlook.office365.com",
    "587",
  ],
];
export function SetupMailboxPreset({
  settings,
  onChange,
}: {
  settings: Settings;
  onChange: (settings: Settings) => void;
}) {
  const selected =
    presets.find(
      (preset) =>
        preset[2] === settings.mailbox.smtp_host &&
        preset[3] === settings.mailbox.imap_host,
    )?.[0] ?? "custom";
  return (
    <section className="panel settings-card">
      <div className="panel-head">
        <h2 className="panel-title">Email account</h2>
      </div>
      <div className="form-grid">
        <label>
          Mailbox provider
          <select
            className="select"
            value={selected}
            onChange={(event) => {
              const preset = presets.find(
                (entry) => entry[0] === event.target.value,
              );
              if (!preset) {
                onChange({
                  ...settings,
                  mailbox: {
                    ...settings.mailbox,
                    smtp_host: "",
                    imap_host: "",
                  },
                });
                return;
              }
              onChange({
                ...settings,
                mailbox: {
                  ...settings.mailbox,
                  transport: "smtp",
                  api_url: "",
                  smtp_host: preset[2],
                  imap_host: preset[3],
                  smtp_port: preset[4],
                  imap_port: "993",
                },
              });
            }}
          >
            <option value="custom">
              Other provider or Zoho region
            </option>
            {presets.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <HelpText label="Server settings">Pick a preset, or enter the SMTP/IMAP servers from your email provider. Zoho servers differ by region. Port 465 uses TLS.</HelpText>
      <HelpText label="App passwords & access">Use an app password if your provider asks for one. Some providers need OAuth or admin approval and may not work with a password alone.</HelpText>
    </section>
  );
}
