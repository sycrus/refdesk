// S2 Run progress and S3 Board review (PRD 8A) for retrieval-only runs. While the run is
// working, the screen polls GET /runs/{id} and shows the state in words; when it ends, it
// shows the board. Nothing the API reports is hidden: the stop banner and its detail,
// both badges on every card, the cost, and where the brief was sent.
import { useEffect, useState } from "react";
import { ApiError, getRun } from "../api/client";
import type { BoardItem, RunView } from "../api/types";
import { Button } from "../components/Button";
import { CostMeter } from "../components/CostMeter";
import { EvidenceCard } from "../components/EvidenceCard";
import { GateStepper } from "../components/GateStepper";
import { StopBanner } from "../components/StopBanner";
import { AttributionStatus } from "../generated/wording";
import "./screens.css";

export const POLL_MS = 500;
const ENDED = new Set(["done", "stopped", "cancelled"]);

const STATE_TEXT: Record<string, string> = {
  init: "Starting…",
  retrieve: "Searching the collection…",
  generate: "Writing a rationale for each item from its record…",
  verify: "Checking every claim against its record…",
  done: "Done.",
  stopped: "Stopped.",
  cancelled: "Cancelled.",
};

export interface RunScreenProps {
  runId: string;
  onNewBoard: () => void;
  onMoreLikeThis: (run: RunView, item: BoardItem) => void;
  onOpenItem?: (itemId: string) => void;
  onReview?: () => void;
  onApprove?: () => void;
}

export function RunScreen({
  runId,
  onNewBoard,
  onMoreLikeThis,
  onOpenItem,
  onReview,
  onApprove,
}: RunScreenProps) {
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setRun(null);
    setError(null);
    async function poll() {
      try {
        const view = await getRun(runId);
        if (cancelled) return;
        setRun(view);
        if (!ENDED.has(view.state)) timer = setTimeout(poll, POLL_MS);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : `Could not reach the API: ${String(err)}`);
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId]);

  if (error) {
    return (
      <section className="rd-screen">
        <p className="rd-error" role="alert">
          {error}
        </p>
        <Button onClick={onNewBoard}>New board</Button>
      </section>
    );
  }
  if (!run) return <p role="status">Loading the run…</p>;

  const request = run.request;
  const working = !ENDED.has(run.state);
  const sentTo = run.sent_to.length ? run.sent_to.join(", ") : "nowhere: no model was called (retrieval only)";
  const models = Object.entries(run.models_used ?? {});
  const verified = run.items.filter((item) => item.attribution_status === AttributionStatus.VERIFIED).length;
  const doneText =
    run.sent_to.length === 0
      ? "Every attribution needs a human check (no verifier ran)."
      : `${verified} verified from the record, ${run.items.length - verified} need a human check.`;

  return (
    <section className="rd-screen" aria-labelledby="board-title">
      <header className="rd-board-head">
        <h1 id="board-title" className="rd-screen-title">
          Board
        </h1>
        <dl className="rd-facts">
          {request && (
            <>
              <dt>Brief</dt>
              <dd>{request.brief}</dd>
              <dt>Mode</dt>
              <dd>{request.usage_mode === "reproduction" ? "Reproduction (open works only)" : "Reference only"}</dd>
            </>
          )}
          <dt>Stays on this machine</dt>
          <dd>{run.keep_local ? "Yes" : "No"}</dd>
          <dt>Brief sent to</dt>
          <dd>{sentTo}</dd>
          {models.length > 0 && (
            <>
              <dt>Models</dt>
              <dd>{models.map(([role, model]) => `${role}: ${model}`).join(", ")}</dd>
            </>
          )}
          <dt>Run</dt>
          <dd className="rd-mono">{run.run_id}</dd>
        </dl>
        <CostMeter spent={run.cost.spent_usd} cap={run.cost.cap_usd} currency={run.cost.currency} />
        <Button onClick={onNewBoard}>New board</Button>
      </header>

      <GateStepper gates={run.gates} />

      <p role="status" className="rd-run-state">
        {working
          ? STATE_TEXT[run.state] ?? `Working: ${run.state}`
          : run.state === "done"
            ? `Done: ${run.items.length} ${run.items.length === 1 ? "item" : "items"}. ${doneText}`
            : STATE_TEXT[run.state] ?? run.state}
      </p>

      {!working && onReview && run.items.some((i) => i.attribution_status !== AttributionStatus.VERIFIED) && (
        <Button variant="primary" onClick={onReview}>
          {`Review flagged items (${run.items.filter((i) => i.attribution_status !== AttributionStatus.VERIFIED).length})`}
        </Button>
      )}

      {onApprove && run.gates.some((g) => (g.id === "G4" || g.id === "G5") && g.state === "active") && (
        <Button variant="primary" onClick={onApprove}>
          Approve and export
        </Button>
      )}
      {run.read_only && run.export && (
        <p role="status">
          {run.export.notice}. <a href={`?run=${encodeURIComponent(run.run_id)}&approve=1`}>See the receipt</a>
        </p>
      )}

      {run.stop_reason && (
        <StopBanner
          reason={run.stop_reason}
          accepted={run.items.length}
          target={request?.target_items ?? run.items.length}
          detail={run.stop_detail}
          actions={<Button onClick={onNewBoard}>Change the brief</Button>}
        />
      )}

      {run.items.length > 0 && (
        <ul className="rd-board-grid" aria-label="References">
          {run.items.map((item) => (
            <li key={item.record.id}>
              <EvidenceCard
                item={item}
                onMoreLikeThis={() => onMoreLikeThis(run, item)}
                detailsHref={`?run=${encodeURIComponent(run.run_id)}&item=${encodeURIComponent(item.record.id)}`}
                onOpenDetails={onOpenItem ? () => onOpenItem(item.record.id) : undefined}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
