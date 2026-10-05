import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

afterEach(() => vi.unstubAllEnvs());

describe("branding before sign-in", () => {
  it("serves public brand assets even before dashboard configuration", () => {
    vi.stubEnv("LEADZEN_API_URL", undefined);
    vi.stubEnv("LEADZEN_API_TOKEN", undefined);
    for (const asset of ["leadzen-logo-light.png", "leadzen-logo-dark.png", "leadzen-by-zyene-approved-light.png", "leadzen-by-zyene-dark.png", "leadzen-favicon.ico", "leadzen-icon-180.png"]) {
      const response = proxy(new NextRequest(`http://localhost:3001/brand/${asset}`));
      expect(response.headers.get("x-middleware-next")).toBe("1");
      expect(response.headers.get("location")).toBeNull();
    }
  });

  it("keeps Workspace, Chat and API routes protected", () => {
    vi.stubEnv("LEADZEN_API_URL", "http://127.0.0.1:8000");
    vi.stubEnv("LEADZEN_API_TOKEN", "synthetic-test-token");
    for (const path of ["/", "/contacts", "/chat", "/brand-private"]) {
      const response = proxy(new NextRequest(`http://localhost:3001${path}`));
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe("http://localhost:3001/login");
    }
    const response = proxy(new NextRequest("http://localhost:3001/api/proxy/leads"));
    expect(response.status).toBe(401);
  });
});
