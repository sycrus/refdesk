# ADR-018: Golden set in two kinds, synthetic v0 and hand-labelled v1

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-11

## Context
The eval harness, scorers and reports (M1) need cases before Joe has time to label 40-50 briefs. `CLAUDE.md` forbids Claude Code from assigning quality labels or expected references, because the eval would then measure agreement with the model's own guesses (PRD 11).

## Decision
`golden-v0-synthetic` is generated in full by Claude Code, every case marked `provenance: synthetic`, and used only to build and test the harness. `golden-v1` onwards is labelled by Joe and is required before any eval number goes public. Every case carries a `corpus_version`; expected references come only from ingested records.

## Options considered
| Option | Why not chosen |
|---|---|
| Wait for hand labels before building the harness | **[Joe]** |
| Use the synthetic set for claims too | **[Joe]** |
| LLM-labelled set reviewed by Joe | **[Joe]** |

## Consequences
- Easier: M1 is not blocked on labelling.
- Harder: two sets to keep apart; every report must state which set produced each number.
- **[Joe]**

## Evidence
No measurement yet. The test: once v1 exists, compare harness metrics on v0 and v1 and report how far the synthetic set misled.

## Revisit trigger
v0 and v1 disagree enough that decisions made on v0 would have changed.
