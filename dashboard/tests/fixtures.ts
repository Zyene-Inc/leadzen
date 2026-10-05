import type { Account } from "@/lib/auth";
import type { WorkspaceSettings } from "@/lib/workspace-settings";
import type { DiscoveryProgress } from "@/lib/discovery";
import type { Contact } from "@/lib/leads";
import { emptySettings } from "@/lib/connection-settings";

export const user: Account = { id: 1, name: "Synthetic user", email: "user@example.com", is_admin: false, is_active: true, must_change_password: false, onboarded: true, purpose: "other", workspace_name: "Synthetic", created_at: "2026-10-02T12:00:00Z", last_login: null, invitation_pending: false, tour_completed: true };
export const settings: WorkspaceSettings = {
  ...emptySettings, settings_key_configured: true,
  workspace: {
    sending_schedule: { timezone: "America/New_York", days: [0, 1, 2, 3, 4], start: "08:00", end: "20:00" },
    identity: { operator_name: "Synthetic user", operator_email: "user@example.com", operator_country_code: "US", country_name: "United States" },
    product: { product_name: "Synthetic product", product_docs: "A useful product for practices" },
    booking_link: "https://example.com/book",
    target: { summary: "Practice owners", audience: { industry: "Dental practices", country: "US", company_size: "any", roles: ["Owner"], seniority: ["owner"], instructions: "Decision makers" }, country_name: "United States", accepted_legal_notice: true },
    countries: [{ code: "US", name: "United States" }],
    checks: { ai: { connected: false }, discovery: { connected: false }, mailbox: { connected: false } },
    data: { engine: "SQLite", path: "/synthetic/workspace/db.sqlite3", size_bytes: 1024, combined: true },
  },
};
export const lead = { id: 1, name: "Bruce", email: "bruce@example.com", first_name: "Bruce", last_name: "Example", company: "Practice", title: "Owner", website: "https://example.com", linkedin_url: "", profile_text: "Owner", state: "Ready to Email", crm_status: "qualified", email_status: "verified", opted_in: false, consent_note: "", reply_count: 0 } as Contact;
export const progress: DiscoveryProgress = { id: "run1", thread_id: "thread1", status: "running", pause_requested: false, stop_requested: false, goal: { count: 3, unit: "leads" }, counts: { discovered: 10, evaluated: 4, qualified: 1, rejected: 3, produced: 1, with_email: 0 }, credits: { used: 0, reported: 0, pending: 0, approved: 0 }, target: "Practice owners", synthetic: true, goal_reached: false, approval_expires_at: "2099-01-01T00:00:00Z", events: [], leads: [] };
