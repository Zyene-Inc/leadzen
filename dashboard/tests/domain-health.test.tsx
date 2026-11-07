import { describe, test, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import { DomainHealth, type DomainHealthResult } from "@/components/domain-health";

const call = vi.mocked(api);

const result: DomainHealthResult = {
  domain: "acme.com",
  state: "failing",
  summary: "Needs attention: DMARC.",
  checked_at: "2026-11-04T15:00:00Z",
  checks: [
    { key: "spf", label: "SPF", status: "pass", message: "Found.", steps: [], fix: null, record: "v=spf1 include:zoho.com ~all" },
    { key: "dkim", label: "DKIM", status: "unknown", message: "Not verified.", steps: ["Generate a key."], fix: { type: "TXT", host: "zoho._domainkey.acme.com", value: "The value your email provider generates" }, record: "" },
    { key: "dmarc", label: "DMARC", status: "fail", message: "Missing.", steps: ["Add a TXT record."], fix: { type: "TXT", host: "_dmarc.acme.com", value: "v=DMARC1; p=none" }, record: "" },
    { key: "mx", label: "MX", status: "pass", message: "Found.", steps: [], fix: null, record: "" },
  ],
};

describe("Domain health", () => {
  test("checks only on request and shows plain results with fixes", async () => {
    call.mockReset();
    call.mockResolvedValueOnce(result);
    render(<DomainHealth address="sender@acme.com" disabled={false} />);
    expect(call).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Check domain" }));
    expect(call).toHaveBeenCalledWith("settings/domain-health", expect.objectContaining({ method: "POST", body: "{}" }));
    expect(await screen.findByText("Needs attention: DMARC.")).toBeTruthy();
    const list = screen.getByRole("list", { name: "DNS records for acme.com" });
    const dmarc = within(list).getByText("DMARC").closest("li")!;
    expect(within(dmarc).getByText("Fix needed")).toBeTruthy();
    expect(within(dmarc).getByText("_dmarc.acme.com")).toBeTruthy();
    const spf = within(list).getByText("SPF").closest("li")!;
    expect(within(spf).queryByText("How to fix")).toBeNull();
    expect(screen.getByRole("button", { name: "Check again" })).toBeTruthy();
  });

  test("shows an error and stays disabled without an account", async () => {
    call.mockReset();
    call.mockRejectedValueOnce(new Error("Connect an email account first"));
    const { rerender } = render(<DomainHealth address="sender@acme.com" disabled={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Check domain" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Connect an email account first");
    rerender(<DomainHealth address="" disabled={false} />);
    expect((screen.getByRole("button", { name: "Check domain" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
