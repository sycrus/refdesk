# ADR-023: Eval corpus snapshots

- **Status:** proposed. The choices below are Joe's (issue #151, 2026-10-31); the reasoning sections are his to write.
- **Date:** 2026-10-31

## Context
A golden set's expected references only mean something against the corpus they were labelled on (ADR-018, PRD 11). Until now `eval` and `eval-rationales` refused to run unless the **whole store** hashed to the golden set's `corpus_version` (`<source>:<count>:<sha256 of sorted IDs>`). Museums keep adding works. On 2026-10-31 a re-ingest added two Met paintings (`met:925165`, `met:925168`), the store went from 2,588 to 2,590 records, and every eval failed with "Not comparable". The only fix was deleting records from the store by hand. The corpus will always change, so the eval has to pin it, not the store.

## Decision
The eval pins the corpus; the store keeps growing (Joe, 2026-10-31, issue #151):
1. A **corpus snapshot** is a committed TSV in `evals/golden/corpus/`, named after the `corpus_version` (colons become dashes), with one row per record: ID, rights status, and a hash of the record's descriptive fields. Its sorted IDs hash to the `corpus_version`, so frozen golden files need no change. Snapshots are frozen like golden files (`scripts/verify.py`).
2. Before any retriever is built, `eval` and `eval-rationales` filter the store to the snapshot. New store records are ignored and counted in the report.
3. **Refuse** if a pinned record is missing from the store, or if its rights status has changed. **Warn** if any other field has changed: the changed IDs are listed in the report, and a hash of their content goes into the config hash (`corpus_drift`, omitted when empty so earlier hashes still reproduce). `compare` refuses runs with different drift.
4. A new golden version pins the snapshot that is current when it is frozen: `scripts/golden_v1_report.py --freeze` writes it, and refuses if it can no longer be rebuilt.
5. `uv run python -m refdesk snapshot` writes the snapshot for the store as it is now.

## Options considered
| Option | Why not chosen |
|---|---|
| Pin the store at ingest (an ID allowlist or an `--until` date) | **[Joe]** |
| A new golden version for every corpus change | **[Joe]** |
| Delete new records from the store by hand (what was done on 2026-10-31) | **[Joe]** |
| Snapshot of IDs only, ignoring content changes | **[Joe]** |
| Refuse on any content change, not only rights | **[Joe]** |
| Snapshots in `evals/corpus/` instead of next to the golden sets | **[Joe]** |

## Consequences
- Easier: re-ingest freely; evals keep running on the corpus their golden set was labelled on. Recall on golden-v0 is unchanged by new works, because retrievers never see them.
- Harder: a snapshot can only be written while the store equals its corpus. If one is lost after the store grows, it is gone, which is why `--freeze` writes it.
- Harder: a rights flip on a pinned record stops every eval on that golden set until a new version is made. Rights flips are rare, and that is the point: an expected reference that may no longer be shown should not be scored silently.
- Locked in: content hashes cover descriptive fields only. `rights.checked_at` and `raw_record_ref` change on re-ingest without changing what the source says, so they are excluded.
- **[Joe]** anything else.

## Evidence
- 2026-10-31: `met-2588-d188937d8a53.tsv` was written from the store when it matched the pinned corpus exactly (verified against the ID hash). Its content hashes are as of 2026-10-31, not as of golden-v0's build. The Met records had last been ingested on 2026-10-26, and today's ingest did not refresh them.
- With the two new works restored (2,590 records, 2,310 vectors in the CLIP index), golden-v0-synthetic gives the same scores as the 12 October reports: Jaccard recall 0.655 [0.535, 0.770], MRR 0.775 (`evals/reports/eval-report-2026-10-31-jaccard-fc1ca0a442f7.md`); CLIP recall 0.454 [0.348, 0.562], MRR 0.735 (`evals/reports/eval-report-2026-10-31-clip-a1cfb3e54b00.md`).

## Revisit trigger
A second source joins the corpus; content drift warnings start appearing often enough to be ignored; or a rights flip blocks an eval and the refusal turns out to be wrong.
