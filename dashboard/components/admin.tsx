"use client";
import { PageHeading } from "@/components/page-heading";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Sidebar } from "@/components/sidebar";
import { EmployeeRow } from "@/components/employee-row";
import { Icon } from "@/components/icon";
import type { Account } from "@/lib/auth";
import { api } from "@/lib/client-api";
type Team = {
  users: Account[];
  totals: { users: number; active: number; admins: number; onboarded: number };
};

export default function Admin({ user }: { user: Account }) {
  const [team, setTeam] = useState<Team | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const load = useCallback(async () => {
    try {
      setTeam(await api<Team>("admin/users"));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load employees",
      );
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  async function action(
    task: () => Promise<{ invitation_status?: string }>,
    success: string,
  ) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await task();
      if (result.invitation_status === "failed")
        setError(
          "Account saved, but the invite email may not have sent. Check Resend and the sender, then choose Resend invite.",
        );
      else setNotice(success);
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not update employee",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = JSON.stringify(
      Object.fromEntries(new FormData(event.currentTarget)),
    );
    await action(
      () =>
        api("admin/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        }),
      "Invite sent. The employee sets their own password. The link lasts 48 hours.",
    );
  }
  function invite(account: Account) {
    if (
      !account.invitation_pending &&
      !window.confirm(
        `Send a password reset link to ${account.email}? They will be signed out.`,
      )
    )
      return;
    void action(
      () => api(`admin/users/${account.id}/invite`, { method: "POST" }),
      "Invite sent. Old links no longer work.",
    );
  }
  function update(account: Account, remove = false) {
    if (
      remove &&
      !window.confirm(
        `Delete ${account.email}? They lose access. Outreach history is kept.`,
      )
    )
      return;
    void action(
      () =>
        api(`admin/users/${account.id}`, {
          method: remove ? "DELETE" : "PUT",
          headers: { "Content-Type": "application/json" },
          body: remove
            ? undefined
            : JSON.stringify({ is_active: !account.is_active }),
        }),
      remove ? "Employee deleted. Access removed." : "Access updated.",
    );
  }
  const filtered =
    team?.users.filter((account) =>
      `${account.name} ${account.email}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) ?? [];
  return (
    <div className="shell">
      <Sidebar user={user} active="admin" />
      <main className="main">
        <div className="topbar">
          <PageHeading title="Employee accounts" help="Invite people, manage access and see who finished setup." />
          <button
            type="button"
            className="button primary"
            disabled={busy}
            onClick={() => setCreating(!creating)}
            aria-expanded={creating}
            aria-controls={creating ? "create-employee" : undefined}
          >
            <Icon name={creating ? "close" : "plus"} />
            {creating ? "Close" : "Add employee"}
          </button>
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="success" role="status">
            {notice}
          </div>
        )}
        <section className="metrics" aria-label="Employee totals">
          {(
            [
              ["Total", team?.totals.users],
              ["Active", team?.totals.active],
              ["Admins", team?.totals.admins],
              ["Setup done", team?.totals.onboarded],
            ] as const
          ).map(([label, count]) => (
            <div className="metric" key={label}>
              <div className="metric-label">{label}</div>
              <div className="metric-value">{count ?? "…"}</div>
            </div>
          ))}
        </section>
        {creating && (
          <section className="panel settings-card" id="create-employee">
            <div className="panel-head">
              <h2 className="panel-title">Add employee</h2>
            </div>
            <form onSubmit={create}>
              <div className="form-grid">
                <label>
                  Name
                  <input
                    name="name"
                    className="input"
                    required
                    maxLength={150}
                    autoComplete="name"
                  />
                </label>
                <label>
                  Work email
                  <input
                    name="email"
                    className="input"
                    type="email"
                    required
                    maxLength={150}
                    autoComplete="email"
                  />
                </label>
              </div>
              <div className="card-actions">
                <button
                  type="submit"
                  className="button primary"
                  disabled={busy}
                >
                  {busy ? "Creating…" : "Add and send invite"}
                </button>
                <span className="panel-meta">
                  Employees set their own password. No public signup.
                </span>
              </div>
            </form>
          </section>
        )}
        <section className="panel team-panel">
          <div className="panel-head">
            <div>
              <h2 className="panel-title">Team</h2>
              <div className="panel-meta">
                Access and invites
              </div>
            </div>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void load()}
            >
              <Icon name="refresh" />
              Refresh
            </button>
          </div>
          <div className="filters">
            <div className="search-field">
              <Icon name="search" />
              <input
                className="input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name or email"
                aria-label="Search employees"
              />
            </div>
          </div>
          <div
            className="table-wrap"
            role="region"
            aria-label="Employee accounts table"
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Status</th>
                  <th>Workspace</th>
                  <th>Manage</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((account) => (
                  <EmployeeRow
                    key={account.id}
                    account={account}
                    currentUserId={user.id}
                    busy={busy}
                    onInvite={invite}
                    onUpdate={update}
                  />
                ))}
              </tbody>
            </table>
            {team && !filtered.length && (
              <div className="empty">No matches.</div>
            )}
          </div>
        </section>
        <p className="settings-help">
          Need help? <a href="mailto:support@zyene.com">support@zyene.com</a>
        </p>
      </main>
    </div>
  );
}
