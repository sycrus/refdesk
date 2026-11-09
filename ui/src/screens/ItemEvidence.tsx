// The evidence for one result (PRD 8A S4, issues 99 and 232): why it fits, the record
// fields behind it, its rights record and credit line as the source gives them, confidence
// and the tier used, and "Report an error". It used to be its own page; it is now the
// panel beside the image in the lightbox. Nothing inferred is shown as verified: the
// badges come from the API in their full fixed wording, a missing value says it is
// missing, and confidence is "not computed" until a model gives it.
import type { BoardItem, RunView } from "../api/types";
import { safeUrl } from "../components/safeUrl";
import { StatusBadge } from "../components/StatusBadge";
import { NOT_LEGAL_ADVICE } from "../generated/wording";
import { DEMO_REPORT_INSTEAD } from "../content/demo";
import { useDemo } from "../demo";
import { ReportForm } from "./ReportForm";
import "./screens.css";

function value(text: string | number | boolean | null | undefined, missing = "Not given by the source.") {
  return text === null || text === undefined || text === "" ? missing : String(text);
}

export function ItemEvidence({ run, item, titleId }: { run: RunView; item: BoardItem; titleId: string }) {
  const demo = useDemo(); // the demo API refuses reports
  const { record } = item;
  const rights = record.rights;
  const recordUrl = safeUrl(record.record_url);
  return (
    <div className="rd-evidence">
      <h2 id={titleId} className="rd-evidence-title">
        {record.title ?? record.id}
      </h2>
      <p className="rd-card-meta">{[record.artist, record.date].filter(Boolean).join(", ")}</p>
      <div className="rd-card-badges">
        <StatusBadge kind="attribution" status={item.attribution_status} />
        <StatusBadge kind="rights" status={rights.status} inferred={!rights.flag_field} />
      </div>

      <section aria-label="Why it fits">
        <h3>Why it fits</h3>
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

      <section aria-label="Evidence from the record">
        <h3>Evidence from the record</h3>
        {item.evidence.length > 0 ? (
          <ul className="rd-card-chips">
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

      <section aria-label="Rights record">
        <h3>Rights record</h3>
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

      <section aria-label="How this result was made">
        <h3>How this result was made</h3>
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

      <section aria-label="Report an error">
        <h3>Report an error</h3>
        {demo ? <p>{DEMO_REPORT_INSTEAD}</p> : <ReportForm runId={run.run_id} itemId={record.id} />}
      </section>
    </div>
  );
}
