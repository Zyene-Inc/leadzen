import { emptySettings, type Settings } from "@/lib/connection-settings";

export type Country = { code: string; name: string };
export type Audience = {
  industry: string;
  country: string;
  company_size: string;
  roles: string[];
  seniority: string[];
  instructions: string;
};
export type Draft = {
  operator_name: string;
  operator_email: string;
  operator_country_code: string;
  purpose: string;
  workspace_name: string;
  product_name: string;
  product_docs: string;
  booking_link: string;
  legacy_target?: string;
  discovery_enabled: boolean;
  audience: Audience;
  confirmed: boolean;
  accepted_legal_notice: boolean;
};
export type CheckKind = "ai" | "discovery" | "mailbox";
export type ConnectionCheck = {
  connected: boolean;
  answered?: boolean;
  credits?: number;
  smtp?: boolean;
  imap?: boolean;
  tested_at?: string;
  synthetic?: boolean;
};
export type Wizard = {
  draft: Partial<Draft>;
  completed_steps: number[];
  checks: Partial<Record<CheckKind, ConnectionCheck>>;
  connections: Settings;
  countries: Country[];
  onboarded: boolean;
};
export const stepLabels = [
  "AI provider",
  "Lead discovery",
  "Your identity",
  "Sending mailbox",
  "Product / offer",
  "Target audience",
];
export const roleOptions = [
  "Owner",
  "Founder",
  "Practice Manager",
  "Marketing Manager",
  "Dentist",
  "Dental technician",
];
export const seniorityOptions = [
  ["owner", "Owner"],
  ["founder", "Founder"],
  ["c_suite", "C-suite"],
  ["partner", "Partner"],
  ["vp", "VP"],
  ["head", "Head"],
  ["director", "Director"],
  ["manager", "Manager"],
  ["senior", "Senior"],
  ["mid-level", "Mid-level"],
  ["entry", "Entry-level"],
  ["intern", "Intern"],
];
export const blankAudience: Audience = {
  industry: "",
  country: "US",
  company_size: "any",
  roles: [],
  seniority: [],
  instructions: "",
};
export function initialDraft(wizard: Pick<Wizard, "draft">): Draft {
  return {
    operator_name: "",
    operator_email: "",
    operator_country_code: "US",
    purpose: "other",
    workspace_name: "",
    product_name: "",
    product_docs: "",
    booking_link: "",
    discovery_enabled: true,
    confirmed: false,
    accepted_legal_notice: false,
    ...wizard.draft,
    audience: wizard.draft.audience ?? {
      ...blankAudience,
      country: wizard.draft.operator_country_code || "US",
    },
  };
}
export function initialConnections(value: Settings): Settings {
  return {
    ...value,
    llm: value.llm.provider
      ? value.llm
      : {
          ...emptySettings.llm,
          enabled: value.llm.enabled,
          api_key_configured: value.llm.api_key_configured,
        },
  };
}
export function targetPreview(audience: Audience, countries: Country[]) {
  const country =
    countries.find((entry) => entry.code === audience.country)?.name ??
    audience.country;
  const size =
    audience.company_size === "any"
      ? "any company size"
      : `${audience.company_size} employees`;
  return `Find ${audience.roles.join(", ") || "your chosen roles"} working at ${audience.industry || "your chosen industry"} in ${country}, ${size}. Seniority: ${audience.seniority.join(", ") || "your chosen levels"}. ${audience.instructions}`.trim();
}
export function stepValues(step: number, draft: Draft) {
  if (step === 2) return { discovery_enabled: draft.discovery_enabled };
  if (step === 3)
    return {
      operator_name: draft.operator_name,
      operator_email: draft.operator_email,
      operator_country_code: draft.operator_country_code,
    };
  if (step === 5)
    return {
      purpose: draft.purpose,
      workspace_name: draft.workspace_name,
      product_name: draft.product_name,
      product_docs: draft.product_docs,
      booking_link: draft.booking_link,
    };
  if (step === 6)
    return {
      audience: draft.audience,
      confirmed: draft.confirmed,
      accepted_legal_notice: draft.accepted_legal_notice,
    };
  return {};
}
