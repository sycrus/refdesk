# Rationale prompts: v1 against v2 (2026-10-27)

> **golden-v0-synthetic: plumbing only, not a claim (ADR-018).** These runs compare
> prompt versions on the same 28 cases × top 3 (84 items). They measure pass rates
> against the verifier, not human-rated quality. Issue #135.

Generator `local-small` (qwen3.5:9b, `reasoning_effort: none`), judge `judge-phi4`
(phi4, one statement at a time, temperature 0), retriever `jaccard`. Generation is not
deterministic: the two v2 runs drew different rationales (code_pass 0.976 and 0.964).

## Pass rates (case means, 95% bootstrap CI)

| Run | Report | code_pass | judge_pass = verified | Claims-only verified* |
|---|---|---|---|---|
| rationale-v1 + fit-v1 (baseline) | `rationale-eval-2026-10-27-local-small-285bc2c7ff8a.md` | 0.881 [0.798, 0.952] | 0.179 [0.107, 0.250] | 0.560 |
| rationale-v2 + fit-v1 | `rationale-eval-2026-10-27-local-small-2ff34049ca11.md` | 0.976 [0.940, 1.000] | 0.381 [0.274, 0.500] | 0.940 |
| rationale-v2 + fit-v2 | `rationale-eval-2026-10-27-local-small-d450507c42a3.md` | 0.964 [0.917, 1.000] | 0.679 [0.560, 0.798] | 0.952 |

\* Code checks plus the judge on claims, ignoring the fit-sentence verdict. Computed from
each run's `runs/<hash>/cases.jsonl`; no interval.

## Why items were not verified

| Reason | v1 + fit-v1 | v2 + fit-v1 | v2 + fit-v2 |
|---|---|---|---|
| judge: fit sentence | 53 | 48 | 24 |
| judge: a claim | 41 | 3 | 1 |
| code: artist (attribution qualifier dropped) | 9 | 2 | 3 |
| unusable rationale | 1 | 0 | 0 |

## What changed and what it means

- **rationale-v2 fixes the claims.** Claim text now restates only the value ("Its medium
  is oil on canvas."), so judge flags on claims fell from 41 to 3, and dropped attribution
  qualifiers fell from 9 to 2–3 (why is not measured).
- **qwen ignores "no facts in the fit".** rationale-v2 asks for an opinion-only fit
  sentence; most fit sentences still repeat the record ("The inclusion of Cats in the
  subject tags makes this painting suitable for a cat-café menu"), and phi4 with fit-v1
  flags many correct ones, especially dates turned into centuries ("created in the 19th
  century" for 1848–49).
- **fit-v2 is more lenient on real output and on smuggled facts.** In the realistic fit
  probe (`fit-probe-2026-10-27-realistic.md`) fit-v2 caught 13/20 smuggled facts against
  fit-v1's 20/20, with 5/20 false alarms against 7/20. In the v2 + fit-v2 run, Claude's
  read of the passed fit sentences found at least one fact the record does not give
  ("Monet's Impressionist style", g0-022). Not checked by a person.

## Options (Joe decides)

1. **rationale-v2 + fit-v1** (strict). About 0.38 verified; every other item shows "Needs
   human check". Keeps the measured 20/20 catch rate on smuggled facts.
2. **rationale-v2 + fit-v2** (lenient). About 0.68 verified; misses about a third of
   smuggled facts in the probe.
3. **The status rests on claims; the fit sentence is flagged on its own.** About 0.94
   verified. The fit sentence keeps fit-v1's strict check, but a flag marks the sentence
   ("Opinion flagged: may state a fact the record does not give") instead of withholding
   "Attribution verified from record" for an attribution that passed. This changes what
   the badge covers (PRD 8B wording, ADR-022), so it needs an ADR-022 amendment.

Whichever is chosen, it is pinned in `config/retrieval.yaml` (`api.reasoning.prompts`),
which keeps v1 until then.
