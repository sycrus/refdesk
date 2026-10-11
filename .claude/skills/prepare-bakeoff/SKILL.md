---
name: prepare-bakeoff
description: Prepare blind rating sheets that compare the system against baselines, then analyse the ratings. Use for "bake-off", "blind rating", "compare against Public.Work or ArtLens", "prepare rating sheets", or when the user has completed ratings and wants results.
---

# Bake-off

## Setup

1. Take the briefs (about 20) from the golden set. Never use briefs that were used to tune the system.
2. Run each automated system on every brief: the full system, the metadata-only baseline, the off-the-shelf similarity baseline, and a well-prompted general assistant with search. For third-party tools (for example Cosmos Public.Work or Rawpixel), the user collects results manually. Do not scrape them. Record links or screenshots.
3. Strip identifiers, randomise order, and assign each board a code. Save the key to a separate file that raters never see.

## Rating sheet

One row per board, with fields:
`rater, brief_id, board_code, usefulness (1-5), non_obviousness (1-5), minutes_to_usable_board, attribution_errors (count, checked against museum records), rights_record_present (y/n), notes`

Use three raters (art directors). Ask for independent ratings.

## Analysis (after ratings are in)

- Join ratings with the key.
- Report each dimension per system with confidence intervals. Report rater agreement.
- Count attribution errors from museum records, not from rater opinion.
- State where baselines won or tied. Do not drop dimensions that the system lost.
- Apply the PRD decision rule: if the system does not win on usefulness or non-obviousness against the best baseline, recommend positioning as a demonstration case study.

Write `reports/bakeoff-YYYY-MM-DD.md` and keep raw ratings in `ratings.jsonl`.
