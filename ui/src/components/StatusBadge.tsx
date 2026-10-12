// StatusBadge (design/components/StatusBadge.md). Fixed wording from wording.py, always an
// icon plus a label. The safety rule lives here: anything not positively verified falls
// to the cautious label. An inferred status, or a value this UI does not recognise
// (untrusted JSON), is never shown as verified or open.
import { AttributionStatus, RightsStatus } from "../generated/wording";
import { Icon, type IconName } from "./Icon";
import "./StatusBadge.css";

type Tone = "ok" | "warn" | "danger";

export type StatusBadgeProps =
  | { kind: "attribution"; status: AttributionStatus | string; inferred?: boolean }
  | { kind: "rights"; status: RightsStatus | string; inferred?: boolean };

interface Resolved {
  label: string;
  tone: Tone;
  icon: IconName;
}

export function resolveStatus(props: StatusBadgeProps): Resolved {
  if (props.kind === "attribution") {
    if (props.status === AttributionStatus.VERIFIED && !props.inferred) {
      return { label: AttributionStatus.VERIFIED, tone: "ok", icon: "check" };
    }
    return { label: AttributionStatus.NEEDS_HUMAN_CHECK, tone: "warn", icon: "alert" };
  }
  if (props.status === RightsStatus.PERMISSION_REQUIRED) {
    return { label: RightsStatus.PERMISSION_REQUIRED, tone: "danger", icon: "lock" };
  }
  if (props.status === RightsStatus.OPEN && !props.inferred) {
    return { label: RightsStatus.OPEN, tone: "ok", icon: "check" };
  }
  return { label: RightsStatus.UNVERIFIED, tone: "warn", icon: "alert" };
}

export function StatusBadge(props: StatusBadgeProps) {
  const { label, tone, icon } = resolveStatus(props);
  return (
    <span className={`rd-badge rd-badge--${tone}`} data-kind={props.kind}>
      <Icon name={icon} />
      <span>{label}</span>
    </span>
  );
}
