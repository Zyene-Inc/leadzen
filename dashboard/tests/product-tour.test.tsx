import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import { user } from "./fixtures";
import Tour from "@/components/tour";

const navigation = vi.hoisted(() => ({ pathname: "/", push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname, useRouter: () => navigation }));

// The provider exercises a short, real DOM interaction flow; the production steps
// remain covered by the browser walkthrough and their existing screen tests.
import { ProductTourProvider, useProductTour } from "@/components/product-tour-provider";
import type { Account } from "@/lib/auth";
import { placeTooltip, settleTourTarget, visibleTourElement, waitForTourCondition, waitForTourElement, type TourRect, type TourViewport } from "@/lib/product-tour-dom";
import { readPendingTour, storeTour, tourIsActive, tourStorageKey, type ProductTourState } from "@/lib/product-tour-state";

vi.mock("@/lib/product-tour-steps", () => ({ productTourSteps: [
  { id: "welcome", route: "/", target: '[data-tour="first"]', title: "Welcome to the workspace", body: "Review your work here." },
  { id: "open", route: "/", target: '[data-tour="open"]', title: "Open the real form", body: "Click Open details.", action: { kind: "click", label: "Click Open details", success: '[data-tour="form"]' } },
  { id: "ready", route: "/next", target: '[data-tour="final"]', title: "You’re ready", body: "You can restart in Settings." },
] }));

const call = vi.mocked(api);
const emptyTour = (): ProductTourState => ({ tourStarted: false, currentStep: "welcome", tourCompleted: false, tourSkipped: false });
const activeTour = (currentStep = "welcome"): ProductTourState => ({ ...emptyTour(), tourStarted: true, currentStep });
const rect = (left = 100, top = 100, width = 100, height = 40): TourRect => ({ left, top, right: left + width, bottom: top + height, width, height });
let serverTour: ProductTourState;
let resizeCallbacks: Set<ResizeObserverCallback>;

beforeEach(() => {
  localStorage.clear();
  navigation.pathname = "/";
  window.history.replaceState({}, "", "/");
  serverTour = emptyTour();
  resizeCallbacks = new Set();
  call.mockImplementation(async (path, init) => {
    if (path !== "tour") throw new Error(`Unexpected product action: ${path}`);
    const { action, currentStep } = JSON.parse(String(init?.body));
    if (action === "start") serverTour = activeTour(currentStep);
    if (action === "progress") serverTour = { ...serverTour, currentStep };
    if (action === "complete") serverTour = { ...serverTour, currentStep, tourCompleted: true, tourSkipped: false };
    if (action === "skip") serverTour = { ...serverTour, currentStep, tourCompleted: false, tourSkipped: true };
    return { tour: serverTour };
  });
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 5));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => window.clearTimeout(id));
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) { resizeCallbacks.add(callback); }
    observe() {} unobserve() {} disconnect() {}
  });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, media: "(prefers-reduced-motion: reduce)", addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(function (this: HTMLElement) {
    if (this.hidden || this.closest('[hidden], [style*="display: none"]')) return [] as unknown as DOMRectList;
    return [this.getBoundingClientRect()] as unknown as DOMRectList;
  });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const bounds = rect(Number(this.dataset.left ?? 100), Number(this.dataset.top ?? 100), this.getAttribute("role") === "dialog" ? 320 : 160, this.getAttribute("role") === "dialog" ? 230 : 44);
    return { ...bounds, x: bounds.left, y: bounds.top, toJSON: () => bounds } as DOMRect;
  });
  if (!HTMLElement.prototype.scrollIntoView) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: () => {} });
  vi.spyOn(HTMLElement.prototype, "scrollIntoView").mockImplementation(() => {});
});

afterEach(() => { document.querySelectorAll('[data-tour="late"]').forEach(element => element.remove()); vi.useRealTimers(); vi.unstubAllGlobals(); });

function Registration({ account }: { account: Account }) {
  const context = useProductTour();
  useEffect(() => { context?.register(account); }, [account, context?.register]);
  return <button onClick={() => void context?.start(account)}>Restart walkthrough</button>;
}

function Harness({ account = { ...user, tour: emptyTour() }, form = false }: { account?: Account; form?: boolean }) {
  return <ProductTourProvider><Registration account={account} /><button data-tour="first">Attention list</button><button data-tour="open">Open details</button>{form && <form data-tour="form"><input aria-label="Contact email" /></form>}<button data-tour="final">Settings help</button></ProductTourProvider>;
}
const writes = () => call.mock.calls.map(([, init]) => JSON.parse(String(init?.body)));
const advanceRoute = (path: string) => { navigation.pathname = path; window.history.pushState({}, "", path); fireEvent(window, new PopStateEvent("popstate")); };

function appendTarget(attributes: Record<string, string> = {}) {
  const target = document.createElement("button");
  target.dataset.tour = "late";
  for (const [key, value] of Object.entries(attributes)) target.setAttribute(key, value);
  document.body.append(target);
  return target;
}

describe("product tour readiness and positioning", () => {
  test("waits for a rendered, enabled target after loading clears", async () => {
    const controller = new AbortController();
    let found = false;
    const ready = waitForTourElement('[data-tour="late"]', controller.signal).then(value => { found = true; return value; });
    const loading = appendTarget({ "aria-busy": "true" });
    await Promise.resolve();
    expect(found).toBe(false);
    loading.removeAttribute("aria-busy");
    expect(await ready).toBe(loading);
    loading.remove();
  });

  test("hidden duplicate targets never win and disabled actions wait until enabled", async () => {
    const hidden = appendTarget({ hidden: "" });
    const disabled = appendTarget({ disabled: "" });
    const ready = waitForTourElement('[data-tour="late"]', new AbortController().signal);
    expect(visibleTourElement('[data-tour="late"]')).toBeNull();
    disabled.removeAttribute("disabled");
    expect(await ready).toBe(disabled);
    hidden.remove(); disabled.remove();
  });

  test("real click success waits for modal visibility, absence and route", async () => {
    const target = appendTarget({ hidden: "" });
    let completed = false;
    const ready = waitForTourCondition({ success: '[data-tour="late"]', route: "/next" }, new AbortController().signal).then(() => { completed = true; });
    target.hidden = false;
    await Promise.resolve();
    expect(completed).toBe(false);
    advanceRoute("/next");
    await ready;
    const closed = waitForTourCondition({ absent: '[data-tour="late"]' }, new AbortController().signal);
    target.remove();
    await closed;
  });

  test("aborting a target wait releases observers and never resolves a late target", async () => {
    const controller = new AbortController();
    const ready = waitForTourElement('[data-tour="late"]', controller.signal);
    const result = expect(ready).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await result;
    const target = appendTarget();
    target.remove();
  });

  test("missing targets have a bounded recovery instead of locking indefinitely", async () => {
    vi.useFakeTimers();
    const ready = waitForTourElement('[data-tour="missing"]', new AbortController().signal, 50);
    const result = expect(ready).rejects.toThrow("not available");
    await vi.advanceTimersByTimeAsync(50);
    await result;
  });

  test.each<[TourRect, { width: number; height: number }, TourViewport]>([
    [rect(20, 20), { width: 320, height: 230 }, { width: 390, height: 844 }],
    [rect(380, 830), { width: 320, height: 230 }, { width: 390, height: 844 }],
    [rect(-80, -30), { width: 320, height: 230 }, { width: 390, height: 844 }],
    [rect(200, 540), { width: 900, height: 700 }, { width: 320, height: 580 }],
    [rect(90, 540), { width: 320, height: 230 }, { width: 390, height: 400, left: 0, top: 250 }],
  ])("keeps tooltips within viewport edges and keyboard viewport %#", (anchor, box, viewport) => {
    const placed = placeTooltip(anchor, box, viewport);
    expect(placed.left).toBeGreaterThanOrEqual((viewport.left ?? 0) + 12);
    expect(placed.top).toBeGreaterThanOrEqual((viewport.top ?? 0) + 12);
    expect(placed.left + Math.min(box.width, viewport.width - 24)).toBeLessThanOrEqual((viewport.left ?? 0) + viewport.width - 12);
    expect(placed.top + Math.min(box.height, viewport.height - 24)).toBeLessThanOrEqual((viewport.top ?? 0) + viewport.height - 12);
  });

  test("uses the preferred side when it fits and flips away from bottom clipping", () => {
    expect(placeTooltip(rect(10, 200), { width: 320, height: 200 }, { width: 1024, height: 768 }, "right").side).toBe("right");
    expect(placeTooltip(rect(200, 730), { width: 320, height: 200 }, { width: 1024, height: 768 }, "bottom").side).toBe("top");
  });

  test("reduced motion removes the reading animation beat after geometry stabilizes", async () => {
    vi.useFakeTimers();
    const target = appendTarget();
    let reducedSettled = false, animatedSettled = false;
    const reduced = settleTourTarget(target, new AbortController().signal, true).then(() => { reducedSettled = true; });
    const animated = settleTourTarget(target, new AbortController().signal, false).then(() => { animatedSettled = true; });
    await vi.advanceTimersByTimeAsync(100);
    expect(reducedSettled).toBe(true);
    expect(animatedSettled).toBe(false);
    await vi.advanceTimersByTimeAsync(350);
    await Promise.all([reduced, animated]);
    target.remove();
  });
});

describe("tour persistence", () => {
  test("browser recovery state is private to the current account", () => {
    const value = { tour: activeTour("open"), pending: true, action: "progress" as const };
    storeTour(user.id, value);
    expect(readPendingTour(user.id)).toEqual(value);
    expect(readPendingTour(user.id + 1)).toBeNull();
    expect(tourIsActive(value.tour)).toBe(true);
    expect(tourIsActive({ ...value.tour, tourSkipped: true })).toBe(false);
    expect(tourIsActive({ ...value.tour, tourCompleted: true })).toBe(false);
  });

  test.each(["not-json", JSON.stringify({ tour: activeTour(), pending: false, action: "progress" }), JSON.stringify({ tour: { ...activeTour(), currentStep: "../private" }, pending: true, action: "progress" }), JSON.stringify({ tour: activeTour(), pending: true, action: "send" })])("ignores corrupt, acknowledged or invalid stored recovery state %#", data => {
    localStorage.setItem(tourStorageKey(user.id), data);
    expect(readPendingTour(user.id)).toBeNull();
  });
});

describe("live product tour orchestration", () => {
  test("guidance for a native dialog target stays inside the dialog", async () => {
    render(<ProductTourProvider><Registration account={{ ...user, tour: activeTour() }} /><dialog open aria-label="Contact details"><button data-tour="first">Dialog action</button></dialog></ProductTourProvider>);
    const guidance = await screen.findByRole("dialog", { name: "Welcome to the workspace" });
    const actualDialog = screen.getByRole("dialog", { name: "Contact details" }) as HTMLDialogElement;
    expect(actualDialog.contains(guidance)).toBe(true);
    await userEvent.click(within(guidance).getByRole("button", { name: "Skip tour" }));
    expect(actualDialog.open).toBe(true);
    expect(screen.queryByRole("dialog", { name: "Welcome to the workspace" })).toBeNull();
  });

  test("inactive, completed and skipped tours leave the application usable", async () => {
    const { rerender } = render(<Harness account={{ ...user, tour: emptyTour() }} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Open details" }));
    expect(call).not.toHaveBeenCalled();
    rerender(<Harness account={{ ...user, id: user.id + 1, tour: { ...activeTour(), tourCompleted: true } }} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(<Harness account={{ ...user, id: user.id + 2, tour: { ...activeTour(), tourSkipped: true } }} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(call).not.toHaveBeenCalled();
  });

  test("starts on real targets and requires the click and rendered form before advancing", async () => {
    const account = { ...user, tour: emptyTour() };
    const { rerender } = render(<Harness account={account} />);
    await userEvent.click(screen.getByRole("button", { name: "Restart walkthrough" }));
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    expect(writes()[0]).toMatchObject({ action: "start", currentStep: "welcome" });
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { name: "Open the real form" });
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Attention list" }));
    expect(screen.getByRole("heading", { name: "Open the real form" })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Open details" }));
    expect(screen.getByRole("heading", { name: "Open the real form" })).toBeTruthy();
    expect(navigation.push.mock.calls.some(([path]) => path === "/next")).toBe(false);
    rerender(<Harness account={account} form />);
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/next"));
    expect(screen.queryByRole("heading", { name: "You’re ready" })).toBeNull();
    advanceRoute("/next");
    rerender(<Harness account={account} form />);
    await screen.findByRole("heading", { name: "You’re ready" });
    expect(writes().every(value => ["start", "progress"].includes(value.action))).toBe(true);
    expect(call.mock.calls.every(([path]) => path === "tour")).toBe(true);
  });

  test("an already visible action result does not advance without the real user click", async () => {
    render(<Harness account={{ ...user, tour: activeTour("open") }} form />);
    await screen.findByRole("heading", { name: "Open the real form" });
    expect(navigation.push).not.toHaveBeenCalledWith("/next");
    expect(writes()).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Open details" }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/next"));
  });

  test("Back preserves progress, navigates to the prior page and waits for its UI", async () => {
    advanceRoute("/next");
    const account = { ...user, tour: activeTour("ready") };
    const { rerender } = render(<Harness account={account} />);
    await screen.findByRole("heading", { name: "You’re ready" });
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/"));
    expect(screen.queryByRole("heading", { name: "Open the real form" })).toBeNull();
    advanceRoute("/");
    rerender(<Harness account={account} />);
    await screen.findByRole("heading", { name: "Open the real form" });
    expect(writes()).toContainEqual({ action: "progress", currentStep: "open" });
  });

  test("refresh resumes the saved step without starting over", async () => {
    const account = { ...user, tour: activeTour("open") };
    const rendered = render(<Harness account={account} />);
    await screen.findByRole("heading", { name: "Open the real form" });
    rendered.unmount();
    render(<Harness account={account} />);
    await screen.findByRole("heading", { name: "Open the real form" });
    expect(screen.queryByRole("heading", { name: "Welcome to the workspace" })).toBeNull();
    expect(writes()).toHaveLength(0);
  });

  test("Skip clears the spotlight immediately and records a terminal state", async () => {
    render(<Harness account={{ ...user, tour: activeTour() }} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(writes()).toContainEqual({ action: "skip", currentStep: "welcome" }));
    expect(serverTour.tourSkipped).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Open details" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("Escape skips the tour and restores connected focus", async () => {
    const account = { ...user, tour: emptyTour() };
    render(<Harness account={account} />);
    const restart = screen.getByRole("button", { name: "Restart walkthrough" });
    await userEvent.click(restart);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(writes().at(-1)).toMatchObject({ action: "skip" }));
    expect(document.activeElement).toBe(restart);
  });

  test("Finish persists completion and restarting explicitly begins again", async () => {
    advanceRoute("/next");
    const account = { ...user, tour: activeTour("ready") };
    const { rerender } = render(<Harness account={account} />);
    await screen.findByRole("heading", { name: "You’re ready" });
    await userEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(writes()).toContainEqual({ action: "complete", currentStep: "ready" }));
    expect(serverTour.tourCompleted).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Restart walkthrough" }));
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/"));
    advanceRoute("/");
    rerender(<Harness account={account} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    expect(writes().at(-1)).toMatchObject({ action: "start", currentStep: "welcome" });
  });

  test("a failed Skip save cannot keep the page dimmed and survives refresh for retry", async () => {
    call.mockRejectedValue(new Error("Connection unavailable"));
    render(<Harness account={{ ...user, tour: activeTour() }} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(readPendingTour(user.id)?.tour.tourSkipped).toBe(true));
    expect(readPendingTour(user.id)?.action).toBe("skip");
  });

  test("a missing target offers recovery while removing the blocking spotlight", async () => {
    vi.useFakeTimers();
    render(<ProductTourProvider><Registration account={{ ...user, tour: activeTour() }} /></ProductTourProvider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(10100); });
    const retry = screen.getByRole("button", { name: /Retry|Try again/i });
    expect(retry).toBeTruthy();
    expect(screen.getByRole("button", { name: "Skip tour" })).toBeTruthy();
    const target = appendTarget();
    target.dataset.tour = "first";
    fireEvent.click(retry);
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(screen.getByRole("heading", { name: "Welcome to the workspace" })).toBeTruthy();
    target.remove();
  });

  test("dialog copy and progress are accessible and target scrolling respects reduced motion", async () => {
    render(<Harness account={{ ...user, tour: activeTour() }} />);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.getAttribute("aria-labelledby")).toBeTruthy();
    expect(dialog.getAttribute("aria-describedby")).toBeTruthy();
    expect(within(dialog).getByText(/1 of 3/)).toBeTruthy();
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: "instant" }));
  });
});

describe("tour navigation and viewport changes", () => {
  test("unrelated navigation pauses without pulling the employee back", async () => {
    const account = { ...user, tour: activeTour() };
    const { rerender } = render(<Harness account={account} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    navigation.push.mockClear();
    advanceRoute("/elsewhere");
    rerender(<Harness account={account} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Tour paused")).toBeTruthy();
    expect(navigation.push).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Resume tour" }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/"));
    advanceRoute("/");
    rerender(<Harness account={account} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    expect(writes()).toHaveLength(0);
  });

  test("keyboard arrows honor an interaction step and Back remains available", async () => {
    render(<Harness account={{ ...user, tour: activeTour() }} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    await userEvent.keyboard("{ArrowRight}");
    await screen.findByRole("heading", { name: "Open the real form" });
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("heading", { name: "Open the real form" })).toBeTruthy();
    expect(navigation.push).not.toHaveBeenCalledWith("/next");
    await userEvent.keyboard("{ArrowLeft}");
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
  });

  test("scroll and resize recalculate the tooltip using the live target bounds", async () => {
    render(<Harness account={{ ...user, tour: activeTour() }} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    const popover = document.querySelector<HTMLElement>(".product-tour-popover")!;
    const target = screen.getByRole("button", { name: "Attention list" });
    const previousLeft = popover.style.left;
    target.dataset.left = "300";
    fireEvent(window, new Event("resize"));
    await waitFor(() => expect(popover.style.left).not.toBe(previousLeft));
    const previousTop = popover.style.top;
    target.dataset.top = "300";
    fireEvent.scroll(document);
    await waitFor(() => expect(popover.style.top).not.toBe(previousTop));
    const beforeTargetResize = popover.style.left;
    target.dataset.left = "500";
    resizeCallbacks.forEach(callback => callback([], {} as ResizeObserver));
    await waitFor(() => expect(popover.style.left).not.toBe(beforeTargetResize));
  });

  test("a hidden or detached target releases the spotlight and offers recovery", async () => {
    render(<Harness account={{ ...user, tour: activeTour() }} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    const target = screen.getByRole("button", { name: "Attention list" });
    target.hidden = true;
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("button", { name: "Retry step" })).toBeTruthy();
    expect(document.querySelector(".product-tour-shade")).toBeNull();
  });

  test("normal motion scrolls smoothly without making readiness depend on a fixed delay", async () => {
    vi.mocked(window.matchMedia).mockReturnValue({ matches: false, media: "(prefers-reduced-motion: reduce)", addEventListener: vi.fn(), removeEventListener: vi.fn() } as unknown as MediaQueryList);
    render(<Harness account={{ ...user, tour: activeTour() }} />);
    await screen.findByRole("heading", { name: "Welcome to the workspace" });
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: "smooth" }));
  });
});

test("refresh recovers unacknowledged progress and retries only the tour state write", async () => {
  serverTour = activeTour("welcome");
  storeTour(user.id, { tour: activeTour("open"), pending: true, action: "progress" });
  render(<Harness account={{ ...user, tour: serverTour }} />);
  await screen.findByRole("heading", { name: "Open the real form" });
  await waitFor(() => expect(writes()).toEqual([{ action: "progress", currentStep: "open" }]));
  expect(serverTour.currentStep).toBe("open");
  expect(readPendingTour(user.id)).toBeNull();
  expect(navigation.push).not.toHaveBeenCalledWith("/next");
});

describe("tour launcher", () => {
  test("starts once through the provider and navigates to the actual workspace", async () => {
    advanceRoute("/tour");
    const account = { ...user, tour: emptyTour() };
    const { rerender } = render(<ProductTourProvider><Tour user={account} /></ProductTourProvider>);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/"));
    expect(writes()).toEqual([{ action: "start", currentStep: "welcome" }]);
    rerender(<ProductTourProvider><Tour user={account} /></ProductTourProvider>);
    expect(writes()).toHaveLength(1);
  });

  test("reports a failed start and retries without a fake slideshow or stuck overlay", async () => {
    advanceRoute("/tour");
    call.mockRejectedValueOnce(new Error("Tour service unavailable"));
    render(<ProductTourProvider><Tour user={{ ...user, tour: emptyTour() }} /></ProductTourProvider>);
    expect((await screen.findByRole("alert")).textContent).toContain("Tour service unavailable");
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/"));
    expect(writes()).toEqual([{ action: "start", currentStep: "welcome" }, { action: "start", currentStep: "welcome" }]);
  });
});

describe("tour account reconciliation", () => {
  test("Skip during pending start stays closed after the start is acknowledged", async () => {
    advanceRoute("/tour");
    storeTour(user.id, { tour: activeTour(), pending: true, action: "start" });
    let acknowledge!: (value: { tour: ProductTourState }) => void;
    call.mockImplementationOnce(() => new Promise(resolve => { acknowledge = resolve; }));
    render(<ProductTourProvider><Tour user={{ ...user, tour: emptyTour() }} /></ProductTourProvider>);
    await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    await act(async () => { acknowledge({ tour: activeTour() }); });
    await waitFor(() => expect(serverTour.tourSkipped).toBe(true));
    expect(navigation.push).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.querySelector(".product-tour-shade")).toBeNull();
  });

  test("pending start waits for account acknowledgement before protected route navigation", async () => {
    advanceRoute("/tour");
    storeTour(user.id, { tour: activeTour(), pending: true, action: "start" });
    let acknowledge!: (value: { tour: ProductTourState }) => void;
    call.mockImplementation(() => new Promise(resolve => { acknowledge = resolve; }));
    render(<ProductTourProvider><Tour user={{ ...user, tour: emptyTour() }} /></ProductTourProvider>);
    await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
    expect(navigation.push).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
    await act(async () => { acknowledge({ tour: activeTour() }); });
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/"));
  });

  test.each(["completed", "skipped"])("stale browser progress cannot reopen an account already %s", async terminal => {
    storeTour(user.id, { tour: activeTour("open"), pending: true, action: "progress" });
    const terminalTour = { ...activeTour("ready"), tourCompleted: terminal === "completed", tourSkipped: terminal === "skipped" };
    render(<Harness account={{ ...user, tour: terminalTour }} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(call).not.toHaveBeenCalled();
    expect(readPendingTour(user.id)).toBeNull();
  });
});

test("a real action during a slow progress save stays responsive and saves steps in order", async () => {
  serverTour = activeTour();
  const account = { ...user, tour: serverTour };
  let releaseProgress!: (value: { tour: ProductTourState }) => void;
  call.mockImplementation(async (_path, init) => {
    const { currentStep } = JSON.parse(String(init?.body));
    if (currentStep === "open") return new Promise(resolve => { releaseProgress = resolve; });
    serverTour = { ...serverTour, currentStep };
    return { tour: serverTour };
  });
  const { rerender } = render(<Harness account={account} />);
  await screen.findByRole("heading", { name: "Welcome to the workspace" });
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("heading", { name: "Open the real form" });
  await userEvent.click(screen.getByRole("button", { name: "Open details" }));
  rerender(<Harness account={account} form />);
  await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/next"));
  expect(writes()).toEqual([{ action: "progress", currentStep: "open" }]);
  await act(async () => { serverTour = activeTour("open"); releaseProgress({ tour: serverTour }); });
  await waitFor(() => expect(writes()).toEqual([{ action: "progress", currentStep: "open" }, { action: "progress", currentStep: "ready" }]));
  advanceRoute("/next");
  rerender(<Harness account={account} form />);
  await screen.findByRole("heading", { name: "You’re ready" });
  expect(serverTour.currentStep).toBe("ready");
});
