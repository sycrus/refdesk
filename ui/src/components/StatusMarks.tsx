// StatusMarks (ADR-026): the compact form of the two status badges, for Shortlist cards.
// Both marks are always present. The shape and symbol carry the state (✓ in a circle for
// verified or open, ? in a diamond for needs a check or unverified, a lock in a square for
// permission required), the word says which status it is, and the fixed wording is the
// accessible name and the tooltip. The state comes from resolveStatus, the same function
// the full badge uses, so a mark can never say more than the badge would.
import type { BoardItem } from "../api/types";
import { Icon } from "./Icon";
import { resolveStatus } from "./StatusBadge";
import "./StatusMarks.css";

function Mark({ word, label, tone }: { word: string; label: string; tone: "ok" | "warn" | "danger" }) {
  return (
    <span className={`rd-mark rd-mark--${tone}`} role="img" aria-label={label} title={label}>
      <span className="rd-mark-symbol" aria-hidden="true">
        {tone === "ok" ? <Icon name="check" /> : tone === "danger" ? <Icon name="lock" /> : "?"}
      </span>
      <span aria-hidden="true">{word}</span>
    </span>
  );
}

export function StatusMarks({ item }: { item: BoardItem }) {
  const attribution = resolveStatus({ kind: "attribution", status: item.attribution_status });
  const rights = resolveStatus({
    kind: "rights",
    status: item.record.rights.status,
    inferred: !item.record.rights.flag_field,
  });
  return (
    <span className="rd-marks">
      <Mark word="Attribution" label={attribution.label} tone={attribution.tone} />
      <Mark word="Rights" label={rights.label} tone={rights.tone} />
    </span>
  );
}
