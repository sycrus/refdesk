"""Retrieval scorers and bootstrap confidence intervals (PRD 11.2, 11.3; run-evals skill).

Plain functions over ranked record IDs, so each can be checked by hand. Every reported
score comes with a bootstrap interval: a single number without one is not reported.
"""

from __future__ import annotations

import random
from collections.abc import Sequence


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Relevant items in the top k, over the most that could fit: min(|relevant|, k).

    Normalising by min(|relevant|, k) keeps the score reachable when a case has more
    relevant items than k (common in golden-v0, median 28 references at k=12).
    """
    if not relevant:
        raise ValueError("recall needs at least one relevant item")
    hits = sum(1 for r in ranked[:k] if r in relevant)
    return hits / min(len(relevant), k)


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return sum(1 for r in ranked[:k] if r in relevant) / k


def mrr(ranked: Sequence[str], relevant: set[str]) -> float:
    """Reciprocal rank of the first relevant item; 0 if none."""
    for position, record_id in enumerate(ranked, start=1):
        if record_id in relevant:
            return 1 / position
    return 0.0


def open_rights_share(ranked: Sequence[str], statuses: dict[str, str], k: int) -> float | None:
    """Share of the top k whose rights status is open. For reproduction cases, anything
    below 1.0 means the retriever surfaced works that cannot be reproduced."""
    top = list(ranked[:k])
    if not top:
        return None
    return sum(1 for r in top if statuses.get(r) == "open") / len(top)


def bootstrap_ci(
    values: Sequence[float], *, seed: int, n_boot: int = 2000, level: float = 0.95
) -> tuple[float, float, float]:
    """(mean, low, high): a percentile bootstrap over cases, reproducible with `seed`."""
    if not values:
        raise ValueError("bootstrap needs at least one value")
    n = len(values)
    mean = sum(values) / n
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(n_boot))
    tail = (1 - level) / 2
    low = means[int(tail * n_boot)]
    high = means[min(n_boot - 1, int((1 - tail) * n_boot))]
    return mean, low, high
