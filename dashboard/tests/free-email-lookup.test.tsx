import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import LeadDetail from "@/components/lead-detail";
import { api } from "@/lib/client-api";
import type { Contact } from "@/lib/leads";
import { lead, user } from "./fixtures";

const call = vi.mocked(api);
const untried = { ...lead, email: "", email_status: "not_requested", qualified: true, linkedin_url: "https://www.linkedin.com/in/bruce-example", lookup: null, free_lookup: null } as Contact;
const missed = { ...untried, free_lookup: { status: "not_found", checked_at: "2026-11-15T12:00:00Z", label: "Free lookup", retry: false } } as Contact;
afterEach(() => { vi.restoreAllMocks(); });

describe("free work-email lookup before buying", () => {
  test("an unchecked lead offers the free lookup first and calls only the free route", async () => {
    call.mockResolvedValueOnce(untried).mockResolvedValueOnce({ status: "not_found" }).mockResolvedValueOnce(missed);
    await act(async () => { render(<LeadDetail user={user} contactId={lead.id} />); });
    expect(screen.getByRole("button", { name: "Find work email" })).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Try free lookup" })); });
    expect(call.mock.calls[1][0]).toBe(`contacts/${lead.id}/free-email`);
    expect(call.mock.calls[1][1]?.method).toBe("POST");
    expect(screen.getByText(/free lookup found no email/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try free lookup" })).toBeNull();
    expect(screen.getByRole("button", { name: "Buy work email" })).toBeTruthy();
  });

  test("an address from the free lookup says no credits were used and offers outreach", async () => {
    call.mockResolvedValueOnce({ ...untried, email: "bruce@example.com", email_status: "verified", crm_status: "email_found", free_lookup: { ...missed.free_lookup!, status: "found" } } as Contact);
    await act(async () => { render(<LeadDetail user={user} contactId={lead.id} />); });
    expect(screen.getByText("Found by the free lookup. No credits used.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /work email/i })).toBeNull();
    expect(screen.getByRole("link", { name: "Prepare outreach" })).toBeTruthy();
  });
});
