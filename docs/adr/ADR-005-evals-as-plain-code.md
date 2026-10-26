# ADR-005: Evals as plain code in the repo

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Every public claim must trace to a measurement (PRD 1A, principle 2). Scores need confidence intervals, runs need manifests, golden sets are frozen, and CI must gate on evals (PRD 11, 13A).

## Decision
Evals are plain Python in the repo (`src/refdesk/evals/`), run by the CLI and pytest, not in an eval platform. Reports go to `evals/reports/` with the config hash in the name; scores are appended to `results/history.csv`.

## Options considered
| Option | Why not chosen |
|---|---|
| A hosted eval platform | **[Joe]** |
| The evals built into a tracing tool (ADR-004) | **[Joe]** |

## Consequences
- Easier: evals run in CI with no service; changes to scorers are reviewed as diffs; results reproduce from a manifest.
- Harder: bootstrap intervals, paired comparison and reports are written and maintained here; no dashboard.
- **[Joe]**

## Evidence
Built: the harness with manifests and config hash (issue #11), scorers with bootstrap intervals (`tests/evals/test_scorers.py`), paired comparison (issue #36), the three-retriever report (issue #37). See `evals/README.md`.

## Revisit trigger
Maintaining the harness takes more time than the evals themselves, or reviewers need a shared view that a report file cannot give.
