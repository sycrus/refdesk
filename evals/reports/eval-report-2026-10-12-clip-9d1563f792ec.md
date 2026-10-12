# Eval report: clip on golden v0-synthetic (2026-10-12)

> **Golden set is synthetic. Never use for claims (ADR-018).** Its expected
> references come from rules over metadata, which favour the metadata baseline.
> These numbers test the harness; they do not measure retrieval quality.

## Config

- Config hash: `9d1563f792ec` (manifest: `runs/9d1563f792ec/manifest.json`)
- Golden set: `evals/golden/golden-v0-synthetic.jsonl`, version `v0-synthetic`, sha256 `9e07ef1f9795`
- Corpus version: `met:2588:d188937d8a53`
- Retriever: `clip` {}; k = 12
- Git: `13cf24907f3e`
- Model: none (retrieval only). Scorers: `scorers-v1`. Bootstrap: 2000 resamples, seed 0
- Deterministic across two runs: yes
- Wall-clock: 0.25 s. Cost: USD 0.00
- Gates: draft. Tripwire only; no thresholds set. (`docs/eval-gate-policy.md`)

## Scores (mean with 95% CI)

| Metric | Score |
|---|---|
| recall@k (capped: hits / min(relevant, k)) | 0.454 [0.348, 0.562] (n=28) |
| precision@k | 0.429 [0.330, 0.536] (n=28) |
| MRR | 0.735 [0.607, 0.863] (n=28) |
| open-rights share of top k (reproduction cases) | 1.000 [1.000, 1.000] (n=2) |

## Recall by difficulty (95% CI)

| Slice | Recall |
|---|---|
| easy | 0.486 [0.357, 0.616] (n=7) |
| hard | 0.483 [0.217, 0.750] (n=5) |
| medium | 0.431 [0.279, 0.596] (n=16) |

## Recall by usage mode (95% CI)

| Slice | Recall |
|---|---|
| reference_only | 0.457 [0.353, 0.569] (n=26) |
| reproduction | 0.417 [0.000, 0.833] (n=2) |

## Failure categories

| Category | Cases | Example |
|---|---|---|
| partial | 26 | g0-001 |
| no_relevant_in_top_k | 2 | g0-023 |

## Not scored

- g0-029: not applicable: decline case
- g0-030: not applicable: decline case
- g0-031: not applicable: decline case

## Per case

| Case | Difficulty | Recall | MRR | Open share | Failure |
|---|---|---|---|---|---|
| g0-001 | easy | 0.57 | 1.00 |  | partial |
| g0-002 | easy | 0.75 | 1.00 |  | partial |
| g0-003 | easy | 0.33 | 1.00 |  | partial |
| g0-004 | easy | 0.58 | 1.00 |  | partial |
| g0-005 | easy | 0.25 | 0.25 |  | partial |
| g0-006 | easy | 0.58 | 1.00 |  | partial |
| g0-007 | easy | 0.33 | 0.50 |  | partial |
| g0-008 | medium | 0.17 | 1.00 |  | partial |
| g0-009 | medium | 0.92 | 1.00 |  | partial |
| g0-010 | medium | 0.33 | 0.50 |  | partial |
| g0-011 | medium | 0.58 | 1.00 |  | partial |
| g0-012 | medium | 0.25 | 0.50 |  | partial |
| g0-013 | medium | 0.83 | 1.00 |  | partial |
| g0-014 | medium | 0.42 | 1.00 |  | partial |
| g0-015 | medium | 0.17 | 0.50 |  | partial |
| g0-016 | medium | 0.33 | 0.17 |  | partial |
| g0-017 | medium | 0.92 | 1.00 |  | partial |
| g0-018 | medium | 0.80 | 1.00 |  | partial |
| g0-019 | medium | 0.10 | 0.50 |  | partial |
| g0-020 | medium | 0.08 | 1.00 |  | partial |
| g0-021 | hard | 0.33 | 1.00 |  | partial |
| g0-022 | hard | 0.83 | 0.50 |  | partial |
| g0-023 | medium | 0.00 | 0.00 |  | no_relevant_in_top_k |
| g0-024 | medium | 0.17 | 0.17 |  | partial |
| g0-025 | medium | 0.83 | 1.00 | 1.00 | partial |
| g0-026 | hard | 0.00 | 0.00 | 1.00 | no_relevant_in_top_k |
| g0-027 | hard | 0.83 | 1.00 |  | partial |
| g0-028 | hard | 0.42 | 1.00 |  | partial |
