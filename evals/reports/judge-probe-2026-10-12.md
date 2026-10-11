# Judge probe (2026-10-12)

> **Synthetic test with known answers.** Each item is a one-sentence rationale built from
> a real record's fields. Half are faithful (record facts plus an opinion about mood);
> half contain exactly one false fact. It measures whether a model catches a false
> fact against the record. It is not agreement with Joe's judgement (needs the 100
> ratings, #16), and real rationales are longer and harder.

- Items: 60 (30 faithful, 30 corrupted: 6 each of wrong_date, wrong_artist, wrong_medium, invented_provenance, invented_subject). Seed 0, temperature 0, thinking off where supported.
- Hardware: RTX 5080 (16 GB), Ollama. One model on the GPU at a time.

| Model | Accuracy [95% CI] | Catches false facts | False alarms | Invalid | VRAM | On GPU | Load | Median per item |
|---|---|---|---|---|---|---|---|---|
| `granite3-guardian:8b (per claim)` | 1.000 [1.000, 1.000] | 100% | 0% | 0% | 7.3 GB | 100% | 6 s | 0.19 s |
| `phi4` | 0.983 [0.950, 1.000] | 97% | 0% | 0% | 11.8 GB | 100% | 7 s | 0.07 s |
| `bespoke-minicheck:7b (per claim)` | 0.967 [0.917, 1.000] | 100% | 7% | 0% | 9.0 GB | 100% | 7 s | 0.22 s |
| `gemma4:26b-a4b-it-q4_K_M` | 0.967 [0.917, 1.000] | 100% | 7% | 0% | 13.5 GB | 70% | 21 s | 0.63 s |
| `qwen3.5:9b` | 0.967 [0.917, 1.000] | 100% | 7% | 0% | 7.4 GB | 100% | 7 s | 0.10 s |
| `gemma3:12b` | 0.950 [0.900, 1.000] | 90% | 0% | 0% | 10.6 GB | 100% | 9 s | 0.13 s |
| `glm-4.7-flash:Q4_K_M` | 0.900 [0.817, 0.967] | 83% | 3% | 0% | 13.5 GB | 69% | 18 s | 0.18 s |
| `granite3-guardian:8b` | 0.867 [0.783, 0.950] | 97% | 23% | 0% | 7.3 GB | 100% | 6 s | 0.08 s |
| `qwen2.5:14b` | 0.833 [0.733, 0.917] | 100% | 33% | 0% | 13.7 GB | 91% | 10 s | 0.11 s |
| `bespoke-minicheck:7b` | 0.500 [0.367, 0.617] | 100% | 100% | 0% | 9.0 GB | 100% | 7 s | 0.08 s |
| `qwen3:4b` | 0.000 [0.000, 0.000] | 0% | 0% | 100% | 7.3 GB | 100% | 4 s | 0.10 s |

## Catch rate by error type

| Model | wrong_date | wrong_artist | wrong_medium | invented_provenance | invented_subject |
|---|---|---|---|---|---|
| `granite3-guardian:8b (per claim)` | 100% | 100% | 100% | 100% | 100% |
| `phi4` | 100% | 100% | 100% | 100% | 83% |
| `bespoke-minicheck:7b (per claim)` | 100% | 100% | 100% | 100% | 100% |
| `gemma4:26b-a4b-it-q4_K_M` | 100% | 100% | 100% | 100% | 100% |
| `qwen3.5:9b` | 100% | 100% | 100% | 100% | 100% |
| `gemma3:12b` | 100% | 100% | 100% | 100% | 50% |
| `glm-4.7-flash:Q4_K_M` | 100% | 100% | 100% | 17% | 100% |
| `granite3-guardian:8b` | 100% | 100% | 100% | 83% | 100% |
| `qwen2.5:14b` | 100% | 100% | 100% | 100% | 100% |
| `bespoke-minicheck:7b` | 100% | 100% | 100% | 100% | 100% |
| `qwen3:4b` | 0% | 0% | 0% | 0% | 0% |
