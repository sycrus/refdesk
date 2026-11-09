import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { BoardItem, Gate, RunView } from "../api/types";
import { AttributionStatus, RightsStatus } from "../generated/wording";
import { StagePanel, stagesFor } from "./StagePanel";

function gates(states: Partial<Record<Gate["id"], Gate["state"]>>): Gate[] {
  return (["G0", "G1", "G2", "G3", "G4", "G5"] as const).map((id) => ({
    id,
    state: states[id] ?? "pending",
    status_text: `${id} says ${states[id] ?? "pending"}.`,
  }));
}

const ITEM: BoardItem = {
  record: {
    id: "met:1",
    source: "met",
    title: "Sample",
    rights: { status: RightsStatus.OPEN, flag_field: "isPublicDomain" },
  },
  rationale: null,
  evidence: [],
  attribution_status: AttributionStatus.VERIFIED,
  flag_reasons: [],
  selected: true,
};

function run(overrides: Partial<RunView> = {}): RunView {
  return {
    run_id: "run-1",
    request: { brief: "Mid-Autumn tin, festive but not red and gold" },
    state: "done",
    gates: gates({ G0: "skipped", G1: "passed", G2: "passed", G3: "skipped", G4: "active" }),
    items: [ITEM, { ...ITEM, selected: false, record: { ...ITEM.record, id: "met:2" } }],
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: true,
    sent_to: [],
    read_only: false,
    ...overrides,
  };
}

const byKey = (view: RunView) => Object.fromEntries(stagesFor(view).map((s) => [s.key, s]));

describe("stagesFor (issue 229)", () => {
  it("passes each gate's state through unchanged", () => {
    const stages = byKey(run());
    expect(stages.brief.state).toBe("skipped");
    expect(stages.verify.state).toBe("skipped");
    expect(stages.approve.state).toBe("active");
    expect(stages.export.state).toBe("pending");
    expect(stages.approve.detail).toBe("G4 says active.");
  });

  it("shows a stage as passed only when its gate has passed", () => {
    const stages = byKey(run({ gates: gates({ G1: "passed", G2: "passed", G3: "active", G4: "pending" }) }));
    expect(stages.search.state).toBe("passed");
    expect(stages.verify.state).toBe("active");
    expect(stages.approve.state).not.toBe("passed");
  });

  it("shows the gate that needs attention when a stage has two, and words for both", () => {
    const stages = byKey(run({ gates: gates({ G1: "passed", G2: "blocked" }) }));
    expect(stages.search.state).toBe("blocked");
    expect(stages.search.detail).toBe("G1 says passed. G2 says blocked.");
  });

  it("never treats a gate the API did not report as passed", () => {
    const stages = byKey(run({ gates: [] }));
    expect(stages.approve.state).toBe("pending");
    expect(stages.approve.reachable).toBe(false);
  });

  it("keeps later stages disabled until their gate is reached", () => {
    const stages = byKey(run({ gates: gates({ G1: "passed", G2: "passed", G3: "pending", G4: "pending" }) }));
    expect(stages.brief.reachable && stages.search.reachable && stages.shortlist.reachable).toBe(true);
    expect(stages.verify.reachable || stages.approve.reachable || stages.export.reachable).toBe(false);
  });

  it("gives the shortlist no gate, and its kept count once the search has ended", () => {
    expect(byKey(run()).shortlist).toMatchObject({ state: "none", detail: "1 of 2 kept", reachable: true });
    expect(byKey(run({ state: "generate" })).shortlist).toMatchObject({ reachable: false, detail: "Waiting for the search" });
  });
});

const LINKS = [
  { key: "new", label: "New board", icon: "plus" as const, href: "/", current: true, onOpen: vi.fn() },
  { key: "history", label: "Run history", icon: "history" as const, href: "?history=1", current: false, onOpen: vi.fn() },
];

describe("StagePanel", () => {
  it("has no board stages until a board is open", () => {
    render(<StagePanel links={LINKS} minimised={false} onToggle={vi.fn()} />);
    expect(screen.queryByRole("list", { name: "Stages of this board" })).toBeNull();
    expect(screen.queryByText(/This board/)).toBeNull();
    expect(screen.getByRole("link", { name: "New board" }).getAttribute("aria-current")).toBe("page");
  });

  it("lists the stages in order with their state in words, and only reached ones are links", async () => {
    const onOpen = vi.fn();
    render(
      <StagePanel
        links={LINKS}
        minimised={false}
        onToggle={vi.fn()}
        board={{ name: "Mid-Autumn tin", run: run(), current: "shortlist", onOpen, href: () => "?run=run-1" }}
      />,
    );
    const stages = screen.getByRole("list", { name: "Stages of this board" });
    expect(screen.getByText("This board · Mid-Autumn tin")).toBeTruthy();
    const approve = within(stages).getByRole("link", { name: "Approve: active (G4)" });
    expect(within(stages).queryByRole("link", { name: /^Export/ })).toBeNull();
    expect(within(stages).getByText("Export: pending (G5). Not reached yet.")).toBeTruthy();
    expect(within(stages).getByRole("link", { name: "Shortlist: no gate" }).getAttribute("aria-current")).toBe("step");
    expect(screen.getByText("Point of no return")).toBeTruthy();
    await userEvent.click(approve);
    expect(onOpen).toHaveBeenCalledWith("approve");
  });

  it("minimises to icons and says which way the toggle goes", async () => {
    const onToggle = vi.fn();
    const { rerender } = render(<StagePanel links={LINKS} minimised={false} onToggle={onToggle} />);
    const toggle = screen.getByRole("button", { name: "Minimise the panel" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    await userEvent.click(toggle);
    expect(onToggle).toHaveBeenCalled();
    rerender(<StagePanel links={LINKS} minimised onToggle={onToggle} />);
    expect(screen.getByRole("button", { name: "Expand the panel" }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByRole("link", { name: "New board" }).getAttribute("title")).toBe("New board");
  });
});
