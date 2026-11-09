// How far a board has got, in words (issue 234). The stage comes from the API
// (RunSummary.stage), which reads it from the gates; it says how far the board has got,
// not where someone was working, so the words describe the state rather than a place.
export type BoardStage = "cancelled" | "search" | "exported" | "export" | "shortlist" | "verify" | "approve";

export const STAGE_LABEL: Record<BoardStage, string> = {
  cancelled: "cancelled",
  search: "still searching",
  exported: "exported",
  export: "approved, not yet exported",
  shortlist: "shortlisting",
  verify: "a kept work needs a check",
  approve: "ready to approve",
};

export function stageLine(stage: BoardStage): string {
  if (stage === "exported") return "Exported · read-only";
  if (stage === "cancelled") return "Cancelled · nothing exported";
  if (stage === "search") return "Searching…";
  if (stage === "export") return "Approved · not yet exported";
  return `Draft · ${STAGE_LABEL[stage]}`;
}
