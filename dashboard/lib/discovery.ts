export type Candidate = {
  id: number;
  source_id: number;
  name: string;
  title: string;
  company: string;
  profile_url: string;
  reason: string;
  email: string;
  outcome: string;
  contact_id: number | null;
};
export type DiscoveryEvent = {
  id: number;
  kind: string;
  data: Partial<Candidate> & {
    filters?: Record<string, string>;
    message?: string;
    profiles_returned?: number;
    email_status?: string;
  };
  created_at: string;
  display_time?: string;
};
/** What the provider search uses versus what only AI qualification checks. */
export type SearchScope = { changes_search: boolean; search: string; qualification: string };
export type DiscoveryProgress = {
  id: string;
  thread_id: string;
  status: string;
  pause_requested: boolean;
  stop_requested: boolean;
  goal: { count: number; unit: "leads" | "emails" };
  counts: {
    discovered: number;
    evaluated: number;
    qualified: number;
    rejected: number;
    produced: number;
    with_email: number;
    awaiting_evaluation?: number;
  };
  credits: {
    used: number | null;
    reported: number;
    pending: number;
    approved: number;
    /** "ai_ark" totals include paid profile search; other providers bill emails only. */
    provider?: string;
  };
  target: string;
  synthetic: boolean;
  goal_reached: boolean;
  approval_expires_at: string | null;
  events: DiscoveryEvent[];
  leads: Candidate[];
  /** Additive progress fields: older saved runs may not have these yet. */
  candidates?: Candidate[];
  current_activity?: Pick<DiscoveryEvent, "kind" | "data" | "created_at"> | null;
  phase?: string;
  /** Absent or null on runs saved before search scopes were recorded. */
  search_scope?: SearchScope | null;
};
export type EmailReview = {
  provider_name?: string;
  items: Candidate[];
  revision: string;
  note: string;
};
export const creditLabel = (data: Pick<DiscoveryProgress, "credits">) =>
  data.credits.provider === "ai_ark" ? "AI Ark credits" : "Email credits";
export const approvedBudget = (data: Pick<DiscoveryProgress, "credits">) =>
  `${data.credits.provider === "ai_ark" ? "Approved AI Ark budget (profile search + emails)" : "Approved email budget"}: ${data.credits.approved} credits.`;
export const findingActive = (status: string) =>
  ["queued", "running"].includes(status);

export function summaryTitle(data: DiscoveryProgress) {
  const emails = data.goal.unit === "emails";
  if (data.status === "failed") return emails ? "Email lookup needs attention" : "Discovery needs attention";
  if (data.goal_reached && !findingActive(data.status) && data.status !== "paused")
    return emails ? "Email lookup done" : "Discovery done";
  if (data.status === "paused") return emails ? "Email lookup paused" : "Finding paused";
  if (["succeeded", "completed"].includes(data.status)) return emails ? "Email lookup finished" : "Discovery finished";
  if (!findingActive(data.status)) return emails ? "Email lookup stopped" : "Finding stopped";
  return emails
    ? `Finding ${data.goal.count} work email${data.goal.count === 1 ? "" : "s"}`
    : `Finding ${data.goal.count} qualified lead${data.goal.count === 1 ? "" : "s"}`;
}

export function summaryNote(data: DiscoveryProgress) {
  const emails = data.goal.unit === "emails";
  if (data.goal_reached && !findingActive(data.status) && data.status !== "paused")
    return emails
      ? `${data.counts.produced} verified email${data.counts.produced === 1 ? "" : "s"} found.`
      : `${data.counts.produced} qualified lead${data.counts.produced === 1 ? "" : "s"} found · ${data.counts.rejected} rejected.`;
  if (data.status === "paused") return "Saved. Resume finishes only what is left, within the same budget.";
  if (!findingActive(data.status)) return "Ended before the goal. Results so far are saved.";
  return "Counts are saved results, not estimates.";
}

export function statusLabel(data: DiscoveryProgress) {
  if (data.stop_requested && findingActive(data.status)) return "Stopping";
  if (data.pause_requested && findingActive(data.status)) return "Pausing";
  const labels: Record<string, string> = {
    queued: "Waiting",
    running: "In progress",
    succeeded: "Complete",
    completed: "Finished",
    failed: "Needs attention",
    cancelled: "Stopped",
    stopped: "Stopped",
    paused: "Paused",
  };
  const fallback = data.status.replaceAll("_", " ");
  return labels[data.status] || `${fallback.charAt(0).toUpperCase()}${fallback.slice(1)}`;
}

export function profileLink(value: string | undefined) {
  try {
    const url = new URL(value || "");
    return url.protocol === "https:" && !url.username && !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}

export const discoveryActivityLabels: Record<string, string> = {
  searching: "Searching profiles",
  search_completed: "Search results received",
  discovered: "Candidate discovered",
  evaluating: "Evaluating fit",
  qualified: "Qualified",
  rejected: "Rejected",
  email_lookup: "Email lookup result",
};

export function currentDiscoveryActivity(data: DiscoveryProgress) {
  if (data.stop_requested && findingActive(data.status))
    return "Stopping at the next safe checkpoint";
  if (data.pause_requested && findingActive(data.status))
    return "Pausing at the next safe checkpoint";
  if (data.status === "queued") return "Waiting for a discovery worker";
  if (data.status === "paused") return "Discovery paused";
  if (!findingActive(data.status)) return summaryTitle(data);
  const event = data.current_activity || data.events.at(-1);
  if (!event) return "Starting discovery";
  if (event.kind === "evaluating")
    return event.data.name ? `Evaluating ${event.data.name}` : "Evaluating a candidate’s fit";
  if (event.kind === "qualified" || event.kind === "rejected")
    return event.data.name
      ? `${event.data.name} ${event.kind === "qualified" ? "qualified" : "was rejected"}`
      : discoveryActivityLabels[event.kind];
  if (event.kind === "discovered") return "Receiving candidate profiles";
  return discoveryActivityLabels[event.kind] || "Discovery in progress";
}

export function currentDiscoverySearch(data: DiscoveryProgress) {
  const filters = [...data.events].reverse().find((event) => event.data.filters)?.data.filters;
  return filters ? Object.values(filters).filter(Boolean).join(" · ") : data.target;
}

/** Candidate IDs belong to discovery; Workspace links must use contact_id. */
export function candidateWorkspaceLink(candidate: Partial<Candidate>) {
  return Number.isInteger(candidate.contact_id) && (candidate.contact_id ?? 0) > 0
    ? `/contacts/${candidate.contact_id}`
    : null;
}

export function recentDiscoveryCandidates(data: DiscoveryProgress, limit = 6) {
  if (data.candidates?.length) {
    const recency = new Map<number, number>();
    data.events.forEach((event, index) => {
      if (typeof event.data.id === "number") recency.set(event.data.id, index);
    });
    return [...data.candidates].reverse().sort((first, second) =>
      (recency.get(second.id) ?? -1) - (recency.get(first.id) ?? -1),
    ).slice(0, limit);
  }
  const rows = new Map<number, Candidate>();
  for (const event of [...data.events].reverse()) {
    if (!["discovered", "evaluating", "qualified", "rejected"].includes(event.kind)) continue;
    const candidate = event.data;
    if (typeof candidate.id !== "number" || rows.has(candidate.id)) continue;
    rows.set(candidate.id, {
      id: candidate.id,
      source_id: candidate.source_id ?? 0,
      name: candidate.name || "Unnamed profile",
      title: candidate.title || "",
      company: candidate.company || "",
      profile_url: candidate.profile_url || "",
      reason: candidate.reason || "",
      email: candidate.email || "",
      outcome: ["qualified", "rejected"].includes(event.kind) ? event.kind : "pending",
      contact_id: candidate.contact_id ?? null,
    });
  }
  // Existing saved runs retain their canonical qualified records even if events rolled off.
  for (const lead of [...data.leads].reverse()) {
    const existing = rows.get(lead.id);
    if (existing) rows.set(lead.id, { ...existing, ...lead });
    else rows.set(lead.id, lead);
  }
  return [...rows.values()].slice(0, limit);
}
