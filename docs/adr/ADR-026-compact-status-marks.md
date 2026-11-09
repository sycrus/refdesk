# ADR-026: Compact status marks on cards

- **Status:** accepted. The choice and the reasons in *Options considered* are Joe's (2026-11-09 UI review, issue #227).
- **Date:** 2026-11-09

## Context
Every result carries two statuses with fixed wording, kept in one constants file (`src/refdesk/wording.py`, generated into `ui/src/generated/wording.ts`). Attribution is "Attribution verified from record" or "Needs human check". Rights is "Open (as stated by source)", "Unverified" or "Permission required" (PRD 8A *Explainability in the UI*). Until now the rule has been to show that wording as a badge on every card, and `StatusBadge` does so.

The image-first UI (PRD 8A, as updated in #226) makes shortlisting image-led: art directors pick by eye, and text comes back for verification before use. Two full-wording badges under every image put the most text on the screen at the stage that needs the least. The 2026-11-09 review compared two options in a clickable mock-up (`design/mockups/board-image-first.html`), both of which always show both statuses.

What must not change in any option: no card ever shows an inferred or unrecognised status as verified or open (`resolveStatus` in `ui/src/components/StatusBadge.tsx` falls back to the cautious status), a status is never left blank, and status is never shown by colour alone.

## Decision
On Shortlist cards in the Images and Captions views, each status shows as a **compact mark** that is always present: a ✓ in a circle for verified or open, a ? in a diamond for needs a check or unverified, and a lock in a square for permission required. Each mark carries the word "Attribution" or "Rights", and its tooltip and screen-reader label are the fixed wording. Wherever the checks happen, cards always show the full fixed wording: the Full view, every card on Verify, and the lightbox evidence panel; Approve groups works under the fixed wording. A Settings option switches Shortlist cards to full-wording badges as well (Joe, 2026-11-09).

## Options considered
| Option | Why not chosen |
|---|---|
| Full fixed wording on every card, in every view (the rule until now) | Different priorities at stages of the process: initial shortlisting stages are visual, and when curating the board the details and checks need to come in |
| Marks only on exceptions: nothing for verified and open, a mark for the rest | Blanks are ambiguous, marks with clear meanings to help with disambiguation. |
| Icon-only marks with no "Attribution" or "Rights" word | For clarity and to prevent ambiguity, the words are still required. The marks alone do not convey enough information as to what they represent. |
| Compact marks by default, full wording as a setting (chosen) | n/a |

## Consequences
- Easier: the Shortlist reads as images. The status is still visible on every card without opening it.
- Harder: the mark's shapes and the words "Attribution" and "Rights" are a second visual vocabulary to keep in step with the fixed wording. Both must come from the same resolver, so a mark can never say more than the badge would.
- Harder: a tooltip is not visible on touch screens, so on a phone the full wording is only in the lightbox, the Full view and Verify.
- Harder: two card styles mean every card state has to be tested in both: each attribution and rights status, as a mark and as a badge (Joe, 2026-11-09).
- Locked in: the fixed wording stays in one constants file. A mark's accessible name is always the fixed wording, never the short word. Verify and the Full view never use marks, whatever the setting.

## Evidence
- No measurement yet. The choice comes from Joe's review of the mock-up on 2026-11-09, not from user testing. The test that would supply evidence is a short task with art directors: shortlist from a board in each style, then say which works need a check; compare time and errors.

## Revisit trigger
An operator misreads a mark as verified, or misses a ? mark, in a session or a bake-off; or the axe check or a screen-reader pass finds the mark's label does not carry the fixed wording.
