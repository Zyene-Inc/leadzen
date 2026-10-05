import type { SendingSchedule } from "@/lib/sending-schedule";
export type SequenceStep = { subject: string; body: string; delay_days: number };
export type Campaign = {
  id: string; name: string; category: string; status: string; automatic_followups: boolean;
  autopilot?: boolean; followup_issue?: string; steps: SequenceStep[]; total: number; sent: number;
  from_address: string; target: string; product: string; booking_link: string; signature: string;
  delay_basis: string; delay_timezone: string;
  sending_schedule?: SendingSchedule;
  recipients: { personal_steps?: SequenceStep[]; id: number; email: string; status: string; next_step: number; next_send_at: string | null }[];
};
