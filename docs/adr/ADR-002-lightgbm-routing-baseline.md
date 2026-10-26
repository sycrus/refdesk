# ADR-002: LightGBM as a baseline for structured-feature routing

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
The decision step answers Q1, "which tier should handle this request?" (PRD 10.1, FR-7). ADR-001 chose a fine-tuned Kev-4B for it. Design principle 4 (PRD 1A) says a complex method must beat a simple one on validation data. A router can only use features available before the decision; a feature that needs the local model's answer makes it a cascade (PRD 12).

## Decision
Train LightGBM on pre-decision features (token count, option count, top retrieval score, number of conditions, usage mode, avoid-list present; PRD 10.3) as one of the routing baselines, on the same split as Kev. Kev is kept only if it beats LightGBM and the confidence cascade. LightGBM decisions are explained with Tree SHAP (PRD 13).

## Options considered
| Option | Why not chosen |
|---|---|
| No learned baseline: rules and the cascade only | **[Joe]** |
| A linear model (logistic regression) on the same features | **[Joe]** |
| Another gradient-boosting library | **[Joe]** |

## Consequences
- Easier: a cheap, fast baseline whose decisions can be explained per feature (Tree SHAP); Kev's gain is measured against something real.
- Harder: LightGBM is a new dependency (not installed yet; added in M4); the feature list must stay limited to what exists before the decision.
- **[Joe]**

## Evidence
No measurement yet. The M4 baselines table (PRD 10.3, "Baselines on the same split") supplies it.

## Revisit trigger
LightGBM matches or beats Kev-4B on the validation split (then ADR-001's revisit trigger applies), or a needed feature turns out to be unavailable before the decision.
