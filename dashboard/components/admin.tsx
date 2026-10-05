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
        caught instanceof Error ? caught.message : "Unable to load employees",
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
          "Account saved, but email delivery could not be confirmed. Check Resend and the verified sender, then use Resend invitation.",
        );
      else setNotice(success);
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to update employee",
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
      "Invitation sent. The employee can create their own password using the setup link. The link expires in 48 hours.",
    );
  }
  function invite(account: Account) {
    if (
      !account.invitation_pending &&
      !window.confirm(
        `Send a password reset invitation to ${account.email}? Existing sessions will be signed out.`,
      )
    )
      return;
    void action(
      () => api(`admin/users/${account.id}/invite`, { method: "POST" }),
      "Setup invitation sent. Earlier setup links have been revoked.",
    );
  }
  function update(account: Account, remove = false) {
    if (
      remove &&
      !window.confirm(
        `Delete ${account.email}? This revokes access. Outreach history will be retained.`,
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
      remove ? "Employee deleted; access revoked." : "Employee access updated.",
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
          <PageHeading title="Employee accounts" help="Invite employees, manage access, and see who has completed setup." />
          <button
            type="button"
            className="button primary"
            disabled={busy}
            onClick={() => setCreating(!creating)}
            aria-expanded={creating}
            aria-controls={creating ? "create-employee" : undefined}
          >
            <Icon name={creating ? "close" : "plus"} />
            {creating ? "Close form" : "Create Employee"}
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
              ["Total accounts", team?.totals.users],
              ["Active accounts", team?.totals.active],
              ["Administrators", team?.totals.admins],
              ["Setup complete", team?.totals.onboarded],
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
              <h2 className="panel-title">Create Employee</h2>
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
                  {busy ? "Creating…" : "Create & send invitation"}
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
                Manage employee access and setup invitations
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
              <div className="empty">No employees match your search.</div>
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
