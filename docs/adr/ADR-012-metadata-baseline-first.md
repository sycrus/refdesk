# ADR-012: Metadata-only baseline built first

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Design principle 4: a complex method must beat the simple one on validation data and human ratings (PRD 1A). FR-4 lists a metadata-only baseline behind the same interface as the other retrievers. Principle 1 prefers structured filters to opaque embeddings where they do the job.

## Decision
Build a metadata-only retriever first (M1): Jaccard similarity over field-named attribute sets (`src/refdesk/retrieval/metadata.py`), behind the shared retrieval interface. Similarity retrieval came after (M2, ADR-010).

## Options considered
| Option | Why not chosen |
|---|---|
| Start with embedding retrieval | **[Joe]** |
| BM25 over text fields as the baseline | **[Joe]** |

## Consequences
- Easier: the eval harness was built and tested before any model; every match is explainable by named fields.
- Harder: golden-v0-synthetic was derived from metadata rules, so it favours this baseline and cannot rank retrievers (ADR-018).
- **[Joe]**

## Evidence
Built: `tests/retrieval/test_metadata_baseline.py`. On golden-v0-synthetic (2026-10-12) Jaccard scored above CLIP, but that set favours metadata by construction; see the comparison report in `evals/reports/`. No valid measurement until golden-v1 (#15).

## Revisit trigger
Golden-v1 or the bake-off shows the baseline ties the combined retriever, in which case the simpler one stays the default.
