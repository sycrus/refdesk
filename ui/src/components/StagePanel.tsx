// The stage panel (PRD 8A Layout, issue 229): the left column of the app. It is always
// open with its own width and can be minimised to icons. The places that are always there
// (New board, Run history) come first; the stages of a board appear only once a board is
// open. Each stage shows the state of the API's gates for it, in words as well as in the
// node, so nothing is shown by colour alone. The panel never decides a gate: stagesFor()
// only maps each stage to its gates (PRD 8B), and the API's states pass through unchanged.
// Without it, the gates were one stepper on the board screen only, and the other screens
// of a board had no way back to an earlier stage.
import type { Gate, GateId, GateState, RunMode, RunView } from "../api/types";
import { Icon, type IconName } from "./Icon";
import "./StagePanel.css";

export type StageKey = "brief" | "search" | "shortlist" | "verify" | "approve" | "export";
export type StageState = GateState | "none";

export interface Stage {
  key: StageKey;
  label: string;
  icon: IconName;
  gates: GateId[];
  state: StageState; // "none": the shortlist is not a gate
  detail: string; // the gates' own status text, or the kept count for the shortlist
  reachable: boolean; // a stage you can open now; later stages stay disabled
}

const ENDED = new Set(["done", "stopped", "cancelled"]);

// For a stage with two gates (Search and check: G1 spend and G2 verify), the node shows
// the one that most needs attention. The words list both gates, unchanged.
const ATTENTION: GateState[] = ["blocked", "active", "pending", "passed", "skipped"];

function pick(gates: Gate[], ids: GateId[]): Gate[] {
  return ids.map((id) => gates.find((g) => g.id === id)).filter((g): g is Gate => g !== undefined);
}

function stateOf(found: Gate[]): StageState {
  if (found.length === 0) return "pending"; // a gate the API did not report is never passed
  return ATTENTION.find((state) => found.some((g) => g.state === state)) ?? "pending";
}

export function stagesFor(run: RunView): Stage[] {
  const ended = ENDED.has(run.state);
  const gate = (key: StageKey, label: string, icon: IconName, ids: GateId[], reachable?: boolean): Stage => {
    const found = pick(run.gates, ids);
    const state = stateOf(found);
    return {
      key,
      label,
      icon,
      gates: ids,
      state,
      detail: found.map((g) => g.status_text).join(" "),
      reachable: reachable ?? (found.length > 0 && state !== "pending"),
    };
  };
  const kept = run.items.filter((item) => item.selected).length;
  return [
    gate("brief", "Brief", "brief", ["G0"], true),
    gate("search", "Search and check", "search", ["G1", "G2"], true),
    {
      key: "shortlist",
      label: "Shortlist",
      icon: "grid",
      gates: [],
      state: "none",
      detail: ended ? `${kept} of ${run.items.length} kept` : "Waiting for the search",
      reachable: ended,
    },
    gate("verify", "Verify", "verify", ["G3"]),
    gate("approve", "Approve", "sign", ["G4"]),
    gate("export", "Export", "export", ["G5"]),
  ];
}

const STATE_WORDS: Record<StageState, string> = {
  passed: "passed",
  active: "active",
  pending: "pending",
  blocked: "blocked",
  skipped: "skipped",
  none: "no gate",
};

const PIP: Partial<Record<StageState, IconName>> = { passed: "check", blocked: "alert", skipped: "dash" };

export interface PanelLink {
  key: string;
  label: string;
  detail?: string;
  icon: IconName;
  href: string;
  current: boolean;
  onOpen: () => void;
}

export interface StagePanelProps {
  links: PanelLink[];
  board?: { name: string; run: RunView; current: StageKey | null; onOpen: (stage: StageKey) => void; href: (stage: StageKey) => string };
  minimised: boolean;
  onToggle: () => void;
  appMode?: { text: string; mock: boolean; mode: RunMode } | null; // issue 251, from /healthz
}

// One icon per run mode, beside the words (never colour alone); mock uses the warning tone.
const MODE_ICON: Record<RunMode, IconName> = {
  recorded: "history",
  mock: "alert",
  local: "check",
  cloud: "alert",
  retrieval_only: "search",
};

export function StagePanel({ links, board, minimised, onToggle, appMode }: StagePanelProps) {
  const stages = board ? stagesFor(board.run) : [];
  return (
    <nav className={`rd-panel${minimised ? " rd-panel--min" : ""}`} aria-label="refdesk">
      <span className="rd-app-brand rd-panel-brand">
        <span aria-hidden="true">R</span>
        <span className="rd-panel-text" aria-hidden="true">
          efDesk
        </span>
        <span className="rd-visually-hidden">RefDesk</span>
      </span>
      {appMode && (
        <p
          className={`rd-panel-mode${appMode.mock ? " rd-panel-mode--mock" : ""}`}
          title={minimised ? appMode.text : undefined}
        >
          <span className="rd-panel-node rd-panel-mode-icon" aria-hidden="true">
            <Icon name={MODE_ICON[appMode.mode] ?? "check"} />
          </span>
          <span className="rd-panel-text">{appMode.text}</span>
        </p>
      )}
      <ul className="rd-panel-list">
        {links.map((link) => (
          <li key={link.key}>
            <a
              className="rd-panel-item"
              href={link.href}
              aria-current={link.current ? "page" : undefined}
              title={minimised ? link.label : undefined}
              onClick={(event) => {
                event.preventDefault();
                link.onOpen();
              }}
            >
              <span className="rd-panel-node" aria-hidden="true">
                <Icon name={link.icon} />
              </span>
              <span className="rd-panel-text">
                <span className="rd-panel-label">{link.label}</span>
                {link.detail && <span className="rd-panel-detail">{link.detail}</span>}
              </span>
            </a>
          </li>
        ))}
      </ul>

      {board && (
        <>
          <p className="rd-panel-sep">
            <span className="rd-panel-text">This board · {board.name}</span>
          </p>
          <ol className="rd-panel-list rd-panel-stages" aria-label="Stages of this board">
            {stages.map((stage, index) => {
              const current = board.current === stage.key;
              const words = `${stage.label}: ${STATE_WORDS[stage.state]}${stage.gates.length ? ` (${stage.gates.join(", ")})` : ""}`;
              const pip = stage.key === "export" && stage.state === "pending" ? "lock" : PIP[stage.state];
              const body = (
                <>
                  <span className={`rd-panel-node rd-panel-node--${stage.state}${current ? " rd-panel-node--current" : ""}`} aria-hidden="true">
                    <Icon name={stage.icon} />
                    {pip && (
                      <span className={`rd-panel-pip rd-panel-pip--${pip}`}>
                        <Icon name={pip} />
                      </span>
                    )}
                  </span>
                  <span className="rd-panel-text">
                    <span className="rd-panel-label">
                      {stage.label}
                      {stage.gates.length > 0 && <span className="rd-panel-gate"> {stage.gates.join("–")}</span>}
                    </span>
                    <span className="rd-panel-detail">
                      {STATE_WORDS[stage.state]}
                      {stage.detail && ` · ${stage.detail}`}
                    </span>
                  </span>
                </>
              );
              return (
                <li key={stage.key} className={`rd-panel-stage${stage.state === "passed" ? " rd-panel-stage--done" : ""}`}>
                  {index === stages.length - 1 && (
                    <p className="rd-panel-nor">
                      <span className="rd-panel-text">Point of no return</span>
                    </p>
                  )}
                  {stage.reachable ? (
                    <a
                      className="rd-panel-item"
                      href={board.href(stage.key)}
                      aria-current={current ? "step" : undefined}
                      aria-label={words}
                      title={minimised ? words : undefined}
                      onClick={(event) => {
                        event.preventDefault();
                        board.onOpen(stage.key);
                      }}
                    >
                      {body}
                    </a>
                  ) : (
                    <span className="rd-panel-item rd-panel-item--off" title={minimised ? words : undefined}>
                      <span className="rd-visually-hidden">{`${words}. Not reached yet.`}</span>
                      <span className="rd-panel-body" aria-hidden="true">
                        {body}
                      </span>
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </>
      )}

      <button
        type="button"
        className="rd-panel-item rd-panel-toggle"
        aria-expanded={!minimised}
        aria-label={minimised ? "Expand the panel" : "Minimise the panel"}
        title={minimised ? "Expand" : "Minimise"}
        onClick={onToggle}
      >
        <span className="rd-panel-node" aria-hidden="true">
          <Icon name="chevrons" />
        </span>
        <span className="rd-panel-text">
          <span className="rd-panel-label">Minimise</span>
        </span>
      </button>
    </nav>
  );
}
