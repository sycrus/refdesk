# ADR-014: FastAPI for the API

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
The API comes first; the MCP server and the UI sit on top of it (FR-12, FR-13). The contract is the endpoint list in PRD 13A, and the MCP server must be able to tell read operations from gated ones. The rest of the code is Python.

## Decision
Build the API with FastAPI. The OpenAPI spec is generated from code (`docs/api/openapi.json`) and checked by a drift test. Operations are tagged so the MCP server can expose only `read` ones.

## Options considered
| Option | Why not chosen |
|---|---|
| Flask | **[Joe]** |
| Django or Django REST Framework | **[Joe]** |
| A Node.js API | **[Joe]** |

## Consequences
- Easier: Pydantic models shared with the schema; the spec comes from code, so it cannot silently drift; background tasks for runs.
- Harder: background tasks run on another thread, so the store opens one connection per call (`docs/architecture.md`).
- **[Joe]**

## Evidence
Built: issues #13 (contract) and #45 (boards and runs). Tests: `tests/api/test_contract.py`, `tests/api/test_boards.py`.

## Revisit trigger
Runs need a durable job queue that background tasks cannot provide.
