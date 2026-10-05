import { formatNewYorkDateTime } from "@/lib/date-time";

export type ActivityEvent = {
  id: string;
  title: string;
  detail: string;
  at: string;
  kind: "info" | "success" | "rejected" | "warning";
  href: string | null;
};

export function activityTime(at: string) {
  return {
    clock: formatNewYorkDateTime(at, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
    timestamp: formatNewYorkDateTime(at),
  };
}
