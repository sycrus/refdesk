import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { NOT_LEGAL_ADVICE, RightsStatus } from "../generated/wording";
import { ConfirmDialog, type ConfirmDialogProps } from "./ConfirmDialog";

const BASE: Omit<ConfirmDialogProps, "open" | "onConfirm" | "onCancel"> = {
  itemCount: 7,
  countsByStatus: { [RightsStatus.OPEN]: 6, [RightsStatus.UNVERIFIED]: 1 },
  reviewed: [{ id: "met:1", title: "Harbour", note: "Checked the record by hand." }],
  excludedUnverified: 2,
  runId: "run-42",
};

function Harness({ onConfirm = vi.fn(), onCancel }: { onConfirm?: ConfirmDialogProps["onConfirm"]; onCancel?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open approval
      </button>
      <ConfirmDialog
        {...BASE}
        open={open}
        onConfirm={onConfirm}
        onCancel={() => {
          onCancel?.();
          setOpen(false);
        }}
      />
    </>
  );
}

async function openDialog(props = {}) {
  render(<Harness {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "Open approval" }));
  return screen.getByRole("dialog");
}

describe("ConfirmDialog", () => {
  it("title states the action and the count", async () => {
    const dialog = await openDialog();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByRole("heading", { name: "Approve and export 7 items" })).toBeTruthy();
  });

  it("summarises counts by rights status, reviewed items and exclusions", async () => {
    await openDialog();
    expect(screen.getByText(RightsStatus.OPEN)).toBeTruthy();
    expect(screen.getByText(/Checked the record by hand/)).toBeTruthy();
    expect(screen.getByText(/2 unverified items are excluded/)).toBeTruthy();
    expect(screen.getByText("run-42")).toBeTruthy();
  });

  it("keeps the primary disabled, with the reason, until acknowledged and named", async () => {
    const onConfirm = vi.fn();
    await openDialog({ onConfirm });
    const approve = screen.getByRole("button", { name: "Approve and export" });
    expect(screen.getByText("Tick the acknowledgement to continue.")).toBeTruthy();
    await userEvent.click(approve);
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("checkbox", { name: NOT_LEGAL_ADVICE }));
    expect(screen.getByText("Enter your name in Approving as.")).toBeTruthy();
    await userEvent.click(approve);
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.type(screen.getByRole("textbox", { name: "Approving as" }), "  Joe  ");
    await userEvent.click(approve);
    expect(onConfirm).toHaveBeenCalledWith({ approver: "Joe", acknowledged: true });
  });

  it("moves focus inside on open and traps it", async () => {
    const dialog = await openDialog();
    expect(dialog.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 8; i++) {
      await userEvent.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    for (let i = 0; i < 8; i++) {
      await userEvent.tab({ shift: true });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });

  it("Escape cancels and focus returns to the trigger", async () => {
    const onCancel = vi.fn();
    await openDialog({ onCancel });
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open approval" }));
  });
});
