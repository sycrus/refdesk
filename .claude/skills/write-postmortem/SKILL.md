---
name: write-postmortem
description: Write a blameless postmortem for a failure drill, outage, bad release or serious bug. Use for "postmortem", "what broke", "write up the drill", or after a Kubernetes or CI failure exercise.
---

# Blameless postmortem

File: `postmortems/YYYY-MM-DD-slug.md`. Add a row to `postmortems/INDEX.md`.

## Gather facts first

Collect logs, commands run, timestamps, commit SHAs and metrics. Build the timeline from evidence, not memory.

## Sections

- **Summary**: one paragraph.
- **Impact**: what failed, for whom, for how long.
- **Timeline**: with times, including when it was detected and by what signal.
- **Root cause and trigger**: separate the underlying cause from what set it off.
- **What went well and what went badly**
- **Time to detect, time to recover**: measured, not estimated.
- **Actions**: each has an owner and a way to verify it worked. Mark which are verified.

## Rules

- Blameless. Describe systems and decisions, not people.
- Ask the user for hindsight analysis and lessons. Do not write the lessons for them.
- Do not rewrite the timeline with hindsight.
- After a fix, rerun the original drill and record the result in the postmortem.
