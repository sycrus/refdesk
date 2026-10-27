# ADR-022: Rationale verification by structured claims

- **Status:** accepted by Joe, 2026-10-27.
- **Date:** 2026-10-26; judge changed 2026-10-27

## Context
FR-5: rationales come only from retrieved records, and a verifier checks each factual claim against the record. FR-6: an inferred or unverifiable attribution is "Needs human check". The UI shows evidence chips linked to record fields (PRD 8A) and must never show an unverified claim as verified (gate G2, PRD 8B). ADR-021 first chose two judges (`granite3-guardian:8b` per claim, `phi4` as cross-check, never the generator's family) and sketched this design as "proposed for M3". It is a separate decision from routing labels, so it gets its own record.

## Decision
The generator returns a rationale as structured claims, each naming the record field it rests on, plus one separate sentence about fit. Checks run in order: (1) plain code checks each field claim against the record's own value; (2) **`phi4` alone** checks each remaining claim, one at a time; (3) `phi4` checks that the fit sentence adds no fact absent from the record. Any failure makes the item "Needs human check" and names the failing claim. `granite3-guardian:8b` is dropped (Joe, 2026-10-27): in the hard probe, built closer to how rationales will actually be produced, it missed every dropped attribution prefix, while phi4 per claim caught all 40 errors with no false alarms. **Pass rule (Joe, 2026-10-27, issue #97):** SUPPORTED passes, UNSUPPORTED fails, a malformed answer gets one retry and then counts as a fail. Claims are judged with the probe's exact instruction (`prompts/judge-v1.md`). The fit sentence uses its own instruction (`prompts/fit-v1.md`), because judge-v1 flagged pure opinion as unsupported (see Evidence).

## Options considered
| Option | Why not chosen |
|---|---|
| Free-text rationale, split into claims afterwards by a model | A splitting model can drop or merge the very claim that is wrong (PRD 10) |
| One judge call on the whole rationale | Measured worse: on the hard probe, phi4 on the whole rationale caught 82% and missed 7 of 10 dropped attribution prefixes; per claim it caught 100% |
| Code checks only, no model judge | Code can only compare values. It may miss the meaning of claims that paraphrase or combine longer text fields, which needs a semantic check |
| Two judges (Granite per claim, phi4 as cross-check), as first chosen in ADR-021 | phi4 alone was as good or better on every probe, and Granite missed all dropped attribution prefixes (FR-6). A second judge also means a second model swap |

## Consequences
- Easier: each evidence chip maps to one checked claim; a failure names the claim; most claims are checked by code, with no model call.
- Harder: the generator must return valid structure (malformed output needs a retry and a failure path); the prompt and schema are versioned together; judging needs the judge model loaded once per phase (`ModelManager`).
- Harder: a model swap between generating and judging (the local generator and phi4 cannot share the GPU). With one judge, that is one swap, not two.
- Harder: one judge means no second opinion; a blind spot in phi4 would go unnoticed until the rationale eval (#102) or Joe's ratings (#16) find it.

## Evidence
Judge probe, 2026-10-12 (issue #58, `evals/reports/judge-probe-2026-10-12.md`): 60 synthetic one-sentence rationales, half with one planted false fact. `granite3-guardian:8b` checking one claim at a time caught 100% of false facts with 0% false alarms; the same model on the whole sentence caught 97% with 23% false alarms. `phi4` on the whole sentence: 97% caught, 0% false alarms. Synthetic and short, so this screens judges; it is not agreement with Joe (#16).

Judge probe v2, 2026-10-27 (issue #122), both judges in both modes:
- v1 set again (`evals/reports/judge-probe-2026-10-27-v1.md`): `phi4` per claim 100% caught, 0% false alarms, the same as Granite per claim. Whole sentence: phi4 97% / 0%, Granite 97% / 23%.
- Hard set (`evals/reports/judge-probe-2026-10-27-hard.md`): 80 five-claim rationales from real records, faithful ones paraphrased, one subtle error each. `phi4` per claim: 100% caught (40/40), 0% false alarms. `phi4` whole rationale: 82%, missing 7 of 10 dropped attribution prefixes. Granite per claim: 75%, missing **all 10** dropped attribution prefixes ("Workshop of X" stated as "by X"), which is the error FR-6 exists for. Granite whole rationale: 57%.
- Limits: synthetic, 40 corrupted items (a 100% score is consistent with a true miss rate up to about 7%), one seed; Met records have no long description text, so checks across paragraph fields are untested. VRAM measured this time: phi4 9.3 GB, Granite 6.4 GB.

Fit-sentence probe, 2026-10-27 (issue #97, `evals/reports/fit-probe-2026-10-27.md`): 40 fit sentences on real records, 20 pure opinion and 20 with one smuggled fact. judge-v1: 20/20 facts caught but **17/20 false alarms** on pure opinion (it would send almost every item to human check). fit-v1: 19/20 caught (missed a smuggled "Venetian setting"), 2/20 false alarms ("The men give it a warm feel" where Men is a record tag; "restrained palette"). Not reviewed by Joe yet: the fit-v1 wording is Claude Code's, chosen on this measurement. Smoke test against local phi4 (`scripts/smoke_judge.py`): a faithful rationale is verified; one with a dropped "Workshop of" and an added patron fails in code and in the judge, naming both claims.

No measurement yet of the full verifier; the rationale eval (issue #102) supplies it, on golden-v1 for any claim.

Prompt comparison on golden-v0 (plumbing only), 2026-10-27 (issue #135, `evals/reports/rationale-prompts-2026-10-27.md`), qwen3.5:9b + phi4: verified 0.18 (rationale-v1 + fit-v1), 0.38 (rationale-v2 + fit-v1), 0.68 (rationale-v2 + fit-v2). rationale-v2 cut judge flags on claims from 41 to 3; most remaining flags are on the fit sentence, which qwen keeps filling with record facts. Realistic fit probe (`evals/reports/fit-probe-2026-10-27-realistic.md`): fit-v2 (judge sees the brief) caught 13/20 smuggled facts against fit-v1's 20/20. Not decided yet: which prompts to pin, and whether the fit verdict should withhold "Attribution verified from record" (option 3 in the report).

## Revisit trigger
Code checks cover too few claims to matter, phi4 misses planted false facts beyond the rule in #97 (including on records with long description text, once a source has them), or generators cannot return valid structure reliably.
