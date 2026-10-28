# Evals

Evals are plain code in this repo (ADR-005). The rules: every score has a confidence interval, every run has a manifest, golden sets are frozen, and synthetic sets never support a claim.

## Golden sets (`evals/golden/`)

| File | What | Use |
|---|---|---|
| `golden-v0-synthetic.jsonl` | 31 cases written by Claude Code; expected references derived by an explicit rule per case over the ingested corpus (`corpus_version met:2588:d188937d8a53`) | Building and testing the harness **only**. Rules over metadata favour the metadata baseline, so it cannot rank retrievers (ADR-018) |
| `golden-v1` (in progress, not frozen) | 45 briefs: 20 labelled blind by Joe twice, 21 reviewed by Joe from Claude's proposals checked by phi4, 4 decline cases (ADR-018). Steps in `labelling/v1/README.md` | Required before any number goes public |

Frozen: `scripts/verify.py` fails any edit, deletion or rename of a committed `golden-vN*.jsonl`. Changes mean a new version. Validation: `evals/reports/golden-v0-synthetic-validation.md`.

## Running

```
uv run python -m refdesk eval --retriever jaccard          # or clip, combined; --k 12 --seed 0
uv run python -m refdesk compare <config-hash-A> <config-hash-B>
uv run python -m refdesk eval-rationales                   # verifier pass rates of rationales
uv run python scripts/golden_v1_report.py                  # golden-v1 trust report; --freeze is Joe's call
```

Each run writes `runs/<config-hash>/manifest.json` and `cases.jsonl` (gitignored), a report `evals/reports/eval-report-<date>-<retriever>-<hash>.md` (committed), and one row per metric in `results/history.csv`. The config hash covers every input that can change a score (git SHA, golden file hash and version, corpus version, retriever and parameters, k, seed, scorer version). `eval` refuses to run when the golden set's corpus version does not match the store.

## Metrics (`scorers-v1`)

- **recall@k, capped:** hits ÷ min(relevant, k). Capped until graded data exists (Joe, 2026-10-11); on golden-v0 it is close to precision@k.
- **precision@k**, **MRR**, and **open-rights share** of the top k for reproduction cases.
- Seeded percentile bootstrap, 95% intervals, overall and by difficulty and usage mode.
- **Paired comparison:** bootstrap over per-case differences between two runs; refuses runs with a different golden set, corpus or scorer version.

Gates: `docs/eval-gate-policy.md`. Today golden-v0 is a non-blocking tripwire: any score change must be explained in the PR.

## Reports so far

| Report | What |
|---|---|
| `eval-report-2026-10-11-jaccard.md` | First run of the harness (before the reproduction rights filter) |
| `eval-report-2026-10-11-jaccard-fb5462038a93.md` | Jaccard after the rights filter: recall 0.655, open share 1.000 |
| `eval-report-2026-10-12-clip-8c995e38a66b.md` | CLIP: recall 0.454; paired vs Jaccard −0.201 [−0.323, −0.083], mostly golden-v0's metadata bias |
| `judge-probe-2026-10-12.md` | 9 local models judging 60 synthetic items with one planted false fact each (ADR-021 evidence) |
| `golden-v0-synthetic-validation.md` | golden-v0 coverage and validation |
| `eval-comparison-2026-10-12-*.md`, `eval-report-2026-10-12-*.md` | Jaccard, CLIP and combined on golden-v0, with run-to-run noise |
| `judge-probe-2026-10-27-v1.md`, `judge-probe-2026-10-27-hard.md` | Harder probes: phi4 per claim caught 40/40 errors with no false alarms; Granite Guardian dropped (ADR-022) |
| `fit-probe-2026-10-27*.md` | Can phi4 check an opinion sentence for smuggled facts? fit-v1 kept; fit-v2 not adopted. `-random-pairs` is superseded |
| `rationale-eval-2026-10-27-*.md`, `rationale-prompts-2026-10-27.md` | Rationale pass rates on golden-v0 (plumbing only). Current prompts (rationale-v2, fit-v1): verified 0.988, fit_pass 0.417 |
