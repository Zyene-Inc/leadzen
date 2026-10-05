import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { safeMcpReturnPath } from "@/lib/mcp-return";
import { proxy } from "@/proxy";

afterEach(() => vi.unstubAllEnvs());

describe("MCP consent after sign-in", () => {
  const path = "/mcp/connect?request=12345678-1234-1234-1234-123456789abc";

  it("preserves the validated pending consent path", () => {
    expect(safeMcpReturnPath(path)).toBe(path);
    vi.stubEnv("LEADZEN_API_URL", "http://127.0.0.1:8000");
    vi.stubEnv("LEADZEN_API_TOKEN", "synthetic-test-token");
    const response = proxy(new NextRequest(`http://localhost:3001${path}`));
    expect(response.headers.get("location")).toBe(`http://localhost:3001/login?returnTo=${encodeURIComponent(path)}`);
  });

  it.each([
    "https://foreign.example/mcp/connect?request=123456789012345678901234",
    "//foreign.example/mcp/connect?request=123456789012345678901234",
    "/\\foreign.example/mcp/connect?request=123456789012345678901234",
    "/mcp/connect?request=short",
    "/mcp/connect?request=123456789012345678901234&redirect=https://foreign.example",
    "/mcp/connect?request=123456789012345678901234&request=123456789012345678901234",
    "/mcp/connect?request=123456789012345678901234#private",
    "/admin",
  ])("rejects unsafe or ambiguous return path %s", value => {
    expect(safeMcpReturnPath(value)).toBeNull();
  });
});
