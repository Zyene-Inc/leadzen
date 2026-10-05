import type { SendingSchedule } from "@/lib/sending-schedule";
import { formatNewYorkDateTime, LEADZEN_TIME_ZONE } from "@/lib/date-time";
export type TimelineEntry = { id: string; label: string; status: string; at: string | null; subject: string };
export function formatTimelineDate(at: string | null) {
  if (!at) return { date: "Date pending", time: "" };
  return {
    date: formatNewYorkDateTime(at, { month: "short", day: "numeric", year: "numeric" }),
    time: `${formatNewYorkDateTime(at)} (${LEADZEN_TIME_ZONE})`,
  };
}
export type OutreachTimeline = {
  events: TimelineEntry[];
  history_truncated: boolean;
  blocked_reason: string;
  can_stop: boolean;
  suppression: { reason: string; at: string } | null;
  sequences: { id: string; name: string; status: string; campaign_status: string; timezone: string; automatic?: boolean; sending_schedule?: SendingSchedule; steps: TimelineEntry[] }[];
};

export type Contact = {
  id: number;
  name: string;
  email: string;
  email_status: "not_requested" | "pending" | "review" | "not_found" | "available" | "verified" | "catch_all_safe";
  first_name: string;
  last_name: string;
  company: string;
  title: string;
  website: string;
  linkedin_url: string;
  state: string;
  crm_status: string;
  qualified: boolean;
  reason: string;
  reply_count: number;
  profile_text: string;
  opted_in: boolean;
  consent_note: string;
  timeline?: OutreachTimeline;
  lookup: null | {
    run_id: string | null;
    status: string;
    receipt_state: string;
    credits_used: number | null;
    email_verdict: string;
    synthetic: boolean;
  };
};

export const leadFilters = [
  ["all", "All"], ["qualified", "Qualified"], ["email_found", "Email Found"],
  ["contacted", "Contacted"], ["replied", "Replied"], ["suppressed", "Suppressed"],
] as const;

export function leadStatus(value: string) {
  return leadFilters.find(([key]) => key === value)?.[1] ?? "Contact";
}

export function emailLabel(lead: Contact) {
  if (lead.email) return lead.email;
  return lead.email_status === "pending" ? "Lookup in progress" : lead.email_status === "review" ? "Lookup needs review" : lead.email_status === "not_found" ? "No email found" : "Not enriched";
}
