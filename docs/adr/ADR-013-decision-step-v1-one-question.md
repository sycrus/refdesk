# ADR-013: Decision step v1: one Kev question (tier choice)

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
The decision contract lists five candidate questions (PRD 10.1): Q1 tier choice, Q2 needs a human check, Q3 culturally sensitive symbol, Q4 brief difficulty, Q5 declined request. Each Kev question needs its own labels, golden set, calibration and a simple baseline. Kev evaluates questions independently, so conditional logic belongs in policy code.

## Decision
In v1, Kev answers one question: Q1, which tier handles the request. Q2, Q3 and Q5 start as plain rules; Q4 is not in v1. A rule is replaced by a Kev question only when it fails on named cases and the rules for adding a question (PRD 10.1) are met.

## Options considered
| Option | Why not chosen |
|---|---|
| All five questions in Kev from the start | **[Joe]** |
| No Kev in v1, rules only | **[Joe]** |

## Consequences
- Easier: one labelled dataset (routing labels, ADR-021) and one calibration; the other flags are readable rules.
- Harder: rules may miss cases a model would catch; each later question costs a new dataset.
- **[Joe]** (including the cost of each wrong Q1 answer, which PRD 10.1 leaves to define)

## Evidence
No measurement yet. M4 supplies it: Kev against the cascade and LightGBM on the same split (ADR-001, ADR-002).

## Revisit trigger
A rule fails on named cases and labelled data for that question exists.
