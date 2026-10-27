// The parts of the API contract the components read (src/refdesk/api/models.py,
// docs/api/openapi.json). Handwritten for now; keep in step with the models.
import type { AttributionStatus, RightsStatus, StopReason } from "../generated/wording";

export type { AttributionStatus, RightsStatus, StopReason };

export type GateId = "G0" | "G1" | "G2" | "G3" | "G4" | "G5";
export type GateState = "passed" | "active" | "pending" | "blocked" | "skipped";

export interface Gate {
  id: GateId;
  state: GateState;
  status_text: string;
  actor?: string | null; // who must act, for human gates
}

export interface RightsRecord {
  status: RightsStatus;
  flag_field: string | null; // the source field the status was read from; null = no flag
  source?: string;
  object_id?: string;
  flag_value?: string | boolean | null; // the raw value, as the source returned it
  licence_string?: string | null;
  checked_at?: string;
}

export interface ArtworkRecord {
  id: string;
  source: string;
  title?: string | null;
  artist?: string | null;
  date?: string | null;
  medium?: string | null;
  image_url?: string | null;
  record_url?: string | null;
  credit_line?: string | null; // verbatim from the source
  rights: RightsRecord;
}

export interface Evidence {
  field: string;
  value: string;
  record_url?: string | null;
}

export interface BoardItem {
  record: ArtworkRecord;
  rationale: string | null;
  evidence: Evidence[];
  attribution_status: AttributionStatus;
  flag_reasons: string[];
  selected: boolean;
  score?: number | null; // retrieval score; higher ranks first
  score_components?: Record<string, number>; // parts that sum to the score
  confidence?: { bucket: "high" | "medium" | "low"; value: number } | null;
  review?: ItemReview | null; // G3 decision, for flagged items
  opinion_flag?: string | null; // fit sentence flagged (issue 135); never changes attribution_status
  tier_used?: string | null;
  cost_usd?: number;
}

export type UsageMode = "reference_only" | "reproduction";
export type LoopState =
  | "init"
  | "retrieve"
  | "decide"
  | "generate"
  | "verify"
  | "assemble"
  | "human_check"
  | "export"
  | "done"
  | "stopped"
  | "cancelled";

export interface Conditions {
  period?: string | null;
  material?: string | null;
  motif?: string | null;
  department?: string | null;
}

export interface BoardRequest {
  brief: string;
  avoid?: string[];
  usage_mode?: UsageMode;
  anchor_id?: string | null;
  conditions?: Conditions;
  keep_local?: boolean;
  budget_cap_usd?: number;
  target_items?: number;
}

export interface Cost {
  spent_usd: number;
  cap_usd: number;
  currency: "USD";
}

export interface RunCreated {
  run_id: string;
  state: LoopState;
}

export interface RunView {
  run_id: string;
  request?: BoardRequest | null;
  state: LoopState;
  stop_reason?: StopReason | null;
  stop_banner?: string | null;
  stop_detail?: string | null;
  gates: Gate[];
  items: BoardItem[];
  cost: Cost;
  keep_local: boolean;
  sent_to: string[];
  models_used?: Record<string, string>;
  approval?: { approver: string; acknowledged: true; approved_at: string } | null;
  export?: ExportReceipt | null;
  read_only: boolean;
}

export interface Problem {
  code: string;
  message: string;
}

export interface ItemReview {
  decision: "keep" | "drop";
  note?: string | null;
  decided_by: string;
  decided_at: string;
}

export interface ReviewRequest {
  reviewer: string;
  decisions: { item_id: string; decision: "keep" | "drop"; note?: string | null }[];
}

export interface ExportReceipt {
  run_id: string;
  file: string;
  exported_at: string;
  approver: string;
  versions: Record<string, string>;
  notice: string;
  not_legal_advice: string;
}
