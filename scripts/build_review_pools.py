"""Pools for the golden-v1 cases Joe reviews rather than labels blind (issue #15, ADR-018).

The 21 non-blind retrieve cases get pools built exactly like the blind ones (same
retrievers, top k, random records and seed; `build_labelling_pools.pool_for`), so Claude's
proposals for every case come from the same kind of candidate set. Writes:

- evals/labelling/v1/review-pools.json            the unranked pool per case
- runs/labelling-v1/review-pool-sources.jsonl     which retriever found each (gitignored)

Declines get no pool: their expected answer is "decline". Re-run after Joe edits a
non-blind brief; proposals for that case must then be made again.

Usage (PowerShell or WSL2; needs `uv sync --extra embed` and the CLIP index):
    uv run python scripts/build_review_pools.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_labelling_pools import (  # noqa: E402
    DRAFTS,
    N_RANDOM,
    OUT,
    RETRIEVERS,
    ROOT,
    SEED,
    TOP_K,
    pool_for,
)

from refdesk.evals.golden import corpus_version  # noqa: E402
from refdesk.retrieval.registry import build_retriever  # noqa: E402
from refdesk.store import Store  # noqa: E402

SOURCES = ROOT / "runs" / "labelling-v1" / "review-pool-sources.jsonl"


def main() -> None:
    drafts = [json.loads(line) for line in DRAFTS.read_text(encoding="utf-8").splitlines() if line]
    blind = set(json.loads((OUT / "blind-cases.json").read_text(encoding="utf-8"))["blind"])
    with Store(ROOT / "data" / "refdesk.sqlite") as store:
        records = list(store.iter_records())
    retrievers = {name: build_retriever(name, records) for name in RETRIEVERS}
    pools, sources_out = {}, []
    for draft in drafts:
        if draft["draft_id"] in blind or draft["expected_decision"] != "retrieve":
            continue
        pool, sources = pool_for(draft, records, retrievers)
        pools[draft["draft_id"]] = pool
        sources_out.append({"draft_id": draft["draft_id"], "sources": sources})
    out = {
        "cases": pools, "seed": SEED, "retrievers": list(RETRIEVERS), "top_k": TOP_K,
        "random_per_case": N_RANDOM, "corpus_version": corpus_version(records),
        "drafts": DRAFTS.relative_to(ROOT).as_posix(),
    }  # fmt: skip
    (OUT / "review-pools.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    SOURCES.parent.mkdir(parents=True, exist_ok=True)
    SOURCES.write_text("".join(json.dumps(s) + "\n" for s in sources_out), encoding="utf-8")
    sizes = [len(p) for p in pools.values()]
    print(f"{len(pools)} review cases, {sum(sizes)} candidates ({min(sizes)}-{max(sizes)})")


if __name__ == "__main__":
    main()
