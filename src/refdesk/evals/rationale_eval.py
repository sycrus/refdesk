"""Rationale eval: how often rationales pass the verifier (issue #102; ADR-018, ADR-022).

For each retrieve case in a golden set, the top-k records go through the board pipeline
(`reasoning.Reasoner`: generate, code checks, judge). Per item:

- **usable**: the generator returned a valid structured rationale (after one retry);
- **code_pass**: every claim's value matches the record (`verifier.check_claims`);
- **judge_pass**: the judge supported every claim's text and the fit sentence;
- **verified**: both passed, so the item would show "Attribution verified from record".

Each case's score is the share of its items; intervals are bootstrapped over cases.

What it is not: human-rated quality. The verifier was screened on synthetic items (judge
probes), so a high pass rate means "the verifier found nothing wrong", not "a person found
it right". On golden-v0-synthetic the report says it is plumbing only (ADR-018). The run
stops loudly if the pipeline stops (budget, keep-local, a model that cannot load): an eval
that skipped items is not reported.
"""

from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from refdesk.evals.golden import GoldenCase
from refdesk.evals.harness import (
    HISTORY_FIELDS,
    EvalConfig,
    EvalResult,
    _fmt,
    _summarise,
    case_query,
)
from refdesk.reasoning import Reasoner
from refdesk.retrieval import Retriever
from refdesk.schema import ArtworkRecord
from refdesk.verifier import item_status
from refdesk.wording import AttributionStatus

RATIONALE_METRICS = ("usable", "code_pass", "judge_pass", "verified")
_CLAIM = re.compile(r"^claim \d+ \((\w+)\): ")


class EvalStopped(RuntimeError):
    """The pipeline stopped (budget, keep-local, model unavailable): no report is written."""


def _reason_kind(reason: str) -> str:
    """Group a flag reason for the failure table, e.g. "judge: date" or "code: artist"."""
    match = _CLAIM.match(reason)
    if match:
        return f"{'judge' if 'judge' in reason else 'code'}: {match.group(1)}"
    if reason.startswith("fit sentence"):
        return "judge: fit sentence"
    if reason.startswith("rationale unusable"):
        return "unusable rationale"
    if "no judge" in reason.lower():
        return "no judge configured"
    return reason.split(":")[0]


def run_rationale_eval(
    retriever: Retriever,
    reasoner: Reasoner,
    cases: list[GoldenCase],
    records: list[ArtworkRecord],
    config: EvalConfig,
    *,
    cap_usd: float = 0.0,
) -> EvalResult:
    by_id = {r.id: r for r in records}
    start = time.perf_counter()
    rows: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    cost = 0.0
    for case in cases:
        row: dict[str, Any] = {"id": case.id, "difficulty": case.difficulty, "brief": case.brief}
        if case.expected_decision == "decline":
            rows.append(row | {"status": "not applicable: decline case"})
            continue
        hits = retriever.search(case_query(case, config.k))
        top = [by_id[h.record_id] for h in hits[: config.k] if h.record_id in by_id]
        if not top:
            rows.append(row | {"status": "no results"})
            continue
        outcome = reasoner.run(brief=case.brief, records=top, keep_local=True, cap_usd=cap_usd)
        if outcome.stop is not None:
            raise EvalStopped(f"{case.id}: {outcome.stop.banner}. {outcome.stop_detail}")
        items = []
        for record in top:
            r = outcome.items[record.id]
            usable = r.generated is not None and r.generated.ok
            code_pass = bool(r.code and r.code.passed)
            judge_pass = bool(r.judged and r.judged.verdict.passed)
            judged = r.judged.verdict if r.judged else None
            verified = item_status(r.code, judged) is AttributionStatus.VERIFIED
            item_reasons = (
                ([r.generated.failure] if r.generated and not r.generated.ok else [])
                + (list(r.code.failures) if r.code else [])
                + (list(r.judged.verdict.failures) if r.judged else [])
                + r.notes
            )
            reasons.update(_reason_kind(x) for x in item_reasons)
            cost += r.cost_usd
            items.append({
                "record_id": record.id, "usable": usable, "code_pass": code_pass,
                "judge_pass": judge_pass, "verified": verified, "reasons": item_reasons,
                "rationale": (
                    " ".join([*(c.text for c in r.generated.rationale.claims),
                              r.generated.rationale.fit])
                    if usable else None
                ),
                "claims": (
                    [c.model_dump() for c in r.generated.rationale.claims] if usable else None
                ),
                "fit": r.generated.rationale.fit if usable else None,
            })  # fmt: skip
        n = len(items)
        rows.append(
            row
            | {"status": "scored", "items": items, "models": dict(outcome.models_used)}
            | {m: sum(i[m] for i in items) / n for m in RATIONALE_METRICS}
        )
    wall_clock = time.perf_counter() - start
    scored = [r for r in rows if r["status"] == "scored"]
    summary = {
        m: s for m in RATIONALE_METRICS if (s := _summarise(scored, m, config.seed, config.n_boot))
    }
    groups = defaultdict(list)
    for r in scored:
        groups[r["difficulty"]].append(r)
    slices = {
        "difficulty": {
            value: s
            for value, group in sorted(groups.items())
            if (s := _summarise(group, "verified", config.seed, config.n_boot))
        }
    }
    # Model answers are not repeated here, so determinism is not checked (reported as such).
    return EvalResult(config, rows, summary, slices, dict(reasons), False, wall_clock, cost)


def _report(result: EvalResult, date: str) -> str:
    c, h = result.config, result.config.config_hash()
    params = c.retriever_params
    lines = [f"# Rationale eval: {params.get('generator_tier')} on {c.golden_version} ({date})", ""]
    if "synthetic" in c.golden_version:
        lines += [
            "> **golden-v0-synthetic: plumbing only, not a claim (ADR-018).** The briefs were",
            "> written by Claude Code and the items are whatever the retriever returned. These",
            "> numbers exercise the pipeline; never quote them as rationale quality.",
            "",
        ]
    lines += [
        "> **What this measures:** pass rates against the verifier (code checks, then the",
        "> judge, ADR-022). The verifier was screened on synthetic items (judge probes), so",
        "> these are not human-rated quality: that needs golden-v1 and Joe's ratings (#16).",
        "",
        f"- Generator: `{params.get('generator_tier')}` (model `{c.model}`); judge: "
        f"`{params.get('judge_tier')}` (model `{params.get('judge_model')}`).",
        f"- Retriever `{c.retriever}`, top {c.k} per case. Golden `{c.golden_version}` "
        f"(sha256 `{c.golden_sha256[:12]}`), corpus `{c.corpus_version}`.",
        "- Prompts: " + ", ".join(f"`{n}` `{s[:12]}`" for n, s in sorted(c.prompt_hashes.items())),
        f"- Git `{c.git_sha[:12]}`{' (dirty)' if c.git_dirty else ''}; config hash `{h}`; "
        f"bootstrap {c.n_boot} resamples, seed {c.seed}. Determinism not checked "
        "(model answers are not repeated).",
        f"- Cost USD {result.cost_usd:.4f}; wall clock {result.wall_clock_s:.0f} s.",
        "",
        "| Metric | Mean [95% CI] (cases) |",
        "|---|---|",
    ]
    meanings = {
        "usable": "valid structured rationale",
        "code_pass": "every claim value matches the record",
        "judge_pass": "judge supported every claim and the fit sentence",
        "verified": "both: would show as verified",
    }
    for m in RATIONALE_METRICS:
        if m in result.summary:
            lines.append(f"| {m} ({meanings[m]}) | {_fmt(result.summary[m])} |")
    lines += ["", "## Verified, by difficulty", "", "| Difficulty | Mean [95% CI] (cases) |"]
    lines += ["|---|---|"]
    for value, s in result.slices.get("difficulty", {}).items():
        lines.append(f"| {value} | {_fmt(s)} |")
    lines += ["", "## Why items were not verified", "", "| Reason | Items |", "|---|---|"]
    for reason, count in sorted(result.failures.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {reason} | {count} |")
    lines += ["", "## Cases", "", "| Case | Brief | Items | Verified |", "|---|---|---|---|"]
    for r in result.rows:
        if r["status"] == "scored":
            lines.append(f"| {r['id']} | {r['brief']} | {len(r['items'])} | {r['verified']:.2f} |")
        else:
            lines.append(f"| {r['id']} | {r['brief']} | {r['status']} | |")
    return "\n".join(lines) + "\n"


def write_rationale_outputs(result: EvalResult, *, root: Path, date: str) -> dict[str, Path]:
    c, h = result.config, result.config.config_hash()
    tier = c.retriever_params.get("generator_tier", "unknown")
    report = root / "evals" / "reports" / f"rationale-eval-{date}-{tier}-{h}.md"
    if report.exists():
        raise FileExistsError(f"{report.name} exists; reports are never overwritten")
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
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_report(result, date), encoding="utf-8")
    history = root / "results" / "history.csv"
    history.parent.mkdir(parents=True, exist_ok=True)
    new = not history.exists()
    with history.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if new:
            writer.writeheader()
        for metric, s in result.summary.items():
            writer.writerow({
                "date": date, "commit": c.git_sha[:12], "retriever": f"rationale:{tier}",
                "golden_version": c.golden_version, "corpus_version": c.corpus_version,
                "metric": f"rationale_{metric}", "mean": f"{s['mean']:.4f}",
                "low": f"{s['low']:.4f}", "high": f"{s['high']:.4f}", "n": s["n"],
                "cost_usd": f"{result.cost_usd:.2f}", "wall_clock_s": f"{result.wall_clock_s:.2f}",
                "config_hash": h,
            })  # fmt: skip
    return {"manifest": manifest, "report": report, "history": history}
