import { formatNewYorkDateTime } from "@/lib/date-time";
import type { SendingWindow } from "@/lib/sending-schedule";

export type EmailDraft = {
  id: string; name: string; to: string; subject: string; body: string;
  preview_body: string; revision: string; approved: boolean;
  state: string; accepted_at: string | null;
};
export type EmailReview = {
  actor_id?: number;
  thread_id?: number | null;
  id: string; kind: "initial" | "reply"; status: string;
  from_address: string; requested_count: number; drafts: EmailDraft[];
  accepted: number; revision: string; stale: boolean; note: string;
};
export type OutreachSetup = {
  eligible: number; remaining_today: number; from_address: string;
  next_send_at: string | null; ai_ready: boolean;
  window: SendingWindow;
  reviews: { id: string; kind: string; status: string; count: number; created_at: string }[];
};
export const sentTime = (value: string | null) => value ? formatNewYorkDateTime(value, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "No timestamp";
