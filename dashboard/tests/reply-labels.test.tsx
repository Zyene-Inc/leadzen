import { expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import Inbox from "@/components/inbox";
import { replyLabelDetail } from "@/lib/reply-labels";
import { user } from "./fixtures";

vi.mock("@/components/sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/lib/workspace-context", () => ({ useWorkspaceContext: vi.fn(), recordWorkspaceContext: vi.fn() }));

const call = vi.mocked(api);
const row = (id: number, name: string, label: string, extra = {}) => ({
  id, name, address: `${name.toLowerCase()}@example.com`, subject: "Re: Patient reviews", snippet: "…", kind: "human_reply",
  last_at: "2026-11-04T15:00:00Z", count: 2, reply_label: { label, return_date: null, action: "", ...extra },
});

test("Inbox shows reply labels and filters by label without sending anything", async () => {
  call.mockReset();
  call.mockImplementation(async (path: string) => {
    if (path.startsWith("inbox/conversations?") && path.includes("label=interested"))
      return { items: [row(1, "Bruce", "interested")], total: 1, limit: 50, offset: 0 };
    if (path.startsWith("inbox/conversations?"))
      return { items: [row(1, "Bruce", "interested"), row(2, "Ann", "out_of_office", { return_date: "2026-11-18", action: "held" })], total: 2, limit: 50, offset: 0 };
    return { items: [] };
  });
  render(<Inbox user={user} />);
  const list = await screen.findByRole("region", { name: "Inbox conversations" });
  const chip = (text: string) => within(list).getAllByText(text).find((el) => el.classList.contains("reply-label"));
  await within(list).findByText("2 conversations");
  expect(chip("Interested")).toBeTruthy();
  expect(chip("Out of office")?.getAttribute("title")).toBe("Back Nov 18. Follow-ups wait until the next business day.");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter by reply label" }), "interested");
  await within(list).findByText("1 conversation");
  expect(call.mock.calls.some(([path]) => String(path).includes("label=interested"))).toBe(true);
  expect(call.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});

test("label details say what LeadZen did", () => {
  expect(replyLabelDetail("unsubscribe", null, "blocked")).toBe("Added to Do not contact.");
  expect(replyLabelDetail("out_of_office", null, "held")).toBe("No return date found. Follow-ups wait 7 days.");
  expect(replyLabelDetail("interested", null, "")).toBe("");
});
