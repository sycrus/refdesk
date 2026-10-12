// StopBanner (design/components/StopBanner.md). Says plainly why a run ended early and what
// the user can do next. The title is the fixed banner from wording.py; an unknown reason
// code is still shown ("Stopped: <code>"), never hidden. There is no dismiss control.
//
// Style: danger for blocks and declines (budget cap reached, request declined), warning
// for recoverable stops. tokens.json lists "cap reached" under danger.
import type { ReactNode } from "react";
import { STOP_REASON_BANNER, StopReason } from "../generated/wording";
import { Icon } from "./Icon";
import "./StopBanner.css";

const DANGER: ReadonlySet<string> = new Set([StopReason.BUDGET_CAP, StopReason.DECLINED]);

export interface StopBannerProps {
  reason: StopReason | string;
  accepted: number;
  target: number;
  exported?: boolean;
  detail?: string | null; // what exactly stopped the run (RunView.stop_detail); shown in full
  actions?: ReactNode; // Buttons: raise the cap, relax conditions, keep the partial board
}

export function stopTitle(reason: string): string {
  return (STOP_REASON_BANNER as Record<string, string>)[reason] ?? `Stopped: ${reason}`;
}

export function StopBanner({ reason, accepted, target, exported = false, detail, actions }: StopBannerProps) {
  const tone = DANGER.has(reason) ? "danger" : "warn";
  return (
    <section className={`rd-stop rd-stop--${tone}`} role="alert">
      <Icon name="alert" />
      <div className="rd-stop-body">
        <h2 className="rd-stop-title">{stopTitle(reason)}</h2>
        <p>
          {accepted} of {target} items accepted.{exported ? "" : " Nothing was exported."}
        </p>
        {detail && <p className="rd-stop-detail">{detail}</p>}
        {actions && <div className="rd-stop-actions">{actions}</div>}
      </div>
    </section>
  );
}
