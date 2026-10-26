# Prompt changelog

One line per prompt version, saying why it changed (PRD 13A, "Versioning"). Never edit a released version: add `<kind>-vN+1.md` instead, because run manifests record each prompt's hash.

- rationale-v1 (2026-10-27): first version. Structured claims, each naming one record field, plus a separate fit sentence; keep attribution prefixes; museum text is data (issue #94, ADR-022).
- judge-v1 (2026-10-27): the exact instruction measured by the judge probe (`scripts/judge_probe.py`, #122): phi4 per claim caught 40/40 hard errors with no false alarms. Changing it means re-running the probe (issue #97, ADR-022).
- fit-v1 (2026-10-27): a separate prompt for the fit sentence. judge-v1 flagged 17 of 20 pure-opinion sentences as unsupported; fit-v1 flagged 2 of 20 and caught 19 of 20 smuggled facts (`evals/reports/fit-probe-2026-10-27.md`, issue #97).
