# ADR-016: Plain-code loop first, then a LangGraph port

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Explainability takes precedence (PRD 1A, principle 1). The loop is a fixed workflow with a bounded loop: stop conditions, budget caps, checkpoints and resume (PRD 10.2). Demonstration goal D10 is to use an agent framework with judgment, through an evaluated port (PRD 3).

## Decision
Build the loop as an explicit state machine in plain Python first (M2 to M4), with tests, as the reference. In M5, port it to LangGraph behind the same API, using its SQLite checkpointer for resume and `interrupt()` for human approval, with stop conditions, budget caps and the verifier kept as explicit guards. Compare both on the same acceptance scenarios and trajectory evals (PRD 10.4). The plain version is not deleted. The port starts only after the plain loop passes its acceptance scenarios.

## Options considered
| Option | Why not chosen |
|---|---|
| LangGraph from the start | **[Joe]** |
| Plain code only, no framework | **[Joe]** |
| Another agent framework | Not evaluated; LangGraph was chosen for its persistence and interrupt features and Joe's prior experience with it (PRD 10.4). Familiarity is a reason, not evidence. **[Joe]** |

## Consequences
- Easier: the plain version is the specification in executable form; the port has a reference to be measured against.
- Harder: two implementations to keep working until the comparison is done.
- **[Joe]**

## Evidence
No measurement yet. The M5 comparison supplies it: code size, resume behaviour, trace readability, failure modes and debuggability. The outcome is recorded here, including which version stays the default.

## Revisit trigger
The comparison is done (update this ADR with the result), or the plain loop's complexity grows past what can be explained.
