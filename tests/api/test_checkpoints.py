"""Checkpoint and resume mechanics (issue #157; PRD 10.2).

The run store's checkpoint table (idempotency key: run ID, step, hash of inputs; the
first result for a key wins), the checkpoint transport (a completed model answer is
stored once and then reused, never sent twice; failures are not stored), and the
resumed run's log (a re-derived retrieval becomes a checkpoint event, so replay keeps
working). The scenario itself — kill a run, resume it — is in test_loop.py.
"""

from test_boards import rec
from test_boards_reasoning import Mocks

from refdesk.boards import RunStore
from refdesk.checkpoints import CheckpointTransport, ResumeLog, checkpointed_search
from refdesk.retrieval import Hit, Query
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.runlog import RunLog, read_events


def store(tmp_path):
    return RunStore(tmp_path / "runs.sqlite")


class TestCheckpointTable:
    def test_put_then_get_round_trips_the_result(self, tmp_path):
        s = store(tmp_path)
        s.put_checkpoint("r1", "llm", "k1", {"status": 200, "body": {"a": 1}})
        assert s.get_checkpoint("r1", "llm", "k1") == {"status": 200, "body": {"a": 1}}
        assert s.checkpoint_count("r1") == 1

    def test_an_unwritten_key_is_a_miss(self, tmp_path):
        s = store(tmp_path)
        assert s.get_checkpoint("r1", "llm", "k1") is None

    def test_the_first_result_for_a_key_wins(self, tmp_path):
        s = store(tmp_path)
        s.put_checkpoint("r1", "llm", "k1", {"status": 200, "body": "first"})
        s.put_checkpoint("r1", "llm", "k1", {"status": 200, "body": "second"})
        assert s.get_checkpoint("r1", "llm", "k1")["body"] == "first"

    def test_steps_and_runs_are_isolated(self, tmp_path):
        s = store(tmp_path)
        s.put_checkpoint("r1", "llm", "k", {"body": "llm"})
        s.put_checkpoint("r1", "retrieve", "k", {"body": "retrieve"})
        s.put_checkpoint("r2", "llm", "k", {"body": "other run"})
        assert s.get_checkpoint("r1", "llm", "k")["body"] == "llm"
        assert s.get_checkpoint("r1", "retrieve", "k")["body"] == "retrieve"
        assert s.get_checkpoint("r2", "llm", "k")["body"] == "other run"


class TestCheckpointTransport:
    def test_the_first_call_goes_to_the_provider_and_is_checkpointed(self, tmp_path):
        mocks = Mocks()
        transport = CheckpointTransport(mocks, store=store(tmp_path), run_id="r", brief="boats")
        status, body = transport.post_json("http://m/v1/chat/completions", {}, {"model": "m"})
        assert status == 200 and body["choices"][0]["message"]["content"]
        assert transport.hits == 0 and mocks.calls == ["m"]

    def test_the_same_request_is_answered_from_the_store_once_recorded(self, tmp_path):
        mocks = Mocks()
        transport = CheckpointTransport(mocks, store=store(tmp_path), run_id="r", brief="boats")
        request = {"model": "m", "messages": [{"role": "user", "content": "boats"}]}
        first = transport.post_json("http://m/v1/chat/completions", {}, request)
        second = transport.post_json("http://m/v1/chat/completions", {}, request)
        assert second == first and second.reused is True
        assert first.reused is False
        assert transport.hits == 1
        assert mocks.calls == ["m"], "the provider was asked twice"

    def test_a_different_request_is_not_reused(self, tmp_path):
        mocks = Mocks()
        transport = CheckpointTransport(mocks, store=store(tmp_path), run_id="r", brief="boats")
        url = "http://m/v1/chat/completions"
        transport.post_json(url, {}, {"model": "m", "messages": [{"role": "user", "content": "a"}]})
        status, _ = transport.post_json(
            url, {}, {"model": "m", "messages": [{"role": "user", "content": "b"}]}
        )
        assert status == 200 and transport.hits == 0 and len(mocks.calls) == 2

    def test_a_failed_call_is_never_checkpointed(self, tmp_path):
        # A 429 is not a completed step: a resumed run should re-ask a provider that
        # may have recovered, and the client's retries replay the attempts live.
        mocks = Mocks(generator_script=["429"])
        s = store(tmp_path)
        transport = CheckpointTransport(mocks, store=s, run_id="r", brief="boats")
        status, body = transport.post_json("http://m/v1/chat/completions", {}, {"model": "m"})
        assert status == 429 and "error" in body
        assert s.checkpoint_count("r") == 0


class TestCheckpointedSearch:
    def test_a_live_search_is_recorded(self, tmp_path):
        s = store(tmp_path)
        query = Query(brief="boats", k=3)
        first = checkpointed_search(
            s, "r", "boats", query, lambda: JaccardRetriever([]).search(query)
        )
        assert first == []
        assert s.checkpoint_count("r") == 1

    def test_hits_round_trip_through_the_checkpoint(self, tmp_path):
        hits = [
            Hit(record_id="met:1", score=0.75, matched=("tag:boats", "medium:oil"), union_size=4,
                components=(("similarity", 0.5), ("attributes", 0.25))),
            Hit(record_id="met:2", score=0.5, matched=("tag:boats",)),
        ]  # fmt: skip
        s = store(tmp_path)
        query = Query(brief="boats")
        checkpointed_search(s, "r", "boats", query, lambda: hits)
        reused = checkpointed_search(s, "r", "boats", query, never_search)
        assert reused == hits
        assert reused[0].matched == ("tag:boats", "medium:oil")
        assert reused[0].components == (("similarity", 0.5), ("attributes", 0.25))

    def test_a_different_query_is_not_reused(self, tmp_path):
        hits = [Hit(record_id="met:1", score=0.75, matched=("tag:boats",))]
        s = store(tmp_path)
        checkpointed_search(s, "r", "boats", Query(brief="boats"), lambda: hits)
        other = checkpointed_search(s, "r", "boats", Query(brief="storm"), lambda: [])
        assert other == []


def never_search():
    raise AssertionError("the live search ran although the checkpoint had the hits")


class TestResumeLog:
    # The loop's retrieve hands the log ArtworkRecords (boards.py), not Hits.
    def test_a_rederived_retrieval_becomes_a_checkpoint_event(self, tmp_path):
        path = tmp_path / "events.jsonl"
        records = [rec("1", ["boats"])]
        RunLog(path, run_id="r", brief="boats").retrieval(3, records, 0.01)
        resumed = ResumeLog(path, run_id="r", brief="boats")
        resumed.retrieval(3, list(records), 0.0)
        events = read_events(path)
        retrieves = [e for e in events if e.tool == "retrieve"]
        reuse = [e for e in events if e.tool == "checkpoint"]
        assert len(retrieves) == 1, "the re-derived retrieval was logged as a second call"
        assert len(reuse) == 1 and reuse[0].args_hash == retrieves[0].args_hash
        assert "reused from checkpoint" in reuse[0].result

    def test_a_genuinely_new_round_is_logged_normally(self, tmp_path):
        path = tmp_path / "events.jsonl"
        RunLog(path, run_id="r", brief="boats").retrieval(3, [rec("1", ["boats"])], 0.01)
        resumed = ResumeLog(path, run_id="r", brief="boats")
        resumed.retrieval(3, [rec("2", [])], 0.02)
        retrieves = [e for e in read_events(path) if e.tool == "retrieve"]
        assert len(retrieves) == 2
        assert retrieves[1].recorded["records"][0]["id"] == "met:2"

    def test_the_resumed_log_continues_the_sequence(self, tmp_path):
        path = tmp_path / "events.jsonl"
        first = RunLog(path, run_id="r", brief="boats")
        first.retrieval(3, [rec("1", ["boats"])], 0.01)
        resumed = ResumeLog(path, run_id="r", brief="boats")
        resumed.retrieval(3, [rec("1", ["boats"])], 0.0)  # reused
        resumed.retrieval(2, [rec("4", [])], 0.01)  # new round
        seqs = [e.seq for e in read_events(path)]
        assert seqs == list(range(1, len(seqs) + 1))
