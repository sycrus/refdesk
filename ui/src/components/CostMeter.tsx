// CostMeter (design/components/CostMeter.md). Spend against the cap, always as a number
// and the cap, with the state written in words as well as coloured: normal below 80% of
// the cap, warning from 80%, blocked at 100%. The consumer shows the stop reason in a
// StopBanner; raising the cap is never automatic.
import "./CostMeter.css";

export const WARN_AT = 0.8;

export type CostState = "normal" | "warning" | "blocked";

// Amounts are floats (0.04 / 0.05 is 0.7999...), so each threshold allows a tiny tolerance;
// without it, exactly 80% or 100% of the cap would read as the state below.
const EPSILON = 1e-9;

export function costState(spent: number, cap: number): CostState {
  if (!(cap > 0)) return "blocked";
  const ratio = spent / cap;
  if (ratio >= 1 - EPSILON) return "blocked";
  return ratio >= WARN_AT - EPSILON ? "warning" : "normal";
}

const NOTE: Record<CostState, string> = {
  normal: "Within the cap.",
  warning: "Near the cap: 80% or more spent.",
  blocked: "Cap reached. The run stops here; raising the cap is your decision.",
};

export interface CostMeterProps {
  spent: number;
  cap: number;
  currency?: string; // the API reports USD
}

const amount = (value: number) => value.toFixed(3);

export function CostMeter({ spent, cap, currency = "USD" }: CostMeterProps) {
  const state = costState(spent, cap);
  const text = `${currency} ${amount(spent)} of ${amount(cap)} cap`;
  const filled = cap > 0 ? Math.min(spent / cap, 1) : 1;
  return (
    <div className={`rd-cost rd-cost--${state}`}>
      <div className="rd-cost-value">{text}</div>
      <div
        className="rd-cost-track"
        role="progressbar"
        aria-label="Spend against the cap"
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-valuenow={Math.min(spent, cap)}
        aria-valuetext={`${text}. ${NOTE[state]}`}
      >
        <div className="rd-cost-fill" style={{ width: `${filled * 100}%` }} />
      </div>
      <div className="rd-cost-note">{NOTE[state]}</div>
    </div>
  );
}
