import { describe, test, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import ResultsPage, { percent, type Results } from "@/components/results";
import { user } from "./fixtures";

const call = vi.mocked(api);
const trend = Array.from({ length: 30 }, (_, i) => ({ date: `2026-09-${String(i + 1).padStart(2, "0")}`, sent: i === 29 ? 4 : 0, replies: i === 29 ? 1 : 0 }));
const data: Results = {
  period: "30", min_sample: 10, trend,
  overview: { sent: 4, contacted: 3, replied: 1, reply_rate: 0.3333, bounced: 1, bounce_rate: 0.2, opted_out: 0 },
  campaigns: [{ id: "c1", name: "Dentists October", status: "active", recipients: 5, contacted: 3, sent: 4, replied: 1, reply_rate: 0.3333, bounced: 1, opted_out: 0, estimated: false,
    steps: [{ step: 0, subject: "Quick question", sent: 3, replies: 0, reply_rate: 0 }, { step: 1, subject: "One more idea", sent: 1, replies: 1, reply_rate: 1 }] }],
  best_campaign: null, best_message: null,
};

describe("Results page", () => {
  test("shows reply rate first, campaigns with per-step results, and honest empty rankings", async () => {
    call.mockResolvedValue(data);
    render(<ResultsPage user={user} />);
    const summary = await screen.findByLabelText("Summary");
    expect(within(summary).getByText("33.3%")).toBeTruthy();
    expect(within(summary).getByText("1 of 3 people replied")).toBeTruthy();
    expect(screen.getByText("Shows once a campaign has emailed 10 people.")).toBeTruthy();
    await userEvent.click(screen.getByText("Dentists October"));
    expect(screen.getByText("Follow-up 1")).toBeTruthy();
    expect(screen.getByText("One more idea")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Emails sent per day" })).toBeTruthy();
  });

  test("period buttons request the chosen range", async () => {
    call.mockResolvedValue(data);
    render(<ResultsPage user={user} />);
    await screen.findByLabelText("Summary");
    await userEvent.click(screen.getByRole("button", { name: "All time" }));
    await waitFor(() => expect(String(call.mock.lastCall?.[0])).toBe("results?period=all"));
    expect(screen.getByRole("button", { name: "All time" }).getAttribute("aria-pressed")).toBe("true");
  });

  test("no sends shows a plain empty state, not an empty chart", async () => {
    call.mockResolvedValue({ ...data, overview: { ...data.overview, sent: 0, contacted: 0, replied: 0, reply_rate: null, bounced: 0, bounce_rate: null }, trend: trend.map((p) => ({ ...p, sent: 0, replies: 0 })), campaigns: [] });
    render(<ResultsPage user={user} />);
    expect(await screen.findByText("No emails sent in this period.")).toBeTruthy();
    expect(screen.getByText(/No campaign emails in this period/)).toBeTruthy();
  });

  test("percent formatting", () => {
    expect(percent(null)).toBe("—");
    expect(percent(0.125)).toBe("12.5%");
    expect(percent(1)).toBe("100%");
  });
});
