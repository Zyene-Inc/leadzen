import type { Settings } from "@/lib/connection-settings";
import type { Audience, ConnectionCheck, Country } from "@/lib/setup-wizard";
import { defaultSendingSchedule, NEW_YORK_TIMEZONE_LABEL, scheduleDayLabel, scheduleHours, type SendingSchedule } from "@/lib/sending-schedule";
import { formatNewYorkDateTime } from "@/lib/date-time";

export type WorkspaceSettings = Settings & {
  workspace: {
    sending_schedule?: SendingSchedule;
    identity: {
      operator_name: string;
      operator_email: string;
      operator_country_code: string;
      country_name: string;
    };
    product: { product_name: string; product_docs: string };
    booking_link: string;
    target: {
      summary: string;
      audience: Audience | null;
      country_name: string;
      accepted_legal_notice: boolean;
    };
    countries: Country[];
    checks: Record<"ai" | "discovery" | "mailbox", ConnectionCheck>;
    data: {
      engine: string;
      path: string;
      size_bytes: number | null;
      combined: boolean;
    };
  };
};
export const settingSections = [
  "ai",
  "finder",
  "identity",
  "mailbox",
  "schedule",
  "product",
  "target",
  "signature",
  "booking",
] as const;
export type SettingSection = (typeof settingSections)[number];
export const settingTitles: Record<SettingSection, string> = {
  ai: "AI",
  finder: "Lead Provider",
  identity: "Identity",
  mailbox: "Mailbox",
  schedule: "Sending hours",
  product: "Product",
  target: "Target",
  signature: "Signature",
  booking: "Booking link",
};
const sizes = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
export function checkedDate(value?: string) {
  return value ? formatNewYorkDateTime(value, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
}
export function databaseSize(bytes: number | null) {
  if (bytes === null) return "Size unavailable";
  return bytes < 1024 * 1024
    ? `${sizes.format(bytes / 1024)} KB`
    : `${sizes.format(bytes / (1024 * 1024))} MB`;
}
export function settingSummary(
  section: SettingSection,
  data: WorkspaceSettings,
) {
  const { workspace, llm, mailbox } = data;
  switch (section) {
    case "ai":
      return {
        main: llm.enabled
          ? llm.provider || "Provider not configured"
          : "AI disabled",
        detail: llm.model,
      };
    case "finder": {
      const credits = workspace.checks.discovery.credits;
      return {
        main: "BetterContact",
        detail:
          credits === undefined
            ? "Balance not checked"
            : `${credits} credits · Saved balance`,
      };
    }
    case "identity":
      return {
        main: workspace.identity.operator_name || "Identity not configured",
        detail: [
          workspace.identity.country_name,
          workspace.identity.operator_email,
        ]
          .filter(Boolean)
          .join(" · "),
      };
    case "mailbox":
      return {
        main: mailbox.address || "Mailbox not configured",
        detail: mailbox.smtp_host.includes("zoho.")
          ? "Zoho"
          : mailbox.transport === "smtp"
            ? mailbox.smtp_host
            : mailbox.transport,
      };
    case "schedule": {
      const schedule = workspace.sending_schedule ?? defaultSendingSchedule();
      return { main: scheduleHours(schedule), detail: `${scheduleDayLabel(schedule.days)} · ${NEW_YORK_TIMEZONE_LABEL}` };
    }
    case "product":
      return {
        main: workspace.product.product_name || "Product description",
        detail: workspace.product.product_docs || "Describe what you offer",
      };
    case "target":
      return {
        main: workspace.target.audience?.industry || "Target audience",
        detail: workspace.target.summary || "Choose who you want to reach",
      };
    case "signature":
      return {
        main: mailbox.signature || "No signature saved",
        detail: "Included in your outreach",
      };
    case "booking":
      return {
        main: workspace.booking_link || "No booking link saved",
        detail: "Optional link for scheduling a conversation",
      };
  }
}
