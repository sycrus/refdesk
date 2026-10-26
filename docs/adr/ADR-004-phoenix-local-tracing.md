# ADR-004: Phoenix for local tracing

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
A run calls several steps and models (retrieve, decide, generate, judge; PRD 10.2). Finding a faulty step needs traces. Briefs may be confidential, so traces are redacted before logging and stay on this machine (PRD 13A, "Observability").

## Decision
Use Arize Phoenix, run locally, for tracing. Langfuse remains an option for prompt management. Tracing is not built yet; it lands with observability in M5 (PRD 17).

## Options considered
| Option | Why not chosen |
|---|---|
| Langfuse for tracing as well | **[Joe]** |
| A hosted tracing service | **[Joe]** |
| The append-only `events.jsonl` run log only (PRD 10.2), no tracing tool | **[Joe]** |

## Consequences
- Easier: traces stay local; no brief leaves the machine for observability.
- Harder: one more service to run (start it only when the task needs it, CLAUDE.md); redaction has to happen before data reaches it.
- **[Joe]**

## Evidence
No measurement yet. Not installed. The M5 observability work supplies it (a traced run with redaction checked).

## Revisit trigger
Prompt management needs grow beyond versioned prompt files, or Phoenix cannot redact a brief before it is stored.
