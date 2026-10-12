# Eval report: combined on golden v0-synthetic (2026-10-12)

> **Golden set is synthetic. Never use for claims (ADR-018).** Its expected
> references come from rules over metadata, which favour the metadata baseline.
> These numbers test the harness; they do not measure retrieval quality.

## Config

- Config hash: `dd2089b9d36e` (manifest: `runs/dd2089b9d36e/manifest.json`)
- Golden set: `evals/golden/golden-v0-synthetic.jsonl`, version `v0-synthetic`, sha256 `9e07ef1f9795`
- Corpus version: `met:2588:d188937d8a53`
- Retriever: `combined` {"weights": {"similarity": 0.6, "attributes": 0.4}, "conditions": {"period": "boost", "material": "boost", "motif": "boost", "department": "boost"}}; k = 12
- Git: `13cf24907f3e`
- Model: none (retrieval only). Scorers: `scorers-v1`. Bootstrap: 2000 resamples, seed 0
- Deterministic across two runs: yes
- Wall-clock: 0.42 s. Cost: USD 0.00
- Gates: draft. Tripwire only; no thresholds set. (`docs/eval-gate-policy.md`)

## Scores (mean with 95% CI)

| Metric | Score |
|---|---|
| recall@k (capped: hits / min(relevant, k)) | 0.697 [0.575, 0.814] (n=28) |
| precision@k | 0.670 [0.548, 0.786] (n=28) |
| MRR | 0.839 [0.714, 0.946] (n=28) |
| open-rights share of top k (reproduction cases) | 1.000 [1.000, 1.000] (n=2) |

## Recall by difficulty (95% CI)

| Slice | Recall |
|---|---|
| easy | 0.900 [0.811, 0.976] (n=7) |
| hard | 0.550 [0.233, 0.850] (n=5) |
| medium | 0.654 [0.474, 0.818] (n=16) |

## Recall by usage mode (95% CI)

| Slice | Recall |
|---|---|
| reference_only | 0.712 [0.584, 0.829] (n=26) |
| reproduction | 0.500 [0.000, 1.000] (n=2) |

## Failure categories

| Category | Cases | Example |
|---|---|---|
| partial | 16 | g0-001 |
| full | 10 | g0-002 |
| no_relevant_in_top_k | 2 | g0-019 |

## Not scored

- g0-029: not applicable: decline case
- g0-030: not applicable: decline case
- g0-031: not applicable: decline case

## Per case

| Case | Difficulty | Recall | MRR | Open share | Failure |
|---|---|---|---|---|---|
| g0-001 | easy | 0.71 | 0.50 |  | partial |
| g0-002 | easy | 1.00 | 1.00 |  | full |
| g0-003 | easy | 0.92 | 1.00 |  | partial |
| g0-004 | easy | 1.00 | 1.00 |  | full |
| g0-005 | easy | 1.00 | 1.00 |  | full |
| g0-006 | easy | 0.75 | 1.00 |  | partial |
| g0-007 | easy | 0.92 | 1.00 |  | partial |
| g0-008 | medium | 0.17 | 1.00 |  | partial |
| g0-009 | medium | 1.00 | 1.00 |  | full |
| g0-010 | medium | 0.58 | 1.00 |  | partial |
| g0-011 | medium | 1.00 | 1.00 |  | full |
| g0-012 | medium | 0.92 | 1.00 |  | partial |
| g0-013 | medium | 1.00 | 1.00 |  | full |
| g0-014 | medium | 0.33 | 0.33 |  | partial |
| g0-015 | medium | 1.00 | 1.00 |  | full |
| g0-016 | medium | 0.67 | 0.33 |  | partial |
| g0-017 | medium | 1.00 | 1.00 |  | full |
| g0-018 | medium | 0.80 | 1.00 |  | partial |
| g0-019 | medium | 0.00 | 0.00 |  | no_relevant_in_top_k |
| g0-020 | medium | 0.25 | 1.00 |  | partial |
| g0-021 | hard | 0.33 | 1.00 |  | partial |
| g0-022 | hard | 0.83 | 1.00 |  | partial |
| g0-023 | medium | 0.58 | 1.00 |  | partial |
| g0-024 | medium | 0.17 | 0.33 |  | partial |
| g0-025 | medium | 1.00 | 1.00 | 1.00 | full |
| g0-026 | hard | 0.00 | 0.00 | 1.00 | no_relevant_in_top_k |
| g0-027 | hard | 1.00 | 1.00 |  | full |
| g0-028 | hard | 0.58 | 1.00 |  | partial |
