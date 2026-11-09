// The earlier stages of a board, read-only (PRD 8A, issue 229). You can go back to them
// until export (PRD 8B rule 5), but what they record does not change:
// - BriefStage (?run=<id>&stage=brief): what was asked. The brief is fixed once the
//   search has run, so the board always matches it; a new board can start from it.
// - SearchStage (?run=<id>&stage=search): what the search did and spent, the stop reason
//   (never hidden), the run's events, and the one action this stage allows: raising the
//   cap, an explicit decision recorded with a name and time (G1).
import { useEffect, useId, useState } from "react";
import { ApiError, createBoard, getRun, raiseCap } from "../api/client";
import type { RunView } from "../api/types";
import { AuditTimeline } from "../components/AuditTimeline";
import { Button } from "../components/Button";
import { CostMeter } from "../components/CostMeter";
import { StopBanner } from "../components/StopBanner";
import { AttributionStatus, USAGE_INSPIRATION, USAGE_PUBLISH } from "../generated/wording";
import { useDemo } from "../demo";
import { sentToText, toAuditEvent } from "./HistoryScreen";
import "./screens.css";

function useRunView(runId: string): [RunView | null, string | null, (run: RunView) => void] {
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    getRun(runId)
      .then((view) => {
        if (!cancelled) setRun(view);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : `Could not reach the API: ${String(err)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);
  return [run, error, setRun];
}

function gateText(run: RunView, id: string): string {
  return run.gates.find((g) => g.id === id)?.status_text ?? "Not reported";
}

export function BriefStage({ runId, onOpenRun }: { runId: string; onOpenRun: (runId: string) => void }) {
  const demo = useDemo();
  const [run, error] = useRunView(runId);
  const [startError, setStartError] = useState<string | null>(null);
  if (error)
    return (
      <p className="rd-error" role="alert">
        {error}
      </p>
    );
  if (!run) return <p role="status">Loading the brief…</p>;
  const request = run.request;
  const conditions = Object.entries(request?.conditions ?? {}).filter(([, value]) => value);
  const avoid = request?.avoid ?? [];

  async function again() {
    if (!request) return;
    setStartError(null);
    try {
      onOpenRun((await createBoard(request)).run_id);
    } catch (err) {
      setStartError(`The new board was not started: ${err instanceof ApiError ? err.message : String(err)}`);
    }
  }

  return (
    <section className="rd-screen rd-detail" aria-labelledby="brief-title">
      <h1 id="brief-title" className="rd-screen-title">
        Brief
      </h1>
      {!request ? (
        <p>This run has no stored request.</p>
      ) : (
        <>
          <p className="rd-stage-brief">{request.brief}</p>
          <dl className="rd-facts">
            <dt>Use</dt>
            <dd>{request.usage_mode === "reproduction" ? USAGE_PUBLISH : USAGE_INSPIRATION}</dd>
            <dt>Stays on this machine</dt>
            <dd>{run.keep_local ? "Yes" : "No"}</dd>
            <dt>Spending cap</dt>
            <dd>USD {(request.budget_cap_usd ?? run.cost.cap_usd).toFixed(3)}</dd>
            <dt>Works wanted</dt>
            <dd>{request.target_items ?? "Not set"}</dd>
            {conditions.flatMap(([key, value]) => [
              <dt key={`${key}-t`}>{key[0].toUpperCase() + key.slice(1)}</dt>,
              <dd key={`${key}-d`}>{value}</dd>,
            ])}
            {avoid.length > 0 && (
              <>
                <dt>Avoid</dt>
                <dd>{avoid.join(", ")}</dd>
              </>
            )}
            {request.anchor_id && (
              <>
                <dt>More like this work</dt>
                <dd className="rd-mono">{request.anchor_id}</dd>
              </>
            )}
            <dt>Intake check (G0)</dt>
            <dd>{gateText(run, "G0")}</dd>
          </dl>
          <p className="rd-note">
            The brief is fixed once the search has run, so the board always matches what was asked. To change it, start a
            new board.
          </p>
          {!demo && (
            <div>
              <Button onClick={() => void again()}>New board from this brief</Button>
            </div>
          )}
          {startError && (
            <p className="rd-error" role="alert">
              {startError}
            </p>
          )}
        </>
      )}
    </section>
  );
}

export function SearchStage({ runId, onResumed }: { runId: string; onResumed: (runId: string) => void }) {
  const demo = useDemo();
  const [run, error, setRun] = useRunView(runId);
  const [newCap, setNewCap] = useState("");
  const [name, setName] = useState("");
  const [capError, setCapError] = useState<string | null>(null);
  const capId = useId();
  const nameId = useId();
  if (error)
    return (
      <p className="rd-error" role="alert">
        {error}
      </p>
    );
  if (!run) return <p role="status">Loading the search…</p>;
  const current = run;
  const verified = current.items.filter((i) => i.attribution_status === AttributionStatus.VERIFIED).length;
  const target = current.request?.target_items ?? current.items.length;
  const canRaise = !demo && current.stop_reason === "budget_cap" && !current.read_only && !current.approval;

  async function raise() {
    setCapError(null);
    const value = Number(newCap);
    if (!name.trim() || !(value > current.cost.cap_usd)) {
      setCapError(`Enter your name and a cap above USD ${current.cost.cap_usd.toFixed(3)}.`);
      return;
    }
    try {
      setRun(await raiseCap(runId, { new_cap_usd: value, raised_by: name.trim() }));
      onResumed(runId);
    } catch (err) {
      setCapError(`The cap was not raised: ${err instanceof ApiError ? err.message : String(err)}`);
    }
  }

  return (
    <section className="rd-screen rd-detail" aria-labelledby="search-title">
      <h1 id="search-title" className="rd-screen-title">
        Search and check
      </h1>
      <CostMeter spent={current.cost.spent_usd} cap={current.cost.cap_usd} currency={current.cost.currency} />
      <dl className="rd-facts">
        <dt>On the board</dt>
        <dd>{`${current.items.length} of ${target} wanted`}</dd>
        <dt>Verified from the record</dt>
        <dd>{verified}</dd>
        <dt>Need a human check</dt>
        <dd>{current.items.length - verified}</dd>
        <dt>Spend (G1)</dt>
        <dd>{gateText(current, "G1")}</dd>
        <dt>Verify (G2)</dt>
        <dd>{gateText(current, "G2")}</dd>
        <dt>Brief sent to</dt>
        <dd>{sentToText(current.sent_to)}</dd>
        <dt>Exported</dt>
        <dd>{current.read_only ? "Yes" : "Nothing was exported"}</dd>
      </dl>
      {current.stop_reason && (
        <StopBanner reason={current.stop_reason} accepted={current.items.length} target={target} detail={current.stop_detail} />
      )}
      {canRaise && (
        <form
          className="rd-cap-raise"
          aria-label="Raise the cap"
          onSubmit={(event) => {
            event.preventDefault();
            void raise();
          }}
        >
          <p className="rd-note">
            Raising the cap is recorded with your name and the time. The search resumes where it stopped and adds to this
            board.
          </p>
          <label className="rd-field" htmlFor={capId}>
            <span>New cap (USD)</span>
            <input id={capId} inputMode="decimal" value={newCap} onChange={(event) => setNewCap(event.target.value)} />
          </label>
          <label className="rd-field" htmlFor={nameId}>
            <span>Your name</span>
            <input id={nameId} value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <div>
            <Button type="submit">Raise the cap and continue</Button>
          </div>
          {capError && (
            <p className="rd-error" role="alert">
              {capError}
            </p>
          )}
        </form>
      )}
      <h2 className="rd-stage-heading">What the run did</h2>
      <AuditTimeline events={(current.events ?? []).map(toAuditEvent)} versions={{}} />
    </section>
  );
}
