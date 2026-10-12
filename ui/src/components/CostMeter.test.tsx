import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CostMeter, costState } from "./CostMeter";

describe("CostMeter", () => {
  it("always shows the number and the cap, not just a bar", () => {
    render(<CostMeter spent={0.012} cap={0.05} />);
    expect(screen.getByText("USD 0.012 of 0.050 cap")).toBeTruthy();
  });

  it("is normal below 80%, warning from 80%, blocked at 100%", () => {
    expect(costState(0.039, 0.05)).toBe("normal");
    expect(costState(0.04, 0.05)).toBe("warning");
    expect(costState(0.05, 0.05)).toBe("blocked");
    expect(costState(0.07, 0.05)).toBe("blocked");
  });

  it("does not miss a threshold through float rounding", () => {
    expect(0.04 / 0.05).toBeLessThan(0.8); // the float trap this guards against
    expect(costState(0.04, 0.05)).toBe("warning");
    expect(costState(0.1 + 0.2, 0.3)).toBe("blocked");
  });

  it("writes the state in the note, not only in colour", () => {
    render(<CostMeter spent={0.045} cap={0.05} />);
    expect(screen.getByText("Near the cap: 80% or more spent.")).toBeTruthy();
  });

  it("is a labelled progressbar whose value text carries the numbers and state", () => {
    render(<CostMeter spent={0.05} cap={0.05} />);
    const bar = screen.getByRole("progressbar", { name: "Spend against the cap" });
    expect(bar.getAttribute("aria-valuemax")).toBe("0.05");
    expect(bar.getAttribute("aria-valuetext")).toContain("USD 0.050 of 0.050 cap");
    expect(bar.getAttribute("aria-valuetext")).toContain("Cap reached");
  });

  it("never draws past the cap", () => {
    const { container } = render(<CostMeter spent={0.2} cap={0.05} />);
    const fill = container.querySelector<HTMLElement>(".rd-cost-fill");
    expect(fill?.style.width).toBe("100%");
  });

  it("treats a missing or zero cap as blocked, never as unlimited", () => {
    expect(costState(0, 0)).toBe("blocked");
  });
});
