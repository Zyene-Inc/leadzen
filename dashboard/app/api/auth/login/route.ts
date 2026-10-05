import { NextResponse } from "next/server";
import { backend, sameOrigin, type Account } from "@/lib/auth";
import { SESSION_COOKIE, SESSION_MAX_AGE_SECONDS } from "@/lib/session";
import { readRequestBody, RequestBodyError } from "@/lib/request-body";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  try {
    const text = await readRequestBody(request, 4096);
    const upstream = await backend("auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: text });
    const payload = await upstream.json();
    if (!upstream.ok) return NextResponse.json({ error: payload.error ?? "Unable to sign in" }, { status: upstream.status, headers: { "Cache-Control": "no-store", ...(upstream.headers.get("Retry-After") ? { "Retry-After": upstream.headers.get("Retry-After")! } : {}) } });
    const user = payload.user as Account;
    const next = user.must_change_password ? "/password" : user.is_admin ? "/admin" : !user.onboarded ? "/onboarding" : !user.tour_completed && !user.tour_started && !user.tour_skipped ? "/tour" : "/";
    const response = NextResponse.json({ user, next }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set({ name: SESSION_COOKIE, value: payload.session_token, httpOnly: true,
      secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: SESSION_MAX_AGE_SECONDS });
    return response;
  } catch (error) {
    if (error instanceof RequestBodyError) return NextResponse.json({ error: error.message }, { status: error.status, headers: { "Cache-Control": "no-store" } });
    return NextResponse.json({ error: "Sign-in is temporarily unavailable. Contact support@zyene.com." }, { status: 503 });
  }
}
