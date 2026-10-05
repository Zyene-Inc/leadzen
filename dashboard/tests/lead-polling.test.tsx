import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import LeadDetail from "@/components/lead-detail";
import { api } from "@/lib/client-api";
import { lead, user } from "./fixtures";

const call = vi.mocked(api);
const running = { ...lead, lookup: { run_id: "test-run", status: "running", credits_used: null, synthetic: false } };
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe("lead detail production polling", () => {
  test("a slow lookup refresh cannot start overlapping requests", async () => {
    let finish!: (value: typeof running) => void;
    call.mockResolvedValueOnce(running).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    vi.useFakeTimers();
    await act(async () => { render(<LeadDetail user={user} contactId={lead.id} />); });
    expect(screen.getByRole("heading", { name: lead.name })).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(call).toHaveBeenCalledTimes(2);
    await act(async () => { finish(running); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(call).toHaveBeenCalledTimes(3);
  });

  test("hidden tabs pause lookup polling and resume when visible", async () => {
    call.mockResolvedValue(running);
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    vi.useFakeTimers();
    await act(async () => { render(<LeadDetail user={user} contactId={lead.id} />); });
    expect(screen.getByRole("heading", { name: lead.name })).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(call).toHaveBeenCalledTimes(1);
    hidden.mockReturnValue(false);
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(call).toHaveBeenCalledTimes(2);
  });

  test("leaving the lead page aborts an in-flight lookup refresh", async () => {
    call.mockResolvedValueOnce(running).mockImplementation(() => new Promise(() => {}));
    vi.useFakeTimers();
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<LeadDetail user={user} contactId={lead.id} />); });
    expect(screen.getByRole("heading", { name: lead.name })).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    const signal = call.mock.lastCall?.[1]?.signal;
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(call).toHaveBeenCalledTimes(2);
  });
});
