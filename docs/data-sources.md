# Data sources

One row per source. Read each source's own terms before relying on a row (PRD 9, issue #4).
**Status of this file:** the Met section was drafted by Claude Code on 2026-10-11 from the sources linked below. Joe confirms it against the Met's own terms page and marks it confirmed. AIC and Cleveland are not started.

## Summary

| Source | Licence | Access | Rights-flag field | Rate limit | Auth | Date checked | Status |
|---|---|---|---|---|---|---|---|
| The Met | CC0 for public-domain works and for the dataset | Collection API (JSON); bulk CSV on GitHub | `isPublicDomain` (bool) | "Please limit request rate to 80 requests per second." We use 1/s. | None | 2026-10-11 | **Draft, Joe to confirm** |
| Art Institute of Chicago | | | | | | | Not started |
| Cleveland Museum of Art | | | | | | | Not started |
| Singapore collections | Permission required | Do not scrape | n/a | n/a | n/a | | Not open |

## The Met

**What the source says** (quoted):
- API docs: the Met "has waived all copyright and related or neighboring rights to this dataset using the Creative Commons Zero license" (over 470,000 artworks), "for unrestricted commercial and noncommercial use". "The use of the Metropolitan Museum of Art Collection API is subject to these terms and conditions" (links to metmuseum.org terms).
- API docs: "we do not require API users to register or obtain an API key".
- API docs, field `isPublicDomain`: "When 'true' indicates an artwork in the Public Domain". Field `rightsAndReproduction`: "Credit line for artworks still under copyright".
- GitHub open-access README: images are not part of the CC0 dataset; open-access artworks are marked with the CC0 icon on the website, and image use is governed by the Open Access page.
- GitHub README guidelines: consider attributing the Met; do not imply endorsement or use the Met's trademarks; make clear when data has been modified.

**How refdesk reads rights** (`src/refdesk/sources/met.py`):

| `isPublicDomain` | Status stored | Image link stored |
|---|---|---|
| `true` | Open (as stated by source) | yes (`primaryImageSmall`) |
| `false` | Permission required | no |
| missing, or not a boolean | Unverified | no |

`licence_string` stores `rightsAndReproduction` verbatim (for example "© Estate of Philip Guston"), or nothing when it is empty. The API has **no licence field**: the CC0 basis comes from the policy above, not from each record. The provenance pack should cite the policy URL next to the flag.

**Slice:** department 11 "European Paintings", classification "Paintings": 2,648 object IDs listed on 2026-10-11 (before the classification filter). That is smaller than the PRD's "10-20k" estimate. At 1 request per second a full slice ingest takes about 45 minutes.

**Images:** store links only. Images are downloaded only for `isPublicDomain: true`, and only if a later task needs them.

**Known drift and gotchas** (each has a contract test in `tests/sources/test_met.py`):
- `GET /v1/search` was retired on 2026-10-01 and now returns **410 Gone**. Use `/v1.1/search` (`offset` and `limit`, max 500 per page, `offset + limit <= 10,000`).
- No rate-limit headers are returned, so the adapter throttles itself and retries 429 and 5xx with backoff.
- In-copyright objects return empty `primaryImage` and `primaryImageSmall`.
- `rightsAndReproduction` can be empty for an in-copyright object (e.g. 492759), so an empty notice does not mean open. Only the flag counts.
- Empty strings mean missing. They are stored as `None`.
- `artistPrefix` ("Workshop of", "Attributed to") is part of the attribution and is kept.
- `metadataDate` gives the last update, which can drive incremental re-ingest (#8).
- Department 11 also holds non-paintings: the first ingest run met `classification: "Miniatures"`. The adapter keeps only `"Paintings"` and records each skip with its reason in `ingest_progress`.
- metmuseum.org web pages returned HTTP 429 to automated fetches on 2026-10-11, so the terms and Open Access pages could not be read automatically. **Joe: read them in a browser.**

**Sources** (checked 2026-10-11):
- API documentation: https://metmuseum.github.io/
- Open access dataset and guidelines: https://github.com/metmuseum/openaccess (licence CC0-1.0)
- Open Access announcement: https://www.metmuseum.org/perspectives/open-access-at-the-met
- To confirm by hand: https://www.metmuseum.org/information/terms-and-conditions and https://www.metmuseum.org/hubs/open-access
