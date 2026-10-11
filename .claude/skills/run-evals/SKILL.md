---
name: run-evals
description: Run the evaluation suite, compare results with a previous run, check for regressions, or write an eval report. Use for "run evals", "did this change make it worse", "compare against baseline", "update the eval report", or before merging changes that affect retrieval, rationales, rights logic or routing.
---

# Run evals

## Before running

1. Read `docs/eval-gate-policy.md` for thresholds, the noise margin and the flake policy. If it does not exist, ask the user to define it from a noise measurement before gating anything.
2. Record the config: git SHA, prompt file hashes, model identifier (pinned digest for local models), data and golden-set version, seed, parameters. Write it to `runs/<hash>/manifest.json`.
3. Choose the tier: PR tier (recorded responses, deterministic) or nightly (real model). Use the mock server by default. Never call a paid API without an explicit budget in config.

## Run

- Compute metrics with bootstrap confidence intervals, per slice (source, task type, difficulty).
- If outputs are nondeterministic, repeat N times and report mean and spread.
- Compare against the previous report only if the golden-set version and metric definitions match. Otherwise say they are not comparable.
- Treat a change smaller than the measured noise as no change.

## Report

Write `evals/reports/eval-report-YYYY-MM-DD.md` with:
- the config hash and versions
- scores with intervals, per slice
- top failure categories with counts and one example each
- cost and wall-clock
- regressions beyond the margin, and what changed since the last report
- anything that could not be compared, and why

Append one row to `results/history.csv` (commit, score, interval, cost, wall-clock).

## Rules

- Never edit golden-set files. If a case looks wrong, report it and ask the user.
- Do not report a single score without an interval.
- If an LLM judge is used, report its agreement with human labels and use a different model from the generator.
