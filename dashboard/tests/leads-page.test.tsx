import { describe, test, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/client-api";
import Contacts from "@/components/contacts";
import { user, lead } from "./fixtures";

const call = vi.mocked(api);
const noEmail = { ...lead, id: 2, name: "Jon", email: "", email_status: "not_requested", qualified: true } as typeof lead;
const summary = { all: 2, email_found: 1, needs_email: 1, contacted: 0, replied: 0 };
const review = { items: [{ id: 2, name: "Jon", eligible: true, reason: "" }], eligible_ids: [2], blocker: "", estimated_credits: 1, provider_name: "AI Ark", revision: "r1" };

function respond() {
  call.mockImplementation(async (path, init) => {
    const route = String(path);
    if (route.startsWith("contacts/emails") && init?.method === "POST") return { run: { id: "run-1" } };
    if (route.startsWith("contacts/emails")) return review;
    if (route.startsWith("leads")) return { items: [lead, noEmail], total: 2, summary };
    return {};
  });
}

describe("Leads page", () => {
  test("shows workspace counts", async () => {
    respond();
    render(<Contacts user={user} />);
    expect((await screen.findByLabelText("Lead counts")).textContent).toContain("1 need email");
  });

  test("a lead without an email can be selected and bulk-looked up", async () => {
    respond();
    render(<Contacts user={user} />);
    const box = await screen.findByLabelText("Select Jon");
    expect((box as HTMLInputElement).disabled).toBe(false);
    await userEvent.click(box);
    expect((screen.getByRole("button", { name: "Prepare outreach" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Find emails (1)" }));
    await screen.findByText(/up to/);
    await userEvent.click(screen.getByRole("button", { name: "Find 1 email" }));
    await screen.findByText(/Finding emails/);
    const post = call.mock.calls.find(([path, init]) => path === "contacts/emails" && init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ contact_ids: [2], revision: "r1", estimated_credits: 1 });
  });

  test("select all picks every lead on the page and outreach uses only leads with email", async () => {
    respond();
    render(<Contacts user={user} />);
    await userEvent.click(await screen.findByLabelText("Select leads on this page"));
    expect(screen.getByText("2 selected")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Prepare outreach (1)" }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("row Find email opens the one-credit confirmation", async () => {
    respond();
    render(<Contacts user={user} />);
    await userEvent.click(await screen.findByRole("button", { name: "Find email" }));
    await screen.findByText("Find this person’s work email?");
    await waitFor(() => expect(call.mock.calls.some(([path]) => path === "contacts/2/email")).toBe(true));
  });

  test("clicking the page box again clears the page selection", async () => {
    respond();
    render(<Contacts user={user} />);
    const all = await screen.findByLabelText("Select leads on this page");
    await userEvent.click(all);
    expect(screen.getByText("2 selected")).toBeTruthy();
    await userEvent.click(all);
    expect(screen.queryByText("2 selected")).toBeNull();
  });

  test("a selected lead follows its refreshed record and rows stay during background refresh", async () => {
    let found = false;
    call.mockImplementation(async (path, init) => {
      const route = String(path);
      if (route.startsWith("contacts/emails") && init?.method === "POST") { found = true; return { run: { id: "run-1" } }; }
      if (route.startsWith("contacts/emails")) return review;
      if (route.startsWith("leads")) return { items: [lead, found ? { ...noEmail, email: "jon@example.com", email_status: "verified" } : noEmail], total: 2, summary };
      return {};
    });
    render(<Contacts user={user} />);
    await userEvent.click(await screen.findByLabelText("Select Jon"));
    await userEvent.click(screen.getByRole("button", { name: "Find emails (1)" }));
    await screen.findByText(/up to/);
    await userEvent.click(screen.getByRole("button", { name: "Find 1 email" }));
    // The bulk start clears only the lookup leads; select Jon again after his email arrives.
    await screen.findByText("jon@example.com");
    await userEvent.click(screen.getByLabelText("Select Jon"));
    expect((screen.getByRole("button", { name: "Prepare outreach" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByRole("button", { name: /Find emails/ })).toBeNull();
  });
});

