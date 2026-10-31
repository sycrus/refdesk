// S7 run history and audit (issue 159): the runs list and one run's events, read-only.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunEvent, RunSummary, RunView } from "../api/types";
import { STOP_REASON_BANNER } from "../generated/wording";
import { HistoryScreen, RunAudit, toAuditEvent } from "./HistoryScreen";

const REDACTED = "[brief redacted]";

function summary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "run-1",
    created_at: "2026-10-31T10:00:00+00:00",
    brief: REDACTED,
    state: "done",
    stop_reason: null,
    stop_banner: null,
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: false,
    sent_to: ["mock", "mock-judge"],
    approver: null,
    read_only: false,
    ...overrides,
  };
}

const EVENTS: RunEvent[] = [
  { seq: 1, run_id: "run-2", at: "2026-10-31T10:00:00+00:00", step: 1, kind: "transition", state: "init" },
  {
    seq: 2,
    run_id: "run-2",
    at: "2026-10-31T10:00:01+00:00",
    step: 2,
    kind: "call",
    state: "generate",
    tool: "llm:local",
    model: "mock",
    tokens_in: 120,
    tokens_out: 30,
    cost_usd: 0,
    result: "3 rationales written.",
  },
  {
    seq: 3,
    run_id: "run-2",
    at: "2026-10-31T10:00:02+00:00",
    step: 3,
    kind: "transition",
    state: "stopped",
    reason_code: "budget_cap",
    result: "Spent USD 0.050 of 0.050.",
  },
];

function run(overrides: Partial<RunView> = {}): RunView {
  return {
    run_id: "run-2",
    request: { brief: "cypresses" },
    state: "stopped",
    stop_reason: "budget_cap",
    stop_banner: STOP_REASON_BANNER.budget_cap,
    stop_detail: "Spent USD 0.050 of 0.050.",
    gates: [],
    items: [],
    cost: { spent_usd: 0.05, cap_usd: 0.05, currency: "USD" },
    keep_local: false,
    sent_to: ["mock", "mock-judge"],
    models_used: { generator: "mock", judge: "mock-judge" },
    approval: null,
    read_only: false,
    events: EVENTS,
    ...overrides,
  };
}

function respond(...bodies: { status?: number; body: unknown }[]) {
  const fetchMock = vi.fn();
  for (const { status = 200, body } of bodies) {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status }));
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("S7 HistoryScreen (runs list)", () => {
  it("lists every run, newest first as the API returns them, with a redacted brief", async () => {
    const fetchMock = respond({
      body: [summary({ run_id: "run-2" }), summary({ run_id: "run-1", created_at: "2026-10-30T09:00:00+00:00" })],
    });
    render(<HistoryScreen onOpenAudit={vi.fn()} />);
    const rows = await screen.findAllByRole("row");
    expect(fetchMock).toHaveBeenCalledWith("/runs");
    // header + two runs, in the API's order (never re-sorted here)
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText("run-2")).toBeTruthy();
    expect(within(rows[2]).getByText("run-1")).toBeTruthy();
    expect(screen.getAllByText(REDACTED)).toHaveLength(2);
  });

  it("shows sent_to for every run, including a run sent nowhere", async () => {
    respond({
      body: [
        summary({ run_id: "run-3", sent_to: ["mock", "mock-judge"] }),
        summary({ run_id: "run-4", sent_to: [], keep_local: true }),
      ],
    });
    render(<HistoryScreen onOpenAudit={vi.fn()} />);
    const rows = await screen.findAllByRole("row");
    const header = within(rows[0]).getAllByRole("columnheader").map((c) => c.textContent);
    const sentCol = header.indexOf("Brief sent to");
    expect(sentCol).toBeGreaterThan(-1);
    const cell = (row: HTMLElement) => row.children[sentCol] as HTMLElement;
    expect(cell(rows[1]).textContent).toBe("mock, mock-judge");
    expect(cell(rows[2]).textContent).toBe("nowhere: no model was called (retrieval only)");
    expect(within(rows[2]).getByText(/stays on this machine/)).toBeTruthy();
  });

  it("never hides a stop reason: the fixed wording, or an unknown code as it is", async () => {
    respond({
      body: [
        summary({ run_id: "run-5", state: "stopped", stop_reason: "budget_cap" }),
        summary({ run_id: "run-6", state: "stopped", stop_reason: "mystery" as never }),
        summary({ run_id: "run-7" }),
      ],
    });
    render(<HistoryScreen onOpenAudit={vi.fn()} />);
    await screen.findByText(STOP_REASON_BANNER.budget_cap);
    expect(screen.getByText("Stopped: mystery")).toBeTruthy();
    expect(screen.getByText("None")).toBeTruthy();
  });

  it("shows cost and approver", async () => {
    respond({
      body: [summary({ approver: "Joe", cost: { spent_usd: 0.0123, cap_usd: 0.05, currency: "USD" } })],
    });
    render(<HistoryScreen onOpenAudit={vi.fn()} />);
    expect(await screen.findByText("Joe")).toBeTruthy();
    expect(screen.getByText("USD 0.0123 of 0.050 cap")).toBeTruthy();
  });

  it("opens a run's events from its row", async () => {
    respond({ body: [summary({ run_id: "run-8" })] });
    const onOpenAudit = vi.fn();
    render(<HistoryScreen onOpenAudit={onOpenAudit} />);
    await userEvent.click(await screen.findByRole("link", { name: "Events for run-8" }));
    expect(onOpenAudit).toHaveBeenCalledWith("run-8");
  });

  it("is read-only: no buttons, no form controls", async () => {
    respond({ body: [summary()] });
    render(<HistoryScreen onOpenAudit={vi.fn()} />);
    await screen.findAllByRole("row");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("says when there are no runs, and reports an API error", async () => {
    respond({ body: [] });
    const { unmount } = render(<HistoryScreen onOpenAudit={vi.fn()} />);
    expect(await screen.findByText("No runs yet.")).toBeTruthy();
    unmount();
    respond({ status: 500, body: { code: "x", message: "store unavailable" } });
    render(<HistoryScreen onOpenAudit={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toBe("store unavailable");
  });
});

describe("S7 RunAudit (one run's events)", () => {
  it("shows every logged event in log order, with tool, tokens, cost and reason", async () => {
    respond({ body: run() });
    render(<RunAudit runId="run-2" onBack={vi.fn()} onOpenBoard={vi.fn()} />);
    const log = await screen.findByRole("region", { name: "Run audit log" });
    const items = within(log).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain("Step 1 Started");
    expect(items[1].textContent).toContain("3 rationales written.");
    expect(items[1].textContent).toContain("tool=llm:local (mock) · tokens=150 · cost=USD 0.0000");
    expect(items[2].textContent).toContain("Step 3 Stopped");
    expect(items[2].textContent).toContain("reason=budget_cap");
  });

  it("shows sent_to, keep-local, the stop reason and its detail, and the versions", async () => {
    respond({ body: run() });
    render(<RunAudit runId="run-2" onBack={vi.fn()} onOpenBoard={vi.fn()} />);
    await screen.findByRole("region", { name: "Run audit log" });
    expect(screen.getByText("mock, mock-judge")).toBeTruthy();
    expect(screen.getByText(STOP_REASON_BANNER.budget_cap)).toBeTruthy();
    expect(screen.getByText(/Spent USD 0.050 of 0.050\./, { selector: ".rd-facts .rd-note" })).toBeTruthy();
    expect(screen.getByText("generator")).toBeTruthy();
    expect(screen.getByText("Not approved")).toBeTruthy();
  });

  it("shows where a retrieval-only run was sent: nowhere", async () => {
    respond({ body: run({ sent_to: [], stop_reason: null, state: "done", events: [] }) });
    render(<RunAudit runId="run-2" onBack={vi.fn()} onOpenBoard={vi.fn()} />);
    expect(await screen.findByText("nowhere: no model was called (retrieval only)")).toBeTruthy();
    expect(screen.getByText("No events recorded yet.")).toBeTruthy();
  });

  it("names the approver once approved", async () => {
    respond({
      body: run({ approval: { approver: "Joe", acknowledged: true, approved_at: "2026-10-31T11:00:00+00:00" } }),
    });
    render(<RunAudit runId="run-2" onBack={vi.fn()} onOpenBoard={vi.fn()} />);
    expect(await screen.findByText("Joe at 2026-10-31T11:00:00+00:00")).toBeTruthy();
  });

  it("is read-only and links back to the history and on to the board", async () => {
    respond({ body: run() });
    const onBack = vi.fn();
    const onOpenBoard = vi.fn();
    render(<RunAudit runId="run-2" onBack={onBack} onOpenBoard={onOpenBoard} />);
    await screen.findByRole("region", { name: "Run audit log" });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    await userEvent.click(screen.getByRole("link", { name: "Open the board" }));
    expect(onOpenBoard).toHaveBeenCalledWith("run-2");
    await userEvent.click(screen.getByRole("link", { name: "Back to the run history" }));
    expect(onBack).toHaveBeenCalled();
  });

  it("reports an unknown run", async () => {
    respond({ status: 404, body: { code: "unknown_run", message: "No run 'nope'." } });
    render(<RunAudit runId="nope" onBack={vi.fn()} onOpenBoard={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("No run 'nope'."));
  });
});

describe("toAuditEvent", () => {
  it("keeps the reason code and leaves tokens out when none were logged", () => {
    const event = toAuditEvent(EVENTS[2]);
    expect(event).toMatchObject({ label: "Step 3 Stopped", tone: "warn", reason_code: "budget_cap" });
    expect(event.tokens).toBeUndefined();
  });
});
