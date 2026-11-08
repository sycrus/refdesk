// The public demo's front page and read-only screens (ADR-025). The API refuses every
// write in the demo profile; the UI only stops offering what would be refused.
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { BoardItem, RunView } from "../api/types";
import { AttributionStatus, RightsStatus, USAGE_INSPIRATION, USAGE_PUBLISH } from "../generated/wording";
import { DEMO_BANNER, DEMO_RUN_NOTE } from "../content/demo";
import { DemoHome } from "./DemoHome";

function item(id: string, status: AttributionStatus = AttributionStatus.VERIFIED, open = true): BoardItem {
  return {
    record: {
      id,
      source: "met",
      title: `Work ${id}`,
      artist: "A painter",
      date: "1850",
      image_url: `https://images.metmuseum.org/${id}.jpg`,
      record_url: `https://www.metmuseum.org/art/collection/search/${id}`,
      rights: open
        ? { status: RightsStatus.OPEN, flag_field: "isPublicDomain" }
        : { status: RightsStatus.PERMISSION_REQUIRED, flag_field: "isPublicDomain" },
    },
    rationale: "Why it fits.",
    evidence: [{ field: "title", value: `Work ${id}` }],
    attribution_status: status,
    flag_reasons: status === AttributionStatus.VERIFIED ? [] : ["claim 1 (artist): differs"],
    selected: false,
  };
}

function run(id: string, brief: string, items: BoardItem[], usage: "reference_only" | "reproduction"): RunView {
  return {
    run_id: id,
    request: { brief, usage_mode: usage, target_items: 12 },
    state: "done",
    gates: [{ id: "G4", state: "pending", status_text: "Waiting for review.", actor: "approver" }],
    items,
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: true,
    sent_to: ["ollama", "ollama-microsoft"],
    models_used: { generator: "qwen3.5:9b", judge: "phi4" },
    read_only: false,
  };
}

const BOATS = run(
  "run-boats",
  "Boats at night for a whisky label",
  [item("met:1"), item("met:2", AttributionStatus.NEEDS_HUMAN_CHECK), item("met:3", AttributionStatus.VERIFIED, false)],
  "reference_only",
);
const SHEEP = run("run-sheep", "Sheep and shepherds for packaging", [item("met:4")], "reproduction");

function api(profile: "demo" | "full") {
  const runs: Record<string, RunView> = { "run-boats": BOATS, "run-sheep": SHEEP };
  const fetchMock = vi.fn(async (url: string) => {
    const path = String(url);
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    if (path === "/healthz") return json({ status: "ok", profile });
    if (path === "/runs") return json(Object.keys(runs).map((run_id) => ({ run_id })));
    const match = path.match(/^\/runs\/([^/?]+)$/);
    if (match && runs[match[1]]) return json(runs[match[1]]);
    return json({ code: "unknown", message: path }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  window.history.pushState(null, "", "/");
  vi.unstubAllGlobals();
});

describe("DemoHome", () => {
  it("shows each recorded board with its brief, use, counts and an open link", async () => {
    api("demo");
    render(<DemoHome onOpenRun={vi.fn()} />);
    const boats = await screen.findByRole("article", { name: "Boats at night for a whisky label" });
    expect(boats.textContent).toContain(USAGE_INSPIRATION);
    expect(boats.textContent).toContain("3 works");
    expect(boats.textContent).toContain("1 needs a human check");
    expect(within(boats).getByRole("link", { name: /Open board/ }).getAttribute("href")).toBe("?run=run-boats");
    const sheep = screen.getByRole("article", { name: "Sheep and shepherds for packaging" });
    expect(sheep.textContent).toContain(USAGE_PUBLISH);
  });

  it("shows thumbnails only for open works, never cropped from a work that needs permission", async () => {
    api("demo");
    render(<DemoHome onOpenRun={vi.fn()} />);
    const boats = await screen.findByRole("article", { name: "Boats at night for a whisky label" });
    const sources = within(boats)
      .getAllByRole("img")
      .map((img) => img.getAttribute("src"));
    expect(sources).toEqual(["https://images.metmuseum.org/met:1.jpg", "https://images.metmuseum.org/met:2.jpg"]);
  });

  it("explains what to look for and how the boards were made", async () => {
    api("demo");
    render(<DemoHome onOpenRun={vi.fn()} />);
    await screen.findByRole("article", { name: "Boats at night for a whisky label" });
    const text = document.body.textContent ?? "";
    expect(text).toContain(AttributionStatus.NEEDS_HUMAN_CHECK);
    expect(text).toMatch(/written for testing/);
    expect(text).toMatch(/qwen3\.5:9b/);
    expect(text).toMatch(/phi4/);
  });
});

describe("App in the demo profile", () => {
  it("opens on the example boards with the banner, and offers no new board", async () => {
    api("demo");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1 })).toBeDefined();
    await screen.findByRole("article", { name: "Boats at night for a whisky label" });
    expect(screen.getByRole("note").textContent).toContain(DEMO_BANNER);
    const nav = screen.getByRole("navigation", { name: "refdesk" });
    expect(within(nav).queryByRole("link", { name: "New board" })).toBeNull();
    expect(within(nav).getByRole("link", { name: "Example boards" })).toBeDefined();
  });

  it("shows a board without the actions the demo refuses", async () => {
    api("demo");
    window.history.pushState(null, "", "?run=run-boats");
    render(<App />);
    await screen.findByRole("list", { name: "References" });
    expect(screen.getByRole("note").textContent).toContain(DEMO_BANNER);
    expect(screen.queryByRole("button", { name: /More like this/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Review flagged items/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "New board" })).toBeNull();
    expect(document.body.textContent).toContain(DEMO_RUN_NOTE);
  });

  it("shows an item without the report form, and says where to report instead", async () => {
    api("demo");
    window.history.pushState(null, "", "?run=run-boats&item=met:2");
    render(<App />);
    await screen.findByRole("heading", { name: "Work met:2" });
    expect(screen.queryByRole("button", { name: /This is wrong/ })).toBeNull();
    expect(document.body.textContent).toMatch(/github\.com\/sycrus\/refdesk\/issues/);
  });
});

describe("App in the full profile", () => {
  it("opens on New board with no demo banner", async () => {
    const fetchMock = api("full");
    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/healthz"));
    expect(await screen.findByRole("button", { name: "Find references" })).toBeDefined();
    expect(screen.queryByRole("note")).toBeNull();
  });
});
