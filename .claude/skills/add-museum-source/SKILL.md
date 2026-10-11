---
name: add-museum-source
description: Add or update an adapter that ingests a museum or open-collection source. Use for "add a source", "integrate the Rijksmuseum", "ingest the Cleveland collection", "update the Met adapter", or when a source's API or licence changes.
---

# Add a museum source

## Before writing code

1. Read the source's terms and open-access policy. Confirm an open licence and a machine-readable rights flag. If terms require permission, stop and tell the user. Do not build an adapter.
2. Record the source in `docs/data-sources.md`: licence, API or dump, rights-flag field, rate limits, authentication, date checked.
3. Fetch a few live responses and compare with the documentation. Note any difference (field names, licence strings).

## Implementation

- Implement a source interface with `iter_records()` returning the normalised schema in the PRD (FR-1). Include the rights record: `flag_field, flag_value, licence_string, checked_at`.
- Be polite: respect rate limits, cache responses, make ingestion resumable and idempotent.
- Store metadata and links. Download images only where the licence allows, and say so in the data-sources file.
- Start with a slice (for example paintings only) before a full ingest.

## Tests (write first)

- Schema test: every record has the required fields.
- Rights test: only objects with the source's open flag are marked open.
- Drift test: the licence value returned by the live API matches what the adapter expects. Fail loudly if it differs from documentation.
- Rate-limit test using the mock server.

## Finish

- Update `docs/data-sources.md` and `docs/adr/` if the choice of source was a decision.
- Report counts: records ingested, records skipped (and why), objects flagged open.
