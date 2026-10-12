// GateStepper (design/components/GateStepper.md). All six gates, always, in order, each with
// its state in words as well as in the node. The UI never decides a gate has passed: the
// state comes from the API (which enforces the gates, PRD 8B). A gate missing from the run
// record, or with a state this UI does not recognise, is shown as pending.
import type { Gate, GateId, GateState } from "../api/types";
import { Icon, type IconName } from "./Icon";
import "./GateStepper.css";

interface GateSpec {
  id: GateId;
  label: string;
  human: boolean;
}

export const GATES: readonly GateSpec[] = [
  { id: "G0", label: "Intake", human: false },
  { id: "G1", label: "Spend", human: false },
  { id: "G2", label: "Verify", human: false },
  { id: "G3", label: "Review", human: true },
  { id: "G4", label: "Approve", human: true },
  { id: "G5", label: "Export", human: true },
];

const STATE_WORD: Record<GateState, string> = {
  passed: "Passed",
  active: "Active",
  pending: "Pending",
  blocked: "Blocked",
  skipped: "Skipped",
};

const STATE_ICON: Record<GateState, IconName> = {
  passed: "check",
  active: "arrow",
  pending: "circle",
  blocked: "alert",
  skipped: "dash",
};

export interface GateStepperProps {
  gates: Gate[];
  onSelect?: (id: GateId) => void; // scroll to the surface that handles the gate
}

function known(state: string): state is GateState {
  return state in STATE_WORD;
}

export function GateStepper({ gates, onSelect }: GateStepperProps) {
  const byId = new Map(gates.map((gate) => [gate.id, gate]));
  return (
    <ol className="rd-gates" aria-label="Approval gates">
      {GATES.map((spec) => {
        const gate = byId.get(spec.id);
        const state: GateState = gate && known(gate.state) ? gate.state : "pending";
        const who = spec.human ? `Human${gate?.actor ? `: ${gate.actor}` : ""}` : "Automatic";
        const content = (
          <>
            <span className="rd-gate-node" aria-hidden="true">
              <Icon name={STATE_ICON[state]} />
            </span>
            <span className="rd-gate-label">{spec.label}</span>
            <span className="rd-gate-state">{STATE_WORD[state]}</span>
            <span className="rd-gate-who">{who}</span>
            <span className="rd-gate-text">{gate?.status_text ?? "No status yet."}</span>
          </>
        );
        return (
          <li
            key={spec.id}
            className={`rd-gate rd-gate--${state}`}
            data-gate={spec.id}
            aria-current={state === "active" ? "step" : undefined}
          >
            {onSelect ? (
              <button type="button" className="rd-gate-button" onClick={() => onSelect(spec.id)}>
                {content}
              </button>
            ) : (
              content
            )}
          </li>
        );
      })}
    </ol>
  );
}
