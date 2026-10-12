import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { STOP_REASON_BANNER, StopReason } from "../generated/wording";
import { Button } from "./Button";
import { StopBanner } from "./StopBanner";

describe("StopBanner", () => {
  it("uses the fixed title for every reason, always starting with 'Stopped:'", () => {
    for (const reason of Object.values(StopReason)) {
      const { unmount } = render(<StopBanner reason={reason} accepted={0} target={12} />);
      const title = screen.getByRole("heading").textContent ?? "";
      expect(title).toBe(STOP_REASON_BANNER[reason]);
      expect(title.startsWith("Stopped:")).toBe(true);
      unmount();
    }
  });

  it("states the result in numbers and what did not happen", () => {
    render(<StopBanner reason={StopReason.BUDGET_CAP} accepted={9} target={12} />);
    expect(screen.getByText("9 of 12 items accepted. Nothing was exported.")).toBeTruthy();
  });

  it("never hides an unknown reason code", () => {
    render(<StopBanner reason="gpu_on_fire" accepted={3} target={12} />);
    expect(screen.getByRole("heading").textContent).toBe("Stopped: gpu_on_fire");
  });

  it("uses danger style for blocks and declines, warning for recoverable stops", () => {
    const { rerender } = render(<StopBanner reason={StopReason.BUDGET_CAP} accepted={0} target={1} />);
    expect(screen.getByRole("alert").className).toContain("rd-stop--danger");
    rerender(<StopBanner reason={StopReason.DECLINED} accepted={0} target={1} />);
    expect(screen.getByRole("alert").className).toContain("rd-stop--danger");
    rerender(<StopBanner reason={StopReason.TIMEOUT} accepted={0} target={1} />);
    expect(screen.getByRole("alert").className).toContain("rd-stop--warn");
  });

  it("offers the next actions and has no dismiss control", () => {
    render(
      <StopBanner
        reason={StopReason.BUDGET_CAP}
        accepted={9}
        target={12}
        actions={
          <>
            <Button>Raise the cap</Button>
            <Button>Keep the partial board</Button>
          </>
        }
      />,
    );
    const names = screen.getAllByRole("button").map((b) => b.textContent);
    expect(names).toEqual(["Raise the cap", "Keep the partial board"]);
  });

  it("shows what exactly stopped the run", () => {
    render(
      <StopBanner
        reason={StopReason.SOURCE_UNAVAILABLE}
        accepted={0}
        target={12}
        detail="Retriever 'combined' could not load: No module named 'torch'."
      />,
    );
    expect(screen.getByText("Retriever 'combined' could not load: No module named 'torch'.")).toBeTruthy();
  });
});
