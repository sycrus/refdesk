# ADR-001: Fine-tune Kev-4B as the decision model

- **Status:** accepted by Joe, 2026-10-26
- **Date:** 2026-10-11

## Context
The router answers one question in v1: which tier handles this request (PRD 10.1, Q1). The decision model must return calibrated probabilities so policy code can set thresholds and abstain (PRD 10.3). The machine has one RTX 5080 (16 GB, about 14 GB free) and WSL2 Ubuntu-24.04.

## Decision
Fine-tune **Kev-4B** from `jaredpalmer/kev-4b@v1.0` on routing labels. Train in WSL2 locally first; fall back to Modal under `training_budget_usd: 10`. Serve from pre-merged full weights. Keep Kev-0.8B as a size ablation. (Amends the seed decision "start with the smallest base".)

The base (zero-shot) Kev-4B is served first. The fine-tuned model replaces it only if it beats the base model by a significant margin on the validation split; otherwise the base model stays and the result is reported (PRD 1A, principle 4). Kev-4B is the first backend behind the decision contract, not the only one: other decision models that speak the same contract can be added as adapters.

## Options considered
| Option | Why not chosen |
|---|---|
| Laya | not measured; added as a baseline in M4 |
| Hosted Jev | No publicly released model for self hosting |
| Kev-0.8B as the main model | Facts: 0.648 dev accuracy on new sources vs 0.817 for 4B. Accuracy not as good given local specs (RTX 5080 16GB VRAM) |
| Kev-9B | Facts: about 17 GB to serve; does not fit locally |
| Zero-shot Kev, no fine-tune | Kept as a baseline, not the decision, check in M4 |
| H2O-Lightning-4B | Same typed-question contract; reported performance is potentially better. Not chosen yet: not measured here, no Kev comparison published, fit on 16 GB and fine-tuning support unconfirmed. Candidate adapter behind the contract |

## Consequences
- Easier: one `base_url` swap between Kev, the cascade and LightGBM (PRD 10.3).
- Harder: WSL2 process management; no unload endpoint, so stopping means killing the process (`scripts/kev.ps1`).
- Locked in: the typed-question contract (choice, yes/no, score, each with calibrated probabilities). Routing labels, policy code and the decision contract (PRD 10.1) depend on it, so any backend must speak it. Current decision models share this shape (Kev, H2O-Lightning-4B), so they are interchangeable behind it.
- Locked in: phased GPU use. Nothing local fits next to Kev-4B, so models swap once per phase (decide, generate, judge). Local runs wait for those swaps; that is an accepted, stated constraint of the local tier.
- Locked in: pre-merged weights for local serving. Loading the adapter separately peaks at 15.9 GB against about 14 GB free, so each retrain (when labels change: a tier's model, the quality bar or the tier list) ends with one CPU merge.
- Not locked in: the backend. Decision models are changing fast, so new ones are added as adapters behind the contract rather than replacing it. LightGBM and the cascade use the same labels with different inputs and swap in the same way.

## Evidence
- Kev README, checked 2026-10-11: sizes, validated context 8,192 for 4B, dev/test accuracy, a 400-record fine-tune gain within noise, adapter-path load peak 15.9 GB vs 8.4 GB for full weights (measured on MLX). https://github.com/jaredpalmer/kev
- Kev fine-tune README, checked 2026-10-26 (https://github.com/jaredpalmer/kev/blob/main/skills/kev-finetune/README.md): about 1,000 records for a +5-point gain with three questions per record (400 was inside the noise); example run 15 minutes on an H100, about $1 per Kev-4B run on Modal; example gain on its own workload 67.7% to 73.6% accuracy (95% CI on the gain +2.3 to +9.7 points). Fine-tuning fits a temperature to your data, which makes thresholds meaningful.
- H2O-Lightning-4B model card v1.4.0.2, checked 2026-10-26 (https://huggingface.co/h2oai/h2o-lightning-4b): built on Qwen3.5-4B, Apache-2.0, choice / yes-no / score (plus box) with calibrated probabilities, not a chat model; 9.3 GB weights; measured on a 48 GB L40S, notes that 24 GB GPUs need adjusted settings; needs vLLM 0.30.0 (a custom build for its recommended mode). Benchmarks are against its own earlier version; no Kev comparison; user fine-tuning not stated.
- Local VRAM need: no measurement yet. Estimate 9-10 GB for short routing inputs; the first training run measures it.

## Revisit trigger
Kev-4B fails to beat LightGBM or the cascade on the validation split, or local training does not fit and Modal cost exceeds the budget, or another decision model behind the same contract (for example H2O-Lightning-4B) beats Kev-4B on the validation split.
