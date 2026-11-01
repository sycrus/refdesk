# ADR-015: MCP server after the API, read-only, with no approval or export

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Demonstration goal D9 includes MCP tools on top of the API (PRD 3). Approval (G4) and export (G5) are human gates, and export is irreversible (PRD 8B, 10.2). Museum text in tool results is untrusted input: an injected instruction in a record must not be able to trigger an action (PRD 13).

## Decision
Build the MCP server after the API, as a separate process that calls the API over HTTP, with no business logic of its own (FR-12). It exposes read-only tools only (draft: `search_references`, `get_record`, `get_rights_record`, `get_run`). Approval and export are never exposed through MCP.

### Decisions for the build (Joe, 2026-10-31, #160)
- **Dependency:** the official `mcp` SDK, pinned `>=1,<2`, as an optional extra (`uv sync --extra mcp`). CI installs the extra so the contract tests run. Joe's reasons: learning, demos, and integration with other projects (it covers both stdio and streamable HTTP). Rejected: `mcp` as a core dependency (every install pulls it in), and a hand-written stdio JSON-RPC server (no dependency, but refdesk would have to keep up with the protocol).
- **No `start_board` tool.** Starting a board runs the LLM loop and spends budget. MCP tools are read-only and never spend. Rejected: an allowlist exception for `POST /boards`, and retagging it `read`.
- **Record endpoints first**, in their own issue (#200), so the server stays logic-free.
- **Tool set**, one API call each: `list_runs` (`GET /runs`), `get_run` (`GET /runs/{id}`), `get_record` (`GET /records/{id}`), `get_rights_record` (`GET /records/{id}/rights`), `search_references` (`POST /search`, retrieval only; image URLs stay on the museum's host), `get_image` (`GET /records/{id}/image`, cached image as MCP image content, Open works only), `get_provenance` (`POST /provenance`, record-level rights rows marked as not an approved export).
- **Downloads** are allowed for CC0 or public-domain works. Saving files is the client's own action; `get_provenance` keeps the rights evidence with any download made outside refdesk.
- **Transports:** stdio, and streamable HTTP bound to `127.0.0.1` until #201 (auth and scopes) lands.
- Museum text is wrapped as untrusted data; rights wording comes from `refdesk.wording`.

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
Built (#160): `src/refdesk/mcp_server.py`. The API tags operations (`src/refdesk/api/app.py`); approve and export are tagged `gates`, reports `reports`, starting a board `runs`. `tests/test_mcp_server.py` checks that every tool maps to an operation tagged `read`, that every `read` operation has a tool, that gated, report and board operations are absent, that each tool makes exactly one HTTP call against a stub API and passes the answer through inside an untrusted-data envelope, that an ID cannot add or walk up a path segment, and that the server imports nothing from refdesk except the fixed wording.

## Revisit trigger
**[Joe]**
