# ADR-024: Re-scope the demonstration goals toward applied AI work

- **Status:** proposed (draft by Claude, 2026-10-31). The direction is Joe's (target roles: applied AI and forward-deployed engineering, less MLOps). The reasoning sections are his to write.
- **Date:** 2026-10-31

## Context
The PRD judges refdesk on two things: product hypotheses (Part A) and demonstration goals D1 to D10 (Part B, PRD 3). PRD 17 sets the bar as "every milestone is built in full whatever the interviews say". The project is now also evidence for job applications in applied AI and FDE roles. Those roles weigh the following more than operating infrastructure: evals on real labels, evidence from users, a working demo, integrations, and the owner's own reasoning.

Facts as of 2026-10-31:
- Every eval number so far comes from `golden-v0-synthetic`, which by rule (ADR-018) is never used for published claims. golden-v1 (#15) is not labelled.
- Not built: the container (#167), kind and CD (#169, #170), drills and postmortems (#171), nightly CI on the self-hosted runner (#166), Kev-4B fine-tune and serving (#164), router in the loop (#165).
- `sycrus/refdesk` is public. ADR-019 and PRD 13A allow the self-hosted runner only while the repo is private.
- Built and merged on 2026-10-31, after the open-issue count in the first draft: the audit view (#159, PR #193), tracing with redaction and golden signals (#172, PR #194), and trajectory evals (#173, PR #195).
- About 23 working days in total (PRD 17).

## Decision
**[Joe]**, to confirm or change. Draft:
1. **Core:** golden-v1 and a real rationale eval (#15, #102); user evidence (#5, #147, #177); the public proof (#178); owner-written reasoning (#12, #153, #176); MCP server (#160). The audit view (#159) is built.
2. **Lighter:** a plain Docker image, no scan gate (#167), which is also the demo image (ADR-025); the LangGraph port and comparison (#174, #175) only if time allows. Trajectory evals (#173) and tracing (#172) were drafted as lighter, but are already built in full and stay as they are.
3. **Parked** (label `future`, with a revisit trigger): kind, CD and drills (#169 to #171); nightly self-hosted CI (#166); the Kev-4B fine-tune (#164). Routing (#162, #163, #165) is cut to a cost-and-quality comparison of baselines on the existing tiers.
4. **Added:** a hosted, read-only demo, or a screen recording, that makes no paid calls. The hosting choice is a separate ADR ([ADR-025](ADR-025-hosted-demo-container.md)).

Effect on the demonstration goals: D4 drops to "containerised" (no deploy and operate). D5 is parked. D6 is reduced to baselines. D1, D7, D8 and D9 stay in full. D10 becomes optional.

## Options considered
| Option | Why not chosen |
|---|---|
| Keep the PRD as written: build every milestone in full | **[Joe]** |
| Re-scope as drafted above | (chosen, if confirmed) **[Joe]** |
| Cut harder: stop new build work and spend the time only on labels, user evidence and write-ups | **[Joe]** |
| Keep the fine-tune (#164) and park the user work (#147, #177) instead | **[Joe]** |
| Delete the parked issues instead of labelling them `future` | **[Joe]** |

## Consequences
- Easier: the remaining days go to the work an applied AI or FDE reviewer reads: a real eval with intervals, user evidence, a demo, and decisions in Joe's own words.
- Harder: the project can no longer claim D4 (deploy and operate) or D5 (fine-tune and calibrate). Those claims leave the README and the PRD Part B table rather than staying as unbuilt promises.
- Harder: more of the remaining work is `ready-for-human`. It depends on Joe's time and on recruiting art directors, not on the build loop, so the loop's queue gets short.
- Conflicts to resolve if accepted:
  - ADR-001 (accepted) stays accepted, but its build is parked. Its status line notes the parking.
  - ADR-009 (kind vs Cloud Run) is deferred.
  - ADR-019's nightly tier is deferred. The repo being public rules out the self-hosted runner anyway.
  - PRD 3, 17 and 19 are updated, with a line in the revision log.
- **[Joe]** anything else: what you give up, and how you will explain the cut in an interview.

## Evidence
No measurement. This is a scope decision, not a technical one. Its inputs are the target roles Joe stated on 2026-10-31, the open-issue list on 2026-10-31 (`gh issue list --state open`), and PRD 3 and 17. **[Joe]**: any job postings or conversations that informed it, with dates. Record impressions as impressions.

## Revisit trigger
**[Joe]**. Candidates:
- An application or interview asks for deployment or fine-tuning evidence.
- The core items are finished with days left in the budget.
- The target roles change.
