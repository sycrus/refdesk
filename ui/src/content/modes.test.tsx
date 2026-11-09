// Run-mode lines (issue 251): every indicator sentence is the generated fixed wording,
// filled with the run's or the config's own facts. Missing facts give no line, never an
// invented one.
import { describe, expect, it } from "vitest";
import type { Health, RunSummary, RunView, TierInfo } from "../api/types";
import {
  MODE_APP_CLOUD,
  MODE_APP_LOCAL,
  MODE_APP_LOCAL_NO_JUDGE,
  MODE_APP_MOCK,
  MODE_APP_RECORDED,
  MODE_APP_RETRIEVAL_ONLY,
  MODE_BOARD_CLOUD,
  MODE_BOARD_CLOUD_NO_JUDGE,
  MODE_BOARD_LOCAL,
  MODE_BOARD_LOCAL_NO_JUDGE,
  MODE_BOARD_MOCK,
  MODE_BOARD_RECORDED,
  MODE_BOARD_RETRIEVAL_ONLY,
} from "../generated/wording";
import { appModeLine, boardModeLine, fill, isMockBoard, MOCK_TAG } from "./modes";

function run(overrides: Partial<RunView> = {}): RunView {
  return {
    run_id: "run-1",
    state: "done",
    gates: [],
    items: [],
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: true,
    sent_to: [],
    read_only: false,
    ...overrides,
  };
}

function summary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "run-1",
    created_at: "2026-11-09T06:00:00Z",
    brief: "[brief redacted]",
    state: "done",
    stop_reason: null,
    stop_banner: null,
    cost: { spent_usd: 0, cap_usd: 0.05, currency: "USD" },
    keep_local: false,
    sent_to: [],
    read_only: false,
    name: "Board b666b9",
    stage: "shortlist",
    cover: [],
    ...overrides,
  };
}

function tier(overrides: Partial<TierInfo> = {}): TierInfo {
  return { tier: "t", provider: "p", model: "m-1", cloud: false, mock: false, ...overrides };
}

describe("fill", () => {
  it("substitutes named placeholders and leaves unknown ones visible", () => {
    expect(fill("a {one} and a {two}", { one: "1" })).toBe("a 1 and a {two}");
  });
});

describe("boardModeLine", () => {
  it("is null when the API could not derive a mode", () => {
    expect(boardModeLine(run({ mode: null }))).toBeNull();
  });

  it("fills the recorded line with the date and both model names", () => {
    const line = boardModeLine(
      run({
        mode: "recorded",
        created_at: "2026-11-08T09:00:00Z",
        models_used: { generator: "qwen3.5:9b", judge: "phi4" },
      }),
    );
    expect(line).toBe(
      fill(MODE_BOARD_RECORDED, { date: "8 Nov 2026", generator: "qwen3.5:9b", judge: "phi4" }),
    );
    expect(line).toContain("nothing sent to a cloud service");
  });

  it("gives no recorded line when the run lacks a model name or a date", () => {
    expect(boardModeLine(run({ mode: "recorded", models_used: { generator: "q" } }))).toBeNull();
    expect(boardModeLine(run({ mode: "recorded", models_used: { generator: "q", judge: "p" } }))).toBeNull();
  });

  it("uses the mock wording verbatim", () => {
    expect(boardModeLine(run({ mode: "mock" }))).toBe(MODE_BOARD_MOCK);
  });

  it("fills the local line with both model names, and says when no judge checked", () => {
    expect(boardModeLine(run({ mode: "local", models_used: { generator: "q", judge: "p" } }))).toBe(
      fill(MODE_BOARD_LOCAL, { generator: "q", judge: "p" }),
    );
    expect(boardModeLine(run({ mode: "local", models_used: { generator: "q" } }))).toBe(
      fill(MODE_BOARD_LOCAL_NO_JUDGE, { generator: "q" }),
    );
    expect(boardModeLine(run({ mode: "local" }))).toBeNull();
  });

  it("fills the cloud line with the cloud providers, or none without them", () => {
    expect(
      boardModeLine(
        run({ mode: "cloud", cloud_providers: ["deepseek"], models_used: { judge: "phi4" } }),
      ),
    ).toBe(fill(MODE_BOARD_CLOUD, { providers: "deepseek", judge: "phi4" }));
    expect(boardModeLine(run({ mode: "cloud", cloud_providers: ["d"] }))).toBe(
      fill(MODE_BOARD_CLOUD_NO_JUDGE, { providers: "d" }),
    );
    expect(boardModeLine(run({ mode: "cloud" }))).toBeNull();
  });

  it("uses the retrieval-only wording verbatim", () => {
    expect(boardModeLine(run({ mode: "retrieval_only" }))).toBe(MODE_BOARD_RETRIEVAL_ONLY);
  });

  it("works for a run summary, which has no models or date (mock tag only needs the mode)", () => {
    expect(isMockBoard(summary({ mode: "mock" }))).toBe(true);
    expect(isMockBoard(summary({ mode: "local" }))).toBe(false);
    expect(MOCK_TAG).toBe("Mock");
  });
});

describe("appModeLine", () => {
  it("names the demo without a tier", () => {
    const line = appModeLine({ status: "ok", profile: "demo", mode: "recorded", generator: null, judge: null });
    expect(line).toEqual({ text: MODE_APP_RECORDED, mock: false, mode: "recorded" });
  });

  it("fills the local line with the configured model names", () => {
    const health: Health = {
      status: "ok",
      profile: "full",
      mode: "local",
      generator: tier({ tier: "local-small", provider: "ollama", model: "qwen3.5:9b" }),
      judge: tier({ tier: "judge-phi4", provider: "ollama-microsoft", model: "phi4" }),
    };
    expect(appModeLine(health)).toEqual({
      text: fill(MODE_APP_LOCAL, { generator: "qwen3.5:9b", judge: "phi4" }),
      mock: false,
      mode: "local",
    });
  });

  it("says when only a generator is configured, and fills the cloud line with its model", () => {
    const alone: Health = {
      status: "ok",
      profile: "full",
      mode: "local",
      generator: tier({ model: "q" }),
      judge: null,
    };
    expect(appModeLine(alone)?.text).toBe(fill(MODE_APP_LOCAL_NO_JUDGE, { generator: "q" }));
    const cloud: Health = {
      status: "ok",
      profile: "full",
      mode: "cloud",
      generator: tier({ model: "deepseek-flash", cloud: true }),
      judge: null,
    };
    expect(appModeLine(cloud)).toEqual({
      text: fill(MODE_APP_CLOUD, { model: "deepseek-flash" }),
      mock: false,
      mode: "cloud",
    });
  });

  it("uses the mock and retrieval-only wording verbatim, and flags mock for the warning tone", () => {
    const mock: Health = {
      status: "ok",
      profile: "full",
      mode: "mock",
      generator: tier({ tier: "mock", provider: "mock", mock: true }),
      judge: tier({ tier: "mock-judge", provider: "mock-judge", mock: true }),
    };
    expect(appModeLine(mock)?.text).toBe(MODE_APP_MOCK);
    expect(appModeLine(mock)?.mock).toBe(true);
    expect(
      appModeLine({ status: "ok", profile: "full", mode: "retrieval_only", generator: null, judge: null })?.text,
    ).toBe(MODE_APP_RETRIEVAL_ONLY);
  });

  it("is null when the mode is unset", () => {
    expect(appModeLine({ status: "ok", profile: "full", mode: null, generator: null, judge: null })).toBeNull();
  });
});
