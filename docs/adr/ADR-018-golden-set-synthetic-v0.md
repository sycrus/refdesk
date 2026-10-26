# ADR-018: Golden set in two kinds, synthetic v0 and reviewed v1

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-11

## Context
The eval harness, scorers and reports (M1) need cases before Joe has time to label 40-50 briefs. `CLAUDE.md` forbids Claude Code from assigning quality labels or expected references, because the eval would then measure agreement with the model's own guesses (PRD 11).

## Decision
`golden-v0-synthetic` is generated in full by Claude Code, every case marked `provenance: synthetic`, and used only to build and test the harness. `golden-v1` onwards is required before any eval number goes public, and is labelled this way (amended 2026-10-26):

1. Claude Code drafts the briefs; Joe edits them.
2. **Blind subset first:** Joe labels about 10 cases (placeholder) from unranked candidates, before seeing any proposal.
3. Claude Code proposes expected references and grades for every case, each citing the record fields it rests on.
4. Judges from other families than Claude check each proposal (ADR-021: `phi4` on relevance to the brief, `granite3-guardian:8b` on any stated fact against the record). Disagreements are flagged for Joe.
5. **Joe reviews every label** and accepts or corrects it. Each case records who proposed, who judged, and whether Joe changed it.
6. The report states Claude's agreement with Joe's blind labels, and the share of proposals Joe corrected. Every case carries a `corpus_version`; expected references come only from ingested records.

## Options considered
| Option | Why not chosen |
|---|---|
| Wait for hand labels before building the harness | Hand labelling takes time, and a working prototype is needed to test first. The synthetic set unblocks building; hand labels gate only claims |
| Use the synthetic set for claims too | **[Joe]** |
| Hand labels from scratch for v1 | Too slow for the prototype. Chosen instead: LLM-proposed, cross-family judged, every label reviewed by Joe, with a blind subset to measure anchoring |
| LLM-labelled set, Joe reviews a sample only | Part of v1 would be unreviewed. Joe reviews every label |

## Consequences
- Easier: M1 is not blocked on labelling.
- Harder: two sets to keep apart; every report must state which set produced each number.
- Harder: v1 labels start from Claude's proposals, so a reviewer may anchor on them; the blind subset measures how much. Claims from v1 must state that labels were proposed by Claude and reviewed by Joe.
- Harder: the judges were screened on false facts (judge probe), not on relevance to a brief; their use here is unmeasured until the blind subset is compared.
- **[Joe]**

## Evidence
No measurement yet. Tests: (1) once v1 exists, compare harness metrics on v0 and v1 and report how far the synthetic set misled; (2) agreement between Claude's proposals and Joe's blind labels on the subset.

## Revisit trigger
v0 and v1 disagree enough that decisions made on v0 would have changed, or Claude's agreement with Joe's blind labels is low enough that review alone cannot be trusted (threshold: **[Joe]**).
