"""Eval harness (PRD 11, 13A; run-evals skill; issue #11).

Runs a retriever over golden cases, scores each case, adds bootstrap intervals overall
and per slice, and writes three things:

- `runs/<config hash>/manifest.json` and `cases.jsonl`: everything needed to reproduce
  the run. The config hash covers every input that can change a score.
- `evals/reports/eval-report-<date>-<retriever>.md`: the human-readable report. It says
  which golden set produced every number, and warns when that set is synthetic.
- one row per metric in `results/history.csv`.

No model is called yet (retrieval only), so cost is 0 and the mock server is not needed.
Gates are governed by `docs/eval-gate-policy.md`; every report quotes its status line.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from refdesk.evals.golden import GoldenCase
from refdesk.evals.scorers import bootstrap_ci, mrr, open_rights_share, precision_at_k, recall_at_k
from refdesk.retrieval import Query, Retriever
from refdesk.schema import ArtworkRecord, RightsStatus

SCORERS_VERSION = "scorers-v1"  # bump when a metric definition changes
METRICS = ("recall", "precision", "mrr", "open_share")
METRIC_NAMES = {
    "recall": "recall@k (capped: hits / min(relevant, k))",
    "precision": "precision@k",
    "mrr": "MRR",
    "open_share": "open-rights share of top k (reproduction cases)",
}


@dataclass(frozen=True)
class EvalConfig:
    retriever: str
    retriever_params: dict[str, Any]
    k: int
    seed: int
    n_boot: int
    golden_path: str
    golden_sha256: str
    golden_version: str
    corpus_version: str
    git_sha: str
    git_dirty: bool
    scorers_version: str = SCORERS_VERSION
    model: str = "none (retrieval only)"
    prompt_hashes: dict[str, str] = field(default_factory=dict)

    def config_hash(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]


@dataclass
class EvalResult:
    config: EvalConfig
    rows: list[dict[str, Any]]
    summary: dict[str, dict[str, float]]
    slices: dict[str, dict[str, dict[str, float]]]
    failures: dict[str, int]
    deterministic: bool
    wall_clock_s: float
    cost_usd: float = 0.0


def case_query(case: GoldenCase, k: int) -> Query:
    c = case.constraints
    return Query(
        brief=case.brief,
        conditions=c.get("conditions", {}),
        anchor_id=c.get("anchor_id"),
        avoid=c.get("avoid", []),
        k=k,
    )


def _failure(recall: float, ranked: list[str], relevant_in_top: int) -> str:
    if not ranked:
        return "no_results"
    if relevant_in_top == 0:
        return "no_relevant_in_top_k"
    return "partial" if recall < 1 else "full"


def _summarise(rows: list[dict], metric: str, seed: int, n_boot: int) -> dict[str, float] | None:
    values = [r[metric] for r in rows if r.get(metric) is not None]
    if not values:
        return None
    mean, low, high = bootstrap_ci(values, seed=seed, n_boot=n_boot)
    return {"mean": mean, "low": low, "high": high, "n": len(values)}


def run_eval(
    retriever: Retriever,
    cases: list[GoldenCase],
    records: list[ArtworkRecord],
    config: EvalConfig,
) -> EvalResult:
    statuses = {
        r.id: "open" if r.rights.status is RightsStatus.OPEN else "not open" for r in records
    }
    start = time.perf_counter()
    rows, rankings = [], {}
    for case in cases:
        row: dict[str, Any] = {
            "id": case.id,
            "difficulty": case.difficulty,
            "usage_mode": case.usage_mode,
            "tags": case.tags,
        }
        if case.expected_decision == "decline":
            rows.append(row | {"status": "not applicable: decline case"})
            continue
        ranked = [h.record_id for h in retriever.search(case_query(case, config.k))]
        rankings[case.id] = ranked
        relevant = {e.record_id for e in case.expected}
        recall = recall_at_k(ranked, relevant, config.k)
        in_top = sum(1 for r in ranked[: config.k] if r in relevant)
        rows.append(
            row
            | {
                "status": "scored",
                "ranked": ranked[: config.k],
                "n_relevant": len(relevant),
                "recall": recall,
                "precision": precision_at_k(ranked, relevant, config.k),
                "mrr": mrr(ranked, relevant),
                "open_share": (
                    open_rights_share(ranked, statuses, config.k)
                    if case.usage_mode == "reproduction"
                    else None
                ),
                "failure": _failure(recall, ranked, in_top),
            }
        )
    wall_clock = time.perf_counter() - start

    # Determinism: run every case again and compare rankings. A nondeterministic retriever
    # would need repeated runs with mean and spread (run-evals skill).
    deterministic = all(
        [h.record_id for h in retriever.search(case_query(c, config.k))] == rankings[c.id]
        for c in cases
        if c.id in rankings
    )

    scored = [r for r in rows if r["status"] == "scored"]
    summary = {m: s for m in METRICS if (s := _summarise(scored, m, config.seed, config.n_boot))}
    slices: dict[str, dict[str, dict[str, float]]] = {}
    for key in ("difficulty", "usage_mode"):
        groups = defaultdict(list)
        for r in scored:
            groups[r[key]].append(r)
        slices[key] = {
            value: s
            for value, group in sorted(groups.items())
            if (s := _summarise(group, "recall", config.seed, config.n_boot))
        }
    failures = dict(Counter(r["failure"] for r in scored))
    return EvalResult(config, rows, summary, slices, failures, deterministic, wall_clock)


def git_state(root: Path) -> tuple[str, bool]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fmt(s: dict[str, float]) -> str:
    return f"{s['mean']:.3f} [{s['low']:.3f}, {s['high']:.3f}] (n={s['n']})"


GATE_POLICY = Path("docs") / "eval-gate-policy.md"


def gate_policy_status(root: Path) -> str:
    """The policy's status line, quoted in every report so readers know what was gated."""
    path = root / GATE_POLICY
    if not path.exists():
        return "**No gate policy** (`docs/eval-gate-policy.md` does not exist). Nothing is gated."
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- **Status:**"):
            return line.removeprefix("- **Status:**").strip() + " (`docs/eval-gate-policy.md`)"
    return "`docs/eval-gate-policy.md` has no status line. Treat nothing as gated."


def _report(result: EvalResult, date: str, gates: str) -> str:
    c, h = result.config, result.config.config_hash()
    synthetic = "synthetic" in c.golden_version
    lines = [
        f"# Eval report: {c.retriever} on golden {c.golden_version} ({date})",
        "",
    ]
    if synthetic:
        lines += [
            "> **Golden set is synthetic. Never use for claims (ADR-018).** Its expected",
            "> references come from rules over metadata, which favour the metadata baseline.",
            "> These numbers test the harness; they do not measure retrieval quality.",
            "",
        ]
    lines += [
        "## Config",
        "",
        f"- Config hash: `{h}` (manifest: `runs/{h}/manifest.json`)",
        f"- Golden set: `{c.golden_path}`, version `{c.golden_version}`, "
        f"sha256 `{c.golden_sha256[:12]}`",
        f"- Corpus version: `{c.corpus_version}`",
        f"- Retriever: `{c.retriever}` {json.dumps(c.retriever_params)}; k = {c.k}",
        f"- Git: `{c.git_sha[:12]}`{' (uncommitted changes)' if c.git_dirty else ''}",
        f"- Model: {c.model}. Scorers: `{c.scorers_version}`. "
        f"Bootstrap: {c.n_boot} resamples, seed {c.seed}",
        f"- Deterministic across two runs: {'yes' if result.deterministic else '**no**'}",
        f"- Wall-clock: {result.wall_clock_s:.2f} s. Cost: USD {result.cost_usd:.2f}",
        f"- Gates: {gates}",
        "",
        "## Scores (mean with 95% CI)",
        "",
        "| Metric | Score |",
        "|---|---|",
        *[f"| {METRIC_NAMES[m]} | {_fmt(s)} |" for m, s in result.summary.items()],
        "",
    ]
    names = {"difficulty": "difficulty", "usage_mode": "usage mode"}
    for key, groups in result.slices.items():
        lines += [f"## Recall by {names[key]} (95% CI)", "", "| Slice | Recall |", "|---|---|"]
        lines += [f"| {value} | {_fmt(s)} |" for value, s in groups.items()]
        lines.append("")
    scored = [r for r in result.rows if r["status"] == "scored"]
    lines += ["## Failure categories", "", "| Category | Cases | Example |", "|---|---|---|"]
    for category, count in sorted(result.failures.items(), key=lambda kv: -kv[1]):
        example = next(r["id"] for r in scored if r["failure"] == category)
        lines.append(f"| {category} | {count} | {example} |")
    skipped = [r for r in result.rows if r["status"] != "scored"]
    lines += [
        "",
        "## Not scored",
        "",
        *([f"- {r['id']}: {r['status']}" for r in skipped] or ["None."]),
        "",
        "## Per case",
        "",
        "| Case | Difficulty | Recall | MRR | Open share | Failure |",
        "|---|---|---|---|---|---|",
    ]
    for r in scored:
        share = "" if r["open_share"] is None else f"{r['open_share']:.2f}"
        lines.append(
            f"| {r['id']} | {r['difficulty']} | {r['recall']:.2f} | {r['mrr']:.2f} | "
            f"{share} | {r['failure']} |"
        )
    return "\n".join(lines) + "\n"


HISTORY_FIELDS = [
    "date", "commit", "retriever", "golden_version", "corpus_version", "metric",
    "mean", "low", "high", "n", "cost_usd", "wall_clock_s", "config_hash",
]  # fmt: skip


def write_outputs(result: EvalResult, *, root: Path, date: str) -> dict[str, Path]:
    c, h = result.config, result.config.config_hash()
    run_dir = root / "runs" / h
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "manifest.json"
    manifest.write_text(
        json.dumps({"config_hash": h, "date": date, "config": asdict(c)}, indent=2) + "\n",
        encoding="utf-8",
    )
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as f:
        for row in result.rows:
            f.write(json.dumps(row) + "\n")

    report = root / "evals" / "reports" / f"eval-report-{date}-{c.retriever}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_report(result, date, gate_policy_status(root)), encoding="utf-8")

    history = root / "results" / "history.csv"
    history.parent.mkdir(parents=True, exist_ok=True)
    new = not history.exists()
    with history.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if new:
            writer.writeheader()
        for metric, s in result.summary.items():
            writer.writerow({
                "date": date, "commit": c.git_sha[:12], "retriever": c.retriever,
                "golden_version": c.golden_version, "corpus_version": c.corpus_version,
                "metric": metric, "mean": f"{s['mean']:.4f}", "low": f"{s['low']:.4f}",
                "high": f"{s['high']:.4f}", "n": s["n"], "cost_usd": f"{result.cost_usd:.2f}",
                "wall_clock_s": f"{result.wall_clock_s:.2f}", "config_hash": h,
            })  # fmt: skip
    return {"manifest": manifest, "report": report, "history": history}
