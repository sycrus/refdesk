# Eval report: jaccard on golden v0-synthetic (2026-10-11)

> **Golden set is synthetic. Never use for claims (ADR-018).** Its expected
> references come from rules over metadata, which favour the metadata baseline.
> These numbers test the harness; they do not measure retrieval quality.

## Config

- Config hash: `fb5462038a93` (manifest: `runs/fb5462038a93/manifest.json`)
- Golden set: `evals/golden/golden-v0-synthetic.jsonl`, version `v0-synthetic`, sha256 `9e07ef1f9795`
- Corpus version: `met:2588:d188937d8a53`
- Retriever: `jaccard` {}; k = 12
- Git: `ef46e70d7467` (uncommitted changes)
- Model: none (retrieval only). Scorers: `scorers-v1`. Bootstrap: 2000 resamples, seed 0
- Deterministic across two runs: yes
- Wall-clock: 0.04 s. Cost: USD 0.00
- Gates: draft. Tripwire only; no thresholds set. (`docs/eval-gate-policy.md`)

## Scores (mean with 95% CI)

| Metric | Score |
|---|---|
| recall@k (capped: hits / min(relevant, k)) | 0.655 [0.535, 0.770] (n=28) |
| precision@k | 0.634 [0.506, 0.753] (n=28) |
| MRR | 0.775 [0.642, 0.893] (n=28) |
| open-rights share of top k (reproduction cases) | 1.000 [1.000, 1.000] (n=2) |

## Recall by difficulty (95% CI)

| Slice | Recall |
|---|---|
| easy | 0.827 [0.622, 0.976] (n=7) |
| hard | 0.533 [0.200, 0.867] (n=5) |
| medium | 0.618 [0.454, 0.771] (n=16) |

## Recall by usage mode (95% CI)

| Slice | Recall |
|---|---|
| reference_only | 0.667 [0.535, 0.790] (n=26) |
| reproduction | 0.500 [0.000, 1.000] (n=2) |

## Failure categories

| Category | Cases | Example |
|---|---|---|
| partial | 17 | g0-001 |
| full | 9 | g0-003 |
| no_relevant_in_top_k | 2 | g0-019 |

## Not scored

- g0-029: not applicable: decline case
- g0-030: not applicable: decline case
- g0-031: not applicable: decline case

## Per case

| Case | Difficulty | Recall | MRR | Open share | Failure |
|---|---|---|---|---|---|
| g0-001 | easy | 0.29 | 1.00 |  | partial |
| g0-002 | easy | 0.83 | 0.33 |  | partial |
| g0-003 | easy | 1.00 | 1.00 |  | full |
| g0-004 | easy | 1.00 | 1.00 |  | full |
| g0-005 | easy | 1.00 | 1.00 |  | full |
| g0-006 | easy | 0.67 | 0.33 |  | partial |
| g0-007 | easy | 1.00 | 1.00 |  | full |
| g0-008 | medium | 0.42 | 0.33 |  | partial |
| g0-009 | medium | 1.00 | 1.00 |  | full |
| g0-010 | medium | 0.33 | 1.00 |  | partial |
| g0-011 | medium | 0.67 | 1.00 |  | partial |
| g0-012 | medium | 1.00 | 1.00 |  | full |
| g0-013 | medium | 0.92 | 1.00 |  | partial |
| g0-014 | medium | 0.42 | 0.50 |  | partial |
| g0-015 | medium | 1.00 | 1.00 |  | full |
| g0-016 | medium | 0.25 | 0.20 |  | partial |
| g0-017 | medium | 0.67 | 1.00 |  | partial |
| g0-018 | medium | 0.80 | 1.00 |  | partial |
| g0-019 | medium | 0.00 | 0.00 |  | no_relevant_in_top_k |
| g0-020 | medium | 0.33 | 0.50 |  | partial |
| g0-021 | hard | 0.25 | 1.00 |  | partial |
| g0-022 | hard | 0.92 | 0.50 |  | partial |
| g0-023 | medium | 0.83 | 1.00 |  | partial |
| g0-024 | medium | 0.25 | 1.00 |  | partial |
| g0-025 | medium | 1.00 | 1.00 | 1.00 | full |
| g0-026 | hard | 0.00 | 0.00 | 1.00 | no_relevant_in_top_k |
| g0-027 | hard | 1.00 | 1.00 |  | full |
| g0-028 | hard | 0.50 | 1.00 |  | partial |
