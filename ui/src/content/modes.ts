// Run-mode lines (issue 251): how a board was made, and what a new board here would use.
// The sentences are fixed wording (generated/wording.ts, from src/refdesk/wording.py) —
// this module only fills their placeholders with the run's or the config's own facts.
// Missing facts give no line rather than an invented one: the template simply does not
// render, and no indicator is a wrong indicator never shown.
import type { Health, RunMode, RunSummary, RunView, TierInfo } from "../api/types";
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
  MODE_MOCK_TAG,
} from "../generated/wording";

// Substitute {name} placeholders. An unknown name stays visible, so a template/fact
// mismatch fails a test instead of silently rendering the wrong sentence.
export function fill(template: string, vars: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (placeholder) => {
    const value = vars[placeholder.slice(1, -1)];
    return value === undefined ? placeholder : value;
  });
}

// "Recorded 8 Nov 2026 …": the date is data, formatted; the words around it are fixed
// English wording, so the date is pinned to one format ("8 Nov 2026") rather than
// reflowing with each visitor's locale.
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const nameOf = (tier: TierInfo | null | undefined): string | null => tier?.model ?? null;

// The board indicator (the board's strip): how this board's brief was answered.
export function boardModeLine(run: RunView | RunSummary): string | null {
  const models = (run as RunView).models_used ?? {};
  const generator = models.generator;
  const judge = models.judge;
  switch (run.mode) {
    case "recorded": {
      if (!generator || !judge || !(run as RunView).created_at) return null;
      return fill(MODE_BOARD_RECORDED, {
        date: shortDate((run as RunView).created_at as string),
        generator,
        judge,
      });
    }
    case "mock":
      return MODE_BOARD_MOCK;
    case "local": {
      if (!generator) return null;
      return judge
        ? fill(MODE_BOARD_LOCAL, { generator, judge })
        : fill(MODE_BOARD_LOCAL_NO_JUDGE, { generator });
    }
    case "cloud": {
      const providers = (run as RunView).cloud_providers?.join(", ");
      if (!providers) return null;
      return judge ? fill(MODE_BOARD_CLOUD, { providers, judge }) : fill(MODE_BOARD_CLOUD_NO_JUDGE, { providers });
    }
    case "retrieval_only":
      return MODE_BOARD_RETRIEVAL_ONLY;
    default:
      return null; // mode unset: no indicator beats a wrong one
  }
}

// The app indicator (stage panel, under the wordmark): what a new board here would use.
export function appModeLine(health: Health): { text: string; mock: boolean; mode: RunMode } | null {
  const generator = health.generator;
  const judge = health.judge;
  let text: string;
  switch (health.mode) {
    case "recorded":
      text = MODE_APP_RECORDED;
      break;
    case "mock":
      text = MODE_APP_MOCK;
      break;
    case "local": {
      const generatorName = nameOf(generator);
      if (!generatorName) return null;
      const judgeName = nameOf(judge);
      text = judgeName
        ? fill(MODE_APP_LOCAL, { generator: generatorName, judge: judgeName })
        : fill(MODE_APP_LOCAL_NO_JUDGE, { generator: generatorName });
      break;
    }
    case "cloud": {
      const modelName = nameOf(generator);
      if (!modelName) return null;
      text = fill(MODE_APP_CLOUD, { model: modelName });
      break;
    }
    case "retrieval_only":
      text = MODE_APP_RETRIEVAL_ONLY;
      break;
    default:
      return null;
  }
  // Mock gets the warning tone in the panel as well as the words (never colour alone).
  return { text, mock: health.mode === "mock" || (generator?.mock ?? false), mode: health.mode };
}

// A mock board is tagged on its strip and its Boards card, so test answers are never
// mistaken for a real result (issue 251).
export function isMockBoard(run: RunView | RunSummary): boolean {
  return run.mode === "mock";
}

export const MOCK_TAG = MODE_MOCK_TAG;
