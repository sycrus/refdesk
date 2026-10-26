# ADR-015: MCP server after the API, read-only, with no approval or export

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Demonstration goal D9 includes MCP tools on top of the API (PRD 3). Approval (G4) and export (G5) are human gates, and export is irreversible (PRD 8B, 10.2). Museum text in tool results is untrusted input: an injected instruction in a record must not be able to trigger an action (PRD 13).

## Decision
Build the MCP server after the API, as a separate process that calls the API over HTTP, with no business logic of its own (FR-12). It exposes read-only tools only (draft: `search_references`, `get_record`, `get_rights_record`, `get_run`). Approval and export are never exposed through MCP.

## Options considered
| Option | Why not chosen |
|---|---|
| MCP server calling the library directly | Logic would be duplicated and could drift from the API. **[Joe]** |
| Expose approval and export as MCP tools behind a confirmation | **[Joe]** |
| No MCP server | **[Joe]** |

## Consequences
- Easier: one source of truth (the API); gated operations are tagged in the API, so the MCP server can refuse anything not tagged `read`.
- Harder: an agent using refdesk through MCP cannot finish a board; a person must approve and export in the UI.
- **[Joe]**

## Evidence
Built so far: the API tags operations (`src/refdesk/api/app.py`); approve and export are tagged `gates`. The MCP server is not built (M4, PRD 17); its contract tests will supply evidence.

## Revisit trigger
**[Joe]**
