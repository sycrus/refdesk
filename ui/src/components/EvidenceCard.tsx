// EvidenceCard (design/components/EvidenceCard.md). One reference: the artwork whole on a
// mat, why it fits, the record fields behind it, the two status badges, and the actions.
//
// Images: shown only when the source states the work is open with a structured flag
// (CLAUDE.md: images only for works whose rights status is Open). Every other status
// shows the metadata and a link to the museum record instead, as the spec requires for
// "Permission required". Missing fields stay empty: nothing is filled in.
import { useId } from "react";
import type { BoardItem } from "../api/types";
import { RightsStatus } from "../generated/wording";
import { Button } from "./Button";
import { safeUrl } from "./safeUrl";
import { StatusBadge } from "./StatusBadge";
import "./EvidenceCard.css";

export interface EvidenceCardProps {
  item: BoardItem;
  onMoreLikeThis?: () => void;
  onReport?: () => void;
  onKeepChange?: (keep: boolean) => void;
  detailsHref?: string; // S4 Item detail for this item
  onOpenDetails?: () => void; // in-app navigation; the link still works without it
}

export function showsImage(item: BoardItem): boolean {
  const { rights, image_url } = item.record;
  return Boolean(safeUrl(image_url)) && rights.status === RightsStatus.OPEN && Boolean(rights.flag_field);
}

export function EvidenceCard({
  item,
  onMoreLikeThis,
  onReport,
  onKeepChange,
  detailsHref,
  onOpenDetails,
}: EvidenceCardProps) {
  const { record } = item;
  const keepId = useId();
  const titleId = useId();
  const recordUrl = safeUrl(record.record_url);
  const alt = [record.title, record.artist].filter(Boolean).join(", ") || `Artwork ${record.id}`;
  return (
    <article className={`rd-card${item.selected ? " rd-card--selected" : ""}`} aria-labelledby={titleId}>
      <div className="rd-card-mat">
        {showsImage(item) ? (
          <img src={safeUrl(record.image_url)} alt={alt} loading="lazy" />
        ) : (
          <p className="rd-card-noimage">
            No image shown: the source does not state this work is open.{" "}
            {recordUrl && <a href={recordUrl}>View the museum record</a>}
          </p>
        )}
      </div>
      <h3 className="rd-card-title" id={titleId}>
        {record.title ?? record.id}
      </h3>
      {(record.artist || record.date) && (
        <p className="rd-card-meta">{[record.artist, record.date].filter(Boolean).join(", ")}</p>
      )}
      <section className="rd-card-why">
        <h4>Why it fits</h4>
        <p>{item.rationale ?? "No rationale yet."}</p>
        {item.evidence.length > 0 && (
          <ul className="rd-card-chips" aria-label="Evidence from the record">
            {item.evidence.map((ev) => {
              const href = safeUrl(ev.record_url) ?? recordUrl;
              return (
              <li key={`${ev.field}:${ev.value}`}>
                {href ? (
                  <a className="rd-chip" href={href}>
                    <span className="rd-chip-field">{ev.field}</span> {ev.value}
                  </a>
                ) : (
                  <span className="rd-chip">
                    <span className="rd-chip-field">{ev.field}</span> {ev.value}
                  </span>
                )}
              </li>
              );
            })}
          </ul>
        )}
      </section>
      {item.score != null && (
        <p className="rd-card-score">
          Score {item.score.toFixed(3)}
          {Object.keys(item.score_components ?? {}).length > 0 &&
            ` = ${Object.entries(item.score_components ?? {})
              .map(([name, value]) => `${name} ${value.toFixed(3)}`)
              .join(" + ")}`}
        </p>
      )}
      <div className="rd-card-badges">
        <StatusBadge kind="attribution" status={item.attribution_status} />
        <StatusBadge kind="rights" status={record.rights.status} inferred={!record.rights.flag_field} />
      </div>
      {item.flag_reasons.length > 0 && (
        <ul className="rd-card-flags" aria-label="Why this needs a human check">
          {item.flag_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <div className="rd-card-actions">
        {detailsHref && (
          <a
            className="rd-button rd-button--ghost rd-card-details"
            href={detailsHref}
            aria-label={`Details for ${record.title ?? record.id}`}
            onClick={(event) => {
              if (onOpenDetails) {
                event.preventDefault();
                onOpenDetails();
              }
            }}
          >
            Details
          </a>
        )}
        {onMoreLikeThis && (
          <Button variant="ghost" onClick={onMoreLikeThis}>
            More like this
          </Button>
        )}
        {onReport && (
          <Button variant="ghost" onClick={onReport}>
            Report
          </Button>
        )}
        {onKeepChange && (
          <label className="rd-card-keep" htmlFor={keepId}>
            <input
              id={keepId}
              type="checkbox"
              checked={item.selected}
              onChange={(event) => onKeepChange(event.target.checked)}
            />
            Keep
          </label>
        )}
      </div>
    </article>
  );
}
