import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Gate } from "../api/types";
import { GateStepper } from "./GateStepper";

const RUN: Gate[] = [
  { id: "G0", state: "passed", status_text: "Brief accepted." },
  { id: "G1", state: "passed", status_text: "USD 0.012 of 0.050." },
  { id: "G2", state: "passed", status_text: "12 checked, 2 flagged." },
  { id: "G3", state: "active", status_text: "2 items to review.", actor: "operator" },
  { id: "G4", state: "pending", status_text: "Waiting for review.", actor: "approver" },
  { id: "G5", state: "pending", status_text: "Not exported.", actor: "approver" },
];

function gate(id: string) {
  const item = document.querySelector<HTMLElement>(`[data-gate="${id}"]`);
  if (!item) throw new Error(`no gate ${id}`);
  return within(item);
}

describe("GateStepper", () => {
  it("always shows all six gates in order", () => {
    render(<GateStepper gates={RUN} />);
    const labels = screen.getAllByRole("listitem").map((li) => li.querySelector(".rd-gate-label")?.textContent);
    expect(labels).toEqual(["Intake", "Spend", "Verify", "Review", "Approve", "Export"]);
  });

  it("shows each state in words, not only in the node", () => {
    render(<GateStepper gates={RUN} />);
    expect(gate("G0").getByText("Passed")).toBeTruthy();
    expect(gate("G3").getByText("Active")).toBeTruthy();
    expect(gate("G5").getByText("Pending")).toBeTruthy();
  });

  it("human gates show who must act; automatic gates say so", () => {
    render(<GateStepper gates={RUN} />);
    expect(gate("G1").getByText("Automatic")).toBeTruthy();
    expect(gate("G4").getByText("Human: approver")).toBeTruthy();
  });

  it("shows a gate missing from the run record as pending, never as passed", () => {
    render(<GateStepper gates={RUN.filter((g) => g.id !== "G4")} />);
    expect(gate("G4").getByText("Pending")).toBeTruthy();
    expect(gate("G4").getByText("No status yet.")).toBeTruthy();
  });

  it("shows an unrecognised state as pending", () => {
    const odd = RUN.map((g) => (g.id === "G5" ? { ...g, state: "done" as Gate["state"] } : g));
    render(<GateStepper gates={odd} />);
    expect(gate("G5").getByText("Pending")).toBeTruthy();
  });

  it("marks the active gate as the current step", () => {
    render(<GateStepper gates={RUN} />);
    const current = document.querySelector('[aria-current="step"]');
    expect(current?.getAttribute("data-gate")).toBe("G3");
  });

  it("selecting a gate reports which one", async () => {
    const onSelect = vi.fn();
    render(<GateStepper gates={RUN} onSelect={onSelect} />);
    await userEvent.click(gate("G4").getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith("G4");
  });
});
