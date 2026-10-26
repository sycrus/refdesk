# ADR-022: Rationale verification by structured claims

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-26

## Context
FR-5: rationales come only from retrieved records, and a verifier checks each factual claim against the record. FR-6: an inferred or unverifiable attribution is "Needs human check". The UI shows evidence chips linked to record fields (PRD 8A) and must never show an unverified claim as verified (gate G2, PRD 8B). ADR-021 chose the judges (`granite3-guardian:8b` per claim, `phi4` as cross-check, never the generator's family) and sketched this design as "proposed for M3". It is a separate decision from routing labels, so it gets its own record.

## Decision
The generator returns a rationale as structured claims, each naming the record field it rests on, plus one separate sentence about fit. Checks run in order: (1) plain code checks each field claim against the record's own value; (2) `granite3-guardian:8b` checks each remaining claim, one at a time; (3) `phi4` checks that the fit sentence adds no fact absent from the record. Any failure makes the item "Needs human check" and names the failing claim. Judge pass thresholds: **[Joe]**, decided in issue #97 and recorded here.

## Options considered
| Option | Why not chosen |
|---|---|
| Free-text rationale, split into claims afterwards by a model | A splitting model can drop or merge the very claim that is wrong (PRD 10). **[Joe]** |
| One judge call on the whole rationale | **[Joe]** |
| Code checks only, no model judge | **[Joe]** |

## Consequences
- Easier: each evidence chip maps to one checked claim; a failure names the claim; most claims are checked by code, with no model call.
- Harder: the generator must return valid structure (malformed output needs a retry and a failure path); the prompt and schema are versioned together; judging needs the judge models loaded once per phase (`ModelManager`).
- **[Joe]**

## Evidence
Judge probe, 2026-10-12 (issue #58, `evals/reports/judge-probe-2026-10-12.md`): 60 synthetic one-sentence rationales, half with one planted false fact. `granite3-guardian:8b` checking one claim at a time caught 100% of false facts with 0% false alarms; the same model on the whole sentence caught 97% with 23% false alarms. `phi4` on the whole sentence: 97% caught, 0% false alarms. Synthetic and short, so this screens judges; it is not agreement with Joe (#16).

Judge probe v2, 2026-10-27 (issue #122), both judges in both modes:
- v1 set again (`evals/reports/judge-probe-2026-10-27-v1.md`): `phi4` per claim 100% caught, 0% false alarms, the same as Granite per claim. Whole sentence: phi4 97% / 0%, Granite 97% / 23%.
- Hard set (`evals/reports/judge-probe-2026-10-27-hard.md`): 80 five-claim rationales from real records, faithful ones paraphrased, one subtle error each. `phi4` per claim: 100% caught (40/40), 0% false alarms. `phi4` whole rationale: 82%, missing 7 of 10 dropped attribution prefixes. Granite per claim: 75%, missing **all 10** dropped attribution prefixes ("Workshop of X" stated as "by X"), which is the error FR-6 exists for. Granite whole rationale: 57%.
- Limits: synthetic, 40 corrupted items (a 100% score is consistent with a true miss rate up to about 7%), one seed; Met records have no long description text, so checks across paragraph fields are untested. VRAM measured this time: phi4 9.3 GB, Granite 6.4 GB.

No measurement yet of the full verifier; the rationale eval (issue #102) supplies it, on golden-v1 for any claim.

## Revisit trigger
Code checks cover too few claims to matter, a judge misses planted false facts above the threshold in #97, or generators cannot return valid structure reliably.
