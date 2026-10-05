import { NextResponse } from "next/server";
import { backend, sameOrigin } from "@/lib/auth";
import { readRequestBody, RequestBodyError } from "@/lib/request-body";
export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  try {
    const body = await readRequestBody(request, 4096);
    const response = await backend("auth/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body });
    return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
  } catch (error) {
    if (error instanceof RequestBodyError) return NextResponse.json({ error: error.message }, { status: error.status, headers: { "Cache-Control": "no-store" } });
    return NextResponse.json({ error: "Setup is temporarily unavailable. Contact support@zyene.com." }, { status: 503 });
  }
}
