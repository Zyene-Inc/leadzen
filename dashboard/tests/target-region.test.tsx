import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api } from "@/lib/client-api";
import { SettingsEditor } from "@/components/settings-editor";
import TargetEditor from "@/components/target-editor";
import { HomeSummaryPanel, type HomeSummary } from "@/components/home-summary";
import { ApprovalCard } from "@/components/chat-results";
import { ChatDiscoveryCard } from "@/components/chat-discovery-card";
import DiscoveryLive from "@/components/discovery-live";
import { blankAudience, initialDraft, targetPreview, type Audience } from "@/lib/setup-wizard";
import type { Approval } from "@/lib/chat";
import { progress, settings, user } from "./fixtures";

const call = vi.mocked(api);
const writes = () => call.mock.calls.filter(([, init]) => !!init?.method);
const payload = (index = 0) => JSON.parse(String(writes()[index][1]?.body));
const countries = [{ code: "US", name: "United States" }, { code: "GB", name: "United Kingdom" }];
const dentists: Audience = { roles: ["Dentist"], industry: "Dental practices", country: "US", region: "Texas", company_size: "1-10", seniority: ["owner"], instructions: "" };
const legacy = { ...dentists, region: undefined } as unknown as Audience;
const scope = { changes_search: false, search: "BetterContact searches your saved Target; location Texas, United States.", qualification: "AI then checks each returned profile against your saved Target." };

describe("Target region", () => {
  test("preview matches the server text with and without a region", () => {
    expect(targetPreview(dentists, countries)).toBe("Find Dentist working at Dental practices in Texas, United States, 1-10 employees. Seniority: owner.");
    expect(targetPreview({ ...dentists, region: "  ", company_size: "any", instructions: "Owners only." }, countries)).toBe("Find Dentist working at Dental practices in United States, any company size. Seniority: owner. Owners only.");
    expect(targetPreview(legacy, countries)).toContain("in United States, 1-10 employees.");
  });

  test("defaults and targets saved before regions get an empty region", () => {
    expect(blankAudience.region).toBe("");
    expect(initialDraft({ draft: {} }).audience.region).toBe("");
    expect(initialDraft({ draft: { audience: legacy } }).audience).toEqual({ ...dentists, region: "" });
    expect(initialDraft({ draft: { audience: dentists } }).audience.region).toBe("Texas");
  });

  test("Settings target editor sends the region with the audience", async () => {
    call.mockResolvedValue(settings);
    render(<SettingsEditor section="target" data={settings} cancel={vi.fn()} onBusy={vi.fn()} saved={vi.fn()} />);
    const region = screen.getByLabelText("State or city (optional)") as HTMLInputElement;
    expect(region.maxLength).toBe(120);
    expect(region.getAttribute("aria-describedby")).toBe("target-region-help");
    expect(screen.getByText(/Leave blank for the whole country/)).toBeTruthy();
    fireEvent.change(region, { target: { value: "Austin, Texas" } });
    expect(screen.getByText(/in Austin, Texas, United States, any company size\./)).toBeTruthy();
    fireEvent.submit(region.closest("form")!);
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(payload().workspace_updates.target.audience.region).toBe("Austin, Texas");
  });

  test("Edit Target sends the region, including an empty one for an older target", async () => {
    const target = { audience: legacy, summary: "Practice owners", countries, accepted_legal_notice: true, place: "United States" };
    call.mockResolvedValueOnce(target);
    const view = render(<TargetEditor user={user} />);
    let region = (await screen.findByLabelText("State or city (optional)")) as HTMLInputElement;
    expect(region.value).toBe("");
    fireEvent.submit(region.closest("form")!);
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0][0]).toBe("target");
    expect(payload().audience.region).toBe("");
    view.unmount();
    call.mockClear();
    call.mockResolvedValueOnce(target);
    render(<TargetEditor user={user} />);
    region = (await screen.findByLabelText("State or city (optional)")) as HTMLInputElement;
    fireEvent.change(region, { target: { value: "Texas" } });
    fireEvent.submit(region.closest("form")!);
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(payload().audience).toEqual(dentists);
  });

  test("home summary shows the saved place, falling back to the country", () => {
    const home: HomeSummary = { operator_name: "Synthetic user", metrics: { found: 0, qualified: 0, with_email: 0, contacted: 0, replies: 0 }, credits: { configured: false, balance: null, checked_at: null, synthetic: true }, target: { summary: "Find dentists", audience: dentists, country_name: "United States", place: "Texas, United States" }, recent_activity: [] };
    const view = render(<HomeSummaryPanel home={home} onRefresh={vi.fn(async () => {})} />);
    expect(screen.getByText("Texas, United States · 1-10 employees")).toBeTruthy();
    view.unmount();
    render(<HomeSummaryPanel home={{ ...home, target: { ...home.target, place: undefined } }} onRefresh={vi.fn(async () => {})} />);
    expect(screen.getByText("United States · 1-10 employees")).toBeTruthy();
  });
});

describe("Provider search scope", () => {
  const approval: Approval = { id: "a", tool: "find_leads", summary: "Find 5 leads", credits: 5, emails: 0, preview: { audience: "Dentists in Austin", note: "Saved separately" } };

  test("find-leads approval separates the provider search from qualification", () => {
    const view = render(<ApprovalCard approval={{ ...approval, preview: { ...approval.preview, ...scope, changes_search: true } }} expiresAt={null} busy={false} onApprove={vi.fn()} />);
    expect(screen.getByText("Provider search:").parentElement?.textContent).toContain(scope.search);
    expect(screen.getByText("Changed for this request")).toBeTruthy();
    expect(screen.getByText("Qualification only:").parentElement?.textContent).toContain(scope.qualification);
    view.unmount();
    render(<ApprovalCard approval={{ ...approval, preview: { ...approval.preview, ...scope } }} expiresAt={null} busy={false} onApprove={vi.fn()} />);
    expect(screen.getByText("Provider search:")).toBeTruthy();
    expect(screen.queryByText("Changed for this request")).toBeNull();
  });

  test("approvals without a scope render no scope lines", () => {
    render(<ApprovalCard approval={approval} expiresAt={null} busy={false} onApprove={vi.fn()} />);
    expect(screen.getByText("Dentists in Austin")).toBeTruthy();
    expect(screen.queryByText("Provider search:")).toBeNull();
    expect(screen.queryByText("Qualification only:")).toBeNull();
  });

  test("Chat discovery card shows the run's scope and nothing for older runs", () => {
    const view = render(<ChatDiscoveryCard data={{ ...progress, search_scope: scope }} />);
    expect(screen.getByText("Provider search:").parentElement?.textContent).toContain(scope.search);
    expect(screen.getByText("Qualification only:").parentElement?.textContent).toContain(scope.qualification);
    view.unmount();
    const older = render(<ChatDiscoveryCard data={{ ...progress, search_scope: null }} />);
    expect(screen.queryByText("Provider search:")).toBeNull();
    older.unmount();
    render(<ChatDiscoveryCard data={progress} />);
    expect(screen.queryByText("Qualification only:")).toBeNull();
  });

  test("Workspace discovery progress shows the run's scope and nothing for older runs", async () => {
    call.mockResolvedValueOnce({ ...progress, status: "completed", goal_reached: true, search_scope: scope });
    const view = render(<DiscoveryLive user={user} runId="run1" />);
    expect((await screen.findByText("Provider search:")).parentElement?.textContent).toContain(scope.search);
    expect(screen.getByText("Qualification only:").parentElement?.textContent).toContain(scope.qualification);
    view.unmount();
    call.mockResolvedValueOnce({ ...progress, status: "completed", goal_reached: true });
    render(<DiscoveryLive user={user} runId="run1" />);
    expect((await screen.findAllByText("Discovery Complete")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Provider search:")).toBeNull();
  });
});
