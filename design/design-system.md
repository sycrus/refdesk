# refdesk design system

A restrained, editorial system for a tool that shows its evidence. It borrows from museum catalogues: paper surfaces, hairline rules, one verdigris accent, a serif for artwork titles. It exists so every screen answers three questions: why is this here, where did it come from, and what did it cost.

Used by the refdesk web app (React and TypeScript). This is a generic system: it names the tokens and components, and the app implements them.

## Content fundamentals

- **Voice.** Plain, precise, evidence first. Say what happened and what the user can do next. No exclamation marks, no cleverness around money or rights.
- **Case.** Sentence case everywhere. Artwork titles keep their own capitalisation.
- **Numbers.** Show the number and what it counts: "9 of 12 items accepted", "USD 0.012 of 0.050 cap".
- **Fixed wording.** These labels never change, because operators learn them.

| Meaning | Label |
|---|---|
| Attribution matches the museum record | Attribution verified from record |
| Attribution could not be confirmed | Needs human check |
| Source states the work is open | Open (as stated by source) |
| Source flag missing or unclear | Unverified |
| Source requires permission | Permission required |
| Run ended early | Stopped: budget cap reached (or step cap, timeout, no progress) |
| After export | Exported. This board is now read-only |

- **Examples.** Good: "Stopped: budget cap reached. 9 of 12 items accepted. Nothing was exported." Not: "Oops, we ran out of budget!"
- **Never** show an inferred attribution or rights status as verified. Never hide a stop reason.

## Visual foundations

- **Surfaces.** `paper` page, `card` for content, `sunken` for wells (image mats, tracks, ID blocks). Separate with `line` hairlines, not shadows. Only dialogs and menus use `shadow-pop`.
- **Colour.** One brand hue, `accent` (verdigris). `ok`, `warn` and `danger` are state colours and appear only with a label and an icon, because they must also be told apart by people who cannot see hue. Pair every state colour with its `-soft` background.
- **Imagery.** Artworks are shown whole, never cropped, on a `sunken` mat with generous padding. Do not apply filters. If rights say "Permission required", show the metadata and a link, not the image.
- **Type.** Newsreader for display and artwork titles, Inter for interface text, JetBrains Mono for IDs, hashes and record fields. Use `display-l` once per screen at most.
- **Spacing.** A 4px grid: `space-1` to `space-8`. Card padding `space-4`, grid gap `space-4`, section gap `space-6`.
- **Radius.** `radius-sm` chips, `radius-md` buttons and inputs, `radius-lg` cards and dialogs, `radius-pill` badges and the cost meter.
- **Focus.** 2px `focus` ring with 2px offset on every interactive element, in both themes.
- **Motion.** Short and quiet: 120 to 200ms ease-out for state changes, nothing that loops. Respect reduced-motion. Show progress with state text, not spinners alone. (The token format has no motion family, so these values live here.)
- **Themes.** Light and dark are the same system. Test every component in both.
- **Polish.** Skeleton states instead of empty flashes, aligned baselines, consistent badge heights, optical alignment of icons with text. Polish here means clarity, not decoration.

## Iconography

Outline icons on a 16px grid, 1.5px stroke, round caps and joins, `currentColor`. A small fixed set: check, alert, lock, circle, dash, arrow. Icons never carry meaning alone: each sits next to a text label. No emoji.

## Components

| Group | Component | Purpose |
|---|---|---|
| Actions | Button | Primary, secondary, ghost and danger actions |
| Actions | ConfirmDialog | The irreversible export confirmation |
| Evidence | StatusBadge | Attribution and rights status with fixed wording |
| Evidence | EvidenceCard | One reference with its why, evidence and badges |
| Flow | GateStepper | The multistage approval gates and their states |
| Flow | CostMeter | Spend against the cap |
| Flow | StopBanner | Why a run ended early |
| Audit | AuditTimeline | The event log of a run |

## Pattern: the approval gates

A run passes through gates. Some are automatic, some need a person. The UI shows all of them in `GateStepper` and exposes a different surface at each.

| Gate | Who | What the UI exposes | Components |
|---|---|---|---|
| G0 Intake | Automatic | Inline validation on the brief. A declined request shows the reason and alternatives | Input, StopBanner |
| G1 Spend | Automatic, or you if the cap is hit | Live cost against the cap. At the cap: raise it (an explicit action) or keep the partial board | CostMeter, StopBanner, Button |
| G2 Verify | Automatic, per item | A badge on every card. Failures become "Needs human check" with a reason | StatusBadge, EvidenceCard |
| G3 Review | You (operator) | A list of flagged items. Keep (with a required note) or drop | EvidenceCard, Button |
| G4 Approve | You (approver) | A summary of counts by rights status, reviewed items and exclusions. Required acknowledgement | ConfirmDialog |
| G5 Export | You, irreversible | Final confirmation, then a receipt with run ID. The board becomes read-only | ConfirmDialog, AuditTimeline |
| G6 Client sign-off | Later | A read-only shared page | not in v1 |

Gate states: passed, active, pending, blocked, skipped. A gate is never shown as passed if a person has not acted on it.

## Accessibility checklist

- Text 4.5:1 on its ground in both themes (verified for the token pairs in `tokens.json`). Control borders and focus rings 3:1.
- State is never colour alone: icon plus label.
- Full keyboard path through the card grid, stepper and dialog. Dialog traps focus and returns it.
- Alt text from artwork title and artist.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`.

## Using this system

Implement the tokens as CSS custom properties (the page generates `tokens.css`). Build components in React against these specs. Keep the fixed wording above in one constants file. When a component here and the app disagree, fix the app or change this system and say why in a revision note.
