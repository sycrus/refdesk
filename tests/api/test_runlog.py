"""Run log: append-only events.jsonl per run, briefs redacted (issue #156; PRD 10.2, 13A).

Every state transition writes one event; every tool call (retrieve, model request) writes
one more, with its recorded output. A brief never reaches the file, even inside an error
message. A recorded run replays with mocked tools (the recordings) and gives the same
items and stop reason. GET /runs/{id} returns the events.
"""

import json

import pytest
from fastapi.testclient import TestClient
from test_boards import conforms, rec
from test_boards_reasoning import CONFIG, Mocks
from test_loop import POOL, Pool, config

from refdesk.api.app import app, get_service
from refdesk.api.models import BoardRequest, LoopState
from refdesk.boards import BoardService, RunStore
from refdesk.loop import LoopController
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.runlog import REDACTED, ReplayDiverged, RunLog, read_events, redact, replay
from refdesk.wording import StopReason

S = LoopState
# Distinctive, so a leak is unambiguous. It also contains "boats", so retrieval matches.
BRIEF = "Confidential: storm boats at dusk for Client Zeta's spring campaign"


def controller(mocks, log, generator_tier="mock", **loop_values):
    reasoner = Reasoner(
        CONFIG, generator_tier=generator_tier, transport=mocks, env={"CLOUD_KEY": "k"},
        approved=True,
    )  # fmt: skip
    return LoopController(config(**loop_values), reasoner, log=log)


def run(ctl, pool=None, target=2, keep_local=False, cap_usd=1.0, brief=BRIEF):
    return ctl.run(
        brief=brief, retrieve=pool or Pool(), target=target, keep_local=keep_local,
        cap_usd=cap_usd,
    )  # fmt: skip


def logged(tmp_path, mocks, generator_tier="mock", **run_args):
    """One logged loop run against the mocks; returns the log path and the result."""
    path = tmp_path / "run-1" / "events.jsonl"
    log = RunLog(path, run_id="run-1", brief=BRIEF)
    return path, run(controller(mocks, log, generator_tier=generator_tier), **run_args)


def mock_reasoner(transport, generator_tier="mock"):
    return Reasoner(
        CONFIG, generator_tier=generator_tier, transport=transport, env={"CLOUD_KEY": "k"},
        approved=True,
    )  # fmt: skip


class TestOneEventPerTransition:
    def test_every_state_in_the_trace_has_exactly_one_transition_event(self, tmp_path):
        path, result = logged(tmp_path, Mocks(), target=2)
        transitions = [e for e in read_events(path) if e.kind == "transition"]
        assert [e.state for e in transitions] == result.trace
        assert [e.step for e in transitions] == list(range(1, len(result.trace) + 1))

    def test_a_multi_round_stop_logs_every_transition_and_its_reason(self, tmp_path):
        path, result = logged(tmp_path, Mocks(judge_script=["unsupported"]), target=2)
        assert result.stop is StopReason.NO_PROGRESS
        transitions = [e for e in read_events(path) if e.kind == "transition"]
        assert [e.state for e in transitions] == result.trace
        stopped = next(e for e in transitions if e.state is S.STOPPED)
        assert stopped.reason_code == "no_progress" and "2 rounds" in stopped.result

    def test_decide_records_the_tier_and_why_there_are_no_probabilities(self, tmp_path):
        path, _ = logged(tmp_path, Mocks(), target=1)
        decide = next(e for e in read_events(path) if e.state is S.DECIDE)
        assert decide.tool == "decide" and decide.result == "tier mock"
        assert decide.probabilities is None and decide.reason_code == "router_not_built"

    def test_calls_carry_hash_tokens_cost_latency_and_model(self, tmp_path):
        path, result = logged(tmp_path, Mocks(), generator_tier="cloud-flash", target=1)
        calls = [e for e in read_events(path) if e.kind == "call" and e.tool.startswith("llm:")]
        assert calls, "no model call was logged"
        for e in calls:
            assert len(e.args_hash) == 64 and e.tokens_in is not None
            assert e.latency_s is not None and e.model
        assert sum(e.cost_usd for e in calls) == pytest.approx(result.spent_usd)

    def test_retrieve_calls_are_logged_with_their_candidates(self, tmp_path):
        path, result = logged(tmp_path, Mocks(), target=2)
        retrieves = [e for e in read_events(path) if e.tool == "retrieve"]
        assert len(retrieves) == result.rounds
        assert retrieves[0].result == "2 candidates: met:1, met:2"
        assert len(retrieves[0].recorded["records"]) == 2

    def test_the_log_is_append_only(self, tmp_path):
        path, _ = logged(tmp_path, Mocks(), target=1)
        first = path.read_text(encoding="utf-8")
        log = RunLog(path, run_id="run-1", brief=BRIEF)
        log.transition(S.INIT, result="second writer")
        text = path.read_text(encoding="utf-8")
        assert text.startswith(first) and len(text.splitlines()) == len(first.splitlines()) + 1
        seqs = [e.seq for e in read_events(path)]
        assert seqs == list(range(1, len(seqs) + 1))  # continues, never restarts


class TestBriefRedaction:
    def test_the_brief_never_appears_in_the_file(self, tmp_path):
        path, _ = logged(tmp_path, Mocks(), target=2)
        assert BRIEF.casefold() not in path.read_text(encoding="utf-8").casefold()

    def test_the_brief_never_appears_even_in_an_error_message(self, tmp_path):
        # A provider whose error body echoes the prompt, brief included.
        class EchoingError(Mocks):
            def post_json(self, url, headers, payload):
                self.calls.append("x")
                prompt = " ".join(m["content"] for m in payload["messages"])
                assert BRIEF in prompt
                return 400, f'{{"error": "bad request, you sent: {BRIEF}"}}'

        path, result = logged(tmp_path, EchoingError(), target=1)
        assert result.stop is StopReason.SOURCE_UNAVAILABLE
        assert BRIEF in result.stop_detail  # the error did carry the brief ...
        text = path.read_text(encoding="utf-8")
        assert BRIEF.casefold() not in text.casefold()  # ... the log did not
        assert REDACTED in text

    def test_a_model_answer_that_quotes_the_brief_is_redacted(self, tmp_path):
        class Quoting(Mocks):
            def post_json(self, url, headers, payload):
                status, body = super().post_json(url, headers, payload)
                body["choices"][0]["message"]["reasoning"] = f"The brief was: {BRIEF}"
                return status, body

        path, _ = logged(tmp_path, Quoting(), target=1)
        assert BRIEF.casefold() not in path.read_text(encoding="utf-8").casefold()

    def test_redact_catches_case_whitespace_and_json_escaping(self):
        brief = 'storm "boats"\nat dusk'
        text = 'a STORM "boats"   at   dusk b; json: storm \\"boats\\"\\nat dusk'
        out = redact(text, brief)
        assert "storm" not in out.lower() and out.count(REDACTED) == 2

    def test_a_brief_cut_off_at_the_end_of_an_error_message_is_redacted(self):
        # The client keeps 200 characters of an error body, which can cut the brief.
        out = redact(f"HTTP 400: you sent: {BRIEF[:30]}", BRIEF)
        assert out == f"HTTP 400: you sent: {REDACTED}"

    def test_redact_walks_nested_values(self):
        out = redact({"k": [BRIEF, {"x": f"pre {BRIEF} post"}]}, BRIEF)
        assert out == {"k": [REDACTED, {"x": f"pre {REDACTED} post"}]}


class TestReplay:
    def _same(self, original, replayed):
        assert replayed.stop is original.stop and replayed.state is original.state
        assert [r.id for r in replayed.records] == [r.id for r in original.records]
        assert {i: replayed.status(i) for i in replayed.items} == {
            i: original.status(i) for i in original.items
        }
        assert replayed.trace == original.trace

    def test_a_completed_run_replays_with_the_same_items_and_stop(self, tmp_path):
        path, original = logged(tmp_path, Mocks(), target=2)
        replayed = replay(path, brief=BRIEF, make_reasoner=mock_reasoner)
        self._same(original, replayed)

    def test_a_failed_run_replays_with_no_live_model_or_retriever(self, tmp_path):
        mocks = Mocks(judge_script=["unsupported"])
        path, original = logged(tmp_path, mocks, target=2)
        assert original.stop is StopReason.NO_PROGRESS
        calls_before = len(mocks.calls)
        replayed = replay(path, brief=BRIEF, make_reasoner=mock_reasoner)
        self._same(original, replayed)
        assert len(mocks.calls) == calls_before  # the recordings answered, not the mock

    def test_a_budget_stop_replays(self, tmp_path):
        path, original = logged(
            tmp_path, Mocks(), generator_tier="cloud-flash", target=3, cap_usd=0.65
        )
        assert original.stop is StopReason.BUDGET_CAP
        replayed = replay(
            path, brief=BRIEF, make_reasoner=lambda t: mock_reasoner(t, "cloud-flash")
        )
        self._same(original, replayed)
        assert replayed.spent_usd == pytest.approx(original.spent_usd)

    def test_a_provider_error_replays(self, tmp_path):
        class Down(Mocks):
            def post_json(self, url, headers, payload):
                return 401, "unauthorized"  # not retried, so the test does not sleep

        path, original = logged(tmp_path, Down(), target=1)
        assert original.stop is StopReason.SOURCE_UNAVAILABLE
        self._same(original, replay(path, brief=BRIEF, make_reasoner=mock_reasoner))

    def test_a_timeout_replays_at_the_same_point(self, tmp_path):
        now = [0.0]

        class Slow(Mocks):
            def post_json(self, url, headers, payload):
                now[0] += 50.0
                return super().post_json(url, headers, payload)

        path = tmp_path / "events.jsonl"
        log = RunLog(path, run_id="run-1", brief=BRIEF)
        reasoner = mock_reasoner(Slow())
        ctl = LoopController(config(timeout_s=120.0), reasoner, clock=lambda: now[0], log=log)
        original = run(ctl, target=3)
        assert original.stop is StopReason.TIMEOUT
        replayed = replay(path, brief=BRIEF, make_reasoner=mock_reasoner)
        self._same(original, replayed)
        assert replayed.stop_detail == original.stop_detail

    def test_a_cancelled_run_replays(self, tmp_path):
        mocks = Mocks()
        path = tmp_path / "events.jsonl"
        log = RunLog(path, run_id="run-1", brief=BRIEF)
        ctl = LoopController(
            config(), mock_reasoner(mocks), cancelled=lambda: len(mocks.calls) >= 1, log=log
        )
        original = run(ctl, target=3)
        assert original.stop is StopReason.CANCELLED
        self._same(original, replay(path, brief=BRIEF, make_reasoner=mock_reasoner))

    def test_a_changed_step_is_reported_where_it_diverges(self, tmp_path):
        path, _ = logged(tmp_path, Mocks(), target=2)
        # Replaying with another generator tier changes the first model request.
        with pytest.raises(ReplayDiverged, match="step"):
            replay(path, brief=BRIEF, make_reasoner=lambda t: mock_reasoner(t, "cloud-flash"))


# --- Through the board service and the API ---


def service(tmp_path, mocks, records=POOL):
    reasoner = Reasoner(CONFIG, generator_tier="mock", transport=mocks)
    return BoardService(
        RunStore(tmp_path / "runs.sqlite"), lambda: records, JaccardRetriever, "jaccard",
        reasoner=reasoner, loop=config(), runs_dir=tmp_path / "runs",
    )  # fmt: skip


class TestBoardServiceAndApi:
    def test_get_runs_includes_the_events_and_conforms_to_the_spec(self, tmp_path):
        svc = service(tmp_path, Mocks())
        app.dependency_overrides[get_service] = lambda: svc
        try:
            client = TestClient(app)
            created = client.post("/boards", json={"brief": BRIEF, "target_items": 2})
            assert created.status_code == 202, created.text
            view = client.get(f"/runs/{created.json()['run_id']}").json()
        finally:
            app.dependency_overrides.clear()
        conforms(view, "RunView")
        states = [e["state"] for e in view["events"] if e["kind"] == "transition"]
        assert states == ["init", "retrieve", "decide", "generate", "verify", "assemble"]
        assert all(e["recorded"] is None for e in view["events"])  # replay material stays on disk
        assert BRIEF not in json.dumps(view["events"])

    def test_the_file_lives_under_the_run_and_replays(self, tmp_path):
        svc = service(tmp_path, Mocks())
        request = BoardRequest(brief=BRIEF, target_items=2)
        run_id = svc.create(request).run_id
        view = svc.execute(run_id, request)
        path = tmp_path / "runs" / run_id / "events.jsonl"
        assert path.exists() and BRIEF.casefold() not in path.read_text("utf-8").casefold()
        replayed = replay(path, brief=BRIEF, make_reasoner=mock_reasoner)
        assert [r.id for r in replayed.records] == [i.record.id for i in view.items]
        assert replayed.stop is view.stop_reason

    def test_a_stop_before_the_loop_is_logged_too(self, tmp_path):
        svc = service(tmp_path, Mocks(), records=[rec("9", ("Cats",))])
        request = BoardRequest(brief=BRIEF, target_items=2)
        run_id = svc.create(request).run_id
        svc.execute(run_id, request)
        events = svc.get(run_id).events
        assert [e.state for e in events] == [S.STOPPED]
        assert events[0].reason_code == "pool_exhausted"

    def test_the_stored_view_does_not_hold_the_events(self, tmp_path):
        svc = service(tmp_path, Mocks())
        request = BoardRequest(brief=BRIEF, target_items=1)
        run_id = svc.create(request).run_id
        svc.execute(run_id, request)
        stored = svc.runs.get(run_id)
        assert stored.events == [] and svc.get(run_id).events
