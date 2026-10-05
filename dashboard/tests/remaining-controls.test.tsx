import { describe, test, expect, vi } from "vitest";
import { act, render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import { Activity } from "@/components/activity-feed";
import { Inbox as StoredInbox, Suppression } from "@/components/workspace-records";
import LeadDetail from "@/components/lead-detail";
import Onboarding from "@/components/onboarding";
import Admin from "@/components/admin";
import type { Wizard } from "@/lib/setup-wizard";
import { user, settings, lead } from "./fixtures";

const call = vi.mocked(api);
const writes = () => call.mock.calls.filter(([, init]) => !!init?.method);
const wizard: Wizard = { draft: { ...settings.workspace.identity, ...settings.workspace.product, audience: settings.workspace.target.audience!, discovery_enabled: false, accepted_legal_notice: true }, completed_steps: [], connections: { ...settings, llm: { ...settings.llm, enabled: false } }, checks: settings.workspace.checks, countries: settings.workspace.countries, onboarded: false };

for (let repetition = 1; repetition <= 10; repetition++) describe(`Remaining controls pass ${repetition}`, () => {
  test("Activity defaults to readable events; Developer Logs opens, refreshes and closes", async () => {
    call.mockImplementation(async path => path === "activity/logs" ? { items: [{ id: "l1", label: "Synthetic run", at: "2026-10-02T12:00:00Z", output: "[INF] synthetic only", truncated: false, unavailable: false }] } : { items: [{ id: "a1", title: "Lead qualified", detail: "Bruce", at: "2026-10-02T12:00:00Z", kind: "success", href: "/contacts/1" }], limit: 100 });
    render(<Activity user={user} />);
    await screen.findByText("Lead qualified");
    expect(call.mock.calls.some(([path]) => path === "activity/logs")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Developer Logs" }));
    await screen.findByText("[INF] synthetic only");
    await userEvent.click(screen.getByRole("button", { name: "Refresh logs" }));
    await userEvent.click(screen.getByRole("button", { name: "Close logs" }));
    expect(screen.queryByText("[INF] synthetic only")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(writes()).toHaveLength(0);
  });
  test("suppression list search, pagination and Add/Cancel use stored records", async () => {
    call.mockResolvedValue({ items: [{ id: 1, email: lead.email, reason: "Opted out", suppressed_at: "2026-10-02T12:00:00Z" }], total: 51, limit: 50, offset: 0 });
    render(<Suppression user={user} />);
    await screen.findByText("Opted out");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(String(call.mock.lastCall?.[0])).toContain("offset=50"));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    fireEvent.change(screen.getByLabelText("Search suppression"), { target: { value: "bruce@example.com" } });
    await waitFor(() => expect(String(call.mock.lastCall?.[0])).toContain("q=bruce%40example.com"));
    await userEvent.click(screen.getByRole("button", { name: "Add to suppression list" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect((screen.getByRole("button", { name: "Refresh" }) as HTMLButtonElement).disabled).toBe(false));
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(writes()).toHaveLength(0);
  });
  test("one-lead email review Cancel, final credit choice and duplicate guard", async () => {
    call.mockImplementation(async (path, init) => path.endsWith("/email") ? init?.method ? {} : { eligible: true, reason: "", revision: "e1", name: "Bruce" } : { ...lead, email: "", email_status: "not_requested", lookup: null, timeline: { events: [], sequences: [], blocked_reason: "", can_stop: false, suppression: null } });
    render(<LeadDetail user={user} contactId={1} />);
    await userEvent.click(await screen.findByRole("button", { name: "Find Work Email" }));
    await screen.findByText(/Find an email for Bruce/);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" })); expect(writes()).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Find Work Email" }));
    await screen.findByText(/Find an email for Bruce/);
    const button = screen.getByRole("button", { name: "Find Email" }); fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(JSON.parse(String(writes()[0][1]?.body))).toMatchObject({ revision: "e1", estimated_credits: 1 });
  });
  test.each([1, 2, 3, 4, 5])("setup step %s Continue sends one draft save; Back preserves draft", async step => {
    const initial = { ...wizard, completed_steps: Array.from({ length: step - 1 }, (_, i) => i + 1) };
    call.mockResolvedValue({ ...initial, completed_steps: [...initial.completed_steps, step] });
    render(<Onboarding user={{ ...user, onboarded: false }} initial={initial} />);
    const form = screen.getByRole("button", { name: "Continue" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    await screen.findByText(new RegExp(`Step ${step + 1} of 6`));
    expect(writes()).toHaveLength(1);
    expect(JSON.parse(String(writes()[0][1]?.body)).step).toBe(step);
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByText(new RegExp(`Step ${step} of 6`))).toBeTruthy();
  });
  test("setup Retry is bounded and final failure is visible without losing the draft", async () => {
    const last = { ...wizard, completed_steps: [1, 2, 3, 4, 5] };
    call.mockImplementation(async path => { if (path === "onboarding/complete") throw new Error("Synthetic completion held"); return last; });
    render(<Onboarding user={{ ...user, onboarded: false }} initial={null} />);
    const retry = screen.getByRole("button", { name: "Retry loading setup" }); fireEvent.click(retry); fireEvent.click(retry);
    await screen.findByText(/Step 6 of 6/);
    expect(call).toHaveBeenCalledOnce();
    fireEvent.submit(screen.getByRole("button", { name: "Finish setup" }).closest("form")!);
    await screen.findByText("Synthetic completion held");
    expect(writes().map(([path]) => path)).toEqual(["onboarding/wizard", "onboarding/complete"]);
  });
  test("admin actions confirm deletion/reset, disable once, and filter employees", async () => {
    const employee = { ...user, id: 2 };
    call.mockResolvedValue({ users: [employee], totals: { users: 1, active: 1, admins: 0, onboarded: 1 } });
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Admin user={{ ...user, is_admin: true }} />);
    await screen.findByRole("button", { name: "Disable" });
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Reset via email" })); expect(writes()).toHaveLength(0);
    const disable = screen.getByRole("button", { name: "Disable" }); fireEvent.click(disable); fireEvent.click(disable);
    await screen.findByText("Employee access updated."); expect(writes()).toHaveLength(1);
    expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ is_active: false });
    vi.mocked(window.confirm).mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Reset via email" }));
    await screen.findByText("Setup invitation sent. Earlier setup links have been revoked.");
    expect(writes()[1][0]).toBe("admin/users/2/invite");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await screen.findByText("Employee deleted; access revoked."); expect(writes()[2][1]?.method).toBe("DELETE");
  });
});

test.each([
  ["stored Inbox", StoredInbox, "Loading inbox…"],
  ["suppression", Suppression, "Loading suppression list…"],
] as const)("%s clears the previous error while refreshing and after recovery", async (_name, View, loadingText) => {
  const recovered = { items: [], total: 0, limit: 50, offset: 0 };
  let complete!: (value: typeof recovered) => void;
  call.mockRejectedValueOnce(new Error("Temporary read failure"))
    .mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  render(<View user={user} />);
  await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("status").textContent).toBe(loadingText);
  await act(async () => complete(recovered));
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(writes()).toHaveLength(0);
});
