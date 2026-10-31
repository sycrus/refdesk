"""The kill switch endpoint (issue #158; PRD 10.2 kill switch, 13A).

`BoardService.cancel` and its effect on the loop are tested with the loop controller
(test_loop.py, TestKillSwitch); this is the HTTP contract: an unknown run is 404, the
request is recorded, and a run executing in its own thread reaches Cancelled before its
next model call. Cancel is idempotent: asking again changes nothing.
"""

import threading
import time

from fastapi.testclient import TestClient
from test_boards import conforms, rec
from test_boards_reasoning import CONFIG, Mocks

from refdesk.api.app import app, get_service
from refdesk.api.models import BoardRequest, LoopState
from refdesk.boards import BoardService, RunStore
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.wording import StopReason

S = LoopState

POOL = [
    rec(str(n), ("Boats",), medium="Oil on canvas", artist=f"Painter {n}") for n in range(1, 11)
]


class SlowMocks(Mocks):
    """The mock behind a run in its own thread: slow enough to cancel mid-run."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls_seen = threading.Event()

    def post_json(self, url, headers, payload):
        result = super().post_json(url, headers, payload)
        self.calls_seen.set()
        time.sleep(0.05)
        return result


def service(tmp_path, mocks):
    reasoner = Reasoner(CONFIG, generator_tier="mock", transport=mocks)
    return BoardService(
        RunStore(tmp_path / "runs.sqlite"), lambda: POOL, JaccardRetriever, "jaccard",
        reasoner=reasoner,
    )  # fmt: skip


def with_service(svc):
    app.dependency_overrides[get_service] = lambda: svc
    return TestClient(app)


def cleanup():
    app.dependency_overrides.clear()


def test_an_unknown_run_is_404(tmp_path):
    from test_readyz import endpoint_service

    client = with_service(endpoint_service(tmp_path))
    try:
        assert client.post("/runs/run-x/cancel").status_code == 404
        assert client.post("/runs/run-x/cancel").json()["code"] == "unknown_run"
    finally:
        cleanup()


def test_cancel_records_the_request_and_the_run_never_calls(tmp_path):
    mocks = SlowMocks()
    svc = service(tmp_path, mocks)
    request = BoardRequest(brief="boats", target_items=2)
    run_id = svc.create(request).run_id
    client = with_service(svc)
    try:
        response = client.post(f"/runs/{run_id}/cancel")
    finally:
        cleanup()
    assert response.status_code == 200
    conforms(response.json(), "RunView")
    assert svc.runs.is_cancelled(run_id)

    view = svc.execute(run_id, request)
    assert view.state is S.CANCELLED and view.stop_reason is StopReason.CANCELLED
    assert view.stop_banner == "Stopped: cancelled"
    assert mocks.calls == [], "a cancelled run made no model call"


def test_a_run_in_flight_reaches_cancelled_before_its_next_call(tmp_path):
    mocks = SlowMocks()
    svc = service(tmp_path, mocks)
    request = BoardRequest(brief="boats", target_items=3)
    run_id = svc.create(request).run_id
    started = threading.Thread(target=svc.execute, args=(run_id, request), daemon=True)
    started.start()
    mocks.calls_seen.wait(10)

    client = with_service(svc)
    try:
        assert client.post(f"/runs/{run_id}/cancel").status_code == 200
    finally:
        cleanup()
    started.join(10)
    view = svc.get(run_id)
    assert view.state is S.CANCELLED
    assert mocks.calls.count("m") < 6, "the run stopped well before its target"


def test_cancel_is_idempotent(tmp_path):
    svc = service(tmp_path, Mocks())
    request = BoardRequest(brief="boats", target_items=1)
    run_id = svc.create(request).run_id
    client = with_service(svc)
    try:
        assert client.post(f"/runs/{run_id}/cancel").status_code == 200
        assert client.post(f"/runs/{run_id}/cancel").status_code == 200
    finally:
        cleanup()
    assert svc.runs.is_cancelled(run_id)
