# Eval gate policy

- **Status:** draft. Tripwire only; no thresholds set.
- **Owner:** Joe. Thresholds, metric definitions and the flake policy are Joe's decisions (CLAUDE.md learning mode). Claude Code may propose wording and measure noise, never set a threshold.
- **Read by:** the run-evals skill, `refdesk eval` (status line shown in every report), and CI once gates exist.

## 1. Principles

1. **No gate without a noise measurement.** A threshold must sit above the measured noise, or the gate fails at random and people learn to ignore it.
2. **Gate on the right golden set.** `golden-v0-synthetic` can only act as a tripwire (did behaviour change?), never as a quality bar (ADR-018). Quality gates wait for `golden-v1`.
3. **Compare like with like.** Two scores are comparable only if the golden version, corpus version and `SCORERS_VERSION` all match. The harness refuses or labels anything else.
4. **Paired, not pooled.** When comparing two versions on the same cases, gate on the per-case differences (paired bootstrap), which is far less noisy than comparing two overall intervals. Built: `uv run python -m refdesk compare <hashA> <hashB>` (#36).

## 2. Metric definitions in force

| Metric | Definition | Version | Decided | Revisit when |
|---|---|---|---|---|
| recall@k | **Capped:** relevant in top k ÷ min(relevant, k) | scorers-v1 | Joe, 2026-10-11 | Graded golden data exists (golden-v1). On golden-v0, capped recall ≈ precision@k because most cases have more than k references |
| precision@k | relevant in top k ÷ k | scorers-v1 | | |
| MRR | 1 ÷ rank of the first relevant item, 0 if none | scorers-v1 | | |
| open-rights share | open items in top k ÷ items in top k (reproduction cases only) | scorers-v1 | | |

Changing any definition means bumping `SCORERS_VERSION` in `src/refdesk/evals/harness.py`. Scores across versions are not compared.

## 3. Noise measurements

| Date | Golden / corpus | System | Run-to-run noise | Case-sampling noise (95% CI width) | Notes |
|---|---|---|---|---|---|
| 2026-10-11 | v0-synthetic / met:2588:d188937d8a53 | Jaccard baseline, k=12 | **0** (deterministic over 2 runs) | recall ±0.12, MRR ±0.13 (n=28) | Config `02add712a369`. No model in the loop |
| 2026-10-12 | v0-synthetic / met:2588:d188937d8a53 | CLIP baseline (ViT-B-32), k=12 | **0** (deterministic over 2 runs) | recall ±0.11, MRR ±0.13 (n=28) | Config `8c995e38a66b`. Paired vs Jaccard: recall −0.201 [−0.323, −0.083] |

How to measure, once a model is in the loop: run the same config **N = [Joe] times**, report the mean and spread per metric, and record the row here. Re-measure when the model, prompts or golden set change.

## 4. Current rule: tripwire on golden-v0 (in force)

While every component is deterministic, **any** change in a golden-v0 score means the code changed behaviour.

- **Rule:** if a PR changes any golden-v0 score, the PR description must say which change caused it and why it is acceptable.
- **Blocks merge:** no. It is a tripwire, not a quality bar.
- **Applies to:** retrieval, rights logic, scorers, and the golden or corpus tooling.

## 5. Quality gates (to define; none in force)

Fill in after golden-v1 exists and noise is measured. Until then, every row is inactive.

| Metric | Golden set | CI tier | Rule | Threshold | On failure | Active |
|---|---|---|---|---|---|---|
| recall@12 (capped) | golden-v1 | PR (recorded responses) | paired drop vs main | [Joe] | block merge | no |
| MRR | golden-v1 | PR | paired drop vs main | [Joe] | block merge | no |
| open-rights share, reproduction | golden-v1 | PR | absolute minimum | [Joe] | block merge | no |
| items shown "verified" with a wrong attribution | golden-v1 | PR | absolute maximum (PRD 15 target: 0) | [Joe] | block merge | no |
| rationale factual accuracy | golden-v1 | nightly (real model) | paired drop | [Joe] | open an issue | no |
| cost per resolved board | golden-v1 | nightly | absolute maximum | [Joe] | open an issue | no |

**Hard invariants vs statistical gates.** Some rules are not about noise at all: a rights or attribution invariant that must always hold (PRD 15: zero wrong attributions shown as verified) belongs in a deterministic test, not a threshold. Decide for each row whether it is a test or a gate. **[Joe]**

## 6. Flake policy

- A gate that fails, then passes on an unchanged re-run: **[Joe]** (for example: allowed once; a second flake opens an issue and the gate is reviewed).
- A gate that flakes more than **[Joe]** times in **[Joe]** runs is suspended, recorded here with the date, and fixed.
- Re-runs are never used to fish for a pass on a real regression.

## 7. Overrides

- Who may override a failing gate: **[Joe]**.
- Every override is recorded in the PR description with the reason and a follow-up issue.

## 8. Change log

| Date | Change | By |
|---|---|---|
| 2026-10-11 | Template created; capped recall confirmed; tripwire on golden-v0 adopted; first noise row recorded | Claude Code drafted, Joe decided |
