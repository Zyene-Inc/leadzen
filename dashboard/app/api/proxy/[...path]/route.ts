import { NextRequest, NextResponse } from "next/server";
import { backend, sameOrigin } from "@/lib/auth";
import { SESSION_COOKIE } from "@/lib/session";
import { readRequestBody, RequestBodyError } from "@/lib/request-body";

type RouteContext = { params: Promise<{ path: string[] }> };
const routes: Record<string, string[]> = {
  overview: ["GET"],
  autopilot: ["GET", "POST"],
  activity: ["GET"],
  "activity/logs": ["GET"],
  discovery: ["GET", "POST"],
  inbox: ["GET"],
  "inbox/check": ["GET", "POST"],
  attention: ["GET"],
  "inbox/conversations": ["GET"],
  outreach: ["GET"],
  "outreach/reviews": ["GET", "POST"],
  suppression: ["GET", "POST"],
  target: ["GET", "PUT"],
  leads: ["GET"],
  jobs: ["GET"],
  "jobs/send": ["POST"],
  settings: ["GET", "PUT"],
  "settings/backup": ["POST"],
  onboarding: ["GET", "PUT"],
  "onboarding/wizard": ["GET", "PUT"],
  "onboarding/test": ["POST"],
  "onboarding/complete": ["POST"],
  "admin/users": ["GET", "POST"],
  tour: ["GET", "POST"],
  contacts: ["POST"],
  campaigns: ["GET", "POST"],
  "chat/context": ["GET", "PUT"],
  "chat/threads": ["GET", "POST"],
  "mcp/connections": ["GET", "POST"],
  "mcp/authorize": ["GET", "POST"],
};

async function proxy(request: NextRequest, context: RouteContext) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { path } = await context.params;
  const route = path.join("/");
  const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  const streaming = new RegExp(`^chat/threads/${uuid}/stream$`).test(route);
  const chatMethods = streaming ? ["GET"] : new RegExp(`^chat/threads/${uuid}$`).test(route)
    ? ["GET", "PUT", "DELETE"]
    : new RegExp(`^chat/threads/${uuid}/messages$`).test(route)
      ? ["POST"]
      : new RegExp(`^chat/runs/${uuid}$`).test(route)
        ? ["GET"]
        : new RegExp(`^chat/runs/${uuid}/(approval|cancel)$`).test(route)
          ? ["POST"]
          : undefined;
  const methods =
    routes[route] ??
    (new RegExp(`^outreach/reviews/${uuid}$`).test(route)
      ? ["GET", "DELETE"]
      : new RegExp(`^outreach/reviews/${uuid}/drafts/${uuid}$`).test(route)
        ? ["POST"]
        : /^inbox\/conversations\/\d+$/.test(route)
          ? ["GET"]
          : undefined) ??
    chatMethods ??
    (new RegExp(`^discovery/${uuid}$`).test(route)
      ? ["GET"]
      : new RegExp(`^discovery/${uuid}/emails$`).test(route)
        ? ["GET", "POST"]
        : new RegExp(`^discovery/${uuid}/(pause|resume|stop)$`).test(route)
          ? ["POST"]
          : undefined) ??
    (/^admin\/users\/\d+\/invite$/.test(route)
      ? ["POST"]
      : /^contacts\/\d+\/email$/.test(route)
        ? ["GET", "POST"]
        : /^contacts\/\d+$/.test(route)
          ? ["GET", "PUT", "DELETE"]
      : /^admin\/users\/\d+$/.test(route)
        ? ["PUT", "DELETE"]
        : /^campaigns\/[0-9a-f-]{36}\/preview$/.test(route)
          ? ["GET"]
        : /^campaigns\/[0-9a-f-]{36}\/run$/.test(route)
          ? ["POST"]
          : /^campaigns\/[0-9a-f-]{36}$/.test(route)
            ? ["PUT", "DELETE"]
            : []);
  if (!methods.includes(request.method))
    return NextResponse.json({ error: "Route not found" }, { status: 404 });
  if (request.method !== "GET" && !sameOrigin(request))
    return NextResponse.json(
      { error: "Invalid request origin" },
      { status: 403 },
    );
  try {
    const body = request.method === "GET" ? undefined : await readRequestBody(request, 65536);
    const upstream = await backend(
      `${route}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body,
        signal: AbortSignal.any([request.signal, AbortSignal.timeout(streaming ? 25000 :
          route === "onboarding/test" || route.startsWith("outreach/reviews") ? 60000 : 15000)]),
      },
      token,
    );
    if (streaming && upstream.ok) return new NextResponse(upstream.body, { status: 200, headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-store", "X-Accel-Buffering": "no" } });
    const backup = route === "settings/backup" && upstream.ok;
    return new NextResponse(backup ? upstream.body : await upstream.arrayBuffer(), {
      status: upstream.status,
      headers: {
        "Content-Type": backup ? "application/vnd.sqlite3" : "application/json",
        ...(backup ? { "Content-Disposition": upstream.headers.get("Content-Disposition") || 'attachment; filename="leadzen-workspace.sqlite3"' } : {}),
        "Cache-Control": "no-store",
        ...(upstream.headers.get("Retry-After") ? { "Retry-After": upstream.headers.get("Retry-After")! } : {}),
      },
    });
  } catch (error) {
    if (error instanceof RequestBodyError) return NextResponse.json({ error: error.message }, { status: error.status, headers: { "Cache-Control": "no-store" } });
    return NextResponse.json(
      {
        error: "LeadZen is temporarily unavailable. Contact support@zyene.com.",
      },
      { status: 503 },
    );
  }
}

export const runtime = "nodejs";
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;

// Allow a bounded body read plus the 60-second connection/draft operation.
export const maxDuration = 80;
