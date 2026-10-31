"""G1 cap raise (issue #158; PRD 10.2 stop table, 13A): an explicit, recorded decision to
raise the spend cap resumes a budget-stopped run from its checkpoint.

The run stops before the model call that would exceed the cap (scenario 1, test_loop.py).
The raise is refused without a name (422), refused for any run the budget cap did not
stop (409), and recorded with who and when — in the store's `cap_raises` table and as a
`cap_raise` event in the run log. The resumed run answers the steps the first execution
completed from its checkpoints (issue #157), so no model call repeats, and the reused
answers count against the new cap. The kill switch outlives a raise: a cancelled run
cannot be raised. Cancel is the other loop control of this issue (test_cancel_endpoint).
"""

import json

import pytest
from fastapi.testclient import TestClient
from test_boards import conforms, rec
from test_boards_reasoning import CONFIG, Mocks

from refdesk.api.app import app, get_service
from refdesk.api.models import BoardRequest, CapRaise, LoopState
from refdesk.boards import BoardService, GateRefused, RunStore
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.runlog import read_events
from refdesk.wording import AttributionStatus, StopReason

S = LoopState

# Ten records that match "boats", each with an artist so attribution can be verified.
POOL = [
    rec(str(n), ("Boats",), medium="Oil on canvas", artist=f"Painter {n}") for n in range(1, 11)
]


class Recording:
    """Every request that reaches a provider, kept so a test can prove none repeats."""

    def __init__(self, inner):
        self.inner = inner
        self.payloads = []

    def post_json(self, url, headers, payload):
        self.payloads.append(payload)
        return self.inner.post_json(url, headers, payload)


def service(tmp_path, transport):
    """A board service whose cloud generator stops at the cap: the first output call
    costs about 0.075 USD, but the next call's worst case would pass the 0.65 cap
    (the pricing in test_boards_reasoning.CONFIG), so the run stops with one call made."""
    reasoner = Reasoner(
        CONFIG, generator_tier="cloud-flash", transport=transport,
        env={"CLOUD_KEY": "k"}, approved=True,
    )  # fmt: skip
    return BoardService(
        RunStore(tmp_path / "runs.sqlite"), lambda: POOL, JaccardRetriever, "jaccard",
        reasoner=reasoner,
    )  # fmt: skip


def budget_stopped(tmp_path, transport=None):
    """A run stopped by the budget cap after one completed generator call."""
    recorder = transport if transport is not None else Recording(Mocks())
    svc = service(tmp_path, recorder)
    request = BoardRequest(brief="boats", target_items=3, budget_cap_usd=0.65)
    run_id = svc.create(request).run_id
    stopped = svc.execute(run_id, request)
    assert stopped.state is S.STOPPED and stopped.stop_reason is StopReason.BUDGET_CAP
    assert stopped.cost.spent_usd > 0
    return svc, recorder, request, run_id


class TestRaiseService:
    def test_a_raise_is_recorded_and_the_run_resumes_without_repeating_a_call(self, tmp_path):
        svc, recorder, request, run_id = budget_stopped(tmp_path)
        calls_at_stop = len(recorder.payloads)
        assert calls_at_stop >= 1

        view = svc.raise_cap(run_id, CapRaise(new_cap_usd=2.0, raised_by="Joe"))
        assert view.state is S.STOPPED and view.cost.cap_usd == 2.0
        assert view.request.budget_cap_usd == 2.0

        raises = svc.runs.cap_raises(run_id)
        assert len(raises) == 1
        assert raises[0].run_id == run_id
        assert raises[0].previous_cap_usd == 0.65 and raises[0].new_cap_usd == 2.0
        assert raises[0].raised_by == "Joe" and raises[0].raised_at is not None

        events = read_events(svc.events_path(run_id))
        raise_events = [e for e in events if e.tool == "cap_raise"]
        assert len(raise_events) == 1
        assert "Joe" in raise_events[0].result and raise_events[0].data["raised_at"]

        final = svc.resume_after_raise(run_id)
        assert final.state is S.DONE and len(final.items) == 3
        assert final.cost.cap_usd == 2.0 and final.cost.spent_usd <= 2.0
        assert all(i.attribution_status is AttributionStatus.VERIFIED for i in final.items)
        # No call repeats: every payload that ever reached a provider is distinct —
        # the call completed before the stop came back from the checkpoint.
        bodies = [json.dumps(p, sort_keys=True) for p in recorder.payloads]
        assert len(bodies) == len(set(bodies))

    def test_only_a_run_the_budget_cap_stopped_can_be_raised(self, tmp_path):
        svc, _, request, run_id = budget_stopped(tmp_path)
        working = svc.create(BoardRequest(brief="boats", target_items=2)).run_id
        with pytest.raises(GateRefused, match="budget cap"):
            svc.raise_cap(working, CapRaise(new_cap_usd=1.0, raised_by="Joe"))
        with pytest.raises(KeyError):
            svc.raise_cap("run-unknown", CapRaise(new_cap_usd=1.0, raised_by="Joe"))

        finished = svc.create(BoardRequest(brief="boats", target_items=1, budget_cap_usd=5.0))
        view = svc.execute(finished.run_id, BoardRequest(brief="boats", target_items=1, budget_cap_usd=5.0))
        assert view.state is S.DONE
        with pytest.raises(GateRefused, match="budget cap"):
            svc.raise_cap(finished.run_id, CapRaise(new_cap_usd=9.0, raised_by="Joe"))

    def test_a_number_that_does_not_raise_the_cap_is_refused(self, tmp_path):
        svc, _, _, run_id = budget_stopped(tmp_path)
        with pytest.raises(GateRefused, match="does not raise"):
            svc.raise_cap(run_id, CapRaise(new_cap_usd=0.65, raised_by="Joe"))
        with pytest.raises(GateRefused, match="does not raise"):
            svc.raise_cap(run_id, CapRaise(new_cap_usd=0.10, raised_by="Joe"))
        assert svc.runs.cap_raises(run_id) == []

    def test_a_cancelled_run_cannot_be_raised(self, tmp_path):
        svc, _, _, run_id = budget_stopped(tmp_path)
        svc.cancel(run_id)
        with pytest.raises(GateRefused, match="cancelled"):
            svc.raise_cap(run_id, CapRaise(new_cap_usd=2.0, raised_by="Joe"))

    def test_a_resume_never_outlives_the_kill_switch(self, tmp_path):
        # The raise was recorded before the cancel: the resume must still stop.
        svc, _, _, run_id = budget_stopped(tmp_path)
        svc.raise_cap(run_id, CapRaise(new_cap_usd=2.0, raised_by="Joe"))
        svc.cancel(run_id)
        final = svc.resume_after_raise(run_id)
        assert final.state is S.CANCELLED


class TestRaiseEndpoint:
    def test_a_raise_without_a_name_is_refused(self, tmp_path):
        svc, _, _, run_id = budget_stopped(tmp_path)
        app.dependency_overrides[get_service] = lambda: svc
        try:
            client = TestClient(app)
            assert client.post(f"/runs/{run_id}/cap", json={"new_cap_usd": 2.0}).status_code == 422
            assert (
                client.post(f"/runs/{run_id}/cap", json={"new_cap_usd": 2.0, "raised_by": "   "}).status_code
                == 422
            )
        finally:
            app.dependency_overrides.clear()
        assert svc.runs.cap_raises(run_id) == [], "nothing was recorded"

    def test_the_endpoint_records_the_raise_and_resumes_in_the_background(self, tmp_path):
        svc, recorder, _, run_id = budget_stopped(tmp_path)
        app.dependency_overrides[get_service] = lambda: svc
        try:
            client = TestClient(app)
            response = client.post(f"/runs/{run_id}/cap", json={"new_cap_usd": 2.0, "raised_by": "Joe"})
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 200
        body = response.json()
        conforms(body, "RunView")
        assert body["cost"]["cap_usd"] == 2.0
        assert body["state"] == "stopped"
        # TestClient runs background tasks before the request returns: the resumed run
        # is already finished here.
        final = svc.get(run_id)
        assert final.state is S.DONE and len(final.items) == 3
        assert len(svc.runs.cap_raises(run_id)) == 1
        bodies = [json.dumps(p, sort_keys=True) for p in recorder.payloads]
        assert len(bodies) == len(set(bodies))

    def test_a_refusal_is_409_with_the_gate(self, tmp_path):
        svc, _, _, _ = budget_stopped(tmp_path)
        working = svc.create(BoardRequest(brief="boats", target_items=2)).run_id
        app.dependency_overrides[get_service] = lambda: svc
        try:
            client = TestClient(app)
            response = client.post(f"/runs/{working}/cap", json={"new_cap_usd": 1.0, "raised_by": "Joe"})
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 409
        assert response.json()["gate"] == "G1"
        assert "budget cap" in response.json()["reason"]

    def test_an_unknown_run_is_404(self, tmp_path):
        from test_readyz import endpoint_service

        app.dependency_overrides[get_service] = lambda: endpoint_service(tmp_path)
        try:
            client = TestClient(app)
            response = client.post("/runs/run-x/cap", json={"new_cap_usd": 1.0, "raised_by": "Joe"})
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 404
        assert response.json()["code"] == "unknown_run"
