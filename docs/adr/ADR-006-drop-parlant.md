# ADR-006: Drop Parlant; routing is handled by the decision step

- **Status:** proposed (decided in planning, PRD Section 19; reasoning sections are Joe's to write)
- **Date:** 2026-10-11 (planning); drafted 2026-10-26

## Context
Parlant was considered during planning. **[Joe]**: what it would have been used for, and what was compared. Routing is the decision step's job: Kev answers Q1 (tier choice), and other flags start as plain rules (FR-7, PRD 10.1). The loop is a fixed workflow with a bounded loop, where models are called at set steps and do not choose tools freely (PRD 10.2).

## Decision
Do not use Parlant. Routing and policy stay in the decision step and in plain policy code.

## Options considered
| Option | Why not chosen |
|---|---|
| Parlant for routing or policy | **[Joe]** |

## Consequences
- Easier: one place decides routing; every rule is code that can be read and tested.
- Harder: **[Joe]**
- **[Joe]**

## Evidence
No measurement. **[Joe]**: sources read when Parlant was considered, with the date checked.

## Revisit trigger
**[Joe]**
