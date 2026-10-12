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

from refdesk.evals.harness import METRIC_NAMES, METRICS
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


# A report covering several runs (issue #37): each run's own scores, then the paired
# difference for every pair, in the order the runs were given (A before B).

SHORT_NAMES = {
    "recall": "Recall",
    "precision": "Precision",
    "mrr": "MRR",
    "open_share": "Open share",
}


def _run_summary(rows: dict[str, dict], *, seed: int, n_boot: int) -> dict[str, tuple]:
    summary = {}
    for metric in METRICS:
        values = [r[metric] for r in rows.values() if r.get(metric) is not None]
        if values:
            summary[metric] = (*bootstrap_ci(values, seed=seed, n_boot=n_boot), len(values))
    return summary


def comparison_report(
    root: Path, runs: list[str], date: str, *, seed: int = 0, n_boot: int = 2000
) -> str:
    if len(runs) < 2:
        raise ValueError("a comparison needs at least two runs")
    pairs = [(a, b) for i, a in enumerate(runs) for b in runs[i + 1 :]]
    comparisons = [compare_runs(root, a, b, seed=seed, n_boot=n_boot) for a, b in pairs]
    loaded = {run: _load(root, run) for run in runs}
    first = loaded[runs[0]][0]
    golden = first["golden_version"]

    lines = [f"# Retriever comparison on golden {golden} ({date})", ""]
    if "synthetic" in golden:
        lines += [
            "> **Golden set is synthetic: it cannot rank retrievers (ADR-018).** Its expected",
            "> references come from rules over metadata, so it favours the metadata baseline",
            "> by construction. This report exercises the comparison harness. Never quote it",
            "> as a measure of retrieval quality; that needs the hand-labelled golden-v1.",
            "",
        ]
    lines += [
        f"Golden `{golden}` (sha256 `{first['golden_sha256'][:12]}`), corpus "
        f"`{first['corpus_version']}`, scorers `{first['scorers_version']}`. "
        f"Bootstrap: {n_boot} resamples, seed {seed}.",
        "",
        "## Runs (mean with 95% CI)",
        "",
        "| Run | Retriever | Params | k | Git | "
        + " | ".join(SHORT_NAMES[m] for m in METRICS)
        + " |",
        "|---|---|---|---|---|" + "---|" * len(METRICS),
    ]
    for run in runs:
        config, rows = loaded[run]
        summary = _run_summary(rows, seed=seed, n_boot=n_boot)
        git = f"`{str(config.get('git_sha', ''))[:12]}`" + (
            " (dirty)" if config.get("git_dirty") else ""
        )
        cells = [
            f"{s[0]:.3f} [{s[1]:.3f}, {s[2]:.3f}] n={s[3]}" if (s := summary.get(m)) else "n/a"
            for m in METRICS
        ]
        params = json.dumps(config.get("retriever_params", {}))
        head = f"| `{run}` | {config.get('retriever')} | `{params}` | {config.get('k')} | {git} | "
        lines.append(head + " | ".join(cells) + " |")
    lines += [
        "",
        "## Paired differences (B - A per case, mean with 95% CI)",
        "",
        "Both runs scored the same cases, so each case is compared with itself. An interval",
        "that excludes 0 means B differed from A on this golden set; better/same/worse counts",
        "cases.",
        "",
    ]
    for c in comparisons:
        lines += [
            f"### B = `{c.run_b}` ({c.config_b.get('retriever')}) "
            f"vs A = `{c.run_a}` ({c.config_a.get('retriever')})",
            "",
            "| Metric | n | B - A | 95% CI | better/same/worse |",
            "|---|---|---|---|---|",
        ]
        for name, m in c.metrics.items():
            lines.append(
                f"| {SHORT_NAMES[name]} | {m.n} | {m.mean_diff:+.3f} "
                f"| [{m.low:+.3f}, {m.high:+.3f}] | {m.better}/{m.same}/{m.worse} |"
            )
        lines.append("")
    lines += [
        "## Metrics",
        "",
        *[f"- {SHORT_NAMES[m]}: {METRIC_NAMES[m]}" for m in METRICS],
        "",
        f"Regenerate: `uv run python -m refdesk compare {' '.join(runs)} --write`",
        "",
    ]
    return "\n".join(lines)


def write_comparison_report(
    root: Path, runs: list[str], date: str, *, seed: int = 0, n_boot: int = 2000
) -> Path:
    """Named by date and run hashes; an existing report is never overwritten."""
    path = root / "evals" / "reports" / f"eval-comparison-{date}-{'-'.join(runs)}.md"
    if path.exists():
        raise FileExistsError(f"{path} exists; reports are never overwritten")
    text = comparison_report(root, runs, date, seed=seed, n_boot=n_boot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path
