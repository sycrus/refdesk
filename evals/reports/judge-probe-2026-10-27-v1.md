# Judge probe, v1 set (2026-10-27)

> **Synthetic test with known answers.** Each item is a one-sentence rationale built from
> a real record's fields. Half are faithful (record facts plus an opinion about mood);
> half contain exactly one false fact. It measures whether a model catches a false
> fact against the record. It is not agreement with Joe's judgement (needs the 100
> ratings, #16), and real rationales are longer and harder.

- Items: 60 (30 faithful, 30 corrupted: 6 each of wrong_date, wrong_artist, wrong_medium, invented_provenance, invented_subject). Seed 0, temperature 0, thinking off where supported.
- Hardware: RTX 5080 (16 GB), Ollama. One model on the GPU at a time.

| Model | Accuracy [95% CI] | Catches false facts | False alarms | Invalid | VRAM | On GPU | Load | Median per item |
|---|---|---|---|---|---|---|---|---|
| `phi4 (per claim)` | 1.000 [1.000, 1.000] | 100% | 0% | 0% | 9.3 GB | 100% | 23 s | 0.17 s |
| `granite3-guardian:8b (per claim)` | 1.000 [1.000, 1.000] | 100% | 0% | 0% | 6.4 GB | 100% | 5 s | 0.19 s |
| `phi4` | 0.983 [0.950, 1.000] | 97% | 0% | 0% | 9.3 GB | 100% | 23 s | 0.07 s |
| `granite3-guardian:8b` | 0.867 [0.783, 0.950] | 97% | 23% | 0% | 6.4 GB | 100% | 5 s | 0.07 s |

## Catch rate by error type

| Model | wrong_date | wrong_artist | wrong_medium | invented_provenance | invented_subject |
|---|---|---|---|---|---|
| `phi4 (per claim)` | 100% | 100% | 100% | 100% | 100% |
| `granite3-guardian:8b (per claim)` | 100% | 100% | 100% | 100% | 100% |
| `phi4` | 100% | 100% | 100% | 100% | 83% |
| `granite3-guardian:8b` | 100% | 100% | 100% | 83% | 100% |
