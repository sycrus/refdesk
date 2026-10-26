# Judge probe, hard set (2026-10-27)

> **Synthetic test with known answers, hard set (#122).** Each item is a five-claim
> rationale built from a real record, claims in random order, plus an opinion. Faithful
> items are paraphrased (to tempt false alarms); corrupted items carry one subtle error:
> a date just outside the record's range, a dropped attribution prefix, a subject more
> specific than the record, or canvas and wood swapped. Not agreement with Joe's
> judgement (#16). Met records have no long description text, so checks across
> paragraph fields remain untested.

- Items: 80 (40 faithful, 40 corrupted: 10 each of near_date, dropped_prefix, overspecific_subject, near_medium). Seed 0, temperature 0, thinking off where supported.
- Hardware: RTX 5080 (16 GB), Ollama. One model on the GPU at a time.

| Model | Accuracy [95% CI] | Catches false facts | False alarms | Invalid | VRAM | On GPU | Load | Median per item |
|---|---|---|---|---|---|---|---|---|
| `phi4 (per claim)` | 1.000 [1.000, 1.000] | 100% | 0% | 0% | 9.3 GB | 100% | 4 s | 0.26 s |
| `phi4` | 0.912 [0.850, 0.963] | 82% | 0% | 0% | 9.3 GB | 100% | 4 s | 0.08 s |
| `granite3-guardian:8b (per claim)` | 0.875 [0.800, 0.938] | 75% | 0% | 0% | 6.4 GB | 100% | 2 s | 0.31 s |
| `granite3-guardian:8b` | 0.787 [0.688, 0.875] | 57% | 0% | 0% | 6.4 GB | 100% | 2 s | 0.08 s |

## Catch rate by error type

| Model | near_date | dropped_prefix | overspecific_subject | near_medium |
|---|---|---|---|---|
| `phi4 (per claim)` | 100% | 100% | 100% | 100% |
| `phi4` | 100% | 30% | 100% | 100% |
| `granite3-guardian:8b (per claim)` | 100% | 0% | 100% | 100% |
| `granite3-guardian:8b` | 100% | 0% | 90% | 40% |
