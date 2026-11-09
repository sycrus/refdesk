// The image-first board (issue 232): status marks, tiles, and the lightbox.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BoardItem, Gate, RunView } from "../api/types";
import { AttributionStatus, RightsStatus } from "../generated/wording";
import { RunScreen } from "../screens/RunScreen";
import { ImageTile } from "./ImageTile";
import { StatusMarks } from "./StatusMarks";

function item(id: string, overrides: Partial<BoardItem> = {}, rights: Partial<BoardItem["record"]["rights"]> = {}): BoardItem {
  return {
    record: {
      id,
      source: "met",
      title: `Work ${id}`,
      artist: "A painter",
      image_url: `https://images.metmuseum.org/${id}.jpg`,
      record_url: `https://www.metmuseum.org/art/collection/search/${id}`,
      rights: { status: RightsStatus.OPEN, flag_field: "isPublicDomain", ...rights },
    },
    rationale: `Why ${id} fits.`,
    evidence: [{ field: "title", value: `Work ${id}` }],
    attribution_status: AttributionStatus.VERIFIED,
    flag_reasons: [],
    selected: false,
    ...overrides,
  };
}

const GATES: Gate[] = (["G0", "G1", "G2", "G3", "G4", "G5"] as const).map((id) => ({
  id,
  state: "pending",
  status_text: `${id}.`,
}));

function view(items: BoardItem[], overrides: Partial<RunView> = {}): RunView {
  return {
    run_id: "run-1",
    request: { brief: "boats", target_items: 12 },
    state: "done",
    gates: GATES,
    items,
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: false,
    sent_to: ["mock"],
    read_only: false,
    ...overrides,
  };
}

function api(...bodies: unknown[]) {
  const fetchMock = vi.fn();
  for (const body of bodies) fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const VERIFIED_WORDS = AttributionStatus.VERIFIED;
const OPEN_WORDS = RightsStatus.OPEN;

describe("status on cards never says more than the record (ADR-026)", () => {
  const cases: [string, BoardItem][] = [
    ["needs a human check", item("a", { attribution_status: AttributionStatus.NEEDS_HUMAN_CHECK })],
    ["an unknown attribution value", item("b", { attribution_status: "verified-ish" as AttributionStatus })],
    ["unverified rights", item("c", {}, { status: RightsStatus.UNVERIFIED })],
    ["open rights with no structured field (inferred)", item("d", {}, { flag_field: null })],
    ["permission required", item("e", {}, { status: RightsStatus.PERMISSION_REQUIRED })],
  ];

  for (const [name, work] of cases) {
    for (const style of ["marks", "wording"] as const) {
      it(`${name}: no verified or open claim in the ${style} style`, () => {
        render(
          <ul>
            <ImageTile item={work} density="captions" cardStyle={style} onOpen={vi.fn()} />
          </ul>,
        );
        const text = document.body.innerHTML;
        const attributionVerified = work.attribution_status === AttributionStatus.VERIFIED;
        const rightsOpen = work.record.rights.status === RightsStatus.OPEN && Boolean(work.record.rights.flag_field);
        if (!attributionVerified) expect(text).not.toContain(VERIFIED_WORDS);
        if (!rightsOpen) expect(text).not.toContain(OPEN_WORDS);
      });
    }
  }

  it("marks are always both present, with the fixed wording as their names", () => {
    render(<StatusMarks item={item("f", { attribution_status: AttributionStatus.NEEDS_HUMAN_CHECK })} />);
    expect(screen.getByRole("img", { name: AttributionStatus.NEEDS_HUMAN_CHECK }).textContent).toContain("?");
    expect(screen.getByRole("img", { name: RightsStatus.OPEN })).toBeTruthy();
  });

  it("a permission-required work shows a lock and no image", () => {
    const work = item("g", {}, { status: RightsStatus.PERMISSION_REQUIRED });
    render(
      <ul>
        <ImageTile item={work} density="images" cardStyle="marks" onOpen={vi.fn()} />
      </ul>,
    );
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(/No image shown/)).toBeTruthy();
    expect(screen.getByRole("img", { name: RightsStatus.PERMISSION_REQUIRED })).toBeTruthy();
  });
});

describe("the board opens on Images; Full keeps the fixed wording", () => {
  it("shows tiles with marks first, then the detailed cards in Full", async () => {
    api(view([item("met:1")]));
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} />);
    const list = await screen.findByRole("list", { name: "References" });
    expect(within(list).getByRole("button", { name: "Open Work met:1" })).toBeTruthy();
    expect(within(list).getByRole("img", { name: VERIFIED_WORDS })).toBeTruthy(); // a mark
    await userEvent.click(screen.getByRole("radio", { name: "Full" }));
    expect(await screen.findByRole("heading", { name: "Work met:1" })).toBeTruthy();
    expect(screen.getByText(VERIFIED_WORDS)).toBeTruthy(); // the full badge
  });
});

describe("the lightbox (issue 232)", () => {
  const flagged = item("met:2", { attribution_status: AttributionStatus.NEEDS_HUMAN_CHECK, flag_reasons: ["claim 1"] });

  it("opens with the details, moves with the arrows and closes with Esc", async () => {
    api(view([item("met:1"), flagged]));
    const onOpenItem = vi.fn();
    const onCloseItem = vi.fn();
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} itemId="met:1" onOpenItem={onOpenItem} onCloseItem={onCloseItem} />);
    const dialog = await screen.findByRole("dialog", { name: "Work met:1" });
    expect(within(dialog).getByRole("complementary", { name: "Details" })).toBeTruthy();
    expect(within(dialog).getByText("Why met:1 fits.")).toBeTruthy();
    await userEvent.keyboard("{ArrowRight}");
    expect(onOpenItem).toHaveBeenCalledWith("met:2");
    await userEvent.keyboard("i");
    expect(within(dialog).queryByRole("complementary", { name: "Details" })).toBeNull();
    await userEvent.keyboard("{Escape}");
    expect(onCloseItem).toHaveBeenCalled();
  });

  it("K on a flagged work does not keep it without a note", async () => {
    const kept = view([{ ...flagged, selected: true }]);
    const reviewed = view([
      { ...flagged, selected: true, review: { decision: "keep", note: "Checked.", decided_by: "Joe", decided_at: "2026-11-09T00:00:00Z" } },
    ]);
    const fetchMock = api(view([flagged]), kept, reviewed);
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} itemId="met:2" onCloseItem={vi.fn()} />);
    await screen.findByRole("dialog", { name: "Work met:2" });
    await userEvent.keyboard("k");
    const form = screen.getByRole("form", { name: "Keep this work" });
    await userEvent.type(within(form).getByLabelText("Your name (recorded with what you keep)"), "Joe");
    await userEvent.click(within(form).getByRole("button", { name: "Keep with this note" }));
    expect(screen.getByRole("alert").textContent).toContain("needs a note");
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the first GET: nothing was kept

    await userEvent.type(within(form).getByLabelText(/^Note/), "Checked.");
    await userEvent.click(within(form).getByRole("button", { name: "Keep with this note" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1][0]).toBe("/runs/run-1/shortlist");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ operator: "Joe", items: [{ item_id: "met:2", keep: true }] });
    expect(fetchMock.mock.calls[2][0]).toBe("/runs/run-1/review");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      reviewer: "Joe",
      decisions: [{ item_id: "met:2", decision: "keep", note: "Checked." }],
    });
  });

  it("says when the board has no such work", async () => {
    api(view([item("met:1")]));
    render(<RunScreen runId="run-1" onNewBoard={vi.fn()} itemId="met:999" onCloseItem={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toBe("This board has no item met:999.");
  });
});
