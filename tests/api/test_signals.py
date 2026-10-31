"""Golden signals from run logs (issue #172; PRD 13A "Observability").

The signals are read from each run's events.jsonl, never from the brief: latency p50 and
p95 per board by tier, error rate, saturation, cost per board, escalation rate, and the
stop reasons (never hidden).
"""

from datetime import UTC, datetime, timedelta

import pytest
from test_boards_reasoning import Mocks
from test_runlog import BRIEF, controller, run

from refdesk.__main__ import main
from refdesk.api.models import EventKind, LoopState, RunEvent
from refdesk.runlog import RunLog
from refdesk.signals import board_metrics, format_signals, golden_signals, percentile

S = LoopState
T0 = datetime(2026, 10, 31, tzinfo=UTC)


def ev(seq, state, *, kind=EventKind.TRANSITION, at_s=0.0, **fields):
    return RunEvent(
        seq=seq, run_id="r", at=T0 + timedelta(seconds=at_s), step=seq, kind=kind,
        state=state, **fields,
    )  # fmt: skip


def board(*, seconds=2.0, tiers=("mock",), cost=0.01, error=False, stop=None, rounds=1):
    """A hand-built run log: Init, then per tier a Decide and one model call."""
    events = [ev(1, S.INIT, data={"generator_tier": tiers[0], "cap_usd": 0.1,
                                  "loop": {"max_rounds": 4}})]  # fmt: skip
    for i, tier in enumerate(tiers):
        events.append(ev(len(events) + 1, S.DECIDE, tool="decide", result=f"tier {tier}"))
        events.append(ev(
            len(events) + 1, S.GENERATE, kind=EventKind.CALL, tool=f"llm:{tier}",
            result="HTTP 500: boom" if error and i == 0 else "HTTP 200",
            cost_usd=cost / len(tiers), round=rounds,
        ))  # fmt: skip
    if stop:
        events.append(ev(len(events) + 1, S.STOPPED, reason_code=stop, round=rounds))
    events.append(ev(len(events) + 1, S.ASSEMBLE, at_s=seconds, round=rounds))
    return events


class TestPercentile:
    def test_nearest_rank(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        assert percentile(values, 50) == 5.0 and percentile(values, 95) == 10.0

    def test_empty_is_none(self):
        assert percentile([], 50) is None


class TestBoardMetrics:
    def test_one_board(self):
        m = board_metrics(board(seconds=3.0, cost=0.02, rounds=2))
        assert m.tier == "mock" and m.latency_s == 3.0 and m.cost_usd == pytest.approx(0.02)
        assert m.model_calls == 1 and m.model_errors == 0 and not m.escalated
        assert m.cap_use == pytest.approx(0.2) and m.round_use == pytest.approx(0.5)

    def test_a_non_200_model_call_is_an_error(self):
        assert board_metrics(board(error=True)).model_errors == 1

    def test_a_timeout_is_an_error(self):
        events = board()
        events[2] = events[2].model_copy(update={"result": "timeout"})
        assert board_metrics(events).model_errors == 1

    def test_a_second_tier_is_an_escalation(self):
        assert board_metrics(board(tiers=("local-small", "cloud-flash"))).escalated

    def test_the_stop_reason_is_kept(self):
        assert board_metrics(board(stop="no_progress")).stop_reason == "no_progress"
        assert board_metrics(board()).stop_reason is None


class TestGoldenSignals:
    def test_latency_is_per_tier(self):
        boards = [board(seconds=s) for s in (1.0, 2.0, 3.0)] + [
            board(seconds=9.0, tiers=("cloud-flash",))
        ]
        sig = golden_signals([board_metrics(b) for b in boards])
        assert sig["latency_s"]["mock"] == {"boards": 3, "p50": 2.0, "p95": 3.0}
        assert sig["latency_s"]["cloud-flash"] == {"boards": 1, "p50": 9.0, "p95": 9.0}

    def test_rates_cost_and_stops(self):
        boards = [board(cost=0.01), board(cost=0.03, error=True),
                  board(tiers=("mock", "cloud-flash")), board(stop="budget_cap")]  # fmt: skip
        sig = golden_signals([board_metrics(b) for b in boards])
        assert sig["boards"] == 4
        assert sig["error_rate"] == pytest.approx(1 / 5)  # 1 failed call of 5
        assert sig["escalation_rate"] == pytest.approx(1 / 4)
        assert sig["cost_usd"]["p50"] == pytest.approx(0.01)
        assert sig["cost_usd"]["total"] == pytest.approx(0.06)
        assert sig["stop_reasons"] == {"budget_cap": 1, "completed": 3}

    def test_no_boards(self):
        sig = golden_signals([])
        assert sig["boards"] == 0 and sig["error_rate"] is None


def mock_batch(tmp_path, n=4):
    """A batch of real loop runs against the mock provider, each with its own run log."""
    for i in range(n):
        log = RunLog(tmp_path / f"run-{i}" / "events.jsonl", run_id=f"run-{i}", brief=BRIEF)
        mocks = Mocks(judge_script=["unsupported"]) if i == n - 1 else Mocks()
        run(controller(mocks, log), target=2)
    return tmp_path


class TestMockBatch:
    def test_signals_for_a_batch_of_mock_runs(self, tmp_path):
        from refdesk.signals import read_runs

        metrics = read_runs(mock_batch(tmp_path))
        sig = golden_signals(metrics)
        assert sig["boards"] == 4 and set(sig["latency_s"]) == {"mock"}
        assert sig["error_rate"] == 0.0 and sig["escalation_rate"] == 0.0
        assert sig["stop_reasons"] == {"completed": 3, "no_progress": 1}
        print("\n" + format_signals(sig))

    def test_the_cli_prints_the_signals_and_never_the_brief(self, tmp_path, capsys):
        assert main(["signals", "--runs", str(mock_batch(tmp_path))]) == 0
        out = capsys.readouterr().out
        assert "latency p50/p95 per board" in out and "error rate" in out
        assert BRIEF.casefold() not in out.casefold()
        print(out)
