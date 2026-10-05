import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { sameOrigin } from "@/lib/auth";

afterEach(() => vi.unstubAllEnvs());

function request(origin?: string, site = "same-origin", forwardedHost?: string) {
  const headers = new Headers({ "sec-fetch-site": site });
  if (origin) headers.set("origin", origin);
  if (forwardedHost) headers.set("x-forwarded-host", forwardedHost);
  return new Request("http://127.0.0.1:3001/api/auth/login", { headers });
}

for (let pass = 1; pass <= 10; pass++) {
  describe(`request origin pass ${pass}`, () => {
    it("allows only the request origin when no public URL is configured", () => {
      vi.stubEnv("LEADZEN_DASHBOARD_PUBLIC_URL", undefined);
      expect(sameOrigin(request("http://127.0.0.1:3001"))).toBe(true);
      expect(sameOrigin(request("https://foreign.example"))).toBe(false);
    });

    it("uses the configured public origin behind a proxy without trusting forwarded hosts", () => {
      vi.stubEnv("NODE_ENV", "production");
      vi.stubEnv("LEADZEN_DASHBOARD_PUBLIC_URL", "https://localhost:3443");
      expect(sameOrigin(request("https://localhost:3443"))).toBe(true);
      expect(sameOrigin(request("http://127.0.0.1:3001"))).toBe(false);
      expect(sameOrigin(request("https://foreign.example", "same-origin", "foreign.example"))).toBe(false);
    });

    it("rejects missing origins and explicitly cross-site requests", () => {
      vi.stubEnv("LEADZEN_DASHBOARD_PUBLIC_URL", "https://localhost:3443");
      expect(sameOrigin(request())).toBe(false);
      expect(sameOrigin(request("https://localhost:3443", "cross-site"))).toBe(false);
    });

    it.each([
      "http://localhost:3443",
      "https://synthetic-user:synthetic-password@localhost:3443",
      "https://localhost:3443/path",
      "invalid-public-url",
    ])("fails closed for invalid production public URL %s", (url) => {
      vi.stubEnv("NODE_ENV", "production");
      vi.stubEnv("LEADZEN_DASHBOARD_PUBLIC_URL", url);
      expect(sameOrigin(request("https://localhost:3443"))).toBe(false);
    });
  });
}
