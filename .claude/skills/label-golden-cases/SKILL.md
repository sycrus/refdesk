---
name: label-golden-cases
description: Help create, format or validate golden evaluation cases (creative briefs with expected references). Use for "add golden cases", "new brief for the eval set", "validate the golden set", "check for leakage", or when preparing cases for labelling. You format and validate; the user assigns quality labels.
---

# Golden cases

The user holds the art expertise. You must not assign quality labels or choose expected references.

## What you may do

- Draft candidate briefs in varied styles and difficulty, for the user to edit.
- Format cases into JSONL, one case per line, with fields:
  `id, brief, constraints, usage_mode, expected, labels, source, labeller, difficulty, tags, version`
- Validate: unique IDs, required fields present, no duplicates or near-duplicates, spread across sources and difficulty, no case copied from few-shot examples or prompts.
- Check leakage: no golden brief text appears in prompts, few-shot examples, training data or the router's training split.
- Produce a summary table (counts by source, difficulty and tag) so gaps are visible.

## What you must not do

- Do not decide which references are good, mediocre or wrong.
- Do not edit a frozen version. Create `golden-vN+1.jsonl` and keep the old file unchanged.
- Do not add cases whose expected attributions you cannot verify against museum records.

## Process

1. Ask the user for the briefs, or offer drafts to react to.
2. For each case, present retrieved candidates without system names and ask the user to label them.
3. Ask the user to relabel 10 cases a day later and report agreement. Below 90%, tighten `evals/labelling-guide.md` before continuing.
4. Record the error taxonomy from real failures, with counts.

Include hard cases: ambiguous briefs, culturally sensitive symbols, over-popular references, and briefs that should be declined (living-artist style requests, authentication).
