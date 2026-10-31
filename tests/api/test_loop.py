"""Loop controller: the PRD 10.2 state machine in plain code (issue #155; PRD 10.4 stage 1).

Acceptance scenarios 1, 2, 4, 5 and 6, the kill switch, and the step-cap, timeout and
pool-exhausted stops. Scenario 3 — kill a run, resume it, no model call or export
repeats — is `TestScenario3Resume` below (issue #157); its mechanics live in
test_checkpoints.py.

The real Reasoner and LLM client run against the in-process mock server (`Mocks`), so
every "model call" below is a real request to the mock, counted in `mocks.calls`.
"""

import re
import threading
import time
from urllib.parse import urlsplit

import pytest
from test_boards import rec
from test_boards_reasoning import CONFIG, Mocks

from refdesk.api.app import resume_interrupted
from refdesk.api.models import ApprovalRequest, BoardRequest, ExportRequest, LoopState
from refdesk.boards import BoardService, GateRefused, RunStore
from refdesk.loop import LoopConfig, LoopController
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.runlog import read_events
from refdesk.wording import AttributionStatus, StopReason

S = LoopState

# Ten records that match "boats", each with an artist so attribution can be verified.
POOL = [
    rec(str(n), ("Boats",), medium="Oil on canvas", artist=f"Painter {n}") for n in range(1, 11)
]


def config(**overrides) -> LoopConfig:
    values = dict(
        max_rounds=6, timeout_s=120.0, stuck_rounds=2, target_items=12, budget_cap_usd=0.05,
        drop_after_failed_verifications=2,
    )  # fmt: skip
    return LoopConfig(**{**values, **overrides})


class Pool:
    """Retrieve: hands out the next unseen candidates, as the board's retriever does."""

    def __init__(self, records=POOL):
        self.left = list(records)
        self.asked: list[int] = []

    def __call__(self, n: int):
        self.asked.append(n)
        taken, self.left = self.left[:n], self.left[n:]
        return taken


def controller(mocks, generator_tier="mock", clock=None, cancelled=None, **loop_values):
    reasoner = Reasoner(
        CONFIG, generator_tier=generator_tier, transport=mocks, env={"CLOUD_KEY": "k"},
        approved=True,
    )  # fmt: skip
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    if cancelled is not None:
        kwargs["cancelled"] = cancelled
    return LoopController(config(**loop_values), reasoner, **kwargs)


def run(ctl, pool=None, target=2, keep_local=False, cap_usd=1.0):
    return ctl.run(
        brief="boats", retrieve=pool or Pool(), target=target, keep_local=keep_local,
        cap_usd=cap_usd,
    )  # fmt: skip


class TestHappyPath:
    def test_follows_the_prd_states_and_assembles_when_k_items_are_accepted(self):
        result = run(controller(Mocks()), target=2)
        assert result.state is S.DONE and result.stop is None
        assert result.trace == [S.INIT, S.RETRIEVE, S.DECIDE, S.GENERATE, S.VERIFY, S.ASSEMBLE]
        assert result.accepted == 2 and result.rounds == 1

    def test_decide_passes_through_to_the_configured_generator_tier(self):
        result = run(controller(Mocks()), target=1)
        assert result.tiers == ["mock"]

    def test_loops_back_to_retrieve_for_more_items_when_some_fail(self):
        # Round 1 (Painters 1 and 2): flagged; round 2: verified. Only accepted items count.
        class FlagFirstTwo(Mocks):
            def post_json(self, url, headers, payload):
                text = " ".join(m["content"] for m in payload["messages"])
                if urlsplit(url).hostname == "j" and re.search(r"Painter [12]\b", text):
                    self.calls.append("j")
                    body = {"model": "mock-1", "usage": {},
                            "choices": [{"message": {"content": "UNSUPPORTED"}}]}  # fmt: skip
                    return 200, body
                return super().post_json(url, headers, payload)

        result = run(controller(FlagFirstTwo()), target=2)
        assert result.state is S.DONE
        assert result.rounds == 2 and result.accepted == 2
        assert result.trace.count(S.RETRIEVE) == 2
        assert len(result.records) == 4  # flagged items stay on the board, flagged


class TestScenario1Budget:
    """The run stops before a model call that would exceed the cap."""

    def test_stops_before_the_call_that_would_exceed_the_cap(self):
        mocks = Mocks()
        result = run(controller(mocks, generator_tier="cloud-flash"), target=3, cap_usd=0.65)
        assert result.state is S.STOPPED and result.stop is StopReason.BUDGET_CAP
        assert mocks.calls.count("c") == 1
        assert result.spent_usd <= 0.65
        assert result.trace[-2:] == [S.STOPPED, S.ASSEMBLE]  # partial board, flagged

    def test_the_cap_holds_across_rounds(self):
        # Every item flagged, so the loop keeps going; spend can never pass the cap.
        mocks = Mocks(judge_script=["unsupported"])
        ctl = controller(mocks, generator_tier="cloud-flash", stuck_rounds=10, max_rounds=10)
        result = run(ctl, target=1, cap_usd=1.25)
        assert result.stop is StopReason.BUDGET_CAP
        assert result.spent_usd <= 1.25
        assert result.rounds >= 2


class TestScenario2NoProgress:
    def test_stops_after_two_rounds_with_no_new_accepted_item(self):
        mocks = Mocks(judge_script=["unsupported"])
        pool = Pool()
        result = run(controller(mocks), pool, target=2)
        assert result.state is S.STOPPED and result.stop is StopReason.NO_PROGRESS
        assert result.rounds == 2 and result.accepted == 0
        assert pool.left, "it stopped although candidates were left"
        assert "2 rounds" in result.stop_detail


class TestScenario4KeepLocal:
    def test_a_keep_local_brief_never_reaches_a_cloud_tier(self):
        mocks = Mocks()
        result = run(controller(mocks, generator_tier="cloud-flash"), keep_local=True)
        assert result.state is S.STOPPED and result.stop is StopReason.DECLINED
        assert mocks.calls == [] and result.sent_to == []
        assert S.GENERATE not in result.trace  # stopped at Decide
        assert "keep-local" in result.stop_detail

    def test_a_keep_local_brief_with_a_local_tier_runs(self):
        result = run(controller(Mocks()), keep_local=True)
        assert result.state is S.DONE and "cloudy" not in result.sent_to


class TestScenario6FailedNeverVerified:
    def test_an_item_failing_verification_is_never_verified_or_accepted(self):
        result = run(controller(Mocks(judge_script=["unsupported"])), target=2)
        assert result.accepted == 0
        for record in result.records:
            assert result.status(record.id) is AttributionStatus.NEEDS_HUMAN_CHECK


class TestKillSwitch:
    def test_a_cancelled_run_reaches_cancelled_before_its_next_model_call(self):
        mocks = Mocks()
        result = run(controller(mocks, cancelled=lambda: len(mocks.calls) >= 1), target=3)
        assert result.state is S.CANCELLED and result.stop is StopReason.CANCELLED
        assert len(mocks.calls) == 1
        assert result.trace[-1] is S.CANCELLED and S.ASSEMBLE not in result.trace

    def test_cancelled_before_anything_makes_no_call(self):
        mocks = Mocks()
        result = run(controller(mocks, cancelled=lambda: True))
        assert result.trace == [S.INIT, S.CANCELLED] and mocks.calls == []


class TestStepCap:
    def test_stops_after_the_last_allowed_retrieval_round(self):
        mocks = Mocks(judge_script=["unsupported"])
        result = run(controller(mocks, max_rounds=2, stuck_rounds=5), target=1)
        assert result.state is S.STOPPED and result.stop is StopReason.STEP_CAP
        assert result.rounds == 2 and result.trace.count(S.RETRIEVE) == 2


class TestTimeout:
    def test_stops_before_the_next_model_call_once_the_wall_clock_runs_out(self):
        now = [0.0]

        class Slow(Mocks):
            def post_json(self, url, headers, payload):
                now[0] += 50.0  # every call takes 50 s
                return super().post_json(url, headers, payload)

        mocks = Slow()
        result = run(controller(mocks, clock=lambda: now[0], timeout_s=120.0), target=3)
        assert result.state is S.STOPPED and result.stop is StopReason.TIMEOUT
        assert len(mocks.calls) == 3  # 0 s, 50 s, 100 s; the fourth would start at 150 s


class TestPoolExhausted:
    def test_assembles_with_a_message_to_relax_conditions(self):
        result = run(controller(Mocks()), Pool(POOL[:3]), target=5)
        assert result.state is S.DONE and result.stop is StopReason.POOL_EXHAUSTED
        assert "relax" in result.stop_detail.lower() and result.accepted == 3
        assert result.trace[-1] is S.ASSEMBLE

    def test_no_candidates_at_all_stops_with_no_model_call(self):
        mocks = Mocks()
        result = run(controller(mocks), Pool([]))
        assert result.state is S.STOPPED and result.stop is StopReason.POOL_EXHAUSTED
        assert mocks.calls == []


# --- Through the board service: scenarios 5 and 6 and the kill switch, end to end ---


def service(tmp_path, mocks, **loop_values):
    reasoner = Reasoner(CONFIG, generator_tier="mock", transport=mocks)
    svc = BoardService(
        RunStore(tmp_path / "runs.sqlite"), lambda: POOL, JaccardRetriever, "jaccard",
        reasoner=reasoner, loop=config(**loop_values),
    )  # fmt: skip
    return svc


def board(svc, **body):
    request = BoardRequest(brief="boats", **body)
    view = svc.create(request)
    return svc.execute(view.run_id, request)


class KillDuringGenerate:
    """A transport that dies mid-call, the way a killed process does: the calls before
    the kill complete (and are checkpointed); the call in flight never returns."""

    def __init__(self, inner, kill_at=2):
        self.inner = inner
        self.kill_at = kill_at  # die with this call (0-based) in flight
        self.payloads = []

    def post_json(self, url, headers, payload):
        index = len(self.payloads)
        self.payloads.append(payload)
        if index == self.kill_at:
            threading.Event().wait()  # the process dies here; this call never returns
        return self.inner.post_json(url, headers, payload)


def run_until_third_call_is_in_flight(killer, started):
    deadline = time.monotonic() + 30
    while len(killer.payloads) < killer.kill_at + 1:
        assert time.monotonic() < deadline, "the run never reached its in-flight call"
        assert started.is_alive(), "the run stopped before the kill"
        time.sleep(0.01)


class TestScenario3Resume:
    """PRD 10.2 scenario 3: kill a run mid-generate, resume it, and count the calls
    and exports: no completed model call repeats and no export repeats (issue #157)."""

    def test_kill_mid_generate_resume_no_model_call_repeats(self, tmp_path):
        mocks = Mocks()
        killer = KillDuringGenerate(mocks, kill_at=2)  # gen1, judge1 done; gen2 dies
        svc = service(tmp_path, killer)
        request = BoardRequest(brief="boats", target_items=2)
        run_id = svc.create(request).run_id
        started = threading.Thread(
            target=svc.execute, args=(run_id, request), daemon=True
        )  # fmt: skip
        started.start()
        run_until_third_call_is_in_flight(killer, started)

        # The process dies here. The store alone answers the resume.
        view = svc.resume(run_id)

        assert view.state is S.DONE and len(view.items) == 2
        # Call 3 was in flight (never completed), so the resume re-asks it — the same
        # request, once. Completed calls (gen1, judge1) are never sent again.
        assert killer.payloads[3] == killer.payloads[2]
        assert killer.payloads.count(killer.payloads[0]) == 1
        assert killer.payloads.count(killer.payloads[1]) == 1
        # The log holds each real call once: the re-derived retrieval and the two
        # completed answers are checkpoint events, not second call events.
        events = read_events(svc.events_path(run_id))
        llm_hashes = [e.args_hash for e in events if e.tool and e.tool.startswith("llm:")]
        # Every answered call is logged exactly once; the in-flight call never returned,
        # so it is never logged.
        assert len(llm_hashes) == len(set(llm_hashes)) == len(killer.payloads) - 1
        reused = [e for e in events if e.tool == "checkpoint"]
        assert len(reused) == 3 and all("reused from checkpoint" in e.result for e in reused)

    def test_a_restarted_api_resumes_from_the_store_alone(self, tmp_path):
        mocks = Mocks()
        killer = KillDuringGenerate(mocks, kill_at=2)
        request = BoardRequest(brief="boats", target_items=2)
        first = service(tmp_path, killer)
        run_id = first.create(request).run_id
        started = threading.Thread(
            target=first.execute, args=(run_id, request), daemon=True
        )  # fmt: skip
        started.start()
        run_until_third_call_is_in_flight(killer, started)

        # A new process, a fresh BoardService on the same store: no request object, no
        # in-memory state — resume_interrupted is what the API's lifespan runs.
        restarted = service(tmp_path, killer)
        resume_interrupted(restarted)
        deadline = time.monotonic() + 30
        while restarted.runs.get(run_id).state not in (S.DONE, S.STOPPED):
            assert time.monotonic() < deadline, "the resumed run never finished"
            time.sleep(0.01)

        view = restarted.runs.get(run_id)
        assert view.state is S.DONE and len(view.items) == 2
        assert killer.payloads[3] == killer.payloads[2]
        assert killer.payloads.count(killer.payloads[0]) == 1
        assert killer.payloads.count(killer.payloads[1]) == 1

    def test_an_export_never_writes_the_pack_twice(self, tmp_path):
        svc = service(tmp_path, Mocks())
        view = board(svc, target_items=2)
        svc.approve(view.run_id, ApprovalRequest(approver="joe", acknowledged=True))
        before = svc.runs.get(view.run_id)  # approved, not yet exported
        receipt = svc.export(view.run_id, ExportRequest(format="csv"))
        pack = (svc.exports_dir / f"{view.run_id}.csv").read_bytes()

        # The crash window: the checkpoint was written, but the read-only save was
        # lost. The recovered store still shows the board as approved-not-exported,
        # so the second export takes the checkpoint path: the same receipt (the same
        # exported_at stamp) and the pack is not rewritten.
        svc.runs.save(before)
        again = svc.export(view.run_id, ExportRequest(format="csv"))
        assert again == receipt
        assert (svc.exports_dir / f"{view.run_id}.csv").read_bytes() == pack


class TestBoardService:
    def test_scenario5_no_export_without_approval(self, tmp_path):
        svc = service(tmp_path, Mocks())
        view = board(svc, target_items=2)
        assert view.state is S.DONE
        with pytest.raises(GateRefused, match="no approval record"):
            svc.export(view.run_id, ExportRequest(format="csv"))
        assert not (svc.exports_dir / f"{view.run_id}.csv").exists()

    def test_scenario6_flagged_items_show_as_needs_human_check(self, tmp_path):
        svc = service(tmp_path, Mocks(judge_script=["unsupported"]))
        view = board(svc, target_items=2)
        assert view.stop_reason is StopReason.NO_PROGRESS and view.stop_banner
        assert view.items and all(
            i.attribution_status is AttributionStatus.NEEDS_HUMAN_CHECK for i in view.items
        )

    def test_a_cancelled_run_is_cancelled_and_can_never_be_exported(self, tmp_path):
        mocks = Mocks()
        svc = service(tmp_path, mocks)
        request = BoardRequest(brief="boats", target_items=3)
        run_id = svc.create(request).run_id
        svc.cancel(run_id)
        view = svc.execute(run_id, request)
        assert view.state is S.CANCELLED and view.stop_reason is StopReason.CANCELLED
        assert view.stop_banner == "Stopped: cancelled" and mocks.calls == []
        with pytest.raises(GateRefused):
            svc.approve(run_id, ApprovalRequest(approver="Joe", acknowledged=True))
        with pytest.raises(GateRefused):
            svc.export(run_id, ExportRequest(format="csv"))

    def test_every_stop_keeps_its_fixed_wording_and_reason(self, tmp_path):
        svc = service(tmp_path, Mocks(judge_script=["unsupported"]), max_rounds=1, stuck_rounds=5)
        view = svc.get(board(svc, target_items=1).run_id)
        assert view.stop_reason is StopReason.STEP_CAP
        assert view.stop_banner == "Stopped: step cap reached" and view.stop_detail


def test_the_repository_loop_config_matches_the_request_defaults():
    loaded = LoopConfig.load("config/loop.yaml")
    defaults = BoardRequest(brief="x")
    assert loaded.target_items == defaults.target_items
    assert loaded.budget_cap_usd == defaults.budget_cap_usd
