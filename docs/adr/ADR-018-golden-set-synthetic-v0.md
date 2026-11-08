# ADR-018: Golden set in two kinds, synthetic v0 and reviewed v1

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-11

## Context
The eval harness, scorers and reports (M1) need cases before Joe has time to label 40-50 briefs. If the model that builds the system also picks the expected answers, the eval measures agreement with the model's own guesses (PRD 11).

## Decision
`golden-v0-synthetic` is generated in full by Claude Code, every case marked `provenance: synthetic`, and used only to build and test the harness. `golden-v1` onwards is required before any eval number goes public, and is labelled this way (amended 2026-10-26):

1. Claude Code drafts the briefs; Joe edits them.
2. **Blind subset first:** Joe labels 20 cases from unranked candidates, before seeing any proposal. A day later he relabels the same 20 without looking, to measure his self-agreement.
3. Claude Code proposes expected references and grades for every case, each citing the record fields it rests on.
4. A judge from another family than Claude, `phi4` (ADR-021, ADR-022), checks each proposal for relevance to the brief and any stated fact against the record. Disagreements are flagged for Joe.
5. **Joe reviews every label** and accepts or corrects it. Each case records who proposed, who judged, and whether Joe changed it.
6. The report states Claude's agreement with Joe's blind labels, Joe's self-agreement, and the share of proposals Joe corrected.

**Rubric.** A candidate is relevant if it fits the brief's meaning, including its subjective qualifiers (for example "staged dramatically"), as far as the brief specifies them; judged semantically, not by keyword. Briefs vary in detail on purpose, and reports break results down by detail level.

**Trust rules.** v1 is frozen only if both hold:
- **Gap:** Claude's agreement with Joe's blind labels is no more than 5 points below Joe's self-agreement on the same 20 briefs. Judged on the paired bootstrap interval: it fails if the whole interval is above 5; if the interval straddles 5, more blind cases are added.
- **Anchoring:** Joe's correction rate in review is no more than 5 points below his blind disagreement rate (for example, 20% blind disagreement needs at least 15% corrections). If it fails, the reviewed cases are relabelled blind.

Every case carries a `corpus_version`; expected references come only from ingested records.

**Amendment 2026-11-08: round 2 after the anchoring fail** (Joe, 2026-11-08, #15). The first trust check (`evals/reports/golden-v1-trust-2026-11-08-08a56219e537.md`) gave gap 1.9 points [-2.5, 6.8], so "add blind cases", and anchoring fail: corrections 18.2% against blind disagreement 41.7%.

1. **More blind cases.** About 25 new briefs (`briefs-draft-b2.jsonl`), labelled blind twice, a day apart, as in step 2. The gap rule is rerun over all blind cases.
2. **Blind relabel of the 21 reviewed cases**, a few days after the review, from `review-relabel.csv` (no proposals, verdicts or review labels; new order).
3. **Rerun anchoring rule, option (iii):** relevance and grade are checked separately, on the same 21 cases, each on a paired bootstrap interval over cases:
   - **Relevance:** per case, the share of Claude's proposals Joe's blind relabel marks not relevant, minus the share Joe rejected in review. Passes if the whole interval is at or below 5 points.
   - **Grade:** among Claude's proposals Joe marked relevant in both relabel and review, the share where his blind grade differs from Claude's, minus the share he regraded in review. Tolerance: Joe's own grade inconsistency between his two blind passes, 17.0 points (same grade on 117 of 141 works both passes marked relevant). Passes if the whole interval is at or below that.
   - *Proposed, for Joe to confirm:* an interval that straddles its limit counts as a fail.
4. **Where review and blind relabel labels differ,** Joe settles each one with both shown, and both are recorded (D3).
5. **If a rule still fails,** the blind relabel labels replace the review labels for those cases, with a caveat in every report that uses v1 (D5).

Disclosure: option (iii) was chosen after seeing that a relevance-only comparison on round 1 would have been 4.8 points (7.2% blind vs 2.4% rejected), and that the gap was mostly grades. It was fixed before any relabel or new blind label existed.

[Joe] Why (iii), and why grade tolerance comes from self-inconsistency: _to write_.

## Options considered
| Option | Why not chosen |
|---|---|
| Wait for hand labels before building the harness | Hand labelling takes time, and a working prototype is needed to test first. The synthetic set unblocks building; hand labels gate only claims |
| Use the synthetic set for claims too | Circular, not just early: v0's answers come from rules over the same metadata the retrievers use, so its scores partly measure agreement with those rules (the 2026-10-12 comparison favours the metadata baseline by construction). A claim needs answers made independently of the system |
| Hand labels from scratch for v1 | Too slow for the prototype. Chosen instead: LLM-proposed, cross-family judged, every label reviewed by Joe, with a blind subset to measure anchoring |
| LLM-labelled set, Joe reviews a sample only | Part of v1 would be unreviewed. Joe reviews every label |

## Consequences
- Easier: M1 is not blocked on labelling.
- Harder: two sets to keep apart; every report must state which set produced each number.
- Harder: v1 labels start from Claude's proposals, so a reviewer may anchor on them; the blind subset measures how much. Claims from v1 must state that labels were proposed by Claude and reviewed by Joe.
- Harder: the judges were screened on false facts (judge probe), not on relevance to a brief; their use here is unmeasured until the blind subset is compared.
- Harder: Claude Code built the system and proposes v1's answers, so claims rest partly on one source. The blind subset, cross-family judges and full review limit this; claims must say how v1 was labelled.
- Harder: the rubric includes subjective qualifiers, so agreement (Joe with himself, and Claude with Joe) will be lower than for keyword relevance; the gap rule compares against Joe's self-agreement for that reason.

## Evidence
No measurement yet. Tests: (1) once v1 exists, compare harness metrics on v0 and v1 and report how far the synthetic set misled; (2) agreement between Claude's proposals and Joe's blind labels on the subset.

## Revisit trigger
v0 and v1 disagree enough that decisions made on v0 would have changed, or either trust rule fails (gap or anchoring), or user testing shows the rubric misses what art directors care about.
