# ADR-007: Defer Mem0; state in SQLite

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
refdesk keeps records, raw responses, ingest progress and run state. The loop needs checkpoints and resume with idempotency keys (PRD 10.2, "Checkpoint and resume"). v1 is single-user and local (PRD 8A). A memory layer such as Mem0 was considered during planning.

## Decision
Keep all state in SQLite (`data/refdesk.sqlite`, `src/refdesk/store.py`). Defer Mem0.

## Options considered
| Option | Why not chosen |
|---|---|
| Mem0 as a memory layer | **[Joe]** |
| A server database (for example Postgres) | **[Joe]** (also bears on ADR-009: API state under Kubernetes) |

## Consequences
- Easier: one file, no service to run; ingest is idempotent and resumable; runs live in a `runs` table.
- Harder: the API holds state locally, so it cannot scale out freely (PRD 13A, ADR-009); there is no memory across briefs.
- **[Joe]**

## Evidence
Built: the store and ingest (issue #8, `tests/test_store.py`: idempotent and resumable), the `runs` table (issue #45). No measurement of a need for cross-brief memory.

## Revisit trigger
A feature needs memory across briefs or users (for example operator preferences), or ADR-009 chooses a separate database for the API.
