"""golden-v1 trust rules (ADR-018, issue #15).

v1 references are proposed by Claude Code and reviewed by Joe, so a reviewer could anchor
on the proposals. Two checks decide whether v1 may be frozen:

- **Gap.** On the blind cases, Claude's agreement with Joe's labels may be at most 5 points
  below Joe's agreement with himself (his second blind pass a day later). Judged on a
  paired bootstrap over cases: fail if the whole interval is above 5 points, pass if it is
  all at or below 5, otherwise add blind cases.
- **Anchoring.** Joe's correction rate in review (proposals rejected or regraded) may be at
  most 5 points below his blind disagreement rate (Claude's blind proposals he did not pick
  with the same grade).

Agreement is over the whole pool shown to Joe: a candidate counts as agreed when both say
relevant or both say not relevant. What breaks without this module: the rules in the ADR
would be checked by hand, or not at all.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from refdesk.evals.golden import GoldenCase
from refdesk.evals.scorers import bootstrap_ci

GAP_POINTS = 5.0
ANCHORING_POINTS = 5.0


def _blind(cases: list[GoldenCase]) -> list[GoldenCase]:
    return [c for c in cases if c.review and c.review.blind]


def _pool_agreement(pool: list[str], a: set[str], b: set[str]) -> float:
    return sum((r in a) == (r in b) for r in pool) / len(pool)


def _claude_by_case(case: GoldenCase) -> float:
    joe = {e.record_id for e in case.expected}
    claude = {p.record_id for p in case.review.proposals}
    return _pool_agreement(case.review.pool, joe, claude)


def _self_by_case(case: GoldenCase) -> float:
    if case.review.relabel is None:
        raise ValueError(f"{case.id}: self-agreement needs Joe's second blind pass (relabel)")
    joe = {e.record_id for e in case.expected}
    return _pool_agreement(case.review.pool, joe, set(case.review.relabel))


def claude_agreement(cases: list[GoldenCase]) -> float:
    values = [_claude_by_case(c) for c in _blind(cases)]
    return sum(values) / len(values)


def self_agreement(cases: list[GoldenCase]) -> float:
    values = [_self_by_case(c) for c in _blind(cases)]
    return sum(values) / len(values)


def blind_disagreement(cases: list[GoldenCase]) -> float:
    """Share of Claude's blind proposals that Joe did not pick with the same grade."""
    total = missed = 0
    for c in _blind(cases):
        joe = {e.record_id: e.grade for e in c.expected}
        for p in c.review.proposals:
            total += 1
            missed += joe.get(p.record_id) != p.grade
    return missed / total if total else 0.0


def correction_rate(cases: list[GoldenCase]) -> float:
    """Share of reviewed proposals Joe rejected or regraded."""
    decisions = [
        p.decision for c in cases if c.review and not c.review.blind for p in c.review.proposals
    ]
    decided = [d for d in decisions if d is not None]
    return sum(d != "accepted" for d in decided) / len(decided) if decided else 0.0


@dataclass(frozen=True)
class TrustResult:
    claude_agreement: float
    self_agreement: float
    gap_points: float  # mean of (self - Claude) per blind case, in points
    gap_interval: tuple[float, float]
    gap_verdict: str  # "pass", "fail" or "add blind cases"
    blind_disagreement: float
    correction_rate: float
    anchoring_verdict: str  # "pass" or "fail"

    @property
    def passed(self) -> bool:
        return self.gap_verdict == "pass" and self.anchoring_verdict == "pass"


def trust_check(
    cases: list[GoldenCase],
    *,
    gap_points: float = GAP_POINTS,
    anchoring_points: float = ANCHORING_POINTS,
    seed: int = 0,
) -> TrustResult:
    blind = _blind(cases)
    if not blind:
        raise ValueError("no blind cases: the trust rules need Joe's blind subset")
    diffs = [100 * (_self_by_case(c) - _claude_by_case(c)) for c in blind]
    mean, low, high = bootstrap_ci(diffs, seed=seed)
    if low > gap_points:
        gap_verdict = "fail"
    elif high <= gap_points:
        gap_verdict = "pass"
    else:
        gap_verdict = "add blind cases"
    disagreement = blind_disagreement(cases)
    corrections = correction_rate(cases)
    anchored = corrections < disagreement - anchoring_points / 100
    return TrustResult(
        claude_agreement=claude_agreement(cases),
        self_agreement=self_agreement(cases),
        gap_points=mean,
        gap_interval=(low, high),
        gap_verdict=gap_verdict,
        blind_disagreement=disagreement,
        correction_rate=corrections,
        anchoring_verdict="fail" if anchored else "pass",
    )


# --- Preparing the blind subset -------------------------------------------------------


def select_blind(drafts: list[dict], *, n: int = 20, seed: int = 0) -> list[str]:
    """Pick n retrieve cases for Joe's blind subset, spread across detail levels in
    proportion (largest remainder), so the gap check is not all sparse or all rich briefs."""
    rng = random.Random(seed)
    levels: dict[str, list[str]] = {}
    for d in drafts:
        if d["expected_decision"] == "retrieve":
            levels.setdefault(d["detail"], []).append(d["draft_id"])
    total = sum(len(v) for v in levels.values())
    if total < n:
        raise ValueError(f"only {total} retrieve cases for a blind subset of {n}")
    shares = {k: n * len(v) / total for k, v in sorted(levels.items())}
    counts = {k: int(s) for k, s in shares.items()}
    for k in sorted(shares, key=lambda k: counts[k] - shares[k])[: n - sum(counts.values())]:
        counts[k] += 1
    chosen = []
    for level, ids in sorted(levels.items()):
        chosen += rng.sample(sorted(ids), counts[level])
    return sorted(chosen)


def build_pool(
    hits: dict[str, list[str]], *, random_ids: list[str], seed: int = 0
) -> tuple[list[str], dict[str, list[str]]]:
    """An unranked pool for one blind case: the union of several retrievers' top hits plus a
    few random records, shuffled so neither rank nor source is visible to Joe.

    Sources are returned separately (kept out of the labelling sheet). The random records
    limit pooling bias: without them, only what the system already finds could ever be
    labelled relevant.
    """
    sources: dict[str, set[str]] = {}
    for name, ids in hits.items():
        for record_id in ids:
            sources.setdefault(record_id, set()).add(name)
    for record_id in random_ids:
        sources.setdefault(record_id, set()).add("random")
    pool = sorted(sources)
    random.Random(seed).shuffle(pool)
    return pool, {k: sorted(v) for k, v in sorted(sources.items())}
