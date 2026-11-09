// S1 New board, the landing page (PRD 8A, issue 230): one prompt, front and centre, with
// one action. The question, then the usage choice with its hint in one tray, then the
// brief. Keep-local and the cap stay visible inside the prompt; the other constraints sit
// in Options, closed by default, with a count of how many are set. Two example briefs and
// "Pick up where you left off" sit below. Validation is the API's job (BoardRequest): this
// form sends what was typed and shows the API's message if it refuses. Novelty is not
// offered: the API accepts it but does not apply it yet (M4).
//
// In the demo (ADR-025) the same page is shown, but the prompt cannot run: the button says
// why, and the recorded example boards follow (Joe, 2026-11-09).
import { type FormEvent, useEffect, useId, useState } from "react";
import { ApiError, createBoard, getRun, listRuns } from "../api/client";
import type { BoardRequest, Conditions, RunView, UsageMode } from "../api/types";
import { Button } from "../components/Button";
import { showsImage } from "../components/EvidenceCard";
import { safeUrl } from "../components/safeUrl";
import { LANDING_EXAMPLES } from "../content/landing";
import { type BoardStage, STAGE_LABEL } from "../content/boards";
import {
  LANDING_DEMO_REASON,
  LANDING_LEAD,
  LANDING_QUESTION,
  USAGE_INSPIRATION,
  USAGE_INSPIRATION_HINT,
  USAGE_PUBLISH,
  USAGE_PUBLISH_HINT,
  USAGE_QUESTION,
} from "../generated/wording";
import { useDemo } from "../demo";
import "./screens.css";

const CONDITION_FIELDS: { key: keyof Conditions; label: string; hint: string }[] = [
  { key: "period", label: "Period", hint: "e.g. 17th century" },
  { key: "material", label: "Material", hint: "e.g. oil" },
  { key: "motif", label: "Motif", hint: "e.g. ships" },
  { key: "department", label: "Department", hint: "e.g. paintings" },
];
const OPTION_NAMES = ["period", "material", "motif", "department", "avoid", "anchor_id"];
const DEFAULT_ITEMS = "12";

export function buildRequest(form: FormData): BoardRequest {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const conditions: Conditions = {};
  for (const { key } of CONDITION_FIELDS) {
    if (text(key)) conditions[key] = text(key);
  }
  return {
    brief: text("brief"),
    usage_mode: (text("usage_mode") || "reference_only") as UsageMode,
    conditions,
    avoid: text("avoid")
      .split(",")
      .map((term) => term.trim())
      .filter(Boolean),
    anchor_id: text("anchor_id") || null,
    keep_local: form.get("keep_local") === "on",
    budget_cap_usd: Number(text("budget_cap_usd") || "0.05"),
    target_items: Number(text("target_items") || DEFAULT_ITEMS),
  };
}

const firstWords = (brief: string) => brief.split(/\s+/).slice(0, 4).join(" ");

// The latest board that can still be worked on: not exported, not cancelled.
function useLatestDraft(enabled: boolean): RunView | null {
  const [draft, setDraft] = useState<RunView | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    listRuns()
      .then(async (runs) => {
        const latest = runs.find((run) => !run.read_only && run.state !== "cancelled");
        if (latest && !cancelled) setDraft(await getRun(latest.run_id));
      })
      .catch(() => undefined); // no draft row is fine; the page works without it
    return () => {
      cancelled = true;
    };
  }, [enabled]);
  return draft;
}

export interface NewBoardProps {
  onCreated: (runId: string) => void;
  onOpenRun?: (runId: string) => void;
  onAllBoards?: () => void;
  leftRunId?: string | null; // the board just left, to say where it was saved (issue 234)
}

// "Saved as a draft at <stage>": the name and stage come from the run list (GET /runs).
function useLeftNote(runId: string | null | undefined): string | null {
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    if (!runId) {
      setNote(null);
      return;
    }
    let cancelled = false;
    listRuns()
      .then((rows) => {
        const row = rows.find((r) => r.run_id === runId);
        if (!cancelled && row && !row.read_only && row.stage !== "cancelled") {
          setNote(`“${row.name}” is saved as a draft: ${STAGE_LABEL[row.stage as BoardStage] ?? row.stage}.`);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [runId]);
  return note;
}

export function NewBoard({ onCreated, onOpenRun, onAllBoards, leftRunId }: NewBoardProps) {
  const leftNote = useLeftNote(leftRunId);
  const demo = useDemo();
  const [brief, setBrief] = useState("");
  const [usage, setUsage] = useState<UsageMode>("reference_only");
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [optionsSet, setOptionsSet] = useState(0);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const draft = useLatestDraft(!demo && Boolean(onOpenRun));
  const optionsId = useId();
  const usageHintId = useId();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (demo || !brief.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      const created = await createBoard(buildRequest(new FormData(event.currentTarget)));
      onCreated(created.run_id);
    } catch (err) {
      setError(err instanceof ApiError ? `The API refused this board: ${err.message}` : `Could not reach the API: ${String(err)}`);
      setSending(false);
    }
  }

  function countOptions(form: HTMLFormElement) {
    const data = new FormData(form);
    const set = OPTION_NAMES.filter((name) => String(data.get(name) ?? "").trim()).length;
    const items = String(data.get("target_items") ?? "").trim();
    setOptionsSet(set + (items && items !== DEFAULT_ITEMS ? 1 : 0));
  }

  const reason = demo ? LANDING_DEMO_REASON : sending ? "Sending the brief…" : !brief.trim() ? "Type a brief first." : undefined;
  const kept = draft ? draft.items.filter((item) => item.selected) : [];
  const cover = draft ? (kept.find(showsImage) ?? draft.items.find(showsImage)) : undefined;

  return (
    <section className="rd-landing" aria-labelledby="landing-title">
      {leftNote && (
        <p className="rd-landing-left" role="status">
          {leftNote}{" "}
          {onAllBoards && (
            <a
              href="?boards=1"
              onClick={(event) => {
                event.preventDefault();
                onAllBoards();
              }}
            >
              Find it in Boards
            </a>
          )}
        </p>
      )}
      <h1 id="landing-title" className="rd-landing-title">
        {LANDING_QUESTION}
      </h1>
      <p className="rd-landing-lead">{LANDING_LEAD}</p>

      <form
        className="rd-landing-form"
        onSubmit={submit}
        onInput={(event) => countOptions(event.currentTarget)}
        aria-labelledby="landing-title"
      >
        <fieldset className="rd-usage" aria-describedby={usageHintId}>
          <legend className="rd-visually-hidden">{USAGE_QUESTION}</legend>
          <div className="rd-usage-switch">
            {(
              [
                ["reference_only", USAGE_INSPIRATION],
                ["reproduction", USAGE_PUBLISH],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="rd-usage-option">
                <input
                  type="radio"
                  name="usage_mode"
                  value={value}
                  checked={usage === value}
                  onChange={() => setUsage(value)}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <p id={usageHintId} className="rd-usage-hint" aria-live="polite">
            {usage === "reproduction" ? USAGE_PUBLISH_HINT : USAGE_INSPIRATION_HINT}
          </p>
        </fieldset>

        <div className="rd-prompt">
          <label className="rd-visually-hidden" htmlFor="landing-brief">
            Brief
          </label>
          <textarea
            id="landing-brief"
            name="brief"
            rows={2}
            value={brief}
            placeholder="e.g. Mid-Autumn tin, festive but not red and gold"
            onChange={(event) => setBrief(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />

          <div id={optionsId} className="rd-prompt-options" hidden={!optionsOpen}>
            {CONDITION_FIELDS.map(({ key, label, hint }) => (
              <label key={key} className="rd-prompt-field">
                <span>{label}</span>
                <input type="text" name={key} placeholder={hint} />
              </label>
            ))}
            <label className="rd-prompt-field rd-prompt-field--wide">
              <span>Avoid (words or record IDs)</span>
              <input type="text" name="avoid" placeholder="e.g. red, met:436535" />
            </label>
            <label className="rd-prompt-field">
              <span>More like this work</span>
              <input type="text" name="anchor_id" placeholder="Record ID" />
            </label>
            <label className="rd-prompt-field">
              <span>Works wanted</span>
              <input type="number" name="target_items" defaultValue={DEFAULT_ITEMS} min="1" max="50" />
            </label>
          </div>

          <div className="rd-prompt-row">
            <div className="rd-prompt-quiet">
              <label className="rd-prompt-check">
                <input type="checkbox" name="keep_local" /> Keep this brief on this machine
              </label>
              <label className="rd-prompt-cap">
                <span>Cap $</span>
                <input
                  type="number"
                  name="budget_cap_usd"
                  defaultValue="0.05"
                  min="0.01"
                  step="0.01"
                  aria-label="Spending cap (USD)"
                />
              </label>
              <button
                type="button"
                className="rd-prompt-more"
                aria-expanded={optionsOpen}
                aria-controls={optionsId}
                onClick={() => setOptionsOpen((open) => !open)}
              >
                Options
                {optionsSet > 0 && (
                  <span className="rd-prompt-count">
                    {optionsSet}
                    <span className="rd-visually-hidden"> set</span>
                  </span>
                )}
              </button>
            </div>
            <Button type="submit" variant="primary" disabledReason={reason} reasonHidden={!demo}>
              Find references
            </Button>
          </div>
        </div>
      </form>

      {error && (
        <p className="rd-error" role="alert">
          {error}
        </p>
      )}

      {!demo && !optionsOpen && (
        <p className="rd-landing-examples">
          <span className="rd-landing-label">Try an example</span>
          {LANDING_EXAMPLES.map((example) => (
            <button key={example} type="button" className="rd-landing-example" onClick={() => setBrief(example)}>
              {example}
            </button>
          ))}
        </p>
      )}

      {draft && onOpenRun && (
        <div className="rd-landing-resume">
          <span className="rd-landing-label">Pick up where you left off</span>
          <div className="rd-landing-resume-row">
            <a
              className="rd-landing-resume-card"
              href={`?run=${encodeURIComponent(draft.run_id)}`}
              onClick={(event) => {
                event.preventDefault();
                onOpenRun(draft.run_id);
              }}
            >
              {cover && <img src={safeUrl(cover.record.image_url)} alt="" />}
              <strong>{firstWords(draft.request?.brief ?? draft.run_id)}</strong>
              <span>{`${kept.length} kept`}</span>
              <span aria-hidden="true">→</span>
            </a>
            {onAllBoards && (
              <a
                className="rd-landing-all"
                href="?boards=1"
                onClick={(event) => {
                  event.preventDefault();
                  onAllBoards();
                }}
              >
                All boards
              </a>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
