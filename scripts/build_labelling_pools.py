"""Prepare golden-v1 blind labelling (issue #15, ADR-018).

Reads the draft briefs, picks the blind subset (20 retrieve cases, spread across detail
levels), and builds an unranked candidate pool for each: the top hits of three retrievers
(jaccard, clip, combined) plus two random records, shuffled. Writes:

- evals/labelling/v1/blind-cases.json   which drafts are blind, with the inputs that made the pools
- evals/labelling/v1/blind-sheet.csv    what Joe labels: one row per candidate, no rank, no source
- runs/labelling-v1/pool-sources.jsonl  which retriever found each candidate (gitignored;
                                        for analysis after labelling, not for Joe to see first)

Claude's proposals are NOT made here. They come after Joe's blind pass (ADR-018 step 3).
Re-run after Joe edits the briefs: pools follow the brief text. Once the sheet holds any
label it is never rebuilt (the run stops): a rebuild would erase Joe's blind pass.

Round-2 batches (ADR-018 amendment 2026-11-08): `--batch b2` reads briefs-draft-b2.jsonl,
makes every retrieve draft blind, and writes blind-cases-b2.json, blind-sheet-b2.csv and
runs/labelling-v1/pool-sources-b2.jsonl. Pools come only from the corpus round 1 was
labelled on (its snapshot, ADR-023), so one golden-v1 never spans two corpus versions; the
run stops if a pinned record is missing or its rights changed.

Usage (PowerShell or WSL2; needs `uv sync --extra embed` and the CLIP index):
    uv run python scripts/build_labelling_pools.py [--batch b2]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

from refdesk.evals.corpus import pin
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


@dataclass(frozen=True)
class BatchPaths:
    drafts: Path
    cases: Path
    sheet: Path
    sources: Path


def batch_paths(batch: str | None) -> BatchPaths:
    """Round 1 (no batch) keeps its original file names; a batch adds `-<batch>`."""
    suffix = f"-{batch}" if batch else ""
    return BatchPaths(
        drafts=OUT / f"briefs-draft{suffix}.jsonl",
        cases=OUT / f"blind-cases{suffix}.json",
        sheet=OUT / f"blind-sheet{suffix}.csv",
        sources=SOURCES.with_name(f"pool-sources{suffix}.jsonl"),
    )


def batch_blind_ids(drafts: list[dict], *, existing: list[str]) -> list[str]:
    """Every retrieve draft of a batch is blind: the batch exists to add blind cases.
    An ID already used in round 1 would merge two different briefs, so it stops the run."""
    reused = sorted({d["draft_id"] for d in drafts} & set(existing))
    if reused:
        raise ValueError(f"batch reuses round-1 draft IDs: {reused}")
    return sorted(d["draft_id"] for d in drafts if d["expected_decision"] == "retrieve")


def has_labels(sheet: Path) -> bool:
    """True when any row of an existing sheet has a label (relevant, grade or note)."""
    if not sheet.exists():
        return False
    with sheet.open(encoding="utf-8", newline="") as f:
        return any(row["relevant"] or row["grade"] or row["note"] for row in csv.DictReader(f))


def pool_for(draft, records, retrievers):
    """One case's unranked pool: each retriever's top hits plus random allowed records."""
    query = Query(brief=draft["brief"], k=TOP_K, usage_mode=draft["usage_mode"])
    hits = {name: [h.record_id for h in r.search(query)] for name, r in retrievers.items()}
    rng = random.Random(f"{SEED}:{draft['draft_id']}")
    found = {i for ids in hits.values() for i in ids}
    eligible = sorted(r.id for r in records if allowed(r, query) and r.id not in found)
    return build_pool(hits, random_ids=rng.sample(eligible, N_RANDOM), seed=SEED)


def _drafts(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser(description="golden-v1 blind labelling pools")
    parser.add_argument("--batch", help="a round-2 batch, e.g. b2 (reads briefs-draft-b2.jsonl)")
    args = parser.parse_args()
    paths = batch_paths(args.batch)
    if has_labels(paths.sheet):
        raise SystemExit(f"{paths.sheet.name} holds labels; rebuilding would erase them")
    drafts = _drafts(paths.drafts)
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        records = list(store.iter_records())
    if args.batch:
        round1 = json.loads(batch_paths(None).cases.read_text(encoding="utf-8"))
        pinned = pin(records, round1["corpus_version"])  # raises on a missing or flipped record
        records = pinned.records
        print(f"pinned to {pinned.version}; {pinned.extra} newer store records ignored")
        blind_ids = batch_blind_ids(drafts, existing=[d["draft_id"] for d in _drafts(DRAFTS)])
    else:
        blind_ids = select_blind(drafts, n=20, seed=SEED)
    by_id = {r.id: r for r in records}
    retrievers = {name: build_retriever(name, records) for name in RETRIEVERS}

    rows, sources_out = [], []
    for draft in drafts:
        if draft["draft_id"] not in blind_ids:
            continue
        pool, sources = pool_for(draft, records, retrievers)
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
    paths.cases.write_text(
        json.dumps(
            {
                "blind": blind_ids,
                "n": len(blind_ids),
                "seed": SEED,
                "retrievers": list(RETRIEVERS),
                "top_k": TOP_K,
                "random_per_case": N_RANDOM,
                "corpus_version": corpus_version(records),
                "drafts": paths.drafts.relative_to(ROOT).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with paths.sheet.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    paths.sources.parent.mkdir(parents=True, exist_ok=True)
    paths.sources.write_text("".join(json.dumps(s) + "\n" for s in sources_out), encoding="utf-8")
    sizes = [sum(1 for row in rows if row["draft_id"] == b) for b in blind_ids]
    print(
        f"{len(blind_ids)} blind cases, {len(rows)} candidates (per case {min(sizes)}-{max(sizes)})"
    )


if __name__ == "__main__":
    main()
