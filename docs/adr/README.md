# ADR index

One decision per file: `ADR-NNN-kebab-title.md`. Sections: Status, Date, Context, Decision, Options considered, Consequences, Evidence, Revisit trigger. Use the `write-adr` skill.

The seed list is in `docs/prd.md`, Section 19 (ADR-001 to ADR-021). Drafts marked **[Joe]** need your reasoning before they move to accepted.

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-kev-decision-model.md) | Fine-tune Kev-4B as the decision model | proposed |
| [002](ADR-002-lightgbm-routing-baseline.md) | LightGBM as a baseline for structured-feature routing | proposed |
| [003](ADR-003-three-tier-local-first.md) | Three-tier local-first plan, mock server as the default | proposed |
| [004](ADR-004-phoenix-local-tracing.md) | Phoenix for local tracing | proposed |
| [005](ADR-005-evals-as-plain-code.md) | Evals as plain code in the repo | proposed |
| [006](ADR-006-drop-parlant.md) | Drop Parlant; routing via the decision step | proposed |
| [018](ADR-018-golden-set-synthetic-v0.md) | Golden set: synthetic v0, hand-labelled v1 | proposed |
| [019](ADR-019-ci-github-actions.md) | GitHub Actions CI tiers and runner policy | proposed |
| [020](ADR-020-routing-tiers-config.md) | Routing tiers as a config list (local qwen3.5:9b, cloud deepseek-flash) | accepted (reasoning [Joe]) |
| [021](ADR-021-routing-labels-cross-family-judge.md) | Synthetic routing labels with a cross-family judge (judges: Granite Guardian per claim, phi4) | accepted (reasoning [Joe]) |
