import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE } from "@/lib/session";
import { safeMcpReturnPath } from "@/lib/mcp-return";
import type { ProductTourState } from "@/lib/product-tour-state";

export type Account = {
  id: number; email: string; name: string; is_admin: boolean; is_active: boolean;
  must_change_password: boolean; onboarded: boolean; purpose: string;
  workspace_name: string; created_at: string; last_login: string | null;
  invitation_pending: boolean; tour_completed: boolean;
  tour_started?: boolean; tour_skipped?: boolean; tour?: ProductTourState;
};

export async function backend(path: string, init: RequestInit = {}, session?: string) {
  const base = process.env.LEADZEN_API_URL?.replace(/\/$/, "");
  const key = process.env.LEADZEN_API_TOKEN;
  if (!base || !key) throw new Error("LeadZen connection is not configured");
  const url = new URL(base);
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/" || !["http:", "https:"].includes(url.protocol)) throw new Error("LeadZen API URL must be an exact origin");
  if (process.env.NODE_ENV === "production" && url.protocol !== "https:") throw new Error("LeadZen API requires HTTPS in production");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${key}`);
  if (session) headers.set("X-LeadZen-Session", session);
  // Never forward the private session header to a redirected host, including
  // redirects caused by a misconfigured upstream reverse proxy.
  return fetch(`${base}/api/${path}`, { ...init, headers, cache: "no-store", redirect: "error", signal: init.signal ?? AbortSignal.timeout(15000) });
}

export async function requireAccount(options: { admin?: boolean; onboarded?: boolean; allowPasswordChange?: boolean; skipTour?: boolean; returnTo?: string } = {}): Promise<Account> {
  const returnTo = safeMcpReturnPath(options.returnTo);
  const loginPath = returnTo ? `/login?returnTo=${encodeURIComponent(returnTo)}` : "/login";
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) redirect(loginPath);
  let response: Response;
  try { response = await backend("auth/me", {}, token); }
  catch { redirect(returnTo ? `${loginPath}&unavailable=1` : "/login?unavailable=1"); }
  if (!response.ok) redirect(loginPath);
  const { user } = await response.json() as { user: Account };
  if (user.must_change_password && !options.allowPasswordChange) redirect("/password");
  if (options.admin && !user.is_admin) redirect("/");
  if (options.onboarded && !user.onboarded) redirect("/onboarding");
  if (options.onboarded && !options.skipTour && !user.is_admin && !user.tour_completed && !user.tour_started && !user.tour_skipped) redirect("/tour");
  return user;
}

export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin || request.headers.get("sec-fetch-site") === "cross-site") return false;
  const publicUrl = process.env.LEADZEN_DASHBOARD_PUBLIC_URL;
  if (!publicUrl) return process.env.NODE_ENV !== "production" && origin === new URL(request.url).origin;
  try {
    const expected = new URL(publicUrl);
    if (expected.username || expected.password || expected.pathname !== "/" || expected.search || expected.hash) return false;
    if (!["http:", "https:"].includes(expected.protocol)) return false;
    if (process.env.NODE_ENV === "production" && expected.protocol !== "https:") return false;
    return origin === expected.origin;
  } catch {
    return false;
  }
}
