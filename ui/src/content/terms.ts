// Disclaimer and terms of use (issue 219). The text lives here only; TermsScreen renders
// it and the footer links to it. Joe approves every line. Each claim must match what the
// system enforces (PRD 8B, rights logic): change the code and this together.
// Not reviewed by a lawyer yet (Joe, 2026-11-08): a good-faith version goes up first.
import {
  NOT_LEGAL_ADVICE,
  RightsStatus,
  USAGE_INSPIRATION,
  USAGE_PUBLISH,
} from "../generated/wording";

export const TERMS_TITLE = "Disclaimer and terms";

// One line under every screen, next to the link.
export const FOOTER_LINE = "Rights as stated by each museum. Not legal advice.";

export interface TermsSection {
  heading: string;
  paragraphs: string[];
}

export const TERMS: { updated: string; sections: TermsSection[] } = {
  updated: "8 November 2026",
  sections: [
    {
      heading: "What refdesk is",
      paragraphs: [
        "refdesk helps you find reference images in open museum collections. For each work it shows the museum's own record and the rights status the museum gives.",
      ],
    },
    {
      heading: "Rights information",
      paragraphs: [
        `Each work's rights status is read from the museum's own rights field and shown as stated by that museum, for example "${RightsStatus.OPEN}". refdesk does not verify it independently, and museums can be wrong or change a status. A status refdesk cannot read is shown as "${RightsStatus.UNVERIFIED}", never as open.`,
        `${NOT_LEGAL_ADVICE} Check the museum's record before you publish anything.`,
      ],
    },
    {
      heading: "What refdesk does not do",
      paragraphs: [
        "refdesk does not authenticate, attribute or value works. It cannot tell you whether a work you own is genuine or what it is worth.",
        "refdesk does not generate images.",
        'refdesk does not clear new work made "in the style of" an artist. A board that mentions an artist whose works are still in copyright is for inspiration only.',
      ],
    },
    {
      heading: "How you use what you find",
      paragraphs: [
        "You decide how you use what you find, and you are responsible for that use. Works the museum marks as open can be used as the museum states. Anything else needs permission from whoever holds the rights.",
      ],
    },
    {
      heading: "Inspiration or publishing",
      paragraphs: [
        `${USAGE_INSPIRATION}: shows every work, whatever its rights, for moodboards, palette and mood. These results are not cleared for publishing.`,
        `${USAGE_PUBLISH}: shows only works the museum marks as open. Use the credit line the museum gives.`,
      ],
    },
    {
      heading: "The public demo",
      paragraphs: [
        "The public demo shows recorded example runs. Their briefs were written for testing, not by clients. The demo is read-only: you cannot start a board, approve or export there.",
        "refdesk does not store anything you type in the demo, has no accounts and does no tracking. The hosting provider keeps standard server logs.",
      ],
    },
    {
      heading: "Images",
      paragraphs: [
        "Images load directly from each museum's own image server, so the museum sees that request like any web visit. Credit lines are as given by the museum.",
      ],
    },
    {
      heading: "No warranty",
      paragraphs: [
        "refdesk is provided as is, for demonstration, with no guarantee that it is accurate, complete or available.",
      ],
    },
    {
      heading: "Report a problem",
      paragraphs: [
        "If a rights status, attribution or image is wrong, or something here should not be shown, open an issue at github.com/sycrus/refdesk/issues.",
      ],
    },
    {
      heading: "About this page",
      paragraphs: [
        "This page has not been reviewed by a lawyer yet. It is a good-faith summary of what refdesk does and does not do.",
      ],
    },
  ],
};
