"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/client-api";
import { flushWorkspaceContext, recordWorkspaceContext, type WorkspaceContext } from "@/lib/workspace-context";
import { useEffect, useState, type ReactNode } from "react";
import { Brand } from "@/components/brand";
import { Avatar } from "@/components/avatar";
import { Icon, type IconName } from "@/components/icon";
import type { Account } from "@/lib/auth";
import { useProductTour } from "@/components/product-tour-provider";

type NavLink = { id: string; icon: IconName; href: string; label: string };

// Grouped like Explee's sidebar: main pages, then Mailbox, then Setup.
const navGroups: { label: string; items: NavLink[] }[] = [
  {
    label: "",
    items: [
      { id: "overview", icon: "overview", href: "/", label: "Dashboard" },
      { id: "contacts", icon: "contacts", href: "/contacts", label: "Leads" },
      { id: "outreach", icon: "send", href: "/outreach", label: "Outreach" },
      { id: "results", icon: "results", href: "/results", label: "Results" },
    ],
  },
  { label: "Mailbox", items: [{ id: "inbox", icon: "inbox", href: "/inbox", label: "Inbox" }] },
  {
    label: "Setup",
    items: [
      { id: "settings", icon: "settings", href: "/settings", label: "Settings" },
      { id: "activity", icon: "activity", href: "/activity", label: "Activity" },
      { id: "suppression", icon: "suppression", href: "/suppression", label: "Do not contact" },
    ],
  },
];

function useWorkspaceMode(user: Account, active: string, setError: (message: string) => void) {
  const router = useRouter();
  const pathname = usePathname();
  const [context, setContext] = useState<WorkspaceContext | null>(null);
  useEffect(() => {
    if (!user.onboarded) return;
    const controller = new AbortController();
    void api<WorkspaceContext>("chat/context", { signal: controller.signal }).then(setContext).catch(() => {});
    return () => controller.abort();
  }, [active, user.id, user.onboarded]);
  async function openChat(event: React.MouseEvent<HTMLAnchorElement>) {
    if (active === "chat" || event.metaKey || event.ctrlKey) return;
    event.preventDefault();
    try {
      await flushWorkspaceContext();
      const latest = await api<WorkspaceContext>("chat/context");
      if (latest.workspacePath?.split("?")[0] !== pathname) {
        await recordWorkspaceContext({ workspacePath: pathname }, user.id);
        await flushWorkspaceContext();
      }
      router.push(latest.lastChatId ? `/chat/${latest.lastChatId}` : "/chat");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not open Chat"); }
  }
  return { context, openChat };
}

export function Sidebar({
  user,
  active,
  chatNavigation,
}: {
  user: Account;
  active: string;
  chatNavigation?: ReactNode;
}) {
  const tour = useProductTour();
  useEffect(() => { tour?.register(user); }, [tour?.register, user]);
  const [error, setError] = useState("");
  const { context, openChat } = useWorkspaceMode(user, active, setError);
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const workspaceActive = ["onboarding", "tour"].includes(active)
    ? "settings"
    : ["campaigns", "sending"].includes(active) ? "outreach" : active === "find-leads" ? "contacts" : active;
  async function logout() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error("Could not sign out. Try again.");
      window.location.assign("/login");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign out");
      setBusy(false);
    }
  }
  return (
    <aside className={`sidebar${menuOpen ? " menu-open" : ""}`}>
      <div className="sidebar-header">
        <Brand />
        <button
          className="button ghost menu-toggle"
          data-tour="nav-toggle"
          type="button"
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          aria-controls="workspace-navigation"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <Icon name={menuOpen ? "close" : "menu"} />
        </button>
      </div>
      <div className="workspace-label">
        <span className="workspace-symbol" aria-hidden="true">
          Z
        </span>
        <div>
          <div className="workspace-name">Zyene</div>
        </div>
        <span className="workspace-plan">Internal</span>
      </div>
      <div className="navigation-area" id="workspace-navigation">
        {user.onboarded && (
          <nav className="sidebar-modes" aria-label="Navigation mode">
            <Link
              data-tour="nav-workspace"
              href={active === "chat" ? context?.workspacePath || "/" : "/"}
              className={active !== "chat" ? "selected" : ""}
              aria-current={active !== "chat" ? "true" : undefined}
            >
              <Icon name="overview" /> Workspace
            </Link>
            <Link
              data-tour="nav-chat"
              href={context?.lastChatId ? `/chat/${context.lastChatId}` : "/chat"}
              onClick={(event) => void openChat(event)}
              className={active === "chat" ? "selected" : ""}
              aria-current={active === "chat" ? "true" : undefined}
            >
              <Icon name="chat" /> Chat
            </Link>
          </nav>
        )}
        {active === "chat" && chatNavigation}
        {!user.onboarded && !user.is_admin && (
          <nav aria-label="Workspace">
            <div className="nav-label">Get started</div>
            <Link className="nav-item active" href="/onboarding" aria-current={active === "onboarding" ? "page" : undefined} onClick={() => setMenuOpen(false)}>
              <Icon name="onboarding" />
              Set up workspace
            </Link>
          </nav>
        )}
        {active !== "chat" && user.onboarded && (
          <nav aria-label="Workspace">
            {navGroups.map((group) => (
              <div className="nav-group" key={group.label || "main"}>
                {group.label && <div className="nav-label">{group.label}</div>}
                {group.items.map((item) => {
                  const current = workspaceActive === item.id || active === item.id;
                  return (
                    <Link
                      key={item.id}
                      data-tour={`nav-${item.id}`}
                      className={`nav-item${current ? " active" : ""}`}
                      href={item.href}
                      aria-current={current ? "page" : undefined}
                      onClick={() => setMenuOpen(false)}
                    >
                      <Icon name={item.icon} />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            ))}
          </nav>
        )}
        {user.is_admin && (
          <nav aria-label="Administration">
            <div
              className={`nav-label${user.onboarded ? " admin-nav-label" : ""}`}
            >
              Administration
            </div>
            <Link
              className={`nav-item ${active === "admin" ? "active" : ""}`}
              href="/admin"
              aria-current={active === "admin" ? "page" : undefined}
              onClick={() => setMenuOpen(false)}
            >
              <Icon name="admin" />
              Employee accounts
            </Link>
          </nav>
        )}
        <details className="sidebar-footer account-menu">
          <summary className="sidebar-person" aria-label="Account menu">
            <Avatar name={user.name || user.email} />
            <div>
              <strong>{user.name || user.email}</strong>
              <div className="account-email">{user.email}</div>
            </div>
            <Icon name="chevrons" />
          </summary>
          <div className="account-menu-list">
            <div className="account-menu-role">{user.is_admin ? "Administrator" : "Employee"}</div>
            <a className="support-link" href="mailto:support@zyene.com">
              <Icon name="help" />
              Contact Zyene support
            </a>
            <button
              type="button"
              className="button ghost signout-button"
              onClick={logout}
              disabled={busy}
            >
              <Icon name="logout" />
              {busy ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </details>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    </aside>
  );
}
