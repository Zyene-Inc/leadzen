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

const workspaceLinks: {
  id: string;
  icon: IconName;
  href: string;
  label: string;
}[] = [
  { id: "overview", icon: "overview", href: "/", label: "Home" },
  { id: "contacts", icon: "contacts", href: "/contacts", label: "Leads" },
  { id: "outreach", icon: "send", href: "/outreach", label: "Outreach" },
  { id: "inbox", icon: "inbox", href: "/inbox", label: "Inbox" },
  { id: "settings", icon: "settings", href: "/settings", label: "Settings" },
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
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not preserve Workspace context"); }
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
      if (!response.ok) throw new Error("Could not sign out. Please retry.");
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
          <div className="workspace-caption">Internal workspace</div>
        </div>
      </div>
      <div className="navigation-area" id="workspace-navigation">
        {(!user.is_admin || user.onboarded) && (
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
        {active !== "chat" && (!user.is_admin || user.onboarded) && (
          <nav aria-label="Workspace">
            <div className="nav-label">Your workspace</div>
            {workspaceLinks.map((item) => (
              <Link
                key={item.id}
                data-tour={`nav-${item.id}`}
                className={`nav-item${workspaceActive === item.id ? " active" : ""}${item.id === "activity" ? " nav-group-start" : ""}`}
                href={item.href}
                aria-current={workspaceActive === item.id ? "page" : undefined}
                onClick={() => setMenuOpen(false)}
              >
                <Icon name={item.icon} />
                {item.label}
              </Link>
            ))}
            <details className="workspace-tools" open={["activity", "suppression"].includes(active) || undefined}>
              <summary className="nav-item">Workspace tools</summary>
              <Link className={`nav-item${active === "activity" ? " active" : ""}`} href="/activity" aria-current={active === "activity" ? "page" : undefined}><Icon name="activity" />Activity</Link>
              <Link className={`nav-item${active === "suppression" ? " active" : ""}`} href="/suppression" aria-current={active === "suppression" ? "page" : undefined}><Icon name="suppression" />Do not contact</Link>
            </details>
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
              Team accounts
            </Link>
          </nav>
        )}
        <div className="sidebar-footer">
          <div className="sidebar-person">
            <Avatar name={user.name || user.email} />
            <div>
              <strong>{user.name || user.email}</strong>
              <div>{user.is_admin ? "Administrator" : "Employee"}</div>
            </div>
          </div>
          <div className="account-email">{user.email}</div>
          <button
            type="button"
            className="button ghost signout-button"
            onClick={logout}
            disabled={busy}
          >
            <Icon name="logout" />
            {busy ? "Signing out…" : "Sign out"}
          </button>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <a className="support-link" href="mailto:support@zyene.com">
            <Icon name="help" />
            Contact Zyene support
          </a>
        </div>
      </div>
    </aside>
  );
}
