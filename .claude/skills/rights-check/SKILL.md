---
name: rights-check
description: Determine, record or export the rights basis for an artwork record or a set of results. Use for "can we use this image", "check rights", "rights basis", "provenance pack", "credit line", or before any export in reproduction mode.
---

# Rights check

This tool records what the museum states. It does not give legal advice and does not decide.

## Rules

1. Read rights only from the source's structured fields (the public-domain or CC0 flag and the licence field). If a field is missing or ambiguous, the result is `unverified`.
2. Never infer public-domain status from an artist's death date, the work's age, or your own memory.
3. Collections whose terms require permission (for example Singapore national collections) are `permission required`. Do not fetch or reuse their images. Link to the record and tell the user to request permission.
4. Distinguish usage modes. Reference only needs less than reproduction. For reproduction also check that a usable image URL exists and note resolution.
5. Rights vary by country and museum. Add the target country to the record and add a not-legal-advice note.

## Record format

For each item write:
`source, object_id, record_url, flag_field, flag_value, licence_string, checked_at, usage_mode, target_country, credit_line, status`
where status is one of `open (as stated by source)`, `unverified`, `permission required`.

## Provenance pack

On request, export a CSV (and PDF if asked) with one row per approved item, plus run ID, model and adapter versions, and the not-legal-advice note. Do not export items that are `unverified` unless the user marks them as reviewed.

## Checks

- Re-verify the flag against the live source if the record is older than the threshold in `docs/data-sources.md`.
- If the licence string differs from what the source documentation says, flag it and add a contract test (see add-museum-source).
