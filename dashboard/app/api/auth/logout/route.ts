import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { backend, sameOrigin } from "@/lib/auth";
import { SESSION_COOKIE } from "@/lib/session";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (token) {
    try {
      const upstream = await backend("auth/logout", { method: "POST" }, token);
      if (!upstream.ok && upstream.status !== 401) throw new Error("Session revocation failed");
    } catch {
      return NextResponse.json({ error: "Could not revoke your session. Please retry sign out." }, { status: 503 });
    }
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set({ name: SESSION_COOKIE, value: "", maxAge: 0, path: "/", httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax" });
  return response;
}
