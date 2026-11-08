// Copy for the public demo (ADR-025): the banner and the example-boards home. The text
// lives here only, for Joe's review. Every claim must match what the system does.
import { AttributionStatus, USAGE_PUBLISH } from "../generated/wording";

export const DEMO_BANNER = "Public demo: recorded example boards, read-only.";
export const DEMO_BANNER_MORE = "Live searches run on the owner's machine.";

export const DEMO_TITLE = "Art references with the evidence attached";
export const DEMO_LEAD =
  "refdesk takes a creative brief, searches open museum collections and builds a board of references. " +
  "Each work comes with why it fits, the museum record behind that, and the rights status the museum gives. " +
  "Nothing is exported until a person approves it.";

export const DEMO_POINTS: { heading: string; text: string }[] = [
  {
    heading: "Why each work fits",
    text: "Every card says why the work matches the brief and shows the record fields that support it.",
  },
  {
    heading: "A second model checks every claim",
    text:
      "A judge from a different model family checks each claim against the museum record, one at a time. " +
      `Anything it cannot confirm is marked "${AttributionStatus.NEEDS_HUMAN_CHECK}", never verified.`,
  },
  {
    heading: "Rights from the museum",
    text:
      "Each status is read from the museum's own rights field. " +
      `Choose "${USAGE_PUBLISH}" and only works the museum marks as open are shown.`,
  },
  {
    heading: "Every step on record",
    text: "Run history shows each run's steps, model calls and cost, so a board can be checked, not just viewed.",
  },
];

export const DEMO_BOARDS_HEADING = "Example boards";

export const DEMO_HOW_HEADING = "How these boards were made";
export function demoHowText(generator: string, judge: string): string {
  return (
    "The briefs were written for testing, not by clients. Each board was made on the owner's machine with local " +
    `models: ${generator} wrote the reasons and ${judge} checked them, so no brief left the machine. ` +
    "They are shown here exactly as recorded."
  );
}
export const DEMO_CODE_LINK = { text: "Code, evals and decision records on GitHub", href: "https://github.com/sycrus/refdesk" };

export const DEMO_REPORT_INSTEAD =
  "Reporting is off in the public demo. To report a wrong rights status, attribution or image, open an issue at github.com/sycrus/refdesk/issues.";

// On a recorded board: the gate row stops at review, because the demo API refuses it.
export const DEMO_RUN_NOTE =
  "In a live run, a person reviews any flagged items and approves the board before anything is exported. " +
  "Those steps are off in the public demo. Open a card to see the evidence behind it.";
