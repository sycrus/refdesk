// S4 Item detail (PRD 8A, issue #99): why one result fits, the evidence behind it, its
// rights record and credit line as the source gives them, confidence and the tier used.
// Opened by a card's "Details" link (?run=<id>&item=<record id>), so a reload or a shared
// link reopens it. Nothing inferred is shown as verified: the badges come from the API, a
// missing value says it is missing, and confidence is "not computed" until a model gives it.
import { useEffect, useState } from "react";
import { ApiError, getRun } from "../api/client";
import type { BoardItem, RunView } from "../api/types";
import { safeUrl } from "../components/safeUrl";
import { StatusBadge } from "../components/StatusBadge";
import { showsImage } from "../components/EvidenceCard";
import { NOT_LEGAL_ADVICE } from "../generated/wording";
import { ReportForm } from "./ReportForm";
import "./screens.css";

export interface ItemDetailProps {
  runId: string;
  itemId: string;
  onBack: () => void;
}

function value(text: string | number | boolean | null | undefined, missing = "Not given by the source.") {
  return text === null || text === undefined || text === "" ? missing : String(text);
}

export function ItemDetail({ runId, itemId, onBack }: ItemDetailProps) {
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRun(runId)
      .then(setRun)
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [runId]);

  if (error) {
    return (
      <p className="rd-error" role="alert">
        {error}
      </p>
    );
  }
  if (!run) return <p role="status">Loading the item…</p>;
  const item: BoardItem | undefined = run.items.find((i) => i.record.id === itemId);
  const back = (
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
  );
  if (!item) {
    return (
      <section className="rd-screen">
        <p role="alert">This board has no item {itemId}.</p>
        {back}
      </section>
    );
  }

  const { record } = item;
  const rights = record.rights;
  const recordUrl = safeUrl(record.record_url);
  const alt = [record.title, record.artist].filter(Boolean).join(", ") || `Artwork ${record.id}`;

  return (
    <section className="rd-screen rd-detail" aria-labelledby="detail-title">
      {back}
      <h1 id="detail-title" className="rd-screen-title">
        {record.title ?? record.id}
      </h1>
      <p className="rd-card-meta">{[record.artist, record.date].filter(Boolean).join(", ")}</p>
      <div className="rd-card-badges">
        <StatusBadge kind="attribution" status={item.attribution_status} />
        <StatusBadge kind="rights" status={rights.status} inferred={!rights.flag_field} />
      </div>
      {showsImage(item) && (
        <div className="rd-card-mat">
          <img src={safeUrl(record.image_url)} alt={alt} />
        </div>
      )}

      <section aria-labelledby="why-title">
        <h2 id="why-title">Why it fits</h2>
        <p>{item.rationale ?? "No rationale: see the reasons below."}</p>
        {item.opinion_flag && <p className="rd-card-opinion-flag">{item.opinion_flag}</p>}
        {item.flag_reasons.length > 0 && (
          <ul className="rd-card-flags" aria-label="Why this needs a human check">
            {item.flag_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="evidence-title">
        <h2 id="evidence-title">Evidence from the record</h2>
        {item.evidence.length > 0 ? (
          <ul className="rd-card-chips" aria-label="Evidence from the record">
            {item.evidence.map((ev) => {
              const href = safeUrl(ev.record_url) ?? recordUrl;
              const chip = (
                <>
                  <span className="rd-chip-field">{ev.field}</span> {ev.value}
                </>
              );
              return (
                <li key={`${ev.field}:${ev.value}`}>
                  {href ? (
                    <a className="rd-chip" href={href}>
                      {chip}
                    </a>
                  ) : (
                    <span className="rd-chip">{chip}</span>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p>No record fields were matched.</p>
        )}
        {recordUrl && (
          <p>
            <a href={recordUrl}>Full museum record</a>
          </p>
        )}
      </section>

      <section aria-labelledby="rights-title">
        <h2 id="rights-title">Rights record</h2>
        <dl className="rd-facts">
          <dt>Status</dt>
          <dd>{rights.status}</dd>
          <dt>Source</dt>
          <dd>{value(rights.source ?? record.source)}</dd>
          <dt>Object ID</dt>
          <dd className="rd-mono">{value(rights.object_id)}</dd>
          <dt>Read from field</dt>
          <dd className="rd-mono">{value(rights.flag_field, "No structured field: not verified.")}</dd>
          <dt>Field value</dt>
          <dd className="rd-mono">{value(rights.flag_value)}</dd>
          <dt>Licence or notice</dt>
          <dd>{value(rights.licence_string, "None given by the source.")}</dd>
          <dt>Checked</dt>
          <dd>{value(rights.checked_at)}</dd>
          <dt>Credit line</dt>
          <dd>{value(record.credit_line)}</dd>
        </dl>
        <p className="rd-note">{NOT_LEGAL_ADVICE}</p>
      </section>

      <section aria-labelledby="how-title">
        <h2 id="how-title">How this result was made</h2>
        <dl className="rd-facts">
          <dt>Confidence</dt>
          <dd>{item.confidence ? `${item.confidence.bucket} (${item.confidence.value.toFixed(2)})` : "Not computed yet."}</dd>
          <dt>Tier used</dt>
          <dd>{value(item.tier_used, "None: no model was called (retrieval only).")}</dd>
          <dt>Cost</dt>
          <dd>USD {(item.cost_usd ?? 0).toFixed(3)}</dd>
          <dt>Score</dt>
          <dd>
            {item.score == null
              ? "Not scored."
              : `${item.score.toFixed(3)}${
                  Object.keys(item.score_components ?? {}).length
                    ? ` = ${Object.entries(item.score_components ?? {})
                        .map(([name, v]) => `${name} ${v.toFixed(3)}`)
                        .join(" + ")}`
                    : ""
                }`}
          </dd>
          <dt>Run</dt>
          <dd className="rd-mono">{run.run_id}</dd>
        </dl>
      </section>

      <section aria-labelledby="report-title">
        <h2 id="report-title">Report an error</h2>
        <ReportForm runId={run.run_id} itemId={record.id} />
      </section>
    </section>
  );
}
