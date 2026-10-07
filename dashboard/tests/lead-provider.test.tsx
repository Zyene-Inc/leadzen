import { useState } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Connections } from "@/components/connections";
import FindLeads from "@/components/find-leads";
import { emptyCredentials, emptySettings, settingsBody, type Settings } from "@/lib/connection-settings";
import { api } from "@/lib/client-api";
import { user } from "./fixtures";

function ProviderEditor() {
  const [settings, setSettings] = useState<Settings>({ ...emptySettings, lead_finder: { provider: "bettercontact", api_key_configured: true, configured_providers: { bettercontact: true, ai_ark: false } } });
  const [credentials, setCredentials] = useState(emptyCredentials);
  return <><Connections settings={settings} onChange={setSettings} credentials={credentials} onCredentials={setCredentials} sections={["finder"]} /><output data-testid="payload">{JSON.stringify(settingsBody(settings, credentials).lead_finder)}</output></>;
}

describe("Lead provider selection", () => {
  test("switching keeps drafts separate and only submits the selected key", async () => {
    const actor = userEvent.setup();
    render(<ProviderEditor />);
    await actor.type(screen.getByLabelText("BetterContact API key"), "synthetic-bettercontact");
    await actor.selectOptions(screen.getByLabelText("Lead provider"), "ai_ark");
    const ark = screen.getByLabelText("AI Ark API key") as HTMLInputElement;
    expect(ark.value).toBe("");
    expect(ark.type).toBe("password");
    expect(screen.getByText(/No key saved/)).toBeTruthy();
    await actor.type(ark, "synthetic-ark");
    expect(JSON.parse(screen.getByTestId("payload").textContent!)).toEqual({ provider: "ai_ark", api_key: "synthetic-ark", clear_api_key: false });
    await actor.selectOptions(screen.getByLabelText("Lead provider"), "bettercontact");
    expect((screen.getByLabelText("BetterContact API key") as HTMLInputElement).value).toBe("synthetic-bettercontact");
    await actor.click(screen.getByRole("checkbox", { name: "Remove the saved BetterContact key when I save" }));
    await actor.selectOptions(screen.getByLabelText("Lead provider"), "ai_ark");
    expect((screen.getByLabelText("AI Ark API key") as HTMLInputElement).value).toBe("synthetic-ark");
    expect(JSON.parse(screen.getByTestId("payload").textContent!).clear_api_key).toBe(false);
  });

  test("AI Ark preview includes paid profiles and sends the reviewed total", async () => {
    vi.mocked(api).mockResolvedValueOnce({ max_count: 25, max_email_count: 12, provider_name: "AI Ark", profile_budget_per_lead: 1, target: "Practice owners", ready: true, blockers: [], revision: "synthetic-revision", active_run: null }).mockResolvedValueOnce({ run: { id: "synthetic-run" } });
    const actor = userEvent.setup();
    render(<FindLeads user={user} />);
    await screen.findByText("Maximum AI Ark search + email budget");
    expect(screen.getByText("Up to 3 credits")).toBeTruthy();
    expect(screen.queryByText("Free discovery")).toBeNull();
    await actor.click(screen.getByRole("button", { name: /Start Finding/i }));
    await waitFor(() => expect(vi.mocked(api)).toHaveBeenCalledTimes(2));
    const sent = JSON.parse(vi.mocked(api).mock.calls[1][1]!.body as string);
    expect(sent.estimated_credits).toBe(3);
    expect(sent.emails).toBe(false);
  });
});
