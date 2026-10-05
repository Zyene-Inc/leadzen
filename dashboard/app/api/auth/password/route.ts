import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { backend, sameOrigin } from "@/lib/auth";
import { SESSION_COOKIE } from "@/lib/session";
import { readRequestBody, RequestBodyError } from "@/lib/request-body";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try {
    const body = await readRequestBody(request, 4096);
    const upstream = await backend("auth/password", { method: "POST", headers: { "Content-Type": "application/json" }, body }, token);
    const response = NextResponse.json(await upstream.json(), { status: upstream.status, headers: { "Cache-Control": "no-store" } });
    if (upstream.ok) response.cookies.set({ name: SESSION_COOKIE, value: "", path: "/", maxAge: 0, httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax" });
    return response;
  } catch (error) {
    if (error instanceof RequestBodyError) return NextResponse.json({ error: error.message }, { status: error.status, headers: { "Cache-Control": "no-store" } });
    return NextResponse.json({ error: "Password change is temporarily unavailable" }, { status: 503 });
  }
}
