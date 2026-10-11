# Build queue

One task per line. The runner takes the first unchecked line.

Format: `- [ ] ID [HUMAN] | description || check`

- `[HUMAN]` marks a learning-critical task. The runner stops and tells you what is needed. Claude Code must never complete these silently (see `CLAUDE.md`).
- The check must be provable from output Claude prints (for example, "run `pytest -q` and show it passing"). The runner adds a turn cap.
- Expand M2 to M5 into tasks only after you have reviewed the M0 and M1 pilot.

## M0 Scope and sources

- [ ] M0-01 | Create the repo scaffold: pyproject, src/refdesk, tests/, docs/, scripts/, .env.example, .gitignore, README stub. Commands must work on Windows PowerShell or WSL2. || Run `pytest -q` and show it exiting cleanly with zero tests, and show `git status` is clean after the commit.
- [ ] M0-02 | Build the mock LLM server (FastAPI) with configurable latency, 429 responses and timeouts, and tests for each failure mode (PRD Section 10, tier 1). || Run `pytest -q` and show tests for latency, 429 and timeout passing.
- [ ] M0-03 [HUMAN] | Write docs/problem-statement.md: the decision being improved, the success metric as a number, the cost of each kind of wrong answer, today's baseline, non-goals. || Joe writes it. Claude Code may provide a template only.
- [ ] M0-04 [HUMAN] | Fill docs/data-sources.md for the Met, Art Institute of Chicago and Cleveland: licence, rights-flag field, rate limits, date checked, known drift. Read each source's terms yourself. || Joe confirms each row against the source's own terms.
- [ ] M0-05 [HUMAN] | Recruit 8 to 10 interviewees and write the interview script (PRD Section 4 and 18). || Joe does this. It is not code.

## M1 Ingest and baselines

- [ ] M1-01 | Define the normalised record schema (FR-1) with a rights record, and schema tests. || Run `pytest -q` and show the schema tests passing, including a test that rejects a record with no rights record.
- [ ] M1-02 | Implement the Met adapter for a paintings slice using the add-museum-source skill, with schema, rights and licence-drift contract tests. Use recorded responses in tests, not live calls. || Run `pytest -q` showing the adapter tests passing and show that the adapter marks only objects with the source's open flag as open.
- [ ] M1-03 | Build the SQLite metadata store and an ingest command that is resumable and idempotent. || Run `pytest -q` showing a test that ingests twice with no duplicates and resumes after an interruption.
- [ ] M1-04 | Implement the metadata-only baseline (Jaccard over attribute sets) behind the retrieval interface (FR-4). || Run `pytest -q` showing the baseline tests passing and a fixed example query returning a stable ranking.
- [ ] M1-05 [HUMAN] | Write 40 to 50 golden briefs and label quality and expected references. Use the label-golden-cases skill to format and validate only. || Joe labels. Claude Code formats, validates and reports leakage and coverage.
- [ ] M1-06 | Build the eval harness: scorers with unit tests, bootstrap confidence intervals, run manifest with config hash, report writer (run-evals skill). Use the mock server by default. || Run `pytest -q` showing scorer tests passing and show a report written to evals/reports/ with intervals and the config hash.
- [ ] M1-07 [HUMAN] | Write ADR-001 to ADR-012 reasoning and rejected options. Claude Code may draft the facts using the write-adr skill. || Joe supplies the judgments.
- [ ] M1-08 | Draft the API contract (OpenAPI) for the endpoints in PRD Section 13A, with /healthz and /readyz and no business logic. || Show the OpenAPI file validates and lists every endpoint in PRD Section 13A.

## M2 to M5

- [ ] M2-00 | Expand M2 (similarity, anchor plus conditions, design tokens and React component library) into tasks after reviewing the M1 pilot. || A reviewed list of M2 tasks exists in this file, each with a check.
