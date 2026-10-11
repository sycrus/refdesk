# ADR-020: Routing tiers as a config list; cloud flash models generate rationales by default

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-11

## Context
Kev-4B (about 8.4 GB served) and a 7-8B local generation model do not fit together in about 14 GB of free VRAM. Cheap cloud "flash" models (GLM, DeepSeek) are available under budget. The skill being demonstrated is fine-tuning and running the decision model, not local generation (PRD 10, 12).

## Decision
Tiers are a config list read by the router and the labelling pipeline. Start with `[local-small, cloud-flash]`, where local-small is a 3-4B Q4 model in Ollama. Rationales default to cloud flash. If the local tier fails the end-to-end quality bar, switch to `[cloud-flash, cloud-strong]`. Model IDs are pinned as dated IDs.

## Options considered
| Option | Why not chosen |
|---|---|
| 7-8B local model with per-step swapping | Swaps on every step make latency numbers meaningless. **[Joe]** |
| Kev-0.8B so both fit | Weak on unseen tasks (see ADR-001). **[Joe]** |
| Hard-coded local/cloud tiers | The fine-tune would be pointless if local fails. **[Joe]** |

## Consequences
- Easier: Kev stays loaded for a whole run; the routing story survives a weak local model.
- Harder: briefs leave the machine by default, so `keep_local` and the per-provider switches matter.
- **[Joe]**

## Evidence
No measurement yet. The test: the M2 local-tier end-to-end run (rationale accuracy on golden-v0, then v1). The chosen local model and the result are recorded here.

## Revisit trigger
A local model passes the quality bar at a cost and latency that beat cloud flash.
