import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MCPConnections, type MCPConnectionsData } from "@/components/mcp-connections";
import MCPConsent, { type MCPConsentData } from "@/components/mcp-consent";
import { returnToMcpClient, validatedMcpRedirect } from "@/lib/mcp-redirect";
import { api } from "@/lib/client-api";
import { user } from "./fixtures";

vi.mock("@/lib/mcp-redirect", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/mcp-redirect")>();
  return { ...actual, returnToMcpClient: vi.fn() };
});

const call = vi.mocked(api);
const metadata: MCPConnectionsData = {
  available: true,
  endpoint: "https://api.leadzen.example/mcp",
  reason: null,
  connections: [],
};
const connection = { id: "employee-grant-1", clientName: "Claude", createdAt: "2026-10-03T15:00:00Z", lastUsedAt: null };
const request = "synthetic_pending_request_12345678";
const consent: MCPConsentData = {
  request,
  clientName: "Claude",
  redirectHost: "claude.ai",
  scopes: ["leadzen:read", "leadzen:write", "offline_access"],
  expiresAt: "2026-10-03T15:10:00Z",
};
const writes = () => call.mock.calls.filter(([, init]) => init?.method === "POST");

beforeEach(() => call.mockResolvedValue(metadata));

test("Settings connectors show both real brand favicon sources, no invented connection or read side effect", async () => {
  render(<MCPConnections />);
  expect(await screen.findByText("No apps connected yet. Connect from Claude or ChatGPT to get started.")).toBeTruthy();
  expect((screen.getByRole("img", { name: "Claude logo" }) as HTMLImageElement).src).toContain("url=https://claude.ai&size=256");
  expect((screen.getByRole("img", { name: "ChatGPT logo" }) as HTMLImageElement).src).toContain("url=https://chatgpt.com&size=256");
  expect((screen.getByLabelText("Server URL") as HTMLInputElement).value).toBe(metadata.endpoint);
  expect(writes()).toHaveLength(0);
});

test("setup guidance expands one provider at a time and explains ChatGPT plan limits", async () => {
  render(<MCPConnections />);
  await screen.findByLabelText("Server URL");
  const claude = screen.getByRole("button", { name: "Set up Claude" });
  await userEvent.click(claude);
  expect(claude.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByRole("link", { name: /Claude setup guide/ }).getAttribute("href")).toContain("support.claude.com");
  expect(screen.getByText(/Under OAuth client, choose Register automatically/)).toBeTruthy();
  const chatgpt = screen.getByRole("button", { name: "Set up ChatGPT" });
  await userEvent.click(chatgpt);
  expect(claude.getAttribute("aria-expanded")).toBe("false");
  expect(chatgpt.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText(/Pro supports read\/fetch access only/)).toBeTruthy();
  expect(screen.getByRole("link", { name: /ChatGPT setup guide/ }).getAttribute("href")).toContain("help.openai.com");
  expect(writes()).toHaveLength(0);
});

test("a missing public server reports the actual setup blocker and cannot copy a localhost URL", async () => {
  call.mockResolvedValue({ ...metadata, available: false, endpoint: null, reason: "Your administrator must configure a public HTTPS MCP server." });
  render(<MCPConnections />);
  expect(await screen.findByText("Your administrator must configure a public HTTPS MCP server.")).toBeTruthy();
  expect(screen.queryByLabelText("Server URL")).toBeNull();
  expect(screen.queryByRole("button", { name: "Copy URL" })).toBeNull();
  expect(screen.getByRole("button", { name: "Set up Claude" })).toBeTruthy();
});

test("connector metadata failure stays visible and retry loads the authenticated state", async () => {
  call.mockRejectedValueOnce(new Error("Connection access unavailable.")).mockResolvedValue(metadata);
  render(<MCPConnections />);
  expect((await screen.findByRole("alert")).textContent).toContain("Connection access unavailable");
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByLabelText("Server URL");
  expect(screen.queryByRole("alert")).toBeNull();
});

test("URL copy uses only the configured endpoint and reports success", async () => {
  const interaction = userEvent.setup();
  const copy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  render(<MCPConnections />);
  await screen.findByLabelText("Server URL");
  await interaction.click(screen.getByRole("button", { name: "Copy URL" }));
  expect(copy).toHaveBeenCalledWith(metadata.endpoint);
  expect(screen.getByRole("status").textContent).toBe("Server URL copied.");
  expect(writes()).toHaveLength(0);
});

test("clipboard rejection gives a manual-copy recovery", async () => {
  const interaction = userEvent.setup();
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("No clipboard permission"));
  render(<MCPConnections />);
  await screen.findByLabelText("Server URL");
  await interaction.click(screen.getByRole("button", { name: "Copy URL" }));
  expect(screen.getByRole("alert").textContent).toContain("copy it manually");
  expect((screen.getByLabelText("Server URL") as HTMLInputElement).readOnly).toBe(true);
});

test("logos fail visibly without substituting a fake brand mark", async () => {
  render(<MCPConnections />);
  await screen.findByLabelText("Server URL");
  fireEvent.error(screen.getByRole("img", { name: "Claude logo" }));
  expect(screen.getByText("Logo unavailable")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Claude", level: 3 })).toBeTruthy();
});

test("disconnect requires a concrete confirmation and sends only the canonical grant id once", async () => {
  call.mockImplementation(async (_path, init) => {
    if (init?.method) return { revoked: true };
    return writes().length ? metadata : { ...metadata, connections: [connection] };
  });
  render(<MCPConnections />);
  await userEvent.click(await screen.findByRole("button", { name: "Disconnect Claude" }));
  expect(writes()).toHaveLength(0);
  expect(screen.getByText("Disconnect this app? Its access stops immediately.")).toBeTruthy();
  const button = screen.getByRole("button", { name: "Confirm disconnect" });
  fireEvent.click(button);
  fireEvent.click(button);
  await waitFor(() => expect(screen.queryByRole("button", { name: "Disconnect Claude" })).toBeNull());
  expect(writes()).toHaveLength(1);
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ connectionId: connection.id });
  expect(screen.getByText("Claude disconnected.")).toBeTruthy();
});

test("cancel disconnect retains access; server rejection never fabricates a disconnected state", async () => {
  call.mockImplementation(async (_path, init) => {
    if (init?.method) throw new Error("This connection does not belong to your account.");
    return { ...metadata, connections: [connection] };
  });
  render(<MCPConnections />);
  await userEvent.click(await screen.findByRole("button", { name: "Disconnect Claude" }));
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(writes()).toHaveLength(0);
  await userEvent.click(screen.getByRole("button", { name: "Disconnect Claude" }));
  await userEvent.click(screen.getByRole("button", { name: "Confirm disconnect" }));
  expect((await screen.findByRole("alert")).textContent).toContain("does not belong");
  expect(screen.getAllByText("Claude")).toHaveLength(2);
  expect(screen.queryByText("Claude disconnected.")).toBeNull();
});

test("connection timestamps render New York time", async () => {
  call.mockResolvedValue({ ...metadata, connections: [connection] });
  render(<MCPConnections />);
  expect(await screen.findByText(/Oct 3, 2026, 11:00 AM/)).toBeTruthy();
  expect(screen.getByText(/New York time/)).toBeTruthy();
});

test("consent reads only the opaque request and shows callback, employee account and bounded permissions", async () => {
  call.mockResolvedValue(consent);
  render(<MCPConsent user={user} request={request} />);
  expect(await screen.findByText("Claude wants access")).toBeTruthy();
  expect(screen.getByText("claude.ai")).toBeTruthy();
  expect(screen.getByText(user.email)).toBeTruthy();
  expect(screen.getByText("Manage your leads, drafts, outreach and nonsecret settings.")).toBeTruthy();
  expect(screen.getByText(/Paid actions and email sending still require a separate approval/)).toBeTruthy();
  expect(call.mock.calls[0][0]).toBe(`mcp/authorize?request=${request}`);
  expect(writes()).toHaveLength(0);
});

test.each(["", "https://evil.example", "x", "request<script>unsafe</script>"])("invalid consent request %s never loads or grants a connection", async (invalid) => {
  render(<MCPConsent user={user} request={invalid} />);
  expect((await screen.findByRole("alert")).textContent).toContain("missing or invalid");
  expect(call).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Connect" })).toBeNull();
});

test("expired or inaccessible consent fails closed and allows a read-only retry", async () => {
  call.mockRejectedValueOnce(new Error("This connection request expired.")).mockResolvedValue(consent);
  render(<MCPConsent user={user} request={request} />);
  expect((await screen.findByRole("alert")).textContent).toContain("expired");
  expect(screen.queryByRole("button", { name: "Connect" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByRole("button", { name: "Connect" });
  expect(writes()).toHaveLength(0);
});

test("navigation from a valid consent request to an invalid request clears the prior approval controls", async () => {
  call.mockResolvedValue(consent);
  const { rerender } = render(<MCPConsent user={user} request={request} />);
  await screen.findByRole("button", { name: "Connect" });
  rerender(<MCPConsent user={user} request="invalid" />);
  expect((await screen.findByRole("alert")).textContent).toContain("missing or invalid");
  expect(screen.queryByRole("button", { name: "Connect" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Deny access" })).toBeNull();
  expect(screen.queryByText("Claude wants access")).toBeNull();
  expect(call).toHaveBeenCalledOnce();
  expect(writes()).toHaveLength(0);
});

test("approval submits only validated request and decision once, preserving errors for review", async () => {
  call.mockImplementation(async (_path, init) => {
    if (init?.method) throw new Error("Request changed. Connect again from your assistant.");
    return consent;
  });
  render(<MCPConsent user={user} request={request} />);
  const connect = await screen.findByRole("button", { name: "Connect" });
  fireEvent.click(connect);
  fireEvent.click(connect);
  expect((await screen.findByRole("alert")).textContent).toContain("Request changed");
  expect(writes()).toHaveLength(1);
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ request, decision: "approve" });
  expect((screen.getByRole("button", { name: "Connect" }) as HTMLButtonElement).disabled).toBe(false);
});

test("denial uses the same server-validated callback flow and cannot follow another host", async () => {
  call.mockImplementation(async (_path, init) => init?.method ? { redirectUrl: "https://evil.example/?code=private" } : consent);
  render(<MCPConsent user={user} request={request} />);
  await userEvent.click(await screen.findByRole("button", { name: "Deny access" }));
  expect((await screen.findByRole("alert")).textContent).toContain("callback could not be verified");
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ request, decision: "deny" });
  expect(returnToMcpClient).not.toHaveBeenCalled();
});

test.each(["approve", "deny"] as const)("successful %s consent returns only to the server-validated assistant callback", async (decision) => {
  const destination = `https://claude.ai/oauth/callback?${decision === "approve" ? "code=server-issued" : "error=access_denied"}&state=client-state`;
  call.mockImplementation(async (_path, init) => init?.method ? { redirectUrl: destination } : consent);
  render(<MCPConsent user={user} request={request} />);
  await userEvent.click(await screen.findByRole("button", { name: decision === "approve" ? "Connect" : "Deny access" }));
  expect(returnToMcpClient).toHaveBeenCalledOnce();
  expect(returnToMcpClient).toHaveBeenCalledWith(destination);
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ request, decision });
  expect((screen.getByRole("button", { name: "Returning to assistant…" }) as HTMLButtonElement).disabled).toBe(true);
});

test.each([
  ["https://claude.ai/oauth/callback?code=verified", "claude.ai", true],
  ["http://127.0.0.1:4567/callback?code=verified", "127.0.0.1:4567", true],
  ["https://evil.example/callback", "claude.ai", false],
  ["https://claude.ai@evil.example/callback", "claude.ai", false],
  ["https://secret@claude.ai/callback", "claude.ai", false],
  ["https://claude.ai/callback#unexpected", "claude.ai", false],
  ["javascript:alert(1)", "claude.ai", false],
  ["data:text/html,unsafe", "claude.ai", false],
  ["http://claude.ai/callback", "claude.ai", false],
  ["/settings", "claude.ai", false],
])("OAuth callback %s respects the validated host and safe schemes", (url, host, allowed) => {
  expect(Boolean(validatedMcpRedirect(String(url), String(host)))).toBe(allowed);
});
