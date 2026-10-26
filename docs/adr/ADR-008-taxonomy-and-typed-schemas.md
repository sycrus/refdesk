# ADR-008: Taxonomy and typed schemas, not an ontology

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Records from different museums must share one shape, and the rights rules must hold whichever adapter wrote a record (FR-1, FR-2). Status labels are learned by operators and must never be paraphrased (PRD 8A). An ontology is listed as optional in demonstration goal D9 and sits in Tier 4, built only if the PRD pulls it in (PRD 3, 17).

## Decision
Use typed schemas and a small fixed taxonomy for governance: frozen Pydantic models for records and rights records (`src/refdesk/schema.py`) and fixed status wording in one constants file (`src/refdesk/wording.py`). An ontology is optional (Tier 4).

## Options considered
| Option | Why not chosen |
|---|---|
| A formal ontology now | **[Joe]** |
| Free-form fields with no schema | **[Joe]** |

## Consequences
- Easier: the schema rejects an "open" status with no structured source field behind it; wording changes fail a test.
- Harder: relations between concepts (periods, movements, subjects) are not modelled; adding a source means fitting the shared schema.
- **[Joe]**

## Evidence
Built: `tests/test_schema.py` (rights invariants), `tests/test_wording.py` (fixed wording).

## Revisit trigger
A feature needs relations between concepts that typed fields cannot express, for example mapping named periods to dates across sources (see issue #64).
