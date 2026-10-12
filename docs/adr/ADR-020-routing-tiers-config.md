# ADR-020: Routing tiers as a config list (local Qwen3.5-9B, cloud DeepSeek flash)

- **Status:** accepted by Joe, 2026-10-12 (model choice). Reasoning sections marked **[Joe]** still to write.
- **Date:** 2026-10-11; models chosen 2026-10-12

## Context
Kev-4B (about 8.4 GB served) and a 7-8B local generation model do not fit together in about 14 GB of free VRAM. Cheap cloud "flash" models (GLM, DeepSeek) are available under budget. The skill being demonstrated is fine-tuning and running the decision model, not local generation (PRD 10, 12).

## Decision
Tiers are a config list (`config/providers.yaml`) read by the router and the labelling pipeline. Kev chooses between them per request.

**Chosen (Joe, 2026-10-12):**
| Tier | Model | Where | Family |
|---|---|---|---|
| `local-small` | `qwen3.5:9b` (Ollama) | local GPU, 7.6 GB | qwen-local |
| `cloud-flash` | `deepseek-flash` (currently DeepSeek-V4.1-Flash) | cloud, $0.30 / $1.20 per 1M tokens at peak | deepseek |
| `cloud-strong` | `deepseek-v4-pro` | cloud, reserve tier | deepseek |

Routing starts as `[local-small, cloud-flash]`. If the local tier fails the M3 quality bar, switch to `[cloud-flash, cloud-strong]` (the fine-tune still has a real choice to learn).

**Changed from the draft:** the local model is 9B, not 3-4B (the measured 4B candidate leaks its reasoning into the answer). No local model fits next to Kev-4B, so models are swapped **once per phase** (decide, generate, judge) by the `ModelManager`, with each load time logged; never per step. DeepSeek names are aliases, so the client records the model each response reports. GLM via the Coding Plan is not used: its usage policy limits it to supported coding tools.

## Options considered
| Option | Why not chosen |
|---|---|
| 7-8B local model with per-step swapping | Swaps on every step make latency numbers meaningless. **[Joe]** |
| Kev-0.8B so both fit | Weak on unseen tasks (see ADR-001). **[Joe]** |
| Hard-coded local/cloud tiers | The fine-tune would be pointless if local fails. **[Joe]** |

## Consequences
- Easier: the routing story survives a weak local model; a reserve cloud tier exists.
- Harder: models swap once per phase, so load times (about 7-20 s per model, measured) add to
  each run; they are logged as events and reported, not hidden.
- Harder: a brief routed to the cloud tier leaves the machine, so `keep_local` and the per-provider switches matter.
- **[Joe]**

## Evidence
- Local model probe, 2026-10-12 (`config/models.yaml`, PR #57): one grounded rationale prompt, thinking off. `qwen3.5:9b`: 7.6 GB, 100% on GPU, 4.4 s, cited only record fields. `qwen3:4b`: reasoning leaked into the answer (unusable). `qwen2.5:14b`, `gemma4`, `glm-4.7-flash`: too large to fit fully on the GPU.
- `qwen3:4b` smoke run (#40, PR #56): 7.5 GB with Ollama defaults, not the ~3 GB estimated, so nothing local coexists with Kev-4B.
- Public reference (not our task): Vectara hallucination leaderboard, 2026-09-22: Qwen3 small models about 5.5% vs DeepSeek-V4-Pro 8.6%.
- Still needed: rationale factual accuracy for both tiers on golden-v1 (M3), with the verifier and judges from ADR-021.

## Revisit trigger
A local model passes the quality bar at a cost and latency that beat cloud flash.
