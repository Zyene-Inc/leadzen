import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { HelpTooltip } from "@/components/help-tooltip";
import { PageHeading } from "@/components/page-heading";

function example() {
  return render(<><HelpTooltip label="Qualified leads">Profiles that match your saved target.</HelpTooltip><button>Next action</button></>);
}

describe("on-demand help", () => {
  it("keeps explanations closed initially and associates keyboard help with the trigger", async () => {
    example();
    expect(screen.queryByRole("tooltip")).toBeNull();
    await userEvent.tab();
    const help = screen.getByRole("button", { name: "Help: Qualified leads" });
    const tooltip = screen.getByRole("tooltip");
    expect(document.activeElement).toBe(help);
    expect(help.getAttribute("aria-describedby")).toBe(tooltip.id);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(document.activeElement).toBe(help);
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Next action" }));
  });

  it("supports hover across the trigger and tooltip without clipping it inside a card", async () => {
    const { container } = example();
    const help = screen.getByRole("button", { name: "Help: Qualified leads" });
    await userEvent.hover(help);
    const tooltip = screen.getByRole("tooltip");
    expect(container.contains(tooltip)).toBe(false);
    await userEvent.hover(tooltip);
    expect(screen.getByRole("tooltip")).toBe(tooltip);
    await userEvent.unhover(tooltip);
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  });

  it("can be pinned and dismissed by tapping, or clicking outside", async () => {
    example();
    const help = screen.getByRole("button", { name: "Help: Qualified leads" });
    await userEvent.click(help);
    expect(screen.getByRole("tooltip")).toBeTruthy();
    await userEvent.click(help);
    expect(screen.queryByRole("tooltip")).toBeNull();
    await userEvent.click(help);
    await userEvent.click(screen.getByRole("button", { name: "Next action" }));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("does not submit its form or propagate Escape into a containing dialog", async () => {
    const submit = vi.fn();
    const escape = vi.fn();
    render(<form onSubmit={submit} onKeyDown={escape}><HelpTooltip label="Timing">Uses working days.</HelpTooltip></form>);
    await userEvent.click(screen.getByRole("button"));
    await userEvent.keyboard("{Escape}");
    expect(submit).not.toHaveBeenCalled();
    expect(escape).not.toHaveBeenCalled();
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("dismisses detached-position help when the page scrolls or resizes", async () => {
    example();
    const help = screen.getByRole("button", { name: "Help: Qualified leads" });
    await userEvent.click(help);
    fireEvent.scroll(document);
    expect(screen.queryByRole("tooltip")).toBeNull();
    await userEvent.click(help);
    fireEvent(window, new Event("resize"));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("keeps page titles concise and their help separately keyboard-accessible", async () => {
    render(<PageHeading title="Leads" help="Review and manage your contacts." />);
    expect(screen.getByRole("heading", { name: "Leads", level: 1 })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Help: Leads" }));
    expect(screen.getByRole("tooltip").textContent).toContain("Review and manage your contacts.");
  });
});
