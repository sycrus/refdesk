---
name: label-golden-cases
description: Help create, format or validate golden evaluation cases (creative briefs with expected references). Use for "add golden cases", "new brief for the eval set", "validate the golden set", "check for leakage", or when preparing cases for labelling. You format, validate and propose; the user reviews and decides every label.
---

# Golden cases

The user holds the art expertise. From `golden-v1` on you may **propose** expected references and grades, but the user decides every label (ADR-018, amended 2026-10-26).

**One exception (ADR-018, CLAUDE.md):** `golden-v0-synthetic` is written entirely by Claude Code, for building and testing the eval harness only. Every case is marked `provenance: synthetic`, and its expected references come from an explicit `rule` applied to the ingested corpus, never from judgement. It must never support a claim or a published number. From `golden-v1` on, everything below applies. Format and validation code: `src/refdesk/evals/golden.py`.

## What you may do

- Draft candidate briefs in varied styles and difficulty, for the user to edit.
- Format cases into JSONL, one case per line, with fields:
  `id, brief, constraints, usage_mode, expected, labels, source, labeller, difficulty, tags, version`
- Validate: unique IDs, required fields present, no duplicates or near-duplicates, spread across sources and difficulty, no case copied from few-shot examples or prompts.
- Check leakage: no golden brief text appears in prompts, few-shot examples, training data or the router's training split.
- Produce a summary table (counts by source, difficulty and tag) so gaps are visible.
- Propose expected references and grades for each case, citing the record fields each rests on, marked as proposals (`labeller: claude-code`, not final).

## What you must not do

- Do not mark a label final. The user accepts or corrects every one.
- Do not show your proposals for the blind subset before the user has labelled it.
- Do not judge your own proposals: judges come from other families (`phi4`, `granite3-guardian:8b`; ADR-021).
- Do not edit a frozen version. Create `golden-vN+1.jsonl` and keep the old file unchanged.
- Do not add cases whose expected attributions you cannot verify against museum records.

## Process

1. Ask the user for the briefs, or offer drafts to react to.
2. **Blind subset first:** pick 20 cases; present unranked candidates without system names and without your proposals; the user labels them.
3. Propose references and grades for every case, run the cross-family judges, and flag disagreements.
4. The user reviews every label (accept or correct). Record per case who proposed, who judged, and whether the user changed it.
5. Report your agreement with the blind labels and the share of proposals the user corrected.
6. A day later, ask the user to relabel the same 20 blind cases without looking, and report self-agreement. Apply the trust rules in ADR-018 (gap, anchoring) before freezing. Below 90%, tighten `evals/labelling-guide.md` before continuing.
7. Record the error taxonomy from real failures, with counts.

Include hard cases: ambiguous briefs, culturally sensitive symbols, over-popular references, and briefs that should be declined (living-artist style requests, authentication).
