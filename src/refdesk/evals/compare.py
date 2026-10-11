"""Paired comparison of two eval runs (issue #36; docs/eval-gate-policy.md, principle 4).

Both runs scored the same golden cases, so the right question is: per case, how much did
run B differ from run A? Bootstrapping those per-case differences gives a much tighter
interval than comparing the two runs' overall intervals, because the variation between
cases (some briefs are simply harder) cancels out.

Runs are only comparable when the golden set (version and file hash), the corpus and the
metric definitions match. Anything else (retriever, k, parameters) is what is being
compared.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from refdesk.evals.harness import METRICS
from refdesk.evals.scorers import bootstrap_ci

MUST_MATCH = ("golden_version", "golden_sha256", "corpus_version", "scorers_version")


class NotComparable(ValueError):
    pass


@dataclass(frozen=True)
class MetricDiff:
    n: int
    mean_diff: float  # mean of (B - A) per case
    low: float
    high: float
    better: int  # cases where B > A
    same: int
    worse: int


@dataclass(frozen=True)
class Comparison:
    run_a: str
    run_b: str
    config_a: dict[str, Any]
    config_b: dict[str, Any]
    metrics: dict[str, MetricDiff]


def _load(root: Path, run_hash: str) -> tuple[dict[str, Any], dict[str, dict]]:
    run = root / "runs" / run_hash
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (run / "cases.jsonl").read_text("utf-8").splitlines()]
    scored = {r["id"]: r for r in rows if r.get("status") == "scored"}
    return manifest["config"], scored


def compare_runs(
    root: Path, run_a: str, run_b: str, *, seed: int = 0, n_boot: int = 2000
) -> Comparison:
    config_a, rows_a = _load(root, run_a)
    config_b, rows_b = _load(root, run_b)
    for field in MUST_MATCH:
        if config_a.get(field) != config_b.get(field):
            raise NotComparable(
                f"{field} differs: {config_a.get(field)!r} vs {config_b.get(field)!r}"
            )

    shared = sorted(set(rows_a) & set(rows_b))
    metrics = {}
    for metric in METRICS:
        pairs = [
            (rows_a[c][metric], rows_b[c][metric])
            for c in shared
            if rows_a[c].get(metric) is not None and rows_b[c].get(metric) is not None
        ]
        if not pairs:
            continue
        diffs = [b - a for a, b in pairs]
        mean, low, high = bootstrap_ci(diffs, seed=seed, n_boot=n_boot)
        metrics[metric] = MetricDiff(
            n=len(diffs),
            mean_diff=mean,
            low=low,
            high=high,
            better=sum(d > 0 for d in diffs),
            same=sum(d == 0 for d in diffs),
            worse=sum(d < 0 for d in diffs),
        )
    return Comparison(run_a, run_b, config_a, config_b, metrics)


def format_comparison(c: Comparison) -> str:
    def describe(cfg: dict[str, Any]) -> str:
        return f"{cfg.get('retriever')} k={cfg.get('k')}"

    lines = [
        f"A = {c.run_a} ({describe(c.config_a)}), B = {c.run_b} ({describe(c.config_b)})",
        f"golden {c.config_a['golden_version']}, corpus {c.config_a['corpus_version']}",
        "",
        f"{'metric':<12} {'n':>3}  {'B - A':>7}  {'95% CI':<18} better/same/worse",
    ]
    for name, m in c.metrics.items():
        ci = f"[{m.low:+.3f}, {m.high:+.3f}]"
        lines.append(
            f"{name:<12} {m.n:>3}  {m.mean_diff:+.3f}  {ci:<18} {m.better}/{m.same}/{m.worse}"
        )
    return "\n".join(lines)
