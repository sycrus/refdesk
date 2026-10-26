# ADR-017: UI as a React + TypeScript static app served by the API

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
FR-13: a web UI covering the flow in PRD 8A, showing evidence, rights status and cost on every result, and never hiding a stop reason. v1 is single-user and local. The UI is also a portfolio asset, so it gets a design system (PRD 8A, 8C), but polish is time-boxed.

## Decision
A Vite + React + TypeScript app, built to static files in `ui/dist` and served by the FastAPI service at `/` (one service). It has a design system in `design/` implemented as CSS custom properties, fixed wording generated from Python, and a design library at the `/design` route in the app.

## Options considered
| Option | Why not chosen |
|---|---|
| HTMX with server-rendered templates | Considered, not chosen (PRD 8A). **[Joe]** |
| A separate UI service | **[Joe]** |
| Storybook for the design library | **[Joe]** |

## Consequences
- Easier: one service to deploy; the UI is mounted after every API route, so API paths win, and it is not in the OpenAPI spec, so MCP can never expose it.
- Harder: an npm toolchain next to uv; the API must be restarted after the first build (`docs/architecture.md`).
- **[Joe]** (PRD 8A also names React and TypeScript as Joe's strongest stack: familiarity, recorded as such)

## Evidence
Built: issues #41 to #46. CI builds, type-checks and runs browser tests with axe (`.github/workflows/ci.yml`, `ui` job).

## Revisit trigger
v1 needs more than one user or a client-facing page (G6, not in v1).
