# ADR-021: Synthetic routing labels with a cross-family judge

- **Status:** accepted by Joe, 2026-10-12 (judge choice). Reasoning sections marked **[Joe]** still to write.
- **Date:** 2026-10-11; judges chosen 2026-10-12

## Context
Kev's Q1 label is "the cheapest tier that met the quality bar" (PRD 10.3). About 1,000-1,500 rows are needed (Kev's README: a 400-record fine-tune gain was within noise). Hand-rating that many is not feasible. A judge that grades its own provider's output may favour it, which would bias labels toward the expensive tier.

## Decision
Generate about 1,500 synthetic briefs, run them through each configured tier, and label with the verifier plus an LLM judge. The judge is picked per row from a different provider `family` than the generator; startup fails if no valid judge exists. Joe rates 100 sampled rows, and the judge's agreement is reported before labels are trusted. Budget: `labelling_budget_usd: 20`.

**Judge (amended by Joe, 2026-10-27): `phi4` (Microsoft) alone, checking one claim at a time**, local and from a family other than the generators (Qwen local, DeepSeek cloud). Granite Guardian is dropped: the hard probe (issue #122) showed it missed every dropped attribution prefix, while phi4 per claim caught every planted error. See ADR-022.

**Judges as first chosen (Joe, 2026-10-12), superseded above:**
- **Primary: `granite3-guardian:8b` (IBM), checking one factual claim at a time** in its groundedness mode.
- **Cross-check: `phi4` (Microsoft)** as a general judge, including on the free-text "fit" sentence (does it slip in any fact that is not in the record?).

**How claims reach the judge (proposed for M3, not yet built; now recorded in [ADR-022](ADR-022-rationale-verification-structured-claims.md)):** the generator returns structured claims, each naming the record field it comes from, plus a separate opinion sentence about fit. Field-value claims are checked by plain code first; phi4 checks the rest one claim at a time, and the fit sentence (Granite in the original version). Any failure makes the item "Needs human check" with the failing claim named. Rationales are not split after the fact, because a splitting model can drop or merge the very claim that is wrong.

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
- Judge probe, 2026-10-12 ([report](../../evals/reports/judge-probe-2026-10-12.md), PR #59): 60 synthetic items with known answers (30 faithful, 30 with exactly one false fact), 9 local models on the RTX 5080. Granite Guardian per claim 1.000 [1.000, 1.000], 0% false alarms, 7.2 GB; phi4 0.983 [0.950, 1.000], 0% false alarms, 11.8 GB. Whole-sentence use of claim checkers fails (MiniCheck rejected every faithful rationale; Guardian 23% false alarms), which is why claims are checked one at a time. Synthetic and easy: rules models out, does not rank the top ones.
- Judge probe v2, 2026-10-27 (issue #122, `evals/reports/judge-probe-2026-10-27-hard.md`): on 80 harder five-claim items, phi4 per claim 100% caught, 0% false alarms; Granite per claim 75%, 0 of 10 dropped attribution prefixes. Basis for the amendment.
- Still needed: the judge's agreement with Joe on 100 sampled rows (#16), with an interval, before any label is trusted.

## Revisit trigger
Judge agreement with Joe is too low to trust (threshold: **[Joe]**), or the judge's cost exceeds the budget.
