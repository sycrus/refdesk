import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("runs its handler when enabled", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>More like this</Button>);
    await userEvent.click(screen.getByRole("button", { name: "More like this" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("a disabled button shows its reason next to it and is described by it", () => {
    render(
      <Button variant="primary" disabledReason="Tick the acknowledgement to continue.">
        Approve and export
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Approve and export" });
    const reason = screen.getByText("Tick the acknowledgement to continue.");
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.getAttribute("aria-describedby")).toBe(reason.id);
  });

  it("a disabled button ignores clicks but stays focusable", async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabledReason="Nothing selected.">
        Export
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Export" });
    await userEvent.tab();
    expect(document.activeElement).toBe(button);
    await userEvent.keyboard("{Enter}");
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("defaults to the secondary variant", () => {
    render(<Button>Cancel</Button>);
    expect(screen.getByRole("button").className).toContain("rd-button--secondary");
  });
});
