# Fit-sentence probe (2026-10-27)

> **Superseded by `fit-probe-2026-10-27-realistic.md`; kept, not overwritten.** This run's
> realistic set paired records with random briefs ("female nudes suit a poster for an
> equestrian event"). phi4 flagged half of those faithful items, judging the pairing
> rather than the facts, which is not what generators produce after retrieval (#135).

> phi4, one fit sentence at a time, temperature 0. Faithful items are opinions about
> mood or use (some name one of the record's own subject tags); corrupted items add
> one fact the record does not give. Synthetic, 20 records, seed 0 (issue #97).

> The realistic set (#135) repeats the record's own facts and names the brief's
> use, as generators do; prompts measured without the brief still get none.

| Set | Prompt | Smuggled facts caught | False alarms on faithful items | Invalid |
|---|---|---|---|---|
| synthetic opinions | `fit-v1` | 19/20 | 2/20 | 0 |
| realistic fit sentences | `fit-v1` | 20/20 | 14/20 | 0 |
| synthetic opinions | `fit-v2` | 19/20 | 0/20 | 0 |
| realistic fit sentences | `fit-v2` | 19/20 | 10/20 | 0 |
| synthetic opinions | `judge-v1` | 20/20 | 17/20 | 0 |
| realistic fit sentences | `judge-v1` | 20/20 | 19/20 | 0 |
