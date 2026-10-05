import { NextRequest, NextResponse } from "next/server";
import { safeMcpReturnPath } from "@/lib/mcp-return";

const SESSION_COOKIE = "leadzen_dashboard_session";

export function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const isAsset = pathname === "/favicon.svg" || pathname === "/apple-touch-icon.png" || pathname.startsWith("/brand/") || pathname.startsWith("/_next/");
  if (isAsset) return NextResponse.next();
  const isApi = pathname.startsWith("/api/");
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const production = process.env.NODE_ENV === "production";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${production ? "" : " 'unsafe-eval'"}`,
    // The existing tour and live textarea use measured inline style attributes.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data: https://t1.gstatic.com",
    "font-src 'self'",
    `connect-src 'self'${production ? "" : " ws: wss:"}`,
    "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
    ...(production ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
  const requestHeaders = new Headers(request.headers);
  // Replace any caller-supplied nonce/policy before rendering framework scripts.
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const finish = (response: NextResponse) => {
    // Preserve SSR bytes across CDNs: injected scripts/email rewriting break
    // nonce-based CSP and can cause hydration mismatches.
    response.headers.set("Cache-Control", "private, no-store, no-transform");
    if (!isApi) response.headers.set("Content-Security-Policy", csp);
    return response;
  };
  const next = () => finish(NextResponse.next({ request: { headers: requestHeaders } }));
  const isPublic = pathname === "/login" || pathname === "/setup" || pathname.startsWith("/api/auth/");
  if (isPublic) return next();

  const isConfigured = Boolean(process.env.LEADZEN_API_URL && process.env.LEADZEN_API_TOKEN);
  if (!isConfigured) {
    if (pathname.startsWith("/api/")) {
      return finish(NextResponse.json({ error: "Dashboard authentication is not configured" }, { status: 503 }));
    }
    return finish(NextResponse.redirect(new URL("/login?setup=required", request.url)));
  }

  if (!request.cookies.get(SESSION_COOKIE)?.value) {
    if (pathname.startsWith("/api/")) {
      return finish(NextResponse.json({ error: "Unauthorized" }, { status: 401 }));
    }
    const returnTo = safeMcpReturnPath(`${pathname}${request.nextUrl.search}`);
    const login = returnTo ? `/login?returnTo=${encodeURIComponent(returnTo)}` : "/login";
    return finish(NextResponse.redirect(new URL(login, request.url)));
  }
  return next();
}

export const config = {
  matcher: ["/((?!favicon.ico).*)"],
};
