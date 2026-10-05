import { Avatar } from "@/components/avatar";
import type { Account } from "@/lib/auth";

function accountStatus(account: Account) {
  if (account.is_admin) return { label: "Admin", tone: "admin" };
  if (!account.is_active) return { label: "Disabled", tone: "disabled" };
  if (account.invitation_pending) return { label: "Invited", tone: "invited" };
  if (account.onboarded) return { label: "Active", tone: "active" };
  return { label: "Onboarding", tone: "ready" };
}

type EmployeeRowProps = {
  account: Account;
  currentUserId: Account["id"];
  busy: boolean;
  onInvite: (account: Account) => void;
  onUpdate: (account: Account, remove?: boolean) => void;
};

export function EmployeeRow({
  account,
  currentUserId,
  busy,
  onInvite,
  onUpdate,
}: EmployeeRowProps) {
  const status = accountStatus(account);
  const actions = [
    {
      id: "access",
      label: account.is_active ? "Disable" : "Enable",
      disabled: busy,
      danger: false,
      run: () => onUpdate(account),
    },
    {
      id: "invite",
      label: account.invitation_pending
        ? "Resend invitation"
        : "Reset via email",
      disabled: busy || !account.is_active,
      danger: false,
      run: () => onInvite(account),
    },
    {
      id: "delete",
      label: "Delete",
      disabled: busy,
      danger: true,
      run: () => onUpdate(account, true),
    },
  ];
  return (
    <tr>
      <td>
        <div className="person-cell">
          <Avatar name={account.name || account.email} />
          <div>
            <div className="person">{account.name || "Unnamed employee"}</div>
            <div className="subtext">{account.email}</div>
          </div>
        </div>
      </td>
      <td>
        <span className={`badge ${status.tone}`}>{status.label}</span>
      </td>
      <td>{account.workspace_name || "Setup pending"}</td>
      <td>
        {account.id === currentUserId || account.is_admin ? (
          <span className="panel-meta">Administrator</span>
        ) : (
          <div className="row-actions">
            {actions.map((action) => (
              <button
                key={action.id}
                type="button"
                className={`button ghost${action.danger ? " danger-button" : ""}`}
                disabled={action.disabled}
                onClick={action.run}
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}
