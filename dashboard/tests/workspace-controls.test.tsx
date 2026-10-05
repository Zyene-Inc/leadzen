import { describe, test, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import Contacts from "@/components/contacts";
import Campaigns from "@/components/campaigns";
import DiscoveryLive from "@/components/discovery-live";
import Inbox from "@/components/inbox";
import SettingsPage from "@/components/settings";
import { SettingsEditor } from "@/components/settings-editor";
import { SettingsData } from "@/components/settings-data";
import { SettingsTest } from "@/components/settings-test";
import { SetupMailboxPreset } from "@/components/setup-mailbox";
import { ApprovalCard } from "@/components/chat-results";
import { ChatHistory } from "@/components/chat-history";
import Tour from "@/components/tour";
import { settingSections, settingTitles } from "@/lib/workspace-settings";
import { leadFilters } from "@/lib/leads";
import { user, settings, lead, progress } from "./fixtures";

const call = vi.mocked(api);
const writes = () => call.mock.calls.filter(([, init]) => !!init?.method);
const payload = (index = 0) => JSON.parse(String(writes()[index][1]?.body));
const row = { id: "c1", name: "Reviewed campaign", category: "outreach", status: "active", automatic_followups: false, steps: [{ subject: "Hello", body: "Reviewed message", delay_days: 0 }], total: 1, sent: 0, from_address: "sender@example.com", target: "Owners", product: "Product", booking_link: "", signature: "", delay_basis: "working_days", delay_timezone: "America/New_York", recipients: [{ id: 1, email: lead.email, status: "pending", next_step: 0, next_send_at: null }] };

for (let repetition = 1; repetition <= 10; repetition++) describe(`Workspace controls pass ${repetition}`, () => {
  test("lead filters, search, pagination, links and form cancellation", async () => {
    call.mockResolvedValue({ items: [lead], total: 51 });
    render(<Contacts user={user} />);
    await screen.findByRole("link", { name: "View Bruce" });
    expect(screen.getByRole("link", { name: "View Bruce" }).getAttribute("href")).toBe("/contacts/1");
    for (const [key, label] of leadFilters) {
      await userEvent.click(screen.getByRole("button", { name: label }));
      await waitFor(() => expect(String(call.mock.lastCall?.[0])).toContain(`stage=${key}`));
    }
    fireEvent.change(screen.getByLabelText("Search leads"), { target: { value: "Bruce & Practice" } });
    await waitFor(() => expect(String(call.mock.lastCall?.[0])).toContain("q=Bruce%20%26%20Practice"));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(String(call.mock.lastCall?.[0])).toContain("offset=50"));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Add contact" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(writes()).toHaveLength(0);
  });
  test("Add contact and Edit save exact fields once", async () => {
    call.mockResolvedValue({ items: [lead], total: 1 });
    render(<Contacts user={user} />);
    await screen.findByRole("button", { name: "Edit" });
    await userEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Email", { exact: true }), { target: { value: "new@example.com" } });
    const save = screen.getByRole("button", { name: "Save contact" });
    fireEvent.click(save); fireEvent.click(save);
    await screen.findByText("Contact saved.");
    expect(writes()).toHaveLength(1); expect(payload()).toMatchObject({ email: "new@example.com", opted_in: false });
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect((screen.getByLabelText("Email", { exact: true }) as HTMLInputElement).readOnly).toBe(true);
    fireEvent.change(screen.getByLabelText("First name"), { target: { value: "Updated" } });
    await userEvent.click(screen.getByRole("button", { name: "Save contact" }));
    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(payload(1)).toMatchObject({ first_name: "Updated" });
  });
  test("Stop, opt-out Cancel/confirm, and delete Cancel/confirm preserve boundaries", async () => {
    call.mockResolvedValue({ items: [lead], total: 1 });
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Contacts user={user} />);
    await screen.findByRole("button", { name: "Stop" });
    await userEvent.click(screen.getByRole("button", { name: "Opt out" }));
    expect(writes()).toHaveLength(0);
    vi.mocked(window.confirm).mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Opt out" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(payload()).toEqual({ suppress: true });
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(writes()).toHaveLength(2)); expect(payload(1)).toEqual({ stop: true });
    await userEvent.click(screen.getByRole("button", { name: "Delete Bruce" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(writes()).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Delete Bruce" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete contact" }));
    await waitFor(() => expect(writes()).toHaveLength(3));
    expect(writes()[2][1]?.method).toBe("DELETE");
  });
  test("CSV rejects malformed input and imports quoted rows correctly", async () => {
    call.mockResolvedValue({ items: [], total: 0 });
    render(<Contacts user={user} />);
    fireEvent.change(screen.getByLabelText("CSV contacts"), { target: { value: 'email,first_name\n"unclosed' } });
    await userEvent.click(screen.getByRole("button", { name: "Import contacts" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "CSV contains an unclosed quoted field");
    expect(writes()).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("CSV contacts"), { target: { value: 'email,company,opted_in\nnew@example.com,"Practice, Inc",true' } });
    await userEvent.click(screen.getByRole("button", { name: "Import contacts" }));
    await screen.findByText("Contacts imported.");
    expect(payload()).toEqual({ contacts: [{ email: "new@example.com", company: "Practice, Inc", opted_in: true }] });
  });
  test("outreach pause, resume review and archive preserve approval boundaries", async () => {
    let current = row;
    call.mockImplementation(async (path, init) => {
      if (path === "autopilot") return { setup: { revision: "r", blockers: [], target: "Owners", product: "Product", sender: "sender@example.com", signature: "", booking_link: "", service_enabled: false }, policy: null, runs: [] };
      if (init?.method) { current = { ...current, status: init.method === "DELETE" ? "archived" : JSON.parse(String(init.body)).status }; return current; }
      if (path === "outreach") return { reviews: [], window: { start: 8, end: 20, timezone: "UTC" } };
      if (path.includes("/preview")) return { from_address: row.from_address, revision: "revision", recipients: [], automatic_available: false };
      return path === "campaigns" ? { items: [current] } : { items: [] };
    });
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Campaigns user={user} />);
    await screen.findByText("Reviewed campaign");
    await userEvent.click(screen.getByRole("button", { name: "Pause outreach" }));
    await userEvent.click(await screen.findByRole("button", { name: "Review & resume" }));
    await screen.findByText(/No eligible emails are due/);
    expect(writes()).toHaveLength(1); // Opening a paused review must never activate it.
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop & archive" }));
    expect(writes()).toHaveLength(1);
    vi.mocked(window.confirm).mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Stop & archive" }));
    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1][1]?.method).toBe("DELETE");
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  });
  test("outreach selects leads, defaults follow-ups off, saves and opens exact review without sending", async () => {
    call.mockImplementation(async (path, init) => {
      if (path === "autopilot") return { setup: { revision: "r", blockers: [], target: "Owners", product: "Product", sender: "sender@example.com", signature: "", booking_link: "", service_enabled: false }, policy: null, runs: [] };
      if (init?.method) return { ...row, ...JSON.parse(String(init.body)), status: "draft" };
      if (path === "outreach") return { reviews: [], ai_ready: false, window: { start: 8, end: 20, timezone: "UTC" } };
      if (path.includes("/preview")) return { from_address: row.from_address, revision: "revision", recipients: [], automatic_available: false };
      return path.startsWith("leads") ? { items: [lead], total: 1, limit: 50 } : { items: [] };
    });
    render(<Campaigns user={user} />);
    await userEvent.click(await screen.findByRole("button", { name: "New outreach" }));
    await userEvent.click(await screen.findByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Prepare drafts" }));
    expect(screen.getAllByLabelText("Subject")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Add follow-ups" }));
    await userEvent.click(screen.getByRole("button", { name: "Add second follow-up" }));
    expect(screen.getAllByLabelText("Days after the previous email").map(e => (e as HTMLInputElement).value)).toEqual(["3", "5"]);
    expect(screen.queryByRole("button", { name: "Add second follow-up" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Turn off follow-ups" }));
    fireEvent.change(screen.getByLabelText("Outreach name"), { target: { value: "New outreach" } });
    fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "Hello" } });
    fireEvent.change(screen.getByLabelText("Message", { exact: true }), { target: { value: "Reviewed copy" } });
    await userEvent.click(screen.getByRole("button", { name: "Review & send" }));
    await screen.findByRole("heading", { name: "Confirm outreach" });
    expect(payload()).toMatchObject({ name: "New outreach", contact_ids: [1], delay_basis: "working_days", steps: [{ subject: "Hello", body: "Reviewed copy", delay_days: 0 }] });
    expect(writes()).toHaveLength(1);
    expect(writes()[0][0]).toBe("campaigns");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("Subject")).toHaveProperty("value", "Hello");
  });
  test.each(["pause", "stop", "resume"])("discovery %s targets only the current run", async action => {
    call.mockResolvedValue({ ...progress, status: action === "resume" ? "paused" : "running" });
    render(<DiscoveryLive user={user} runId="run1" />);
    const button = await screen.findByRole("button", { name: action === "pause" ? "Pause Finding" : action === "resume" ? "Resume Finding" : "Stop" });
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0][0]).toBe(`discovery/run1/${action}`);
  });
  test("completed discovery links and Find Emails open a cancellable paid review", async () => {
    call.mockImplementation(async path => path.endsWith("/emails") ? { revision: "x", note: "", items: [] } : { ...progress, status: "completed", goal_reached: true });
    render(<DiscoveryLive user={user} runId="run1" />);
    expect((await screen.findByRole("link", { name: "Review Leads" })).getAttribute("href")).toBe("#discovery-results");
    expect(screen.getByRole("link", { name: "Find More" }).getAttribute("href")).toBe("/find-leads");
    await userEvent.click(screen.getByRole("button", { name: "Find Emails" }));
    await screen.findByText(/No eligible profiles/);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(writes()).toHaveLength(0);
  });
  test.each(settingSections)("Settings %s Edit/Close/Cancel", async section => {
    call.mockResolvedValue(settings);
    render(<SettingsPage user={user} />);
    const edit = await screen.findByRole("button", { name: `Edit ${settingTitles[section]}` });
    await userEvent.click(edit);
    expect(screen.getByRole("button", { name: "Save changes" })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(writes()).toHaveLength(0);
    await userEvent.click(edit);
    await userEvent.click(edit);
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });
  test.each(settingSections)("Settings %s Save uses the settings boundary once", async section => {
    call.mockResolvedValue(settings);
    const saved = vi.fn();
    render(<SettingsEditor section={section} data={settings} cancel={vi.fn()} onBusy={vi.fn()} saved={saved} />);
    const form = screen.getByRole("button", { name: "Save changes" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    expect(writes()).toHaveLength(1); expect(writes()[0][0]).toBe("settings"); expect(writes()[0][1]?.method).toBe("PUT");
    if (section === "ai") {
      expect(Object.keys(payload())).toEqual(["llm"]);
      expect(payload().llm).toEqual({ enabled: settings.llm.enabled, provider: settings.llm.provider, model: settings.llm.model, base_url: settings.llm.base_url, api_key: "" });
    }
    if (section === "finder") expect(payload()).toEqual({ lead_finder: { provider: "bettercontact", api_key: "", clear_api_key: false } });
    if (section === "signature") expect(payload()).toEqual({ mailbox: { signature: settings.mailbox.signature } });
    if (section === "mailbox") {
      expect(Object.keys(payload())).toEqual(["mailbox"]);
      expect(payload().mailbox.signature).toBeUndefined();
      expect(payload().mailbox.password_configured).toBeUndefined();
      expect(payload().mailbox.password).toBe("");
    }
    if (section === "booking") expect(payload()).toEqual({ workspace_updates: { booking_link: settings.workspace.booking_link } });
  });
  test.each(["discovery", "mailbox"] as const)("saved %s test requires separate confirmation", async kind => {
    call.mockResolvedValue(settings);
    render(<SettingsTest kind={kind} data={{ ...settings, lead_finder: { provider: "bettercontact", api_key_configured: true }, mailbox: { ...settings.mailbox, address: "sender@example.com", password_configured: true } }} disabled={false} saved={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Test" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm test" }));
    await waitFor(() => expect(writes()).toHaveLength(1)); expect(payload()).toEqual({ kind });
  });
  test("Backup Database confirms download and guards double clicks", async () => {
    const download = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:synthetic");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("synthetic sqlite fixture", { headers: { "Content-Disposition": 'attachment; filename="workspace.sqlite3"' } }));
    render(<SettingsData data={settings} />);
    const button = screen.getByRole("button", { name: "Backup Database" }); fireEvent.click(button); fireEvent.click(button);
    await screen.findByText("Workspace backup downloaded.");
    expect(fetcher).toHaveBeenCalledOnce(); expect(download).toHaveBeenCalledOnce(); expect(create).toHaveBeenCalledOnce();
  });
  test("mailbox presets emit correct Zoho, Gmail, Microsoft and custom settings", async () => {
    const change = vi.fn();
    render(<SetupMailboxPreset settings={settings} onChange={change} />);
    const select = screen.getByLabelText("Mailbox provider");
    for (const [preset, host, port] of [["zoho", "smtppro.zoho.com", "465"], ["gmail", "smtp.gmail.com", "465"], ["microsoft", "smtp.office365.com", "587"], ["custom", "", "587"]]) {
      await userEvent.selectOptions(select, preset);
      expect(change.mock.lastCall?.[0].mailbox).toMatchObject({ smtp_host: host, smtp_port: port });
    }
    expect(call).not.toHaveBeenCalled();
  });
  test("Inbox search, pagination, conversation and Back read stored data only", async () => {
    call.mockImplementation(async path => path === "inbox/conversations/1" ? { id: 1, name: "Bruce", address: lead.email, can_reply: false, reply_blocker: "Suppressed", total_messages: 1, messages: [{ id: 1, direction: "in", from: lead.email, to: "sender@example.com", subject: "Reply", body: "STOP", body_truncated: false, sent_at: "2026-10-02T12:00:00Z", kind: "human_reply", accepted: false }] } : { items: [{ id: 1, name: "Bruce", address: lead.email, subject: "Reply", snippet: "STOP", last_at: "2026-10-02T12:00:00Z", count: 1 }], total: 51, limit: 50, offset: 0 });
    render(<Inbox user={user} />);
    await userEvent.click(await screen.findByRole("button", { name: /Bruce.*Reply/ }));
    const conversation = await screen.findByRole("region", { name: "Conversation" });
    expect(within(conversation).getByText("STOP")).toBeTruthy();
    expect((within(conversation).getByRole("button", { name: "Suggest reply" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Back to inbox" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(String(call.mock.lastCall?.[0])).toContain("offset=50"));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByRole("button", { name: "Check for replies" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search conversations"), { target: { value: "Bruce" } });
    await waitFor(() => expect(String(call.mock.lastCall?.[0])).toContain("q=Bruce"));
    expect(writes()).toHaveLength(0);
  });
  test("chat exact-action Approve, Cancel, busy and history filter links", async () => {
    const approve = vi.fn();
    const approval = { id: "a1", tool: "sync_replies", summary: "Read this inbox", credits: 0, emails: 0, preview: { note: "Read only" } };
    const { rerender } = render(<ApprovalCard approval={approval} expiresAt={null} busy={false} onApprove={approve} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Approve this action" }));
    expect(approve.mock.calls).toEqual([[false], [true]]);
    rerender(<ApprovalCard approval={approval} expiresAt={null} busy={true} onApprove={approve} />);
    expect((screen.getByRole("button", { name: "Updating…" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<ChatHistory items={[{ id: "t1", title: "Find dental owners", updated_at: new Date().toISOString() }]} />);
    expect(screen.getByRole("link", { name: "New chat" }).getAttribute("href")).toBe("/chat");
    fireEvent.change(screen.getByLabelText("Filter chats"), { target: { value: "absent" } });
    expect(screen.getByText("No matching conversations.")).toBeTruthy();
  });
  test("tour entry opens the guided workspace rather than rendering a slide deck", () => {
    render(<Tour user={user} />);
    expect(screen.getByRole("heading", { name: "Your product tour" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("your real workspace");
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
    expect(call).not.toHaveBeenCalled();
  });
});
