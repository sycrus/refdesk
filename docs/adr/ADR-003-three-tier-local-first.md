# ADR-003: Three-tier local-first plan, with the mock server as the default

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
refdesk is local-first and cost-bounded (PRD 1A, principle 5). Tests, CI and infrastructure drills need model answers that are fast, free and repeatable. Real briefs may be confidential, and both cloud providers are based in China (PRD 10, "Providers and data flow").

## Decision
Three tiers behind one client: (1) a mock LLM server, the default for tests, drills and CI; (2) a local model through Ollama; (3) a capped cloud model. Paid calls need a key in `.env`, a budget in `config/budgets.yaml` and a run with `--approve`; a blocked paid call is a hard error, never a silent fall back to the mock. Which models fill tiers 2 and 3 is ADR-020.

## Options considered
| Option | Why not chosen |
|---|---|
| Cloud only | **[Joe]** |
| Local only | **[Joe]** |
| Recorded responses only, no mock server | **[Joe]** |

## Consequences
- Easier: CI never calls a real model or spends money; failures (429, 500, timeout) can be scripted; `keep_local` has a tier to stay on.
- Harder: the mock can drift from real provider behaviour; three paths to keep working.
- **[Joe]**

## Evidence
Built: the mock server (`refdesk.llm.mock_server`, issue #39) and the client guards (`refdesk.llm.client`, issue #38), covered by `tests/llm/test_mock_server.py` and `tests/llm/test_client.py`. No measurement yet of how far mock answers differ from real ones.

## Revisit trigger
The local tier fails the M3 quality bar (ADR-020 records the switch), or a bug reaches main because the mock behaved differently from a real provider.
