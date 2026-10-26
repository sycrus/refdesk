# ADR index

One decision per file: `ADR-NNN-kebab-title.md`. Sections: Status, Date, Context, Decision, Options considered, Consequences, Evidence, Revisit trigger. Use the `write-adr` skill.

The seed list is in `docs/prd.md`, Section 19 (ADR-001 to ADR-021). Drafts marked **[Joe]** need your reasoning before they move to accepted.

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-kev-decision-model.md) | Fine-tune Kev-4B as the decision model | accepted |
| [002](ADR-002-lightgbm-routing-baseline.md) | LightGBM as a baseline for structured-feature routing | proposed |
| [003](ADR-003-three-tier-local-first.md) | Three-tier local-first plan, mock server as the default | proposed |
| [004](ADR-004-phoenix-local-tracing.md) | Phoenix for local tracing | proposed |
| [005](ADR-005-evals-as-plain-code.md) | Evals as plain code in the repo | proposed |
| [006](ADR-006-drop-parlant.md) | Drop Parlant; routing via the decision step | proposed |
| [007](ADR-007-defer-mem0-state-in-sqlite.md) | Defer Mem0; state in SQLite | proposed |
| [008](ADR-008-taxonomy-and-typed-schemas.md) | Taxonomy and typed schemas, not an ontology | proposed |
| [009](ADR-009-kind-for-learning-vs-cloud-run.md) | Kubernetes (kind) for learning, compared with Cloud Run | proposed |
| [010](ADR-010-reuse-off-the-shelf-retrieval.md) | Reuse off-the-shelf retrieval | proposed |
| [011](ADR-011-cc0-only-sources.md) | CC0-only sources; no scraping of permission-required collections | proposed |
| [012](ADR-012-metadata-baseline-first.md) | Metadata-only baseline built first | proposed |
| [013](ADR-013-decision-step-v1-one-question.md) | Decision step v1: one Kev question (tier choice) | proposed |
| [014](ADR-014-fastapi.md) | FastAPI for the API | proposed |
| [015](ADR-015-mcp-after-api-read-only.md) | MCP server after the API, read-only, no approval or export | proposed |
| [016](ADR-016-plain-loop-then-langgraph-port.md) | Plain-code loop first, then a LangGraph port | proposed |
| [017](ADR-017-react-ui-served-by-api.md) | UI: React + TypeScript static app served by the API | proposed |
| [018](ADR-018-golden-set-synthetic-v0.md) | Golden set: synthetic v0, reviewed v1 (proposed by Claude, judged cross-family, reviewed by Joe) | proposed |
| [019](ADR-019-ci-github-actions.md) | GitHub Actions CI tiers and runner policy | proposed |
| [020](ADR-020-routing-tiers-config.md) | Routing tiers as a config list (local qwen3.5:9b, cloud deepseek-flash) | accepted (reasoning [Joe]) |
| [021](ADR-021-routing-labels-cross-family-judge.md) | Synthetic routing labels with a cross-family judge (judge: phi4 per claim; Granite dropped 2026-10-27) | accepted (reasoning [Joe]) |
| [022](ADR-022-rationale-verification-structured-claims.md) | Rationale verification by structured claims (code checks, then phi4 per claim) | accepted |
