# Problem statement

Status:  Draft v1, Joe

What this file does: it states the one decision refdesk improves, how we will know it improved, and what a wrong answer costs. The PRD hypotheses (Section 3A), the decision contract (`docs/decision-contract.md`) and the success metrics (Section 15) should all trace back to it. Without it, "better" has no anchor and the evals measure whatever is easy to measure.

## 1. The decision being improved

- **Who decides:**
1. Operators, Creatives searching for assets to use directly or remix (Visual Designers, Art Directors and Art-based Creative Directors etc), 
2. Approvers, people who sign off on the legality and appropriateness of the asset (Creative Directors, producers, studio heads etc).

- **What they decide:** 
1. Which images to use for a specific use case (branding, campaigns),
2. Information that helps to further the search along a path or decide on a direction.

- **When, and under what pressure (time, client, budget):** 
Specific to cases when the budget doesn't allow for numerous stock or paid images, or when the art direction is using images of artworks from museums, and going through separate sites are time consuming or troublesome.

- **What they do with the result:** 
Users can use the images as is for assets (primary use case), or as moodboards for pitches.

### Terms

| Term | Meaning |
|---|---|
| Operator | Users whose goal is to search and pin images |
| Approver | Users whose goal is to clear the Operator's selection for production |
| Board | One query and its results |
| Thread| Related searches, linked by the #206 rule |
|  Pin| Adds items to a Moodboard |
|  Moodboard| Collection of images pinned and organized by Operators |
|  Refine| Keyword edits to the same search terms, same thread |
|  Pivot| Signiciant edits to the search terms based on ideas obtained from current thread, now moved to a new and different thread |

## 2. Why it is hard today

| Pain | Evidence or assumption | Source |
|---|---|---|
| Hard to find CC0 or other similar permissive licenses for images by theme across corpuses | Open access sites are institution specific | Observed (Customer zero), query: "smile", Museo, Google Art & Culture |
| Hard to find provenance outside of museum sites, making rights to use uncertain, harder to find more work by same artist | Observed (Customer zero), query: "smile" | Pinterest, Cosmos (Public Work)
| Rigid keyword or tag-based results, instead of proper image understanding | Trial searches across various museum open access | Met Open Access, Cosmos |
| No justification for why images are surfaced against the search, beyond tags | Observed (Customer zero), query: "smile" | Museo (clicking on museum entry redirects to site without justification) |
| Only obvious or more famous works are surfaced | Assumption H4 | |

## 3. Today's baseline

| Current approach | Designed For | What it gets right | Where it fails | Measured how / when |
|---|---|---|---|---|
| Keyword based museum search | Operator | Gets images based on keyword matching | Not all have understanding of image content |  |
| Aggregated search |  Operator | Allows search across multiple museum collections | Not enough data to defend the authorship of each result |  |
| Metadata |  Operator/Approver | Information provided about the image | Not comprehensive, or missing metadata for further search or approvals |  |

## 4. Success metrics

### 4a. Operator: relevance (comparison)

- **User story:** 
  As an art director, I want to be able to search for images around a theme , so I can pin them as potential directions .
- **Primary metric:** 
  - Share of returned images the art director marks as "pinned", per search of 12 results.
- **Target and comparison:** 
  -  At least 10 percentage points above the best baseline, reported with a 95% interval; a tie is reported as a tie.
- **Measured on:** 
  - 20 held-out briefs, 3 editors rating per item, system labels hidden.
- **Secondary (reported, not gated):** 
  - Minutes to a pin.

### 4a-2. Operator decision 2: exploration (descriptive, not gated)

- **User story:**
  As an art director, I want to be able to view relevant information around the images so I can use those terms to refine my searches, or pursue different directions.
- **Unit of measurement (the thread):** 
  - One project thread with search terms logged: the first search and every later search that refines it. 
  - It ends when the editor exports it, drops it, or leaves it idle for 14 days. Not a browser session, because work on one idea spans days.
- **Same thread or new thread:** 
  - Refinements made with the tool's own controls (filter change, "more like this", adjacent era such as 1970s → 1980s, similar styles) continue the thread.
  - A new free-text search starts a new thread unless the editor chooses "continue this thread".
- **What counts as a pivot:** 
  - User given an option to add to existing thread but does not (tool guesses and suggests, but user ignores or rejects).
- **Thread yield:** 
  - 70% of threads end with at least one pinned image.
- **Effort to first candidate:** 
  - Median 3 searches to the first pinned image.
  - Median 3 clicks of "Show me more" to the first pinned image.
- **Pivot yield:** 
  - 30% of pinned images came from a search after the first.
- **Productive pivot window:**
  - A pin within the next 5 actions.
- **Abandoned direction (not a failure):** 
  - A one-question prompt when a search thread is closed: "Dropping this because: results were poor / the idea doesn't work / found enough / other". "The idea doesn't work", reached quickly, counts as a useful outcome. Dropped boards/threads are reported separately and do not count against thread yield.
- **Compared against:** 
  - The same tool with images shown as title only, no surfaced metadata or reasons, ie without additional context
- **Measured on:** 
  - 6 think-aloud sessions plus 2 weeks of own use; participants consent to interaction logging; reported as counts and examples, no target.
- **Known ways it misleads:** 
  - Curiosity clicks that go nowhere look like interest
  - Own-use sessions are biased by knowing the system.

### 4b. Approver: clearance (gate)

- **User story:**
  - As a producer, I want each pinned image to come with its licence terms and sources, so I can sign off without searching elsewhere.
- **Gate metric:** 
  - 0 images shown as "Open (as stated by source)" whose museum record does not give an open license (CC0 or public domain) at the time checked.
- **Sufficiency metric:** 
  - At least 80% of pinned images  signed off by the producer from the export alone.
- **Over-flagging limit:** 
  - No more than 25% of images marked "needs human check" on the evaluation set.
- **Measured on:** 
  - Licence status counted against the museum's records (not rater opinion); sign-off rated by 2-3 producers.

### 4c. How they combine

- **Claim holds when:** 
  - Operator metric beats the best baseline AND the Approver gate passes. Either failing means the claim fails.
- **Guardrails (must not get worse; some are true by design, so they are not headline results):** 
  - Every surfaced image has a licence record
  - median cost per search at or below the cap
  - p95 latency under  seconds.
- **What result makes me reposition as a demonstration (PRD 3A decision rule):** 
  - no Operator win over the best baseline on relevance or novelty, whatever the Approver result.

## 5. Working definition: usable board

**Status: placeholder, pending interview evidence.** Revise after the interviews; changes to be recorded in the change log below.

A board is usable when all of these hold:

- at least 8 of search results accepted by the art director;
- 0 wrong attributions shown as Attribution verified from record;
- every item has a rights label;

## 6. Cost of each kind of wrong answer

| Wrong answer | Example | Who pays | Cost (rough) | Recoverable? | Rank |
|---|---|---|---|---|---|
| Wrong attribution shown as verified | Image attributed to wrong artist| Producer and client|Takedown, re-edit, time spent to redo, compromised client relationship| Partly: after release, only at high cost|2 |
| Rights status wrong (shown Open, is not) | Image says CC0 but is licensable | Producer and client| Takedown, replacement with edits, copyright lawsuits, compromised client relationship| Partly, high cost| 1 |
| Obvious / stale search results only | Literal results of still life with fruits only| Art/Creative Directors| Time spent to refine search terms, trust in platform| Yes, but trust in platform eroded| 5|
| Good reference missed | Image that fits the search term is omitted from search results| Art/Creative Directors| Missed opportunity, time to consider less ideal images| Yes|7 |
| Over-abstention ("needs human check" on everything) | Every image has the same label| Producer | Time spend to evaluate every single image| No, trust in platform to perform this feature is gone| 6|
| Cost overrun on a board | Spend cap exceed on one board as results are poor| Art/Creative Directors| Cost to use the platform far outweighs potential savings| Partly, but trust in platform eroded| 3|
| Time overrun on a board | Too much time spent on one board as results are poor| Art/Creative Directors| Manpower costs to use the platform far outweighs potential savings| Partly, but trust in platform eroded| 4|

- **The asymmetry in one sentence** (which error is far worse than the others, and so what the system should prefer to do when unsure): 
  - A wrong 'Attribution verified from record' image far more costly than a missed image, so when the attribution is unclear the tool marks it 'needs human check' rather than 'Attribution verified from record'.

## 7. Non-goals

- Editing images
  - Reason: a different product and different rights questions; it would dilute the licence-clearance claim.
- Legal advice on image license rights
  - Reason: legal service, outside what a search tool can be accountable for.

## 8. Open questions and how they get answered

| Question | Answered by (interview, eval, bake-off) | Milestone  |Blocks |
|---|---|---|---
| What interaction events are logged?| Interviews, talk alouds| #206| 4a-2 metrics|
| What consent participants give? | Design decision| M5, before #147| Any session with logging|
| Where are events stored? | Engineering decision| M5 before #147|4a-2 metrics|
| How is an abandoned concept recorded without interrupting exploration? | Interviews on user flow and typical creative processes and workflows, think alouds| #206|4a-2 abandonment|
| Is pinning to a moodboard separate from S3 select and S6 approval?| Prototype| #206|4b|

## Change log

| Date | Change | Why |
|---|---|---|
| 2026-11-02 | First version |  |
