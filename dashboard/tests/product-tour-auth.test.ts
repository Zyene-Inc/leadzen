import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { requireAccount, type Account } from "@/lib/auth";
import { POST as signIn } from "@/app/api/auth/login/route";
import LoginPage from "@/app/login/page";
import { SESSION_COOKIE } from "@/lib/session";
import { user } from "./fixtures";

const auth = vi.hoisted(() => ({
  token: "synthetic-tour-session" as string | undefined,
  redirect: vi.fn((path: string): never => { throw new Error(`redirect:${path}`); }),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => name === "leadzen_dashboard_session" && auth.token ? { value: auth.token } : undefined }) }));
vi.mock("next/navigation", () => ({ redirect: auth.redirect, useRouter: () => ({ replace: auth.replace, refresh: auth.refresh }) }));

const consent = "/mcp/connect?request=12345678-1234-1234-1234-123456789abc";
const neverStarted = (): Account => ({ ...user, tour_completed: false, tour_started: false, tour_skipped: false });
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  auth.token = "synthetic-tour-session";
  vi.stubEnv("LEADZEN_API_URL", "http://127.0.0.1:8000");
  vi.stubEnv("LEADZEN_API_TOKEN", "synthetic-private-proxy-key");
  vi.stubEnv("LEADZEN_DASHBOARD_PUBLIC_URL", "http://localhost:3001");
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { window.history.replaceState(null, "", "/"); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function me(account: Account, status = 200) {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ user: account }), { status, headers: { "Content-Type": "application/json" } }));
}

function loginRequest(body: object = { email: "employee@preview.example", password: "synthetic-password" }) {
  return new Request("http://localhost:3001/api/auth/login", { method: "POST", headers: { Origin: "http://localhost:3001", "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

describe("server tour guard", () => {
  test("only an authenticated, onboarded employee who never started is redirected to the entry", async () => {
    me(neverStarted());
    await expect(requireAccount({ onboarded: true })).rejects.toThrow("redirect:/tour");
    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/auth/me");
    expect(new Headers(request.headers).get("X-LeadZen-Session")).toBe(auth.token);
    expect(new Headers(request.headers).get("Authorization")).toBe("Bearer synthetic-private-proxy-key");
    expect(request.cache).toBe("no-store");
  });

  test.each([
    { tour_started: true }, { tour_skipped: true }, { tour_completed: true }, { is_admin: true },
  ])("allows real routes with server tour/admin state %j", async flags => {
    const account = { ...neverStarted(), ...flags };
    me(account);
    expect(await requireAccount({ onboarded: true })).toEqual(account);
    expect(auth.redirect).not.toHaveBeenCalled();
  });

  test("entry and MCP consent can explicitly bypass only the tour gate", async () => {
    const account = neverStarted();
    me(account);
    expect(await requireAccount({ onboarded: true, skipTour: true, returnTo: consent })).toEqual(account);
    me({ ...account, must_change_password: true, tour_started: true });
    await expect(requireAccount({ onboarded: true, skipTour: true, returnTo: consent })).rejects.toThrow("redirect:/password");
    me({ ...account, onboarded: false, tour_skipped: true });
    await expect(requireAccount({ onboarded: true, skipTour: true, returnTo: consent })).rejects.toThrow("redirect:/onboarding");
  });

  test("active or skipped tours do not bypass password, setup or administrator access", async () => {
    me({ ...neverStarted(), tour_started: true, must_change_password: true });
    await expect(requireAccount({ onboarded: true })).rejects.toThrow("redirect:/password");
    me({ ...neverStarted(), tour_skipped: true, onboarded: false });
    await expect(requireAccount({ onboarded: true })).rejects.toThrow("redirect:/onboarding");
    me({ ...neverStarted(), tour_started: true });
    await expect(requireAccount({ admin: true })).rejects.toThrow("redirect:/");
  });

  test("missing/expired sessions remain blocked and MCP return paths stay constrained", async () => {
    auth.token = undefined;
    await expect(requireAccount({ onboarded: true, returnTo: consent })).rejects.toThrow(`redirect:/login?returnTo=${encodeURIComponent(consent)}`);
    expect(fetchMock).not.toHaveBeenCalled();
    auth.token = "synthetic-tour-session";
    me({ ...neverStarted(), tour_started: true }, 401);
    await expect(requireAccount({ onboarded: true, returnTo: "https://foreign.example" })).rejects.toThrow("redirect:/login");
    fetchMock.mockRejectedValue(new Error("synthetic offline"));
    await expect(requireAccount({ onboarded: true, returnTo: consent })).rejects.toThrow(`redirect:/login?returnTo=${encodeURIComponent(consent)}&unavailable=1`);
  });
});

describe("sign-in routing", () => {
  test.each([
    [{}, "/tour"], [{ tour_started: true }, "/"], [{ tour_skipped: true }, "/"], [{ tour_completed: true }, "/"],
    [{ tour_started: true, must_change_password: true }, "/password"],
    [{ tour_skipped: true, onboarded: false }, "/onboarding"], [{ is_admin: true }, "/admin"],
  ])("uses authoritative backend state %j to choose %s", async (flags, destination) => {
    const account = { ...neverStarted(), ...flags };
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ user: account, session_token: "synthetic-new-session" }), { status: 200 }));
    const response = await signIn(loginRequest({ email: "employee@preview.example", password: "synthetic-password", tour_started: true, tour_skipped: true }));
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.next).toBe(destination);
    expect(payload.user).toEqual(account);
    expect(payload.session_token).toBeUndefined();
    expect(JSON.stringify(payload)).not.toContain("synthetic-private-proxy-key");
    const cookie = response.headers.get("Set-Cookie") ?? "";
    expect(cookie).toContain(`${SESSION_COOKIE}=synthetic-new-session`);
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=lax");
  });

  test("cross-origin requests cannot set tour/session state through sign-in", async () => {
    const request = new Request("http://localhost:3001/api/auth/login", { method: "POST", headers: { Origin: "https://foreign.example" }, body: "{}" });
    expect((await signIn(request)).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("client MCP consent return after sign-in", () => {
  test.each([
    [{ tour_started: true }, consent], [{ tour_skipped: true }, consent], [{ tour_completed: true }, consent],
    [{ is_admin: true }, consent], [{}, "/tour"], [{ tour_started: true, must_change_password: true }, "/password"],
    [{ tour_skipped: true, onboarded: false }, "/onboarding"],
  ])("returns safely with account state %j", async (flags, destination) => {
    window.history.replaceState(null, "", `/login?returnTo=${encodeURIComponent(consent)}`);
    const account = { ...neverStarted(), ...flags };
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ user: account, next: destination === consent ? "/" : destination }), { status: 200 }));
    render(createElement(LoginPage));
    await userEvent.type(screen.getByLabelText("Work email"), "employee@preview.example");
    await userEvent.type(screen.getByLabelText("Password"), "synthetic-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(auth.replace).toHaveBeenCalledWith(destination));
    expect(auth.refresh).toHaveBeenCalledOnce();
  });

  test("an active tour never enables an arbitrary return redirect", async () => {
    window.history.replaceState(null, "", "/login?returnTo=https%3A%2F%2Fforeign.example");
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ user: { ...neverStarted(), tour_started: true }, next: "/" }), { status: 200 }));
    render(createElement(LoginPage));
    await userEvent.type(screen.getByLabelText("Work email"), "employee@preview.example");
    await userEvent.type(screen.getByLabelText("Password"), "synthetic-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(auth.replace).toHaveBeenCalledWith("/"));
  });
});
