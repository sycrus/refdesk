# ADR-024: Re-scope the demonstration goals toward applied AI work

- **Status:** proposed (draft by Claude, 2026-10-31; facts and options updated 2026-11-02). The direction is Joe's (target roles: applied AI and forward-deployed engineering, less MLOps). 
- **Date:** 2026-10-31

## Context
The PRD judges refdesk on two things: product hypotheses (Part A) and demonstration goals D1 to D10 (Part B, PRD 3). PRD 17 sets the bar as "every milestone is built in full whatever the interviews say". The project is now also evidence for job applications in applied AI and FDE roles. Those roles weigh the following more than operating infrastructure: evals on real labels, evidence from users, a working demo, integrations, and the owner's own reasoning.

Facts as of 2026-10-31:
- Every eval number so far comes from `golden-v0-synthetic`, which by rule (ADR-018) is never used for published claims. golden-v1 (#15) is not labelled.
- Not built: the container (#167), kind and CD (#169, #170), drills and postmortems (#171), nightly CI on the self-hosted runner (#166), Kev-4B fine-tune and serving (#164), router in the loop (#165).
- `sycrus/refdesk` is public. ADR-019 and PRD 13A allow the self-hosted runner only while the repo is private.
- Built and merged on 2026-10-31, after the open-issue count in the first draft: the audit view (#159, PR #193), tracing with redaction and golden signals (#172, PR #194), and trajectory evals (#173, PR #195).
- Built and merged on 2026-11-01: the read API for records, search, images and provenance (#200, PR #202) and the read-only MCP server on top of it (#160, PR #203).
- Merged on 2026-11-02: the problem statement (#3, PR #207). It defines Operator and Approver metrics and labels most pains as customer-zero observation or assumption, because no interviews have taken place.
- Interviews (#5) have not started, and PRD Section 4 had asked for them before building past M1. Recruiting art directors is slow for a solo learning project, and the build went ahead under PRD v0.2 ("Build is no longer gated on interviews").
- About 23 working days in total (PRD 17).

## Decision
1. **Core:** golden-v1 and a real rationale eval (#15, #102); a customer-zero log of Joe's own briefs; the public proof (#178), which ships without waiting for outside raters; owner-written reasoning (#12, #153, #176). The MCP server (#160) and the audit view (#159) are built.
   **Opportunistic:** the bake-off (#177) and usability test (#147) run when outreach (LinkedIn) finds willing raters, at whatever n is available, reported with n and intervals. The kits stay ready so a session can start at short notice. Interviews (#5) are asked of raters who are willing.
2. **Lighter:** a plain Docker image, no scan gate (#167), which is also the demo image (ADR-025); the LangGraph port and comparison (#174, #175) only if time allows. Trajectory evals (#173) and tracing (#172) were drafted as lighter, but are already built in full and stay as they are.
3. **Parked** (label `future`, with a revisit trigger): kind, CD and drills (#169 to #171); nightly self-hosted CI (#166); the Kev-4B fine-tune (#164). Routing (#162, #163, #165) is cut to a cost-and-quality comparison of baselines on the existing tiers.
4. **Added:** a two-level demo: a hosted, read-only demo on recorded runs that makes no paid calls, and live sessions on Joe's machine for raters and clients. Details in [ADR-025](ADR-025-hosted-demo-container.md).

Effect on the demonstration goals: D4 drops to "containerised" (no deploy and operate). D5 is parked. D6 is reduced to baselines. D1, D7, D8 and D9 stay in full. D10 becomes optional.

## Options considered
| Option | Why not chosen |
|---|---|
| Status quo: every M0-M5 issue stays a commitment, built as its blockers clear, and D1-D10 all stay claims (PRD 17: "every milestone is built in full") | I am building whatever I can that I'm not a blocker in. |
| Re-scope as drafted above | chosen |
| Gate further build on interviews first (PRD Section 4 as first written) | Waiting for interviews leaves nothing to show in the meatime. As a learning project, and current upskilling phase is more technical than requirements gathering/ testing. |
| Cut harder: stop new build work and spend the time only on labels, user evidence and write-ups | I am building whatever I can that I'm not a blocker in. User evidence depends on availability of testers, and write ups can be done once I have learnt from building, and later, testing. |
| Full-scale user evidence: 8-10 interviews, three art directors in moderated bake-off and usability sessions | Depends on interest and recruitment of testers. |
| Customer-zero evidence only: no outside raters at all | Requirements gathering and translation of user evidence is part of the FDE learning journey. Outside raters are still important to ensure that the implementation scales to other users and potentially reveal other use cases. |
| Keep the fine-tune (#164) and park the user work (#147, #177) instead |I prioritise what the resources I have now can deliver and what makes the strongest case for applied AI roles. The fine-tune is weighted towards ML engineering and has a long chain of dependencies (#16, #153, #162, #163); user work is already opportunistic, so parking it frees little time. |
| Delete the parked issues instead of labelling them `future` | Easier to keep on record in the event we need to revisit, and backlog stays honest. |

## Consequences
- Easier: the remaining days go to the work an applied AI or FDE reviewer reads: a real eval with intervals, user evidence, a demo, and decisions in Joe's own words.
- Harder: the project can no longer claim D4 (deploy and operate) or D5 (fine-tune and calibrate). Those claims leave the README and the PRD Part B table rather than staying as unbuilt promises.
- Harder: more of the remaining work is `ready-for-human`. It depends on Joe's time and on finding raters, not on the build loop, so the loop's queue gets short.
- Harder: user evidence may not arrive. If it does, it is likely small, the bake-off intervals will be wide, and H1-H4 may end as "not shown" rather than won or lost. The PRD decision rule (3A) and honest reporting (11.6) cover this; the README states n, or states that the bake-off has not run.
- #178 (public proof) lists #177 as a blocker. It is decoupled: the proof ships on golden-v1 and the rationale eval, and the bake-off results are added when they exist.
- Conflicts to resolve if accepted:
  - ADR-001 (accepted) stays accepted, but its build is parked. Its status line notes the parking.
  - ADR-009 (kind vs Cloud Run) is deferred.
  - ADR-019's nightly tier is deferred. The repo being public rules out the self-hosted runner anyway.
  - PRD 3, 17 and 19 are updated, with a line in the revision log.

## Evidence
No measurement. This is a scope decision, not a technical one. Its inputs are the target roles Joe stated on 2026-10-31, the open-issue list on 2026-10-31 (`gh issue list --state open`), and PRD 3 and 17.

Role requirements, added as job descriptions are reviewed. Record the role type and what is asked, not the employer. Impressions are marked as impressions.

| Date | Role type | What it asks for | Bearing on this decision |
|---|---|---|---|
| **[Joe]** | e.g. FDE, AI engineer, applied AI | | |
## Revisit trigger
- An application or interview asks for deployment or fine-tuning evidence.
- The core items are finished with days left in the budget.
- The target roles change.
- Outreach finds raters: run #177 (and #147 if they have time), then update the README.
