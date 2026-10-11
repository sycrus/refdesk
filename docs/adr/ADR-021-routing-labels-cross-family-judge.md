# ADR-021: Synthetic routing labels with a cross-family judge

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-11

## Context
Kev's Q1 label is "the cheapest tier that met the quality bar" (PRD 10.3). About 1,000-1,500 rows are needed (Kev's README: a 400-record fine-tune gain was within noise). Hand-rating that many is not feasible. A judge that grades its own provider's output may favour it, which would bias labels toward the expensive tier.

## Decision
Generate about 1,500 synthetic briefs, run them through each configured tier, and label with the verifier plus an LLM judge. The judge is picked per row from a different provider `family` than the generator; startup fails if no valid judge exists. Joe rates 100 sampled rows, and the judge's agreement is reported before labels are trusted. Budget: `labelling_budget_usd: 20`.

## Options considered
| Option | Why not chosen |
|---|---|
| Hand-label every row | **[Joe]** |
| A single fixed judge | It would grade its own family when that family is a tier. **[Joe]** |
| Verifier pass only, no judge | **[Joe]** |

## Consequences
- Easier: enough rows to train and calibrate.
- Harder: labels inherit the judge's errors; the judge's agreement with Joe bounds the claim.
- **[Joe]**

## Evidence
No measurement yet. The test: judge vs Joe agreement on 100 rows, reported with an interval and the position-bias check from PRD 11.4.

## Revisit trigger
Judge agreement with Joe is too low to trust (threshold: **[Joe]**), or the judge's cost exceeds the budget.
