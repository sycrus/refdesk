# ADR-011: CC0-only sources; no scraping of permission-required collections

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
refdesk shows and exports references that a studio may use. Rights must come from records, never inference (PRD 1A, principle 3; FR-2). Some collections, including Singapore national collections, require written permission stating use, timeframe and identity (PRD 9).

## Decision
Ingest only collections whose terms and machine-readable flags confirm open use (CC0 or public domain). Use only objects whose structured rights flag says so. Never scrape collections whose terms require permission; record them as "not open, date checked". Download images only for open works and only from the source's own image host.

## Options considered
| Option | Why not chosen |
|---|---|
| Include permission-required collections, links only | **[Joe]** |
| Infer public-domain status from an artist's death date | Rights would come from inference, not records (PRD 9 rules). **[Joe]** |
| Ask Singapore institutions for a dataset | Parked: a possible partnership, not a data source (PRD 9, 16). **[Joe]** |

## Consequences
- Easier: every rights badge traces to a source field; the provenance pack can cite the flag and the policy.
- Harder: coverage is limited to open collections; Southeast Asian collections are out of v1.
- **[Joe]**

## Evidence
`docs/data-sources.md`: the Met's `isPublicDomain` mapping and quoted terms (drafted 2026-10-11; Joe to confirm against the Met's terms page, issue #4). Slice: 2,588 records, 2,308 open, 280 permission required, 0 unverified. Rights logic tested in `tests/test_schema.py` and `tests/sources/test_met.py`.

## Revisit trigger
An institution grants a dataset or partnership, or a source's terms or flags change.
