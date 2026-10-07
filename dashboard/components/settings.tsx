"use client";
import { HelpTooltip } from "@/components/help-tooltip";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { WorkspacePage } from "@/components/workspace-records";
import { SettingsEditor } from "@/components/settings-editor";
import { SettingsTest } from "@/components/settings-test";
import { SettingsData } from "@/components/settings-data";
import { MCPConnections } from "@/components/mcp-connections";
import type { Account } from "@/lib/auth";
import { useStoredData } from "@/lib/use-stored-data";
import {
  settingSections,
  settingSummary,
  settingTitles,
  type SettingSection,
  type WorkspaceSettings,
} from "@/lib/workspace-settings";

const sectionHelp: Record<SettingSection, string> = {
  ai: "Connect a model for discovery, qualification and drafting. Manual campaigns work without AI. Provider usage can incur charges.",
  finder: "Choose BetterContact or AI Ark for profiles and verified work emails. You can also add or import contacts yourself.",
  identity: "Your outreach name and email. These do not change your login or sending mailbox.",
  mailbox: "The account used to send email and check replies. Test the connection after changing it.",
  schedule: "Choose outreach days and hours in New York (Eastern Time). Daylight saving time adjusts automatically. Daily Autopilot uses the same selected days and start time for lead discovery. Changes require reviewing automatic approvals again.",
  product: "Describe what you offer and who it helps. This guides qualification and email drafts.",
  target: "Choose the people and companies to find. Changes apply to new searches.",
  signature: "Added to outgoing emails unless a campaign supplies its own signature.",
  booking: "An optional scheduling URL. Insert the booking-link tag where you want it in a campaign.",
};

function SettingsRow({
  section,
  data,
  editing,
  edit,
  close,
  saved,
  locked,
}: {
  section: SettingSection;
  data: WorkspaceSettings;
  editing: boolean;
  edit: () => void;
  close: () => void;
  saved: (data: WorkspaceSettings) => void;
  locked: boolean;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const previouslyEditing = useRef(false);
  useEffect(() => {
    if (previouslyEditing.current && !editing) button.current?.focus();
    previouslyEditing.current = editing;
  }, [editing]);
  const summary = settingSummary(section, data);
  const testKind =
    section === "finder"
      ? "discovery"
      : section === "ai" || section === "mailbox"
        ? section
        : null;
  function cancel() {
    close();
  }
  return (
    <section className="central-settings-section" id={section === "schedule" ? "sending-hours" : undefined}>
      <div className="central-settings-row">
        <div className="central-settings-label"><h2>{settingTitles[section]}</h2><HelpTooltip label={settingTitles[section]}>{sectionHelp[section]}</HelpTooltip></div>
        <div className="central-settings-value">
          <strong>{summary.main}</strong>
          {summary.detail && <p>{summary.detail}</p>}
        </div>
        <button
          ref={button}
          className="button"
          type="button"
          data-tour={section === "schedule" ? editing ? "schedule-close" : "schedule-edit" : undefined}
          aria-label={`Edit ${settingTitles[section]}`}
          aria-expanded={editing}
          disabled={busy || (locked && !editing)}
          onClick={editing ? cancel : edit}
        >
          {editing ? "Close" : "Edit"}
        </button>
      </div>
      {!editing && testKind && (
        <SettingsTest
          kind={testKind}
          data={data}
          disabled={locked}
          saved={saved}
        />
      )}
      {editing && (
        <SettingsEditor
          section={section}
          data={data}
          cancel={cancel}
          onBusy={setBusy}
          saved={(next) => {
            saved(next);
            cancel();
          }}
        />
      )}
    </section>
  );
}
export default function SettingsPage({ user }: { user: Account }) {
  const { data, setData, loading, error, refresh } =
    useStoredData<WorkspaceSettings>("settings");
  const [editing, setEditing] = useState<SettingSection | null>(null);
  const [notice, setNotice] = useState("");
  function saved(next: WorkspaceSettings) {
    setData(next);
    setNotice("Settings updated.");
  }
  return (
    <WorkspacePage
      user={user}
      active="settings"
      title="Settings"
      description="Your connections, identity, product, audience and data in one place."
      actions={
        <Link className="button" data-tour="tour-restart" href="/tour">
          Take Product Tour
        </Link>
      }
    >
      {error && (
        <div className="error" role="alert">
          {error}
          <button className="button" type="button" onClick={refresh}>
            Try again
          </button>
        </div>
      )}
      {notice && (
        <div className="success" role="status">
          {notice}
        </div>
      )}
      {loading && !data && <div className="skeleton" />}
      {data && (
        <div className="central-settings">
          <MCPConnections />
          {settingSections.map((section) => (
            <SettingsRow
              key={section}
              section={section}
              data={data}
              editing={editing === section}
              edit={() => {
                setNotice("");
                setEditing(section);
              }}
              close={() => setEditing(null)}
              saved={saved}
              locked={editing !== null}
            />
          ))}
          <SettingsData data={data} />
        </div>
      )}
    </WorkspacePage>
  );
}
