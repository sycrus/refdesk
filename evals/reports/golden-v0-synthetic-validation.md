# golden-v0-synthetic: validation report

- Generated: 2026-10-11T14:41:42+00:00 by `scripts/build_golden_v0.py`
- Corpus version: `met:2588:d188937d8a53`
- Cases: 31. Errors: **0**. Rule-size problems: **0**.
- Distinct records referenced: 689
- Expected references per retrieve case: min 5, median 28, max 50
- Prompt files checked for leakage: none exist yet

> **Synthetic. Never use for claims (ADR-018).** Every case was written by Claude Code,
> and its expected references come from an explicit rule over metadata, not from judgement.
> Rules over metadata favour the metadata baseline, so this set must not be used to compare
> retrievers. It exists to build and test the eval harness.

## Errors

None.

## By difficulty

| Value | Cases |
|---|---|
| easy | 7 |
| hard | 8 |
| medium | 16 |

## By expected_decision

| Value | Cases |
|---|---|
| decline | 3 |
| retrieve | 28 |

## By usage_mode

| Value | Cases |
|---|---|
| reference_only | 29 |
| reproduction | 2 |

## By tags

| Value | Cases |
|---|---|
| anchor | 1 |
| animals | 6 |
| architecture | 1 |
| authentication | 1 |
| avoid list | 1 |
| boats | 2 |
| cities | 1 |
| culturally sensitive | 2 |
| decline | 3 |
| image generation | 1 |
| interiors | 1 |
| landscape | 5 |
| living artist | 1 |
| medium | 2 |
| miniatures | 1 |
| mood | 1 |
| music | 1 |
| people | 3 |
| period | 8 |
| place | 1 |
| portraits | 2 |
| religious | 3 |
| reproduction | 2 |
| rights | 1 |
| still life | 2 |

## Cases

| ID | Difficulty | Expected | Rule |
|---|---|---|---|
| g0-001 | easy | 7 | `{"tags_all": ["Still Life", "Flowers"], "century": 17}` |
| g0-002 | easy | 26 | `{"tags_all": ["Dogs", "Portraits"]}` |
| g0-003 | easy | 15 | `{"tags_all": ["Horses", "Landscapes"]}` |
| g0-004 | easy | 42 | `{"tags_all": ["Cows"]}` |
| g0-005 | easy | 33 | `{"tags_all": ["Birds"]}` |
| g0-006 | easy | 50 | `{"classification": ["Miniatures"], "tags_all": ["Women"], "year_range": [1780, 1820]}` |
| g0-007 | easy | 17 | `{"tags_all": ["Cats"]}` |
| g0-008 | medium | 28 | `{"tags_all": ["Mountains"], "century": 19}` |
| g0-009 | medium | 29 | `{"tags_all": ["Still Life"], "tags_any": ["Fruit", "Grapes"]}` |
| g0-010 | medium | 30 | `{"tags_all": ["Ruins"]}` |
| g0-011 | medium | 38 | `{"tags_any": ["Musical Instruments", "Music"]}` |
| g0-012 | medium | 23 | `{"tags_all": ["Reading"]}` |
| g0-013 | medium | 18 | `{"tags_any": ["Venice"]}` |
| g0-014 | medium | 35 | `{"tags_all": ["Madonna and Child"], "century": 15, "medium_any": ["gold"]}` |
| g0-015 | medium | 39 | `{"tags_all": ["Gardens"]}` |
| g0-016 | medium | 24 | `{"tags_all": ["Interiors", "Women"], "century": 17}` |
| g0-017 | medium | 22 | `{"tags_any": ["Ships"]}` |
| g0-018 | medium | 5 | `{"tags_all": ["Boats"], "tags_any": ["Night", "Evening"]}` |
| g0-019 | medium | 10 | `{"tags_all": ["Rivers"], "century": 18}` |
| g0-020 | medium | 29 | `{"tags_all": ["Girls"], "century": 19}` |
| g0-021 | hard | 16 | `{"artist_contains": "van gogh", "exclude_ids": ["met:436535"]}` |
| g0-022 | hard | 48 | `{"tags_all": ["Flowers"], "artist_excludes": "van gogh"}` |
| g0-023 | medium | 20 | `{"classification": ["Pastels & Oil Sketches on Paper"]}` |
| g0-024 | medium | 27 | `{"tags_all": ["Saints"], "century": 16}` |
| g0-025 | medium | 36 | `{"tags_any": ["Sheep", "Shepherds"], "rights": "open"}` |
| g0-026 | hard | 21 | `{"century": 20, "rights": "open"}` |
| g0-027 | hard | 40 | `{"tags_all": ["Crucifixion"]}` |
| g0-028 | hard | 41 | `{"tags_any": ["Orientalist"]}` |
| g0-029 | hard | decline | `null` |
| g0-030 | hard | decline | `null` |
| g0-031 | hard | decline | `null` |
