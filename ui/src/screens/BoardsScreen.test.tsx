// S10 Boards and S9 Settings (issue 234).
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunSummary } from "../api/types";
import { MODE_MOCK_TAG } from "../generated/wording";
import { BoardsScreen } from "./BoardsScreen";
import { SettingsScreen } from "./SettingsScreen";

function row(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "run-b666b94144e2",
    created_at: "2026-11-09T06:00:00Z",
    brief: "[brief redacted]",
    state: "done",
    stop_reason: null,
    stop_banner: null,
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: false,
    sent_to: [],
    approver: null,
    read_only: false,
    name: "Board b666b9",
    stage: "shortlist",
    cover: [{ record_id: "met:1", image_url: "https://images.metmuseum.org/1.jpg", alt: "Work" }],
    saved_at: "2026-11-09T06:06:00Z",
    ...overrides,
  };
}

function api(rows: RunSummary[], rename?: (body: { name: string }) => unknown) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/runs") return new Response(JSON.stringify(rows), { status: 200 });
    if (url.endsWith("/name") && rename) return new Response(JSON.stringify(rename(JSON.parse(String(init?.body)))), { status: 200 });
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("S10 Boards", () => {
  it("shows each board's name, stage, stop reason and four cover tiles, and opens it at its stage", async () => {
    api([
      row(),
      row({ run_id: "run-2", name: "Lunar New Year", stage: "verify", stop_banner: "Stopped: budget cap reached", cover: [] }),
      row({ run_id: "run-3", name: "Exported one", stage: "exported", read_only: true }),
    ]);
    const onOpenBoard = vi.fn();
    render(<BoardsScreen onOpenBoard={onOpenBoard} />);
    const list = await screen.findByRole("list", { name: "Boards" });
    const cards = within(list).getAllByRole("listitem");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]).getByText("Draft · shortlisting")).toBeTruthy();
    expect(within(cards[1]).getByText("Draft · a kept work needs a check")).toBeTruthy();
    expect(cards[0].querySelectorAll(".rd-board-cover > *")).toHaveLength(4); // one image, three empty tiles
    expect(within(cards[1]).getByText("Stopped: budget cap reached")).toBeTruthy(); // never hidden
    expect(within(cards[2]).getByText("Exported · read-only")).toBeTruthy();
    expect(within(cards[2]).queryByRole("button", { name: /^Rename/ })).toBeNull();
    await userEvent.click(within(cards[1]).getByRole("link"));
    expect(onOpenBoard).toHaveBeenCalledWith("run-2", "verify");
  });

  it("never shows the brief", async () => {
    api([row()]);
    render(<BoardsScreen onOpenBoard={vi.fn()} />);
    await screen.findByText("Board b666b9");
    expect(document.body.textContent).not.toContain("[brief redacted]");
  });

  it("renames a board", async () => {
    const fetchMock = api([row()], (body) => ({ name: body.name }));
    render(<BoardsScreen onOpenBoard={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Rename Board b666b9" }));
    const input = screen.getByLabelText("New name");
    await userEvent.clear(input);
    await userEvent.type(input, "Mid-Autumn tin");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Mid-Autumn tin")).toBeTruthy();
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/name"));
    expect(JSON.parse(String(call![1]!.body))).toEqual({ name: "Mid-Autumn tin" });
  });

  it("tags a mock board's card, and leaves real boards untagged (issue 251)", async () => {
    api([
      row({ name: "Mock answers", mode: "mock" }),
      row({ run_id: "run-2", name: "Real answers", mode: "local" }),
    ]);
    render(<BoardsScreen onOpenBoard={vi.fn()} />);
    await screen.findByText("Mock answers");
    const mockCard = screen.getByText("Mock answers").closest("li") as HTMLElement;
    const realCard = screen.getByText("Real answers").closest("li") as HTMLElement;
    expect(within(mockCard).getByText(MODE_MOCK_TAG)).toBeTruthy();
    expect(within(realCard).queryByText(MODE_MOCK_TAG)).toBeNull();
  });
});

describe("S9 Settings", () => {
  it("stores the card style and the appearance in this browser", async () => {
    render(<SettingsScreen />);
    await userEvent.click(screen.getByRole("radio", { name: /^Full wording/ }));
    expect(localStorage.getItem("refdesk-card-style")).toBe("wording");
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    await userEvent.click(screen.getByRole("radio", { name: /^Compact marks/ }));
    expect(localStorage.getItem("refdesk-card-style")).toBeNull();
  });
});
