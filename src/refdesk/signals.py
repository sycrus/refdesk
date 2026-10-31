"""Golden signals from run logs (issue #172; PRD 13A "Observability").

What it does: reads every `<runs>/<run_id>/events.jsonl` (runlog.py) and reports, for the
batch: board latency p50 and p95 by tier, error rate, saturation, cost per board,
escalation rate, and how every board ended. It only reads the redacted logs, so it never
sees a brief.

Definitions (mechanical; SLO targets on top of them are Joe's, see #172):
- Board latency: first event to last event of a run (Init to Assemble, or the stop).
  The tier is the run's generator tier from its Init event.
- Error rate: model request attempts that were not HTTP 200 (a timeout counts), over
  all model request attempts in the batch.
- Saturation: how close boards came to their limits: share of the cost cap spent and
  share of the retrieval rounds used (`loop.max_rounds`), p95 and max.
- Cost per board: sum of `cost_usd` over the run's calls; p50, p95 and total.
- Escalation rate: share of boards whose Decide steps chose more than one tier. Until the
  router (#165) exists every Decide passes the generator tier through, so this is 0 by
  construction; human-check escalations are not in the run log yet.
- Stop reasons: counted per reason; a board with none is "completed". Never hidden.

What breaks without it: there is no number to set an SLO against, and a slow tier or a
failing provider only shows up one run at a time.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from refdesk.api.models import EventKind, LoopState, RunEvent
from refdesk.runlog import FILENAME, read_events

COMPLETED = "completed"


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


@dataclass
class BoardMetrics:
    run_id: str
    tier: str | None
    latency_s: float
    cost_usd: float
    model_calls: int
    model_errors: int
    escalated: bool
    cap_use: float | None
    round_use: float | None
    stop_reason: str | None


def board_metrics(events: list[RunEvent]) -> BoardMetrics:
    init = next((e for e in events if e.state is LoopState.INIT), None)
    params = init.data if init else {}
    calls = [e for e in events if e.kind is EventKind.CALL and (e.tool or "").startswith("llm:")]
    tiers = {(e.result or "").removeprefix("tier ") for e in events if e.tool == "decide"}
    stops = [
        e for e in events
        if e.kind is EventKind.TRANSITION and e.state in (LoopState.STOPPED, LoopState.CANCELLED)
    ]  # fmt: skip
    cost = sum(e.cost_usd or 0.0 for e in events)
    cap = params.get("cap_usd")
    max_rounds = (params.get("loop") or {}).get("max_rounds")
    rounds = max((e.round for e in events), default=0)
    return BoardMetrics(
        run_id=events[0].run_id if events else "",
        tier=params.get("generator_tier"),
        latency_s=(events[-1].at - events[0].at).total_seconds() if events else 0.0,
        cost_usd=cost,
        model_calls=len(calls),
        model_errors=sum(1 for e in calls if e.result != "HTTP 200"),
        escalated=len(tiers) > 1,
        cap_use=cost / cap if cap else None,
        round_use=rounds / max_rounds if max_rounds else None,
        stop_reason=stops[-1].reason_code if stops else None,
    )


def read_runs(runs_dir: str | Path) -> list[BoardMetrics]:
    """One BoardMetrics per run directory that holds a run log."""
    paths = sorted(Path(runs_dir).glob(f"*/{FILENAME}"))
    return [board_metrics(events) for p in paths if (events := read_events(p))]


def _spread(values: list[float]) -> dict[str, float | None]:
    return {"p95": percentile(values, 95), "max": max(values) if values else None}


def golden_signals(boards: list[BoardMetrics]) -> dict[str, Any]:
    by_tier: dict[str, list[float]] = defaultdict(list)
    for b in boards:
        by_tier[b.tier or "unknown"].append(b.latency_s)
    calls = sum(b.model_calls for b in boards)
    costs = [b.cost_usd for b in boards]
    return {
        "boards": len(boards),
        "latency_s": {
            tier: {"boards": len(v), "p50": percentile(v, 50), "p95": percentile(v, 95)}
            for tier, v in sorted(by_tier.items())
        },
        "model_calls": calls,
        "error_rate": sum(b.model_errors for b in boards) / calls if calls else None,
        "saturation": {
            "cap_use": _spread([b.cap_use for b in boards if b.cap_use is not None]),
            "round_use": _spread([b.round_use for b in boards if b.round_use is not None]),
        },
        "cost_usd": {
            "p50": percentile(costs, 50), "p95": percentile(costs, 95),
            "total": sum(costs) if boards else None,
        },  # fmt: skip
        "escalation_rate": sum(b.escalated for b in boards) / len(boards) if boards else None,
        "stop_reasons": dict(sorted(Counter(b.stop_reason or COMPLETED for b in boards).items())),
    }


def _n(value: float | None, fmt: str = ".3f") -> str:
    return "n/a" if value is None else format(value, fmt)


def format_signals(sig: dict[str, Any]) -> str:
    lines = [f"golden signals over {sig['boards']} boards"]
    lines.append("latency p50/p95 per board (s), by tier:")
    for tier, v in sig["latency_s"].items():
        lines.append(f"  {tier}: {v['boards']} boards, p50 {_n(v['p50'])}, p95 {_n(v['p95'])}")
    lines.append(f"error rate: {_n(sig['error_rate'])} of {sig['model_calls']} model calls")
    sat = sig["saturation"]
    lines.append(
        f"saturation: cost cap used p95 {_n(sat['cap_use']['p95'])} max "
        f"{_n(sat['cap_use']['max'])}; rounds used p95 {_n(sat['round_use']['p95'])} max "
        f"{_n(sat['round_use']['max'])}"
    )
    c = sig["cost_usd"]
    lines.append(
        f"cost per board (USD): p50 {_n(c['p50'], '.4f')}, p95 {_n(c['p95'], '.4f')}, "
        f"total {_n(c['total'], '.4f')}"
    )
    lines.append(f"escalation rate: {_n(sig['escalation_rate'])} (0 until the router, #165)")
    lines.append("stop reasons: " + ", ".join(f"{k} {v}" for k, v in sig["stop_reasons"].items()))
    return "\n".join(lines)
