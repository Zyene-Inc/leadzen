"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Connections } from "@/components/connections";
import { SetupIdentity } from "@/components/setup-profile";
import { SetupAudience } from "@/components/setup-audience";
import { SendingScheduleEditor } from "@/components/sending-schedule-editor";
import { defaultSendingSchedule, normalizeSendingSchedule, scheduleError } from "@/lib/sending-schedule";
import {
  emptyCredentials,
  type Settings,
} from "@/lib/connection-settings";
import { api } from "@/lib/client-api";
import { initialDraft, stepValues } from "@/lib/setup-wizard";
import {
  settingTitles,
  type SettingSection,
  type WorkspaceSettings,
} from "@/lib/workspace-settings";

export function SettingsEditor({
  section,
  data,
  saved,
  cancel,
  onBusy,
}: {
  section: SettingSection;
  data: WorkspaceSettings;
  saved: (data: WorkspaceSettings) => void;
  cancel: () => void;
  onBusy: (busy: boolean) => void;
}) {
  // Each opening gets its own editable copy; closing discards this draft.
  const [connections, setConnections] = useState<Settings>(() => ({
    llm: { ...data.llm },
    mailbox: { ...data.mailbox },
    lead_finder: { ...data.lead_finder },
    settings_key_configured: data.settings_key_configured,
  }));
  const [credentials, setCredentials] = useState(emptyCredentials);
  const [draft, setDraft] = useState(() =>
    initialDraft({
      draft: {
        ...data.workspace.identity,
        ...data.workspace.product,
        booking_link: data.workspace.booking_link,
        ...(data.workspace.target.audience
          ? { audience: data.workspace.target.audience }
          : {}),
        confirmed: false,
        accepted_legal_notice: data.workspace.target.accepted_legal_notice,
      },
    }),
  );
  const [busy, setBusy] = useState(false);
  const [schedule, setSchedule] = useState(() => normalizeSendingSchedule(data.workspace.sending_schedule ?? defaultSendingSchedule()));
  const [error, setError] = useState("");
  const submitting = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const isConnection =
    section === "ai" ||
    section === "finder" ||
    section === "mailbox" ||
    section === "signature";
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (section === "schedule") {
      const invalid = scheduleError(schedule);
      if (invalid) { setError(invalid); return; }
    }
    submitting.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    let body: object;
    // Only the open editor may update its section. A stale snapshot from another
    // tab must not overwrite unrelated connections or the signature.
    if (section === "ai") body = { llm: { enabled: connections.llm.enabled, provider: connections.llm.provider, model: connections.llm.model, base_url: connections.llm.base_url, api_key: credentials.ai } };
    else if (section === "finder") body = { lead_finder: { provider: "bettercontact", api_key: credentials.bettercontact, clear_api_key: credentials.clearBettercontact } };
    else if (section === "signature") body = { mailbox: { signature: connections.mailbox.signature } };
    else if (section === "mailbox") {
      const { transport, api_url, smtp_username, address, smtp_host, smtp_port, imap_host, imap_port } = connections.mailbox;
      body = { mailbox: { transport, api_url, smtp_username, address, smtp_host, smtp_port, imap_host, imap_port, password: credentials.smtp, api_key: credentials.mailApi, imap_password: credentials.imap } };
    }
    else if (section === "schedule") body = { workspace_updates: { sending_schedule: normalizeSendingSchedule(schedule) } };
    else if (section === "identity")
      body = { workspace_updates: { identity: stepValues(3, draft) } };
    else if (section === "target")
      body = { workspace_updates: { target: stepValues(6, draft) } };
    else if (section === "product")
      body = {
        workspace_updates: {
          product: {
            product_name: draft.product_name,
            product_docs: draft.product_docs,
          },
        },
      };
    else body = { workspace_updates: { booking_link: draft.booking_link } };
    try {
      saved(
        await api<WorkspaceSettings>("settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to save settings",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <form className="central-settings-editor" data-tour={section === "schedule" ? "schedule-editor" : undefined} onSubmit={save} onKeyDown={(event) => { if (event.key === "Escape" && !busy) { event.preventDefault(); cancel(); } }}>
      <h3 ref={heading} tabIndex={-1}>
        Edit {settingTitles[section]}
      </h3>
      <fieldset disabled={busy}>
        {section === "schedule" && <SendingScheduleEditor value={schedule} onChange={setSchedule} />}
        {section === "identity" && (
          <SetupIdentity
            draft={draft}
            countries={data.workspace.countries}
            onChange={setDraft}
          />
        )}
        {section === "target" && (
          <SetupAudience
            draft={draft}
            countries={data.workspace.countries}
            onChange={setDraft}
          />
        )}
        {(section === "ai" ||
          section === "finder" ||
          section === "mailbox") && (
          <Connections
            settings={connections}
            onChange={setConnections}
            credentials={credentials}
            onCredentials={setCredentials}
            sections={[section]}
            includeSignature={false}
          />
        )}
        {section === "product" && (
          <div className="form-grid">
            <label className="wide">
              Product name
              <input
                className="input"
                maxLength={160}
                value={draft.product_name}
                onChange={(event) =>
                  setDraft({ ...draft, product_name: event.target.value })
                }
              />
            </label>
            <label className="wide">
              Describe your product
              <textarea
                className="input textarea"
                required
                rows={4}
                maxLength={10000}
                value={draft.product_docs}
                onChange={(event) =>
                  setDraft({ ...draft, product_docs: event.target.value })
                }
              />
            </label>
          </div>
        )}
        {section === "signature" && (
          <label>
            Email signature
            <textarea
              className="input textarea"
              rows={5}
              maxLength={10000}
              value={connections.mailbox.signature}
              onChange={(event) =>
                setConnections({
                  ...connections,
                  mailbox: {
                    ...connections.mailbox,
                    signature: event.target.value,
                  },
                })
              }
            />
          </label>
        )}
        {section === "booking" && (
          <label>
            Booking link (optional)
            <input
              className="input"
              type="url"
              maxLength={500}
              placeholder="https://…"
              value={draft.booking_link}
              onChange={(event) =>
                setDraft({ ...draft, booking_link: event.target.value })
              }
            />
          </label>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="central-settings-actions">
          <button className="button" type="button" onClick={cancel}>
            Cancel
          </button>
          <button
            className="button primary"
            type="submit"
            disabled={isConnection && !data.settings_key_configured}
          >
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </fieldset>
    </form>
  );
}
