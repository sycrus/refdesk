// S7 Run history and audit (PRD 8A, issue 159). Read-only: two views, no controls that
// change a run.
// - HistoryScreen (?history=1): every past run, newest first, from GET /runs. The brief is
//   redacted by the API; each row shows state, stop reason (fixed wording, never hidden),
//   cost, where the brief was sent and who approved.
// - RunAudit (?audit=<run id>): one run's events from the run log (GET /runs/{id}), in log
//   order, with versions. Model and adapter versions appear here only (PRD 8A).
// Without this screen the run log exists only as runs/<id>/events.jsonl on disk, so the
// operator cannot show where a brief went or why a run stopped.
import { useEffect, useState } from "react";
import { ApiError, getRun, listRuns } from "../api/client";
import type { Cost, RunEvent, RunSummary, RunView } from "../api/types";
import { AuditTimeline, type AuditEvent, type EventTone } from "../components/AuditTimeline";
import { stopTitle } from "../components/StopBanner";
import "./screens.css";

// The one wording for where a brief went, shared with S2/S3 (RunScreen).
export function sentToText(sentTo: string[]): string {
  return sentTo.length ? sentTo.join(", ") : "nowhere: no model was called (retrieval only)";
}

export function costText(cost: Cost): string {
  return `${cost.currency} ${cost.spent_usd.toFixed(4)} of ${cost.cap_usd.toFixed(3)} cap`;
}

const STATE_LABEL: Record<string, string> = {
  init: "Started",
  retrieve: "Retrieve",
  decide: "Decide",
  generate: "Generate",
  verify: "Verify",
  assemble: "Assemble",
  human_check: "Human check",
  export: "Export",
  done: "Done",
  stopped: "Stopped",
  cancelled: "Cancelled",
};

function stateLabel(state: string): string {
  return STATE_LABEL[state] ?? state;
}

function tone(event: RunEvent): EventTone {
  if (event.kind === "call") return "neutral";
  if (event.state === "done") return "ok";
  if (event.state === "stopped" || event.state === "cancelled") return "warn";
  return "neutral";
}

// A run-log line as the AuditTimeline shows it. Nothing is dropped that says why: the
// reason code and result are carried through as logged.
export function toAuditEvent(event: RunEvent): AuditEvent {
  const tokens =
    event.tokens_in != null || event.tokens_out != null ? (event.tokens_in ?? 0) + (event.tokens_out ?? 0) : undefined;
  const tool = event.tool ? (event.model ? `${event.tool} (${event.model})` : event.tool) : undefined;
  return {
    at: event.at,
    label: event.kind === "call" ? `Step ${event.step} call` : `Step ${event.step} ${stateLabel(event.state)}`,
    tone: tone(event),
    what: event.result ?? (event.kind === "call" ? `Called ${event.tool ?? "a tool"}.` : `Entered ${event.state}.`),
    tool,
    tokens,
    cost_usd: event.cost_usd ?? undefined,
    reason_code: event.reason_code ?? undefined,
  };
}

function message(err: unknown): string {
  return err instanceof ApiError ? err.message : `Could not reach the API: ${String(err)}`;
}

function link(href: string, text: string, onClick: () => void, label?: string) {
  return (
    <a
      href={href}
      aria-label={label}
      onClick={(event) => {
        event.preventDefault();
        onClick();
      }}
    >
      {text}
    </a>
  );
}

export interface HistoryScreenProps {
  onOpenAudit: (runId: string) => void;
}

export function HistoryScreen({ onOpenAudit }: HistoryScreenProps) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((err) => setError(message(err)));
  }, []);

  return (
    <section className="rd-screen" aria-labelledby="history-title">
      <h1 id="history-title" className="rd-screen-title">
        Run history
      </h1>
      <p className="rd-note">Read-only. Briefs are redacted here; open a run's events to see what it did.</p>
      {error ? (
        <p className="rd-error" role="alert">
          {error}
        </p>
      ) : !runs ? (
        <p role="status">Loading the run history…</p>
      ) : runs.length === 0 ? (
        <p>No runs yet.</p>
      ) : (
        // Focusable so a keyboard user can scroll the table sideways on a narrow screen.
        <div className="rd-table-wrap" role="region" aria-label="Past runs" tabIndex={0}>
          <table className="rd-table">
            <caption className="rd-visually-hidden">Past runs, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Started</th>
                <th scope="col">Brief</th>
                <th scope="col">State</th>
                <th scope="col">Stop reason</th>
                <th scope="col">Cost</th>
                <th scope="col">Brief sent to</th>
                <th scope="col">Approver</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <th scope="row" className="rd-mono">
                    {link(
                      `?audit=${encodeURIComponent(run.run_id)}`,
                      run.run_id,
                      () => onOpenAudit(run.run_id),
                      `Events for ${run.run_id}`,
                    )}
                  </th>
                  <td>
                    <time dateTime={run.created_at}>{run.created_at}</time>
                  </td>
                  <td>{run.brief}</td>
                  <td>
                    {stateLabel(run.state)}
                    {run.keep_local && <span className="rd-note"> · stays on this machine</span>}
                  </td>
                  <td>{run.stop_reason ? stopTitle(run.stop_reason) : "None"}</td>
                  <td className="rd-mono">{costText(run.cost)}</td>
                  <td>{sentToText(run.sent_to)}</td>
                  <td>{run.approver ?? "Not approved"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export interface RunAuditProps {
  runId: string;
  onBack: () => void;
  onOpenBoard: (runId: string) => void;
}

export function RunAudit({ runId, onBack, onOpenBoard }: RunAuditProps) {
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRun(null);
    setError(null);
    getRun(runId)
      .then(setRun)
      .catch((err) => setError(message(err)));
  }, [runId]);

  const back = <p className="rd-back">{link("?history=1", "Back to the run history", onBack)}</p>;
  if (error) {
    return (
      <section className="rd-screen">
        {back}
        <p className="rd-error" role="alert">
          {error}
        </p>
      </section>
    );
  }
  if (!run) return <p role="status">Loading the run log…</p>;

  const versions = { ...(run.models_used ?? {}), ...(run.export?.versions ?? {}) };
  return (
    <section className="rd-screen" aria-labelledby="audit-title">
      {back}
      <h1 id="audit-title" className="rd-screen-title">
        Run events: <span className="rd-mono">{run.run_id}</span>
      </h1>
      <dl className="rd-facts">
        <dt>State</dt>
        <dd>{stateLabel(run.state)}</dd>
        <dt>Stop reason</dt>
        <dd>
          {run.stop_reason ? stopTitle(run.stop_reason) : "None"}
          {run.stop_detail && <span className="rd-note"> · {run.stop_detail}</span>}
        </dd>
        <dt>Cost</dt>
        <dd className="rd-mono">{costText(run.cost)}</dd>
        <dt>Stays on this machine</dt>
        <dd>{run.keep_local ? "Yes" : "No"}</dd>
        <dt>Brief sent to</dt>
        <dd>{sentToText(run.sent_to)}</dd>
        <dt>Approver</dt>
        <dd>{run.approval ? `${run.approval.approver} at ${run.approval.approved_at}` : "Not approved"}</dd>
      </dl>
      <p>{link(`?run=${encodeURIComponent(run.run_id)}`, "Open the board", () => onOpenBoard(run.run_id))}</p>
      <h2 className="rd-section-title">Run log</h2>
      <AuditTimeline events={(run.events ?? []).map(toAuditEvent)} versions={versions} />
    </section>
  );
}
