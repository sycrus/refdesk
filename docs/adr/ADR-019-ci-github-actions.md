# ADR-019: GitHub Actions CI tiers and self-hosted runner policy

- **Status:** proposed (draft; reasoning sections are Joe's to write)
- **Date:** 2026-10-11

## Context
The tracker is on GitHub (`sycrus/refdesk`, private). PRD 13A asks for a fast, deterministic PR tier and a nightly real-model tier. Real models (Kev, Ollama) only run on the dev machine.

## Decision
GitHub Actions, with actions pinned by SHA. From M0, a PR job on `ubuntu-latest` runs pytest plus the frozen-golden and secret checks (a Python port of `verify.ps1`). From M4, a nightly job, and in M5 CD to kind, run on a self-hosted runner on the dev machine. The self-hosted runner is removed before the repo becomes public.

## Options considered
| Option | Why not chosen |
|---|---|
| CI only in M5, as first planned | **[Joe]** |
| Hosted GPU runners | **[Joe]** |
| Self-hosted runner on a public repo | GitHub warns that forks can run code on it. **[Joe]** |

## Consequences
- Easier: regressions caught from the first commit.
- Harder: the nightly tier depends on the dev machine being on.
- **[Joe]**

## Evidence
GitHub documentation on self-hosted runner security (recommended for private repositories only). Date checked: **[Joe]**.

## Revisit trigger
The repo goes public, or the nightly job's flake rate exceeds the gate policy.
