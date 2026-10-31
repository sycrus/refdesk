# Trajectory eval 2026-10-31 (trajectory-v0-synthetic, e57b882faa3e)

Issue #173; PRD 11.7. Suite `tests/fixtures/trajectory/trajectory-v0-synthetic` (provenance: **synthetic**), 5 briefs, k = 3 recorded runs each, replayed through the current loop with the recordings standing in for the retriever and the model.

**Plumbing only.** The suite is synthetic and recorded against the mock tiers. The k runs differ because faults were planted in the recordings, not because a real model varied, so these numbers say the harness and the loop's handling of planted faults work, nothing about model reliability (ADR-018).

## Summary

| Metric | Mean over briefs [95% CI] |
|---|---|
| Single-run success (share of a brief's k runs that succeed) | 0.867 [0.733, 1.000] |
| pass^3 (all 3 runs of a brief succeed) | 0.600 [0.200, 1.000] |

Gate: **PASS**: 0 of 15 runs differ from their expected outcome.

## Failed runs by step

| Step | Runs | Share of failed runs |
|---|---|---|
| wrong_retrieval | 1 | 0.50 |
| bad_decision | 0 | 0.00 |
| verification_miss | 0 | 0.00 |
| bad_stop | 0 | 0.00 |
| rationale_error | 1 | 0.50 |
| diverged | 0 | 0.00 |

## Per brief

| Brief | Single-run success | pass^k | Run outcomes |
|---|---|---|---|
| t01-calm-harbour | 3/3 | 1 | success, success, success |
| t02-recovers-from-a-wrong-rationale | 3/3 | 1 | success, success, success |
| t03-unusable-rationales | 2/3 | 0 | success, rationale_error, success |
| t04-restricted-candidate | 2/3 | 0 | success, wrong_retrieval, success |
| t05-keep-local | 3/3 | 1 | success, success, success |

## Runs

| Brief | Run | Outcome | Expected | Stop | Accepted | Rounds | Why |
|---|---|---|---|---|---|---|---|
| t01-calm-harbour | 1 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t01-calm-harbour | 2 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t01-calm-harbour | 3 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t02-recovers-from-a-wrong-rationale | 1 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t02-recovers-from-a-wrong-rationale | 2 | success | success | - | 2 | 2 | 2 of 2 items accepted |
| t02-recovers-from-a-wrong-rationale | 3 | success | success | - | 2 | 2 | 2 of 2 items accepted |
| t03-unusable-rationales | 1 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t03-unusable-rationales | 2 | rationale_error | rationale_error | no_progress | 0 | 2 | 0 of 2 accepted: rationales were unusable or rejected |
| t03-unusable-rationales | 3 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t04-restricted-candidate | 1 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t04-restricted-candidate | 2 | wrong_retrieval | wrong_retrieval | - | 2 | 1 | worked on records the brief does not allow: ['met:900032'] |
| t04-restricted-candidate | 3 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t05-keep-local | 1 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t05-keep-local | 2 | success | success | - | 2 | 1 | 2 of 2 items accepted |
| t05-keep-local | 3 | success | success | - | 2 | 1 | 2 of 2 items accepted |

## Config

- Config hash `e57b882faa3e`: suite version and SHA-256 of the manifest and recordings (`8aec883c80f5`), k, loop overrides (none), scorer `trajectory-v1`, seed 0, 2000 bootstrap draws, git SHA.
- Code: `6d80fed37576` (dirty). Prompts {'rationale': 'rationale-v2', 'judge': 'judge-v1', 'fit': 'fit-v1'}; loop {'max_rounds': 6, 'timeout_s': 120.0, 'stuck_rounds': 2, 'target_items': 2, 'budget_cap_usd': 0.05, 'drop_after_failed_verifications': 2}.
- Reproduce: `uv run python -m refdesk eval-trajectories`.
