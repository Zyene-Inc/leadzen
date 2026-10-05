import { type AnchorHTMLAttributes, type ReactNode } from "react";
import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname } from "next/navigation";
import { api } from "@/lib/client-api";
import { ProductTourProvider } from "@/components/product-tour-provider";
import { productTourSteps } from "@/lib/product-tour-steps";
import type { ProductTourState } from "@/lib/product-tour-state";
import type { Account } from "@/lib/auth";
import Dashboard from "@/components/overview";
import Contacts from "@/components/contacts";
import Campaigns from "@/components/campaigns";
import Inbox from "@/components/inbox";
import SettingsPage from "@/components/settings";
import Chat from "@/components/chat";
import Tour from "@/components/tour";
import { user, settings, lead } from "./fixtures";

// Keep all product screens, forms, Sidebar and tour steps real. Only Next's
// navigation adapter and API transport are replaced with a synthetic harness.
vi.unmock("@/components/sidebar");
vi.unmock("@/lib/workspace-context");
const navigation = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const value = { path: "/tour", subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; }, navigate: (path: string) => {}, router: { push: (path: string) => {}, replace: (path: string) => {}, refresh: () => {} } };
  value.navigate = path => { value.path = path; window.history.pushState({}, "", path); window.dispatchEvent(new PopStateEvent("popstate")); listeners.forEach(listener => listener()); };
  value.router.push = value.navigate;
  value.router.replace = value.navigate;
  return value;
});
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return { usePathname: () => useSyncExternalStore(navigation.subscribe, () => navigation.path, () => navigation.path), useRouter: () => navigation.router };
});
vi.mock("next/link", () => ({ default: ({ children, onClick, href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { children: ReactNode; href: string }) => <a {...props} href={href} onClick={event => { onClick?.(event); if (!event.defaultPrevented && href.startsWith("/") && !event.metaKey && !event.ctrlKey) { event.preventDefault(); navigation.navigate(href); } }}>{children}</a> }));
const call = vi.mocked(api);
let serverTour: ProductTourState;
const emptyTour = (): ProductTourState => ({ tourStarted: false, currentStep: "welcome", tourCompleted: false, tourSkipped: false });
const context = { workspaceId: "synthetic-workspace", workspaceName: "Synthetic", workspacePath: "/", product: "Synthetic product", target: { summary: "Practice owners" }, referencedLeads: [], selectedLeadIds: [], lastChatId: null };
const overview = { ai_ready: false, transport: "preview", leads: { total: 1, ready: 1, emailed: 0, completed: 0, suppressed: 0 }, today: { sent: 0, inbound: 0 }, mailboxes: [], activity: [], home: { operator_name: "Synthetic user", metrics: { found: 1, qualified: 1, with_email: 1, contacted: 0, replies: 0 }, credits: { configured: false, balance: null, checked_at: null, synthetic: true }, target: { summary: "Practice owners", audience: null, country_name: "United States" }, recent_activity: [] } };
const setup = { eligible: 1, remaining_today: 5, from_address: "sender@example.com", ai_ready: false, next_send_at: null, window: { start: 8, end: 20, timezone: "America/New_York", weekdays_only: true }, reviews: [] };

beforeEach(() => {
  localStorage.clear();
  serverTour = emptyTour();
  navigation.path = "/tour";
  window.history.replaceState({}, "", "/tour");
  call.mockImplementation(async (path, init) => {
    if (path === "tour") {
      if (!init?.method) return { tour: serverTour };
      const { action, currentStep } = JSON.parse(String(init.body));
      if (action === "start") serverTour = { ...emptyTour(), tourStarted: true, currentStep };
      if (action === "progress") serverTour = { ...serverTour, currentStep };
      if (action === "complete") serverTour = { ...serverTour, currentStep, tourCompleted: true, tourSkipped: false };
      if (action === "skip") serverTour = { ...serverTour, currentStep, tourCompleted: false, tourSkipped: true };
      return { tour: serverTour };
    }
    if (path === "chat/context") return context;
    if (init?.method) throw new Error(`Tour attempted a feature write: ${path}`);
    if (path === "overview") return overview;
    if (path === "settings") return settings;
    if (path === "outreach") return setup;
    if (path === "autopilot") return { setup: { revision: "synthetic", blockers: [], target: "Owners", product: "Product", sender: setup.from_address, signature: "", booking_link: "", service_enabled: false }, policy: null, runs: [] };
    if (path === "mcp/connections") return { available: false, endpoint: null, reason: "Synthetic local fixture", connections: [] };
    if (path === "inbox/check") return { check: null };
    if (path.startsWith("leads")) return { items: [lead], total: 1, limit: 50, offset: 0 };
    return { items: [], total: 0, limit: 50, offset: 0 };
  });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, media: "(prefers-reduced-motion: reduce)", addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 5));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => window.clearTimeout(id));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  if (!HTMLElement.prototype.scrollIntoView) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: () => {} });
  vi.spyOn(HTMLElement.prototype, "scrollIntoView").mockImplementation(() => {});
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(function (this: HTMLElement) { return this.hidden || this.closest('[hidden]') ? [] as unknown as DOMRectList : [this.getBoundingClientRect()] as unknown as DOMRectList; });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ left: 100, top: 100, width: 200, height: 44, right: 300, bottom: 144, x: 100, y: 100, toJSON: () => ({}) });
});
afterEach(() => vi.unstubAllGlobals());

function Pages() {
  const path = usePathname();
  const account: Account = { ...user, tour: serverTour, tour_completed: serverTour.tourCompleted };
  if (path === "/tour") return <Tour user={account} />;
  if (path === "/contacts") return <Contacts user={account} />;
  if (path === "/outreach") return <Campaigns user={account} />;
  if (path === "/inbox") return <Inbox user={account} />;
  if (path === "/settings") return <SettingsPage user={account} />;
  if (path === "/chat") return <Chat user={account} />;
  return <Dashboard user={account} />;
}
const Application = () => <ProductTourProvider><Pages /></ProductTourProvider>;
const tourWrites = () => call.mock.calls.filter(([path, init]) => path === "tour" && init?.method).map(([, init]) => JSON.parse(String(init?.body)));
const featureWrites = () => call.mock.calls.filter(([path, init]) => init?.method && !["tour", "chat/context"].includes(path));
const stepDialog = async (id: string) => {
  const step = productTourSteps.find(item => item.id === id)!;
  try { return await screen.findByRole("dialog", { name: step.title }); }
  catch (cause) { throw new Error(`Step ${id}: server=${JSON.stringify(serverTour)} route=${window.location.pathname} target=${!!document.querySelector(step.target)} recovery=${document.querySelector(".product-tour-recovery")?.textContent ?? "none"} actions=${JSON.stringify(tourWrites())}`, { cause }); }
};

test("walks every production step over actual screens and finishes without sending or changing data", async () => {
  render(<Application />);
  for (let index = 0; index < productTourSteps.length; index++) {
    const step = productTourSteps[index];
    const dialog = await stepDialog(step.id);
    expect(within(dialog).getByText(`${index + 1} of ${productTourSteps.length}`)).toBeTruthy();
    expect(window.location.pathname).toBe(step.route);
    const target = document.querySelector<HTMLElement>(step.target);
    expect(target?.isConnected).toBe(true);
    if (step.action) {
      expect((within(dialog).getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
      await userEvent.click(target!);
    } else await userEvent.click(within(dialog).getByRole("button", { name: index === productTourSteps.length - 1 ? "Finish" : "Next" }));
  }
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await waitFor(() => expect(serverTour.tourCompleted).toBe(true));
  expect(featureWrites()).toEqual([]);
  expect(tourWrites().map(value => value.currentStep)).toEqual([...productTourSteps.map(step => step.id), "ready"]);
  expect(screen.getByRole("link", { name: "Take Product Tour" })).toBeTruthy();
  // Normal product remains usable after the tour, including the real editor.
  await userEvent.click(screen.getByRole("button", { name: "Edit Sending hours" }));
  expect(screen.getByLabelText("Start time")).toHaveProperty("value", "08:00");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(featureWrites()).toEqual([]);
});

test.each([
  ["contact-details", "/contacts", "Email"],
  ["schedule-details", "/settings", "Start time"],
])("refresh at %s reopens the actual unsaved form and keeps progress", async (id, path, field) => {
  serverTour = { ...emptyTour(), tourStarted: true, currentStep: id };
  navigation.path = path;
  window.history.replaceState({}, "", path);
  const first = render(<Application />);
  await stepDialog(id);
  expect(screen.getByLabelText(field, { exact: true })).toBeTruthy();
  first.unmount();
  render(<Application />);
  const dialog = await stepDialog(id);
  expect(screen.getByLabelText(field, { exact: true })).toBeTruthy();
  expect(tourWrites()).toEqual([]);
  expect(featureWrites()).toEqual([]);
  await userEvent.click(within(dialog).getByRole("button", { name: "Back" }));
  const previous = productTourSteps[productTourSteps.findIndex(step => step.id === id) - 1];
  await stepDialog(previous.id);
  await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
  await waitFor(() => expect(serverTour.tourSkipped).toBe(true));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(featureWrites()).toEqual([]);
});
