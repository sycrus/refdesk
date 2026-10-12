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
}
