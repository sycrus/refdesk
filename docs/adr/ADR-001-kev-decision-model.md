# ADR-001: Fine-tune Kev-4B as the decision model

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-11

## Context
The router answers one question in v1: which tier handles this request (PRD 10.1, Q1). The decision model must return calibrated probabilities so policy code can set thresholds and abstain (PRD 10.3). The machine has one RTX 5080 (16 GB, about 14 GB free) and WSL2 Ubuntu-24.04.

## Decision
Fine-tune **Kev-4B** from `jaredpalmer/kev-4b@v1.0` on routing labels. Train in WSL2 locally first; fall back to Modal under `training_budget_usd: 10`. Serve from pre-merged full weights. Keep Kev-0.8B as a size ablation. (Amends the seed decision "start with the smallest base".)

## Options considered
| Option | Why not chosen |
|---|---|
| Laya | **[Joe]** |
| Hosted Jev | **[Joe]** |
| Kev-0.8B as the main model | Facts: 0.648 dev accuracy on new sources vs 0.817 for 4B. **[Joe: why that rules it out for the demo]** |
| Kev-9B | Facts: about 17 GB to serve; does not fit locally |
| Zero-shot Kev, no fine-tune | Kept as a baseline, not the decision. **[Joe]** |

## Consequences
- Easier: one `base_url` swap between Kev, the cascade and LightGBM (PRD 10.3).
- Harder: WSL2 process management; no unload endpoint, so stopping means killing the process (`scripts/kev.ps1`).
- **[Joe: what is now locked in]**

## Evidence
- Kev README, checked 2026-10-11: sizes, validated context 8,192 for 4B, dev/test accuracy, a 400-record fine-tune gain within noise, adapter-path load peak 15.9 GB vs 8.4 GB for full weights (measured on MLX). https://github.com/jaredpalmer/kev
- Local VRAM need: no measurement yet. Estimate 9-10 GB for short routing inputs; the first training run measures it.

## Revisit trigger
Kev-4B fails to beat LightGBM or the cascade on the validation split, or local training does not fit and Modal cost exceeds the budget.
