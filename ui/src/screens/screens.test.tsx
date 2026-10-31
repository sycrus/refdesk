import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BoardItem, Gate, RunView } from "../api/types";
import { AttributionStatus, NOT_LEGAL_ADVICE, RightsStatus, STOP_REASON_BANNER, StopReason } from "../generated/wording";
import { ApproveScreen, packPreview } from "./ApproveScreen";
import { ItemDetail } from "./ItemDetail";
import { NewBoard } from "./NewBoard";
import { ReviewScreen } from "./ReviewScreen";
import { RunScreen } from "./RunScreen";

const GATES: Gate[] = [
  { id: "G0", state: "skipped", status_text: "No intake checks yet." },
  { id: "G1", state: "passed", status_text: "No paid calls: USD 0.000 of 0.050." },
  { id: "G2", state: "skipped", status_text: "No verifier yet (M3): every attribution needs a human check." },
  { id: "G3", state: "active", status_text: "1 items need a human check.", actor: "operator" },
  { id: "G4", state: "pending", status_text: "Waiting for review.", actor: "approver" },
  { id: "G5", state: "pending", status_text: "Not exported.", actor: "approver" },
];

const ITEM: BoardItem = {
  record: {
    id: "met:436535",
    source: "met",
    title: "Wheat Field with Cypresses",
    artist: "Vincent van Gogh",
    date: "1889",
    image_url: "https://images.metmuseum.org/x.jpg",
    record_url: "https://www.metmuseum.org/art/collection/search/436535",
    rights: { status: RightsStatus.OPEN, flag_field: "isPublicDomain" },
  },
  rationale: null,
  evidence: [{ field: "subject_tags", value: "Cypresses" }],
  attribution_status: AttributionStatus.NEEDS_HUMAN_CHECK,
  flag_reasons: ["No verifier yet (M3): the attribution has not been checked against the record."],
  selected: false,
  score: 0.25,
  score_components: { attributes: 0.25 },
};

function view(overrides: Partial<RunView> = {}): RunView {
  return {
    run_id: "run-1",
    request: { brief: "cypresses", usage_mode: "reference_only", target_items: 12 },
    state: "done",
    gates: GATES,
    items: [ITEM],
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: true,
    sent_to: [],
    read_only: false,
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
  vi.useRealTimers();
});

describe("S1 NewBoard", () => {
  it("sends the brief and only the constraints that were filled in", async () => {
    const fetchMock = respond({ status: 202, body: { run_id: "run-9", state: "retrieve" } });
    const onCreated = vi.fn();
    render(<NewBoard onCreated={onCreated} />);
    await userEvent.type(screen.getByLabelText("Brief"), "stormy sea");
    await userEvent.type(screen.getByLabelText("Period"), "17th century");
    await userEvent.type(screen.getByLabelText(/^Avoid/), "red, met:1");
    await userEvent.click(screen.getByLabelText(/Keep this brief on this machine/));
    await userEvent.click(screen.getByRole("button", { name: "Find references" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("run-9"));
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent).toMatchObject({
      brief: "stormy sea",
      conditions: { period: "17th century" },
      avoid: ["red", "met:1"],
      keep_local: true,
      usage_mode: "reference_only",
      anchor_id: null,
    });
  });

  it("shows the API's own reason when it refuses the board", async () => {
    respond({ status: 400, body: { code: "unknown_anchor", message: "No record 'met:404'." } });
    render(<NewBoard onCreated={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Brief"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Find references" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "The API refused this board: No record 'met:404'.",
    );
  });
});

describe("S2/S3 RunScreen", () => {
  it("shows progress while the run works, then the board", async () => {
    respond({ body: view({ state: "retrieve", items: [] }) }, { body: view() });
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    expect(await screen.findByText("Searching the collection…")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Wheat Field with Cypresses" }, { timeout: 2000 })).toBeTruthy();
  });

  it("shows both badges, evidence, the score and where the brief was sent", async () => {
    respond({ body: view() });
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    expect(await screen.findByText(AttributionStatus.NEEDS_HUMAN_CHECK)).toBeTruthy();
    expect(screen.getByText(RightsStatus.OPEN)).toBeTruthy();
    expect(screen.getByText("Cypresses")).toBeTruthy();
    expect(screen.getByText("Score 0.250 = attributes 0.250")).toBeTruthy();
    expect(screen.getByText("nowhere: no model was called (retrieval only)")).toBeTruthy();
    expect(screen.getByText("cypresses")).toBeTruthy(); // the brief
  });

  it("with rationales, shows them, the models used and how many items were verified", async () => {
    const verified: BoardItem = {
      ...ITEM,
      rationale: "The record gives the artist as Vincent van Gogh. Its quiet mood suits the brief.",
      attribution_status: AttributionStatus.VERIFIED,
      flag_reasons: [],
    };
    const flagged: BoardItem = {
      ...ITEM,
      record: { ...ITEM.record, id: "met:2", title: "Cypresses" },
      flag_reasons: ["claim 1 (date): the judge found it unsupported"],
    };
    respond({
      body: view({
        items: [verified, flagged],
        sent_to: ["mock", "mock-judge"],
        models_used: { generator: "mock-1", judge: "mock-1" },
      }),
    });
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    expect(await screen.findByText(verified.rationale as string)).toBeTruthy();
    expect(screen.getByText("mock, mock-judge")).toBeTruthy();
    expect(screen.getByText("generator: mock-1, judge: mock-1")).toBeTruthy();
    expect(screen.getByText("Done: 2 items. 1 verified from the record, 1 need a human check.")).toBeTruthy();
    expect(screen.getByText("claim 1 (date): the judge found it unsupported")).toBeTruthy();
  });

  it("shows generate and verify progress", async () => {
    respond({ body: view({ state: "verify", items: [] }) });
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    expect(await screen.findByText("Checking every claim against its record…")).toBeTruthy();
  });

  it("never hides a stop reason or its detail", async () => {
    respond({
      body: view({
        state: "stopped",
        items: [],
        stop_reason: StopReason.SOURCE_UNAVAILABLE,
        stop_banner: STOP_REASON_BANNER.source_unavailable,
        stop_detail: "Retriever 'combined' could not load: No module named 'torch'.",
      }),
    });
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: STOP_REASON_BANNER.source_unavailable })).toBeTruthy();
    expect(screen.getByText("Retriever 'combined' could not load: No module named 'torch'.")).toBeTruthy();
    expect(screen.getByText("0 of 12 items accepted. Nothing was exported.")).toBeTruthy();
  });

  it("an unknown run says so", async () => {
    respond({ status: 404, body: { code: "unknown_run", message: "No run 'run-x'." } });
    render(<RunScreen runId="run-x" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toBe("No run 'run-x'.");
  });

  it("More like this hands over the run and the item", async () => {
    respond({ body: view() });
    const onMoreLikeThis = vi.fn();
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={onMoreLikeThis} />);
    await userEvent.click(await screen.findByRole("button", { name: "More like this" }));
    expect(onMoreLikeThis.mock.calls[0][1].record.id).toBe("met:436535");
  });
});

// S2 live meter and kill switch (issue 158): the meter tracks the polled spend against
// the cap, and Cancel asks before it stops the run, because a cancelled run can never be
// approved or exported (the API enforces that; the button only reflects it).
describe("S2 live meter and cancel", () => {
  it("the cost meter updates while the run works", async () => {
    respond(
      { body: view({ state: "generate", items: [], cost: { spent_usd: 0.012, cap_usd: 0.05, currency: "USD" } }) },
      { body: view({ state: "verify", items: [], cost: { spent_usd: 0.041, cap_usd: 0.05, currency: "USD" } }) },
    );
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    expect(await screen.findByText("USD 0.012 of 0.050 cap")).toBeTruthy();
    expect(await screen.findByText("USD 0.041 of 0.050 cap", {}, { timeout: 2000 })).toBeTruthy();
  });

  it("Cancel asks first, then posts the kill switch and shows the cancelled run", async () => {
    const fetchMock = respond(
      { body: view({ state: "generate", items: [] }) },
      { body: view({ state: "generate", items: [] }) }, // the POST /cancel response
      {
        body: view({
          state: "cancelled",
          items: [],
          stop_reason: StopReason.CANCELLED,
          stop_banner: STOP_REASON_BANNER.cancelled,
          stop_detail: "Cancelled by the operator.",
        }),
      },
    );
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel the run" }));
    expect(screen.getByRole("group", { name: "Confirm the kill switch" })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Yes, cancel the run" }));
    const call = await waitFor(() => {
      const posted = fetchMock.mock.calls.find(([url]) => url === "/runs/run-1/cancel");
      expect(posted).toBeTruthy();
      return posted;
    });
    expect(call?.[1]?.method).toBe("POST");
    expect(await screen.findByRole("heading", { name: STOP_REASON_BANNER.cancelled })).toBeTruthy();
    expect(screen.getByText("Cancelled by the operator.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel the run" })).toBeNull();
  });

  it("Keep the run going dismisses the confirm and posts nothing", async () => {
    const fetchMock = respond(
      { body: view({ state: "retrieve", items: [] }) },
      { body: view({ state: "generate", items: [] }) },
    );
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel the run" }));
    await userEvent.click(screen.getByRole("button", { name: "Keep the run going" }));
    expect(screen.queryByRole("group", { name: "Confirm the kill switch" })).toBeNull();
    expect(screen.getByRole("button", { name: "Cancel the run" })).toBeTruthy();
    const cancels = fetchMock.mock.calls.filter(([url]) => url === "/runs/run-1/cancel");
    expect(cancels).toEqual([]);
  });

  it("shows the API's refusal instead of pretending the run was cancelled", async () => {
    respond(
      { body: view({ state: "retrieve", items: [] }) },
      { status: 404, body: { code: "unknown_run", message: "No run 'run-1'." } },
    );
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel the run" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, cancel the run" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The run was not cancelled: No run 'run-1'.");
  });

  it("an ended run has no Cancel button", async () => {
    respond({ body: view() });
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} onMoreLikeThis={vi.fn()} />);
    await screen.findByRole("heading", { name: "Wheat Field with Cypresses" });
    expect(screen.queryByRole("button", { name: "Cancel the run" })).toBeNull();
  });
});

describe("S4 ItemDetail", () => {
  const detailed: BoardItem = {
    ...ITEM,
    record: {
      ...ITEM.record,
      credit_line: "Purchase, The Annenberg Foundation Gift, 1993",
      rights: {
        status: RightsStatus.OPEN,
        flag_field: "isPublicDomain",
        flag_value: true,
        source: "met",
        object_id: "436535",
        licence_string: null,
        checked_at: "2026-10-11T14:06:35Z",
      },
    },
    rationale: "The record gives the artist as Vincent van Gogh. Its quiet mood suits the brief.",
    attribution_status: AttributionStatus.VERIFIED,
    flag_reasons: [],
    tier_used: "mock",
    cost_usd: 0,
  };

  it("shows each section from the API, with missing values said to be missing", async () => {
    respond({ body: view({ items: [detailed] }) });
    render(<ItemDetail runId="run-1" itemId="met:436535" onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Wheat Field with Cypresses" })).toBeTruthy();
    for (const name of ["Why it fits", "Evidence from the record", "Rights record", "How this result was made"]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeTruthy();
    }
    expect(screen.getByText(detailed.rationale as string)).toBeTruthy();
    expect(screen.getByText(AttributionStatus.VERIFIED)).toBeTruthy();
    expect(screen.getByText("isPublicDomain")).toBeTruthy();
    expect(screen.getByText("Purchase, The Annenberg Foundation Gift, 1993")).toBeTruthy();
    expect(screen.getByText("None given by the source.")).toBeTruthy(); // licence string
    expect(screen.getByText("Not computed yet.")).toBeTruthy(); // confidence
    expect(screen.getByText("mock")).toBeTruthy(); // tier used
    expect(screen.getByText(NOT_LEGAL_ADVICE)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Full museum record" })).toBeTruthy();
  });

  it("an item the board does not have says so", async () => {
    respond({ body: view() });
    render(<ItemDetail runId="run-1" itemId="met:999" onBack={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toBe("This board has no item met:999.");
  });
});

describe("S8 This is wrong", () => {
  async function openForm() {
    await userEvent.click(await screen.findByRole("button", { name: "This is wrong" }));
  }

  it("files the report and shows the API's status", async () => {
    const fetchMock = respond({ body: view() }, { status: 202, body: { report_id: "report-1", status: "queued for review" } });
    render(<ItemDetail runId="run-1" itemId="met:436535" onBack={vi.fn()} />);
    await openForm();
    await userEvent.selectOptions(screen.getByLabelText("What is wrong"), "rights");
    await userEvent.type(screen.getByLabelText("What you found"), "The Met page says the image is restricted.");
    await userEvent.type(screen.getByLabelText("Your name (recorded with the report)"), "Joe");
    await userEvent.click(screen.getByRole("button", { name: "Send report" }));
    expect((await screen.findByText(/queued for review/)).textContent).toBe(
      "Report report-1: queued for review. The board is not changed.",
    );
    expect(fetchMock.mock.calls[1][0]).toBe("/reports");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      run_id: "run-1",
      item_id: "met:436535",
      error_type: "rights",
      note: "The Met page says the image is restricted.",
      reporter: "Joe",
    });
  });

  it("shows the API's refusal", async () => {
    respond({ body: view() }, { status: 400, body: { code: "unknown_item", message: "This board has no item 'met:436535'." } });
    render(<ItemDetail runId="run-1" itemId="met:436535" onBack={vi.fn()} />);
    await openForm();
    await userEvent.type(screen.getByLabelText("What you found"), "Wrong artist.");
    await userEvent.type(screen.getByLabelText("Your name (recorded with the report)"), "Joe");
    await userEvent.click(screen.getByRole("button", { name: "Send report" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This board has no item 'met:436535'.");
  });

  it("explains why it cannot send until the note and name are filled", async () => {
    const fetchMock = respond({ body: view() });
    render(<ItemDetail runId="run-1" itemId="met:436535" onBack={vi.fn()} />);
    await openForm();
    expect(screen.getByText("Say what you found and who you are.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Send report" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("S5 ReviewScreen", () => {
  const flaggedItem: BoardItem = { ...ITEM, flag_reasons: ["claim 2 (date): the judge found it unsupported"] };

  it("keeps Continue disabled with the reason until every flagged item is decided", async () => {
    respond({ body: view({ items: [flaggedItem] }) });
    render(<ReviewScreen runId="run-1" onBack={vi.fn()} onContinue={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Needs human check" })).toBeTruthy();
    expect(screen.getByText("claim 2 (date): the judge found it unsupported")).toBeTruthy();
    expect(screen.getByText("1 flagged item still needs a saved decision.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continue to approval" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("shows the API's refusal, then saves a decision and opens Continue", async () => {
    const decided = {
      ...flaggedItem,
      review: { decision: "drop" as const, decided_by: "Joe", decided_at: "2026-10-27T10:00:00Z" },
    };
    const fetchMock = respond(
      { body: view({ items: [flaggedItem] }) },
      { status: 422, body: { detail: [{ loc: ["body", "decisions", 0], msg: "Value error, keeping a flagged item requires a note (G3)" }] } },
      { body: view({ items: [decided] }) },
    );
    const onContinue = vi.fn();
    render(<ReviewScreen runId="run-1" onBack={vi.fn()} onContinue={onContinue} />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your name (recorded with each decision)"), "Joe");
    await user.click(screen.getByLabelText("Keep"));
    await user.click(screen.getByRole("button", { name: "Save decisions" }));
    expect((await screen.findByRole("alert")).textContent).toContain("requires a note");

    await user.click(screen.getByLabelText("Drop"));
    await user.click(screen.getByRole("button", { name: "Save decisions" }));
    expect(await screen.findByText("Saved: dropped by Joe")).toBeTruthy();
    const body = JSON.parse(fetchMock.mock.calls[2][1].body);
    expect(body).toEqual({ reviewer: "Joe", decisions: [{ item_id: "met:436535", decision: "drop", note: null }] });
    await user.click(screen.getByRole("button", { name: "Continue to approval" }));
    expect(onContinue).toHaveBeenCalled();
  });
});

describe("S6 ApproveScreen", () => {
  const verified: BoardItem = { ...ITEM, attribution_status: AttributionStatus.VERIFIED, flag_reasons: [] };
  const dropped: BoardItem = {
    ...ITEM,
    record: { ...ITEM.record, id: "met:2" },
    review: { decision: "drop", decided_by: "Joe", decided_at: "2026-10-27T10:00:00Z" },
  };
  const unverifiedRights: BoardItem = {
    ...verified,
    record: { ...ITEM.record, id: "met:3", rights: { status: RightsStatus.UNVERIFIED, flag_field: null } },
  };
  const readyGates = GATES.map((g) =>
    g.id === "G4" ? { ...g, state: "active" as const, status_text: "Ready for approval." } : g,
  );

  it("previews the pack with the API's rule: dropped and unreviewed unverified items are left out", () => {
    const preview = packPreview([verified, dropped, unverifiedRights]);
    expect(preview.included.map((i) => i.record.id)).toEqual(["met:436535"]);
    expect(preview.excludedUnverified).toBe(1);
    expect(preview.countsByStatus).toEqual({ [RightsStatus.OPEN]: 1 });
  });

  it("keeps approval closed, with the reason, until the API opens G4", async () => {
    respond({ body: view({ items: [ITEM] }) });
    render(<ApproveScreen runId="run-1" onBack={vi.fn()} />);
    const button = await screen.findByRole("button", { name: "Approve and export 0 items" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("Approval is not open yet: Waiting for review.")).toBeTruthy();
  });

  it("approves through the dialog, exports and shows the receipt", async () => {
    const receipt = {
      run_id: "run-1",
      file: "runs/exports/run-1.csv",
      exported_at: "2026-10-27T10:05:00Z",
      approver: "Joe",
      versions: { generator: "mock-1", judge: "mock-1", retriever: "jaccard", git: "abc123" },
      notice: "Exported. This board is now read-only",
      not_legal_advice: NOT_LEGAL_ADVICE,
    };
    const fetchMock = respond(
      { body: view({ items: [verified], gates: readyGates }) },
      { body: view({ items: [verified], approval: { approver: "Joe", acknowledged: true, approved_at: "t" } }) },
      { body: receipt },
      { body: view({ items: [verified], read_only: true, export: receipt }) },
    );
    render(<ApproveScreen runId="run-1" onBack={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Approve and export 1 item" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Approving as"), "Joe");
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "Approve and export" }));
    expect(await screen.findByText("runs/exports/run-1.csv")).toBeTruthy();
    expect(screen.getByText("Exported. This board is now read-only")).toBeTruthy();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ approver: "Joe", acknowledged: true });
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ format: "csv" });
  });
});
