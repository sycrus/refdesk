// S5 Needs human check (PRD 8A, 8B gate G3; issue 100). Every flagged item, with the
// reasons it was flagged, gets keep (with a note) or drop. The API records who decided and
// when, refuses keep without a note, and keeps approval closed until every flagged item is
// decided; this screen only reflects that. Continue stays disabled, with the reason next to
// it, until the API says the review is complete.
import { useEffect, useId, useState } from "react";
import { ApiError, getRun, reviewRun } from "../api/client";
import type { BoardItem, RunView } from "../api/types";
import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { AttributionStatus } from "../generated/wording";
import "./screens.css";

type Choice = { decision?: "keep" | "drop"; note: string };

export interface ReviewScreenProps {
  runId: string;
  onBack: () => void;
  onContinue: () => void;
}

function isFlagged(item: BoardItem) {
  return item.attribution_status !== AttributionStatus.VERIFIED;
}

function ReviewItem({
  item,
  choice,
  onChange,
}: {
  item: BoardItem;
  choice: Choice;
  onChange: (choice: Choice) => void;
}) {
  const id = useId();
  const { record } = item;
  const title = record.title ?? record.id;
  return (
    <li className="rd-review-item">
      <fieldset>
        <legend>
          <span className="rd-review-title">{title}</span>
          {record.artist && <span className="rd-card-meta">, {record.artist}</span>}
        </legend>
        <div className="rd-card-badges">
          <StatusBadge kind="attribution" status={item.attribution_status} />
          <StatusBadge kind="rights" status={record.rights.status} inferred={!record.rights.flag_field} />
        </div>
        <ul className="rd-card-flags" aria-label={`Why ${title} needs a human check`}>
          {item.flag_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
        <div className="rd-review-choices">
          <label>
            <input
              type="radio"
              name={`${id}-decision`}
              checked={choice.decision === "keep"}
              onChange={() => onChange({ ...choice, decision: "keep" })}
            />
            Keep
          </label>
          <label>
            <input
              type="radio"
              name={`${id}-decision`}
              checked={choice.decision === "drop"}
              onChange={() => onChange({ ...choice, decision: "drop" })}
            />
            Drop
          </label>
        </div>
        <label htmlFor={`${id}-note`}>Note (required to keep)</label>
        <textarea
          id={`${id}-note`}
          value={choice.note}
          rows={2}
          onChange={(event) => onChange({ ...choice, note: event.target.value })}
        />
        {item.review && (
          <p className="rd-note">
            Saved: {item.review.decision === "keep" ? "kept" : "dropped"} by {item.review.decided_by}
          </p>
        )}
      </fieldset>
    </li>
  );
}

export function ReviewScreen({ runId, onBack, onContinue }: ReviewScreenProps) {
  const reviewerId = useId();
  const [run, setRun] = useState<RunView | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [reviewer, setReviewer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  function load(view: RunView) {
    setRun(view);
    const next: Record<string, Choice> = {};
    for (const item of view.items.filter(isFlagged)) {
      next[item.record.id] = { decision: item.review?.decision, note: item.review?.note ?? "" };
    }
    setChoices(next);
  }

  useEffect(() => {
    getRun(runId)
      .then(load)
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [runId]);

  if (!run) {
    return error ? (
      <p className="rd-error" role="alert">
        {error}
      </p>
    ) : (
      <p role="status">Loading the review…</p>
    );
  }

  const flagged = run.items.filter(isFlagged);
  const undecided = flagged.filter((item) => !item.review).length;
  const g3 = run.gates.find((gate) => gate.id === "G3");

  async function save() {
    setError(null);
    setSaved(null);
    const decisions = Object.entries(choices)
      .filter(([, c]) => c.decision)
      .map(([item_id, c]) => ({ item_id, decision: c.decision as "keep" | "drop", note: c.note || null }));
    try {
      const view = await reviewRun(runId, { reviewer, decisions });
      load(view);
      setSaved(`Saved ${decisions.length} ${decisions.length === 1 ? "decision" : "decisions"}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  return (
    <section className="rd-screen rd-detail" aria-labelledby="review-title">
      <a
        className="rd-back"
        href={`?run=${encodeURIComponent(runId)}`}
        onClick={(event) => {
          event.preventDefault();
          onBack();
        }}
      >
        Back to the board
      </a>
      <h1 id="review-title" className="rd-screen-title">
        Needs human check
      </h1>
      {g3 && <p role="status">{g3.status_text}</p>}
      {flagged.length === 0 ? (
        <p>No flagged items: nothing to review.</p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <label htmlFor={reviewerId}>Your name (recorded with each decision)</label>
          <input id={reviewerId} value={reviewer} onChange={(event) => setReviewer(event.target.value)} />
          <ul className="rd-review-list" aria-label="Flagged items">
            {flagged.map((item) => (
              <ReviewItem
                key={item.record.id}
                item={item}
                choice={choices[item.record.id] ?? { note: "" }}
                onChange={(choice) => setChoices({ ...choices, [item.record.id]: choice })}
              />
            ))}
          </ul>
          {error && (
            <p className="rd-error" role="alert">
              {error}
            </p>
          )}
          {saved && <p role="status">{saved}</p>}
          <Button type="submit" variant="secondary">
            Save decisions
          </Button>
        </form>
      )}
      <Button
        variant="primary"
        onClick={onContinue}
        disabledReason={
          undecided > 0
            ? `${undecided} flagged ${undecided === 1 ? "item still needs" : "items still need"} a saved decision.`
            : undefined
        }
      >
        Continue to approval
      </Button>
    </section>
  );
}
