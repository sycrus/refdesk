"""Prepare golden-v1 blind labelling (issue #15, ADR-018).

Reads the draft briefs, picks the blind subset (20 retrieve cases, spread across detail
levels), and builds an unranked candidate pool for each: the top hits of three retrievers
(jaccard, clip, combined) plus two random records, shuffled. Writes:

- evals/labelling/v1/blind-cases.json   which drafts are blind, with the inputs that made the pools
- evals/labelling/v1/blind-sheet.csv    what Joe labels: one row per candidate, no rank, no source
- runs/labelling-v1/pool-sources.jsonl  which retriever found each candidate (gitignored;
                                        for analysis after labelling, not for Joe to see first)

Claude's proposals are NOT made here. They come after Joe's blind pass (ADR-018 step 3).
Re-run after Joe edits the briefs: pools follow the brief text.

Usage (PowerShell or WSL2; needs `uv sync --extra embed` and the CLIP index):
    uv run python scripts/build_labelling_pools.py
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from refdesk.evals.golden import corpus_version
from refdesk.evals.labelling import build_pool, select_blind
from refdesk.retrieval import Query, allowed
from refdesk.retrieval.registry import build_retriever
from refdesk.store import Store

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "evals" / "labelling" / "v1" / "briefs-draft.jsonl"
OUT = ROOT / "evals" / "labelling" / "v1"
SOURCES = ROOT / "runs" / "labelling-v1" / "pool-sources.jsonl"
RETRIEVERS = ("jaccard", "clip", "combined")
TOP_K = 6
N_RANDOM = 2
SEED = 0


def main() -> None:
    drafts = [json.loads(line) for line in DRAFTS.read_text(encoding="utf-8").splitlines() if line]
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        records = list(store.iter_records())
    by_id = {r.id: r for r in records}
    blind_ids = select_blind(drafts, n=20, seed=SEED)
    retrievers = {name: build_retriever(name, records) for name in RETRIEVERS}

    rows, sources_out = [], []
    for draft in drafts:
        if draft["draft_id"] not in blind_ids:
            continue
        query = Query(brief=draft["brief"], k=TOP_K, usage_mode=draft["usage_mode"])
        hits = {name: [h.record_id for h in r.search(query)] for name, r in retrievers.items()}
        rng = random.Random(f"{SEED}:{draft['draft_id']}")
        found = {i for ids in hits.values() for i in ids}
        eligible = sorted(r.id for r in records if allowed(r, query) and r.id not in found)
        pool, sources = build_pool(hits, random_ids=rng.sample(eligible, N_RANDOM), seed=SEED)
        sources_out.append({"draft_id": draft["draft_id"], "sources": sources})
        for record_id in pool:
            r = by_id[record_id]
            rows.append({
                "draft_id": draft["draft_id"], "brief": draft["brief"],
                "usage_mode": draft["usage_mode"], "candidate": record_id,
                "title": r.title or "", "artist": r.artist or "",
                "date": r.date or f"{r.date_begin}-{r.date_end}", "medium": r.medium or "",
                "subjects": ", ".join(r.subject_tags), "record_url": r.record_url or "",
                "image_url": r.image_url or "", "relevant": "", "grade": "", "note": "",
            })  # fmt: skip

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "blind-cases.json").write_text(
        json.dumps(
            {
                "blind": blind_ids,
                "n": len(blind_ids),
                "seed": SEED,
                "retrievers": list(RETRIEVERS),
                "top_k": TOP_K,
                "random_per_case": N_RANDOM,
                "corpus_version": corpus_version(records),
                "drafts": DRAFTS.relative_to(ROOT).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (OUT / "blind-sheet.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    SOURCES.parent.mkdir(parents=True, exist_ok=True)
    SOURCES.write_text("".join(json.dumps(s) + "\n" for s in sources_out), encoding="utf-8")
    sizes = [sum(1 for row in rows if row["draft_id"] == b) for b in blind_ids]
    print(
        f"{len(blind_ids)} blind cases, {len(rows)} candidates (per case {min(sizes)}-{max(sizes)})"
    )


if __name__ == "__main__":
    main()
