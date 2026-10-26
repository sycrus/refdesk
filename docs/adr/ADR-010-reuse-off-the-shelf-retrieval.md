# ADR-010: Reuse off-the-shelf retrieval

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
FR-3 combines structured filters and embedding similarity in one score. FR-4 asks for an off-the-shelf visual-similarity baseline. The product's claim rests on evidence, rights records and explanations, not on a new retrieval model (PRD 1, 10: "Put effort into evidence and evals").

## Decision
Use an off-the-shelf image embedding model, OpenCLIP `ViT-B-32` with `laion2b_s34b_b79k` weights, in an exact FAISS `IndexFlatIP`, kept as FAISS so an approximate index can replace it if the corpus grows. Effort goes to the evidence layer. **[Joe]**: whether `ViT-B-32` is the chosen model or only a default (it was picked as a default when the index was built).

## Options considered
| Option | Why not chosen |
|---|---|
| Train or fine-tune a retrieval model | **[Joe]** |
| A larger CLIP model | **[Joe]** |
| A hosted vector database | **[Joe]** |
| Knowledge-graph embeddings | Parked: plain metadata baselines went far in the source paper's own evaluation (PRD 16). **[Joe]** |

## Consequences
- Easier: no training; the index builds from cached images of open works in one command (`refdesk embed met`).
- Harder: PyTorch is a large optional extra (`--extra embed`), CI cannot run CLIP, and the model's view of similarity is not explainable per result.
- **[Joe]**

## Evidence
Built: issues #32, #33, #34. Comparison on golden-v0-synthetic, 2026-10-12 (`evals/reports/eval-comparison-2026-10-12-c5fac8a985f3-9d1563f792ec-dd2089b9d36e.md`): that set favours the metadata baseline by construction, so it cannot rank retrievers (ADR-018). No valid measurement yet; golden-v1 (#15) and the bake-off supply it.

## Revisit trigger
On golden-v1 or in the bake-off, the similarity component adds nothing over metadata, or a different embedding model does clearly better.
