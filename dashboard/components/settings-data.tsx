"use client";
import { HelpTooltip } from "@/components/help-tooltip";
import { useRef, useState } from "react";
import { databaseSize, type WorkspaceSettings } from "@/lib/workspace-settings";

export function SettingsData({ data }: { data: WorkspaceSettings }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const submitting = useRef(false);
  async function backup() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/proxy/settings/backup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true }),
        cache: "no-store",
      });
      if (!response.ok) {
        if (response.status === 401) window.location.assign("/login");
        const result = await response.json();
        throw new Error(result.error || "Unable to create backup");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download =
        response.headers
          .get("Content-Disposition")
          ?.match(/filename="([^"]+)"/)?.[1] || "leadzen-workspace.sqlite3";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("Workspace backup downloaded.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to create backup",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="central-settings-section">
      <div className="central-settings-row">
        <div className="central-settings-label"><h2>Data</h2><HelpTooltip label="Workspace backup">Downloads this workspace’s configuration, leads and messages. Restoring encrypted connections also requires the server’s settings key.</HelpTooltip></div>
        <div className="central-settings-value">
          <strong>Local database</strong>
          <p>
            {data.workspace.data.engine} ·{" "}
            {databaseSize(data.workspace.data.size_bytes)} · Combined finder and
            sender data
          </p>
          <details className="central-data-details"><summary>Storage details</summary><code>{data.workspace.data.path}</code></details>
        </div>
        <button
          className="button"
          type="button"
          disabled={busy}
          onClick={() => void backup()}
        >
          {busy ? "Creating backup…" : "Backup Database"}
        </button>
      </div>
      <p className="central-data-note">
        Backups contain private workspace data. Keep them secure.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
    </section>
  );
}
