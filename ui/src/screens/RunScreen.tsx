// S2 Run progress and S3 Board review (PRD 8A) for retrieval-only runs. While the run is
// working, the screen polls GET /runs/{id} and shows the state in words, the live cost
// meter against the cap, and the kill switch: Cancel asks first, because a cancelled run
// can never be approved or exported. When the run ends, it shows the board. Nothing the
// API reports is hidden: the stop banner and its detail, both badges on every card, the
// cost, and where the brief was sent. Once the run ends, Keep on each card puts the work on
// the shortlist (issue 231): a work nobody kept is not kept, so review, approval and export
// cover kept works only. "Saved" is shown only after the API confirms the change.
import { useEffect, useId, useState } from "react";
import { ApiError, cancelRun, getRun, shortlistRun } from "../api/client";
import type { BoardItem, RunView } from "../api/types";
import { Button } from "../components/Button";
import { CostMeter } from "../components/CostMeter";
import { EvidenceCard } from "../components/EvidenceCard";
import { StopBanner } from "../components/StopBanner";
import { AttributionStatus, USAGE_INSPIRATION, USAGE_PUBLISH } from "../generated/wording";
import { DEMO_RUN_NOTE } from "../content/demo";
import { useDemo } from "../demo";
import { sentToText } from "./HistoryScreen";
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
  onMoreLikeThis?: (run: RunView, item: BoardItem) => void; // absent in the demo
  onOpenItem?: (itemId: string) => void;
  onReview?: () => void;
  onApprove?: () => void;
  onRun?: (run: RunView) => void; // the stage panel follows this run (issue 229)
}

export function RunScreen({
  runId,
  onNewBoard,
  onMoreLikeThis,
  onOpenItem,
  onReview,
  onApprove,
  onRun,
}: RunScreenProps) {
  const demo = useDemo(); // the demo cannot start boards: no "New board" here
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  useEffect(() => {
    if (run) onRun?.(run);
  }, [run, onRun]);
  const [operator, setOperator] = useState("");
  const [shortlistError, setShortlistError] = useState<string | null>(null);
  const operatorId = useId();

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
        {!demo && <Button onClick={onNewBoard}>New board</Button>}
      </section>
    );
  }
  if (!run) return <p role="status">Loading the run…</p>;

  const request = run.request;
  const working = !ENDED.has(run.state);
  async function doCancel() {
    try {
      setRun(await cancelRun(runId));
      setConfirmingCancel(false);
    } catch (err) {
      setCancelError(err instanceof ApiError ? err.message : `Could not reach the API: ${String(err)}`);
    }
  }
  async function keep(itemId: string, value: boolean) {
    setShortlistError(null);
    if (!operator.trim()) {
      setShortlistError("Enter your name first: it is recorded with what you keep.");
      return;
    }
    try {
      setRun(await shortlistRun(runId, { operator: operator.trim(), items: [{ item_id: itemId, keep: value }] }));
    } catch (err) {
      setShortlistError(`Not saved: ${err instanceof ApiError ? err.message : `could not reach the API: ${String(err)}`}`);
    }
  }
  const canShortlist = !demo && !working && !run.read_only && !run.approval && run.state !== "cancelled";
  const keptCount = run.items.filter((item) => item.selected).length;
  const keptFlagged = run.items.filter((i) => i.selected && i.attribution_status !== AttributionStatus.VERIFIED).length;
  const sentTo = sentToText(run.sent_to);
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
              <dt>Use</dt>
              <dd>{request.usage_mode === "reproduction" ? USAGE_PUBLISH : USAGE_INSPIRATION}</dd>
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
        {working && !confirmingCancel && (
          <Button variant="danger" onClick={() => { setCancelError(null); setConfirmingCancel(true); }}>
            Cancel the run
          </Button>
        )}
        {confirmingCancel && (
          <div className="rd-cancel" role="group" aria-label="Confirm the kill switch">
            <p>Cancel this run now? A cancelled run can never be approved or exported.</p>
            <span className="rd-cancel-actions">
              <Button
                variant="danger"
                onClick={() => {
                  void doCancel();
                }}
              >
                Yes, cancel the run
              </Button>
              <Button onClick={() => setConfirmingCancel(false)}>Keep the run going</Button>
            </span>
          </div>
        )}
        {cancelError && (
          <p role="alert">
            The run was not cancelled: {cancelError}
          </p>
        )}
        {!demo && <Button onClick={onNewBoard}>New board</Button>}
      </header>

      <p role="status" className="rd-run-state">
        {working
          ? STATE_TEXT[run.state] ?? `Working: ${run.state}`
          : run.state === "done"
            ? `Done: ${run.items.length} ${run.items.length === 1 ? "item" : "items"}. ${doneText}`
            : STATE_TEXT[run.state] ?? run.state}
      </p>

      {demo && !working && <p className="rd-demo-run-note">{DEMO_RUN_NOTE}</p>}

      {!working && onReview && keptFlagged > 0 && (
        <Button variant="primary" onClick={onReview}>
          {`Review flagged items (${keptFlagged})`}
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
          actions={demo ? undefined : <Button onClick={onNewBoard}>Change the brief</Button>}
        />
      )}

      {canShortlist && run.items.length > 0 && (
        <div className="rd-shortlist-bar">
          <label htmlFor={operatorId}>Your name (recorded with what you keep)</label>
          <input id={operatorId} value={operator} onChange={(event) => setOperator(event.target.value)} />
          <p role="status">
            {`${keptCount} of ${run.items.length} kept.`}
            {run.saved_at && ` Saved ${new Date(run.saved_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`}
          </p>
          {shortlistError && (
            <p className="rd-error" role="alert">
              {shortlistError}
            </p>
          )}
        </div>
      )}

      {run.items.length > 0 && (
        <ul className="rd-board-grid" aria-label="References">
          {run.items.map((item) => (
            <li key={item.record.id}>
              <EvidenceCard
                item={item}
                onMoreLikeThis={onMoreLikeThis ? () => onMoreLikeThis(run, item) : undefined}
                detailsHref={`?run=${encodeURIComponent(run.run_id)}&item=${encodeURIComponent(item.record.id)}`}
                onOpenDetails={onOpenItem ? () => onOpenItem(item.record.id) : undefined}
                onKeepChange={canShortlist ? (value) => keep(item.record.id, value) : undefined}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
