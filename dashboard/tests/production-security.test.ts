// @vitest-environment node
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { NextRequest } from "next/server";
import { backend, sameOrigin } from "@/lib/auth";
import { readRequestBody } from "@/lib/request-body";
import { proxy as gate } from "@/proxy";
import { POST as login } from "@/app/api/auth/login/route";
import { GET, POST, maxDuration } from "@/app/api/proxy/[...path]/route";
import nextConfig from "@/next.config";

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("LEADZEN_API_URL", "https://api.preview.example");
  vi.stubEnv("LEADZEN_API_TOKEN", "synthetic-private-api-key");
  vi.stubEnv("LEADZEN_DASHBOARD_PUBLIC_URL", "https://preview.example");
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function request(path: string, method = "GET", body?: string) {
  return new NextRequest(`https://preview.example/api/proxy/${path}`, {
    method, body,
    headers: { Origin: "https://preview.example", Cookie: "leadzen_dashboard_session=synthetic-session" },
  });
}
const context = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });

describe("production connection boundary", () => {
  test("uses server credentials, refuses redirects and disables caching", async () => {
    const fetch = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    await backend("auth/me", { redirect: "follow" }, "synthetic-session");
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.preview.example/api/auth/me");
    expect(init.redirect).toBe("error");
    expect(init.cache).toBe("no-store");
    expect(new Headers(init.headers).get("X-LeadZen-Session")).toBe("synthetic-session");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer synthetic-private-api-key");
  });
  test.each(["http://api.preview.example", "https://user:pass@api.preview.example", "https://api.preview.example/path", "https://api.preview.example?token=secret", "https://api.preview.example#fragment", "invalid"])("fails closed before sending credentials for %s", async value => {
    vi.stubEnv("LEADZEN_API_URL", value);
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(backend("auth/me", {}, "synthetic-session")).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
  test("requires an explicit production browser origin", () => {
    vi.stubEnv("LEADZEN_DASHBOARD_PUBLIC_URL", undefined);
    expect(sameOrigin(request("settings", "POST", "{}"))).toBe(false);
  });
});

describe("bounded request reads", () => {
  test("rejects oversized declared content without reading it", async () => {
    await expect(readRequestBody(new Request("https://preview.example", { method: "POST", body: "{}", headers: { "Content-Length": "100000" } }), 4096)).rejects.toMatchObject({ status: 413 });
  });
  test("counts UTF-8 bytes rather than JavaScript characters", async () => {
    await expect(readRequestBody(new Request("https://preview.example", { method: "POST", body: "é".repeat(2049) }), 4096)).rejects.toMatchObject({ status: 413 });
  });
  test("cancels a chunked stream as soon as its byte limit is exceeded", async () => {
    const cancel = vi.fn();
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(4097)); }, cancel });
    const req = new Request("https://preview.example", { method: "POST", body: stream, duplex: "half" } as RequestInit);
    await expect(readRequestBody(req, 4096)).rejects.toMatchObject({ status: 413 });
    expect(cancel).toHaveBeenCalledOnce();
  });
  test("preserves a UTF-8 code point split between chunks", async () => {
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array([0xc3])); controller.enqueue(new Uint8Array([0xa9])); controller.close(); } });
    const req = new Request("https://preview.example", { method: "POST", body: stream, duplex: "half" } as RequestInit);
    expect(await readRequestBody(req, 2)).toBe("é");
  });
  test("rejects malformed UTF-8 without forwarding replacement text", async () => {
    const req = new Request("https://preview.example", { method: "POST", body: new Uint8Array([0xff]) });
    await expect(readRequestBody(req, 4096)).rejects.toMatchObject({ status: 400 });
  });
  test("times out and cancels a stalled body", async () => {
    vi.useFakeTimers();
    const cancel = vi.fn();
    const stream = new ReadableStream({ cancel });
    const req = new Request("https://preview.example", { method: "POST", body: stream, duplex: "half" } as RequestInit);
    const result = expect(readRequestBody(req, 4096)).rejects.toMatchObject({ status: 408 });
    await vi.advanceTimersByTimeAsync(15000);
    await result;
    expect(cancel).toHaveBeenCalledOnce();
  });
  test("login and authenticated proxy return 413 before upstream work", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const signIn = new Request("https://preview.example/api/auth/login", { method: "POST", headers: { Origin: "https://preview.example" }, body: "é".repeat(2049) });
    expect((await login(signIn)).status).toBe(413);
    expect((await POST(request("settings", "PUT", "x".repeat(65537)), context("settings"))).status).toBe(413);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("private responses and production headers", () => {
  test("supplies a unique nonce to Next, overrides caller headers and prevents inline script injection", () => {
    const req = new NextRequest("https://preview.example/login", { headers: { "x-nonce": "attacker", "Content-Security-Policy": "script-src *" } });
    const first = gate(req), second = gate(req);
    const policy = first.headers.get("Content-Security-Policy")!;
    expect(policy).toContain("'strict-dynamic'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("upgrade-insecure-requests");
    expect(policy.split("; ").find(value => value.startsWith("script-src"))).not.toContain("unsafe-inline");
    expect(policy).not.toContain("unsafe-eval");
    expect(first.headers.get("x-middleware-request-x-nonce")).not.toBe("attacker");
    expect(first.headers.get("x-middleware-request-content-security-policy")).toBe(policy);
    expect(second.headers.get("Content-Security-Policy")).not.toBe(policy);
    expect(first.headers.get("Cache-Control")).toBe("private, no-store, no-transform");
  });
  test("error responses cannot be publicly cached", () => {
    const response = gate(new NextRequest("https://preview.example/api/proxy/settings"));
    expect(response.status).toBe(401);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store, no-transform");
  });
  test("production enables HSTS without forcing it in development", async () => {
    const headers = await nextConfig.headers!();
    expect(headers[0].headers).toContainEqual({ key: "Strict-Transport-Security", value: "max-age=31536000" });
    vi.stubEnv("NODE_ENV", "development");
    expect((await nextConfig.headers!())[0].headers.some(value => value.key === "Strict-Transport-Security")).toBe(false);
  });
  test("propagates provider/API throttling retry information", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"error":"Please wait"}', { status: 429, headers: { "Retry-After": "60" } })));
    const response = await GET(request("leads"), context("leads"));
    expect(response.status).toBe(429);
    expect(response.headers.get("Retry-After")).toBe("60");
    expect(maxDuration).toBeGreaterThan(60 + 15);
  });
  test("only forwards allowlisted routes and rejects cross-origin changes", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    expect((await GET(request("auth/me"), context("auth/me"))).status).toBe(404);
    const foreign = request("settings", "PUT", "{}"); foreign.headers.set("Origin", "https://foreign.example");
    expect((await POST(foreign, context("settings"))).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
});
