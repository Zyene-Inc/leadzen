import { LEADZEN_TIME_ZONE, LEADZEN_TIME_ZONE_LABEL } from "@/lib/date-time";

export type SendingSchedule = {
  timezone: string;
  days: number[];
  start: string;
  end: string;
};

export type SendingWindow = {
  start: number;
  end: number;
  timezone: string;
  weekdays_only?: boolean;
  days?: number[];
  start_time?: string;
  end_time?: string;
};

export const scheduleDays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
export const scheduleDayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
export const NEW_YORK_TIMEZONE = LEADZEN_TIME_ZONE;
export const NEW_YORK_TIMEZONE_LABEL = LEADZEN_TIME_ZONE_LABEL;
export const defaultSendingSchedule = (): SendingSchedule => ({ timezone: NEW_YORK_TIMEZONE, days: [0, 1, 2, 3, 4], start: "08:00", end: "20:00" });

export function normalizeSendingSchedule(schedule: SendingSchedule): SendingSchedule {
  return { ...schedule, timezone: NEW_YORK_TIMEZONE, days: [...schedule.days] };
}

function timeFromHour(hour: number) {
  const minutes = Math.round(hour * 60);
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

export function windowSchedule(window: SendingWindow): SendingSchedule {
  return {
    timezone: NEW_YORK_TIMEZONE,
    days: window.days ?? (window.weekdays_only === false ? [0, 1, 2, 3, 4, 5, 6] : [0, 1, 2, 3, 4]),
    start: window.start_time ?? timeFromHour(window.start),
    end: window.end_time ?? timeFromHour(window.end),
  };
}

export function scheduleTime(value: string) {
  const [hours, minutes] = value.split(":").map(Number);
  return `${hours % 12 || 12}${minutes ? `:${String(minutes).padStart(2, "0")}` : ""} ${hours < 12 ? "AM" : "PM"}`;
}

export function scheduleHours(schedule: SendingSchedule) {
  return `${scheduleTime(schedule.start)}–${scheduleTime(schedule.end)}`;
}

export function scheduleDayLabel(days: number[]) {
  const ordered = [...new Set(days)].sort((a, b) => a - b);
  if (ordered.join(",") === "0,1,2,3,4") return "Weekdays";
  if (ordered.length === 7) return "Every day";
  if (ordered.join(",") === "5,6") return "Weekends";
  return ordered.map((day) => scheduleDays[day]).filter(Boolean).join(", ");
}

export function scheduleSummary(schedule: SendingSchedule) {
  return `${scheduleDayLabel(schedule.days)} · ${scheduleHours(schedule)} · ${NEW_YORK_TIMEZONE_LABEL}`;
}

export function scheduleError(schedule: SendingSchedule) {
  if (!schedule.days.length) return "Choose at least one sending day.";
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(schedule.start) || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(schedule.end)) return "Choose a start and end time.";
  if (schedule.end <= schedule.start) return "End time must be later than start time on the same day.";
  if (schedule.timezone !== NEW_YORK_TIMEZONE) return "Sending hours must use New York (Eastern Time). Reopen this setting and try again.";
  return "";
}
