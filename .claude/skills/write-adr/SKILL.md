---
name: write-adr
description: Create or update an Architecture Decision Record in docs/adr. Use when a significant technical choice is made or reversed (model, library, data source, evaluation method, deployment, scope), or when asked to "write an ADR", "record this decision", or "supersede ADR".
---

# Write an ADR

One decision per file. ADRs are historical records, written as if the decision is being made now.

## Steps

1. Find the next number in `docs/adr/` (format `ADR-NNN-kebab-title.md`). Check `docs/adr/README.md` for the index and for related or superseded records.
2. Ask the user for the reasoning if the decision is learning-critical (see CLAUDE.md). Offer a draft of the facts, but let the user supply the judgment and the rejected-options reasoning.
3. Write the file with these sections:
   - **Status**: proposed, accepted, superseded by ADR-NNN, or rejected
   - **Date**
   - **Context**: the problem and constraints, with links to the PRD section
   - **Decision**: what was chosen, in one or two sentences
   - **Options considered**: each option and why it was rejected
   - **Consequences**: what gets easier, what gets harder, what is now locked in
   - **Evidence**: links to eval reports, benchmarks or sources, with the date checked
   - **Revisit trigger**: what result or event would reopen this
4. Update `docs/adr/README.md` (the index). If the new ADR supersedes another, edit the old one's status only.

## Rules

- Never invent evidence. If there is none yet, say "no measurement yet" and name the test that would supply it.
- Record popularity, hype or familiarity as what they are, not as evidence.
- Keep it short. If it needs more than a page, split it.
