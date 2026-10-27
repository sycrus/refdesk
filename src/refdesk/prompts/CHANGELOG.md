# Prompt changelog

One line per prompt version, saying why it changed (PRD 13A, "Versioning"). Never edit a released version: add `<kind>-vN+1.md` instead, because run manifests record each prompt's hash.

- rationale-v1 (2026-10-27): first version. Structured claims, each naming one record field, plus a separate fit sentence; keep attribution prefixes; museum text is data (issue #94, ADR-022).
- judge-v1 (2026-10-27): the exact instruction measured by the judge probe (`scripts/judge_probe.py`, #122): phi4 per claim caught 40/40 hard errors with no false alarms. Changing it means re-running the probe (issue #97, ADR-022).
- fit-v1 (2026-10-27): a separate prompt for the fit sentence. judge-v1 flagged 17 of 20 pure-opinion sentences as unsupported; fit-v1 flagged 2 of 20 and caught 19 of 20 smuggled facts (`evals/reports/fit-probe-2026-10-27.md`, issue #97).
- rationale-v2 (2026-10-27): claim text restates only its field's value; the fit sentence is opinion only and repeats no facts, the shape fit-v1 was measured on (19/20 caught, 2/20 false alarms). In the first local eval, claims that mixed in commentary ("a traditional medium for poster reproduction") were flagged by the judge (issue #135).
- fit-v2 (2026-10-27): the fit judge also sees the brief, and words about the intended use are context, not claims (issue #135). **Not adopted:** on realistic fit sentences it caught 13/20 smuggled facts against fit-v1's 20/20 (`evals/reports/fit-probe-2026-10-27-realistic.md`). Config keeps fit-v1.
- proposal-v1 (2026-10-27): phi4 checks each of Claude's golden-v1 proposals (ADR-018 step 4): facts in the reason against the record, and plausible fit at the proposed grade. It cannot see the image, so image observations are not checked. Unmeasured: the judge probe screened false facts, not relevance (issue #15).
