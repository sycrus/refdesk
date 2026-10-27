# golden-v1 labelling (issue #15, ADR-018)

Work in progress for `golden-v1`. Nothing here is a golden set yet; the frozen file is written only after the trust rules pass.

## Files

| File | What | Who |
|---|---|---|
| `briefs-draft.jsonl` | 45 draft briefs by Claude Code: 15 sparse, 16 moderate, 14 rich; 4 declines; hard cases (ambiguous, culturally sensitive, over-popular). Each has a `note` saying why it is there | Joe edits, adds or removes |
| `blind-cases.json` | The 20 blind drafts (seed 0, spread across detail levels) and the inputs that built their pools | Generated |
| `blind-sheet.csv` | One row per candidate for the 20 blind cases, in random order, with no rank and no retriever name | **Joe labels** |

`runs/labelling-v1/pool-sources.jsonl` (gitignored) records which retriever found each candidate. Do not open it before labelling.

## Steps

1. **Edit the briefs** in `briefs-draft.jsonl`. Then rebuild the pools, because they follow the brief text: `uv run python scripts/build_labelling_pools.py` (PowerShell or WSL2; needs `uv sync --extra embed`).
2. **Blind pass.** In `blind-sheet.csv`, for each row fill:
   - `relevant`: `y` or `n`. Relevant means it fits the brief's meaning, including its subjective qualifiers ("staged dramatically"), as far as the brief specifies them. Judge the meaning, not keywords. For reproduction briefs, rights do not matter here: the pools only hold open works.
   - `grade` (only when `y`): `2` fits the whole brief, `1` fits part of it.
   - `note`: optional, especially for close calls.

   Or use the labelling page (issue #138), which shows the brief beside each work's cached image and writes the same three columns as you go: `uv run python -m refdesk.evals.label_app`, then open http://127.0.0.1:8200. Keys: `y`/`n`, then `1`/`2`; `e` for a note; `←`/`→` to move; `u` for the next unlabelled row. It shows no rank or retriever. Works without a cached image show a link to the museum record instead. From another device (for example over Tailscale), add `--host <this PC's Tailscale address>` and open the URL it prints: it carries a token, and without it the page refuses every request.
3. **Second blind pass, a day later.** Copy the sheet to `blind-sheet-pass2.csv`, clear the `relevant`, `grade` and `note` columns without reading them, and label again. This measures your self-agreement. With the page: `uv run python -m refdesk.evals.label_app --pass2` does the copy and clearing for you, and resumes the same file on later runs.
4. **Then Claude Code proposes** references for every case, `phi4` judges each proposal, and you review the 21 non-blind cases (accept, reject or regrade every proposal).
5. **Trust rules** (`refdesk.evals.labelling.trust_check`): the gap must be at most 5 points on the paired interval, and your review corrections at most 5 points below your blind disagreement. Only then is `evals/golden/golden-v1.jsonl` written and frozen.

## Known limits

- Pools come from the system's own retrievers plus 2 random records per case. Relevant works none of them found cannot be labelled, so recall on v1 is recall within the pools.
- Met records have no long description text; relevance rests on title, artist, date, medium, subject tags and the image.
