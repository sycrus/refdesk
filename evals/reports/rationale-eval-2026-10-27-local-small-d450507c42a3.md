# Rationale eval: local-small on v0-synthetic (2026-10-27)

> **golden-v0-synthetic: plumbing only, not a claim (ADR-018).** The briefs were
> written by Claude Code and the items are whatever the retriever returned. These
> numbers exercise the pipeline; never quote them as rationale quality.

> **What this measures:** pass rates against the verifier (code checks, then the
> judge, ADR-022). The verifier was screened on synthetic items (judge probes), so
> these are not human-rated quality: that needs golden-v1 and Joe's ratings (#16).

- Generator: `local-small` (model `qwen3.5:9b`); judge: `judge-phi4` (model `phi4`).
- Retriever `jaccard`, top 3 per case. Golden `v0-synthetic` (sha256 `9e07ef1f9795`), corpus `met:2588:d188937d8a53`.
- Prompts: `fit-v2` `b3047ff88c29`, `judge-v1` `3f4d7fefab35`, `rationale-v2` `350808185daa`
- Git `c2fe269f0e61`; config hash `d450507c42a3`; bootstrap 2000 resamples, seed 0. Determinism not checked (model answers are not repeated).
- Cost USD 0.0000; wall clock 442 s.

| Metric | Mean [95% CI] (cases) |
|---|---|
| usable (valid structured rationale) | 1.000 [1.000, 1.000] (n=28) |
| code_pass (every claim value matches the record) | 0.964 [0.917, 1.000] (n=28) |
| judge_pass (judge supported every claim and the fit sentence) | 0.679 [0.560, 0.798] (n=28) |
| verified (both: would show as verified) | 0.679 [0.560, 0.798] (n=28) |

## Verified, by difficulty

| Difficulty | Mean [95% CI] (cases) |
|---|---|
| easy | 0.667 [0.429, 0.905] (n=7) |
| hard | 0.667 [0.333, 0.933] (n=5) |
| medium | 0.688 [0.521, 0.833] (n=16) |

## Why items were not verified

| Reason | Items |
|---|---|
| judge: fit sentence | 24 |
| code: artist | 3 |
| judge: title | 1 |

## Cases

| Case | Brief | Items | Verified |
|---|---|---|---|
| g0-001 | Seventeenth-century flower still lifes for a spring tea tin | 3 | 0.33 |
| g0-002 | Dogs in portraits, for a pet-food brand's heritage campaign | 3 | 0.33 |
| g0-003 | Horses in open landscapes for an equestrian event poster | 3 | 1.00 |
| g0-004 | Cows in pasture for a heritage dairy brand | 3 | 1.00 |
| g0-005 | Birds for a bird-seed packaging range | 3 | 0.33 |
| g0-006 | Portrait miniatures of women from around 1800 for a jewellery-box lid | 3 | 0.67 |
| g0-007 | Cats, any period, for a cat-café menu | 3 | 1.00 |
| g0-008 | Nineteenth-century mountain scenery for an outdoor gear catalogue | 3 | 0.33 |
| g0-009 | Fruit and grape still lifes for a wine label | 3 | 1.00 |
| g0-010 | Classical ruins in landscape, Grand Tour mood, for a travel journal cover | 3 | 1.00 |
| g0-011 | Music-making and musical instruments for a concert-hall season brochure | 3 | 0.67 |
| g0-012 | People absorbed in reading, for a library membership campaign | 3 | 1.00 |
| g0-013 | Views of Venice for a travel poster series | 3 | 1.00 |
| g0-014 | Fifteenth-century Madonna and Child panels with gold for a museum-shop notebook | 3 | 1.00 |
| g0-015 | Gardens for a seed catalogue cover | 3 | 0.67 |
| g0-016 | Seventeenth-century domestic interiors with women for a homeware brand | 3 | 0.00 |
| g0-017 | Ships at sea for a maritime museum's shop range | 3 | 0.67 |
| g0-018 | Boats at night for a whisky label | 3 | 0.67 |
| g0-019 | Rivers in eighteenth-century landscapes for a riverside hotel | 3 | 0.33 |
| g0-020 | Girls in nineteenth-century paintings for a children's clothing brand | 3 | 0.33 |
| g0-021 | More like this: Van Gogh's Wheat Field with Cypresses | 3 | 0.67 |
| g0-022 | Flower paintings, but not Van Gogh: too familiar for this client | 3 | 1.00 |
| g0-023 | Oil sketches and pastels on paper, any subject, for a sketchbook range | 3 | 1.00 |
| g0-024 | Saints in sixteenth-century paintings | 3 | 0.33 |
| g0-025 | Sheep and shepherds for a wool brand's packaging, to be reproduced | 3 | 1.00 |
| g0-026 | Twentieth-century paintings to reproduce on packaging | 3 | 0.00 |
| g0-027 | Crucifixion imagery for a fashion print | 3 | 1.00 |
| g0-028 | Orientalist scenes for a restaurant interior | 3 | 0.67 |
| g0-029 | Make a new painting in the style of David Hockney for our label | not applicable: decline case | |
| g0-030 | Is the Rembrandt I bought at auction genuine? | not applicable: decline case | |
| g0-031 | Generate an image of our product painted like a Monet | not applicable: decline case | |
