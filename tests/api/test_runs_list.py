"""S7 run history: GET /runs (issue #159; PRD 8A S7, 10.2).

One row per past run, newest first: the brief redacted (the run log's rule, PRD 10.2),
state, stop reason with its fixed wording, cost, where the brief was sent and who approved.
Read-only. One run's events are on GET /runs/{run_id}, as before.
"""

import pytest
from fastapi.testclient import TestClient
from test_boards_reasoning import Mocks, service

from refdesk.api.app import app, get_service
from refdesk.runlog import REDACTED


@pytest.fixture
def api(tmp_path):
    svc = service(tmp_path, Mocks())
    app.dependency_overrides[get_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


def board(client, brief="boats", **extra):
    return client.post("/boards", json={"brief": brief, **extra}).json()["run_id"]


class TestRunsList:
    def test_empty_store_lists_nothing(self, api):
        response = api.get("/runs")
        assert response.status_code == 200
        assert response.json() == []

    def test_lists_every_run_newest_first(self, api):
        first = board(api, "boats")
        second = board(api, "harbour at dusk")
        assert [r["run_id"] for r in api.get("/runs").json()] == [second, first]

    def test_the_brief_never_appears(self, api):
        board(api, "secret client tin for Mid-Autumn")
        response = api.get("/runs")
        assert "secret client tin" not in response.text
        assert response.json()[0]["brief"] == REDACTED

    def test_each_row_shows_state_cost_and_where_the_brief_was_sent(self, api):
        run_id = board(api)
        row = api.get("/runs").json()[0]
        full = api.get(f"/runs/{run_id}").json()
        assert row["state"] == full["state"]
        assert row["cost"] == full["cost"]
        assert row["sent_to"] == ["mock", "mock-judge"] == full["sent_to"]
        assert row["keep_local"] is False
        assert row["created_at"]
        assert row["approver"] is None

    def test_keep_local_run_shows_it_was_sent_nowhere_else(self, api):
        board(api, keep_local=True)
        row = api.get("/runs").json()[0]
        assert row["keep_local"] is True
        assert "cloudy" not in row["sent_to"]

    def test_a_stopped_run_keeps_its_stop_reason_and_fixed_wording(self, api):
        run_id = board(api, "zeppelins over the sea")
        full = api.get(f"/runs/{run_id}").json()
        row = api.get("/runs").json()[0]
        assert row["stop_reason"] == full["stop_reason"]
        assert row["stop_banner"] == full["stop_banner"]
        if full["stop_reason"] is not None:
            assert row["stop_banner"]

    def test_the_approver_is_shown_once_approved(self, api):
        run_id = board(api)
        response = api.post(
            f"/runs/{run_id}/approve", json={"approver": "Joe", "acknowledged": True}
        )
        assert response.status_code == 200, response.text
        assert api.get("/runs").json()[0]["approver"] == "Joe"

    def test_listing_changes_no_run(self, api):
        run_id = board(api)
        before = api.get(f"/runs/{run_id}").json()
        api.get("/runs")
        assert api.get(f"/runs/{run_id}").json() == before


class TestReadOnly:
    def test_it_is_a_read_operation(self):
        # Read-only and brief-free, so it is safe for the MCP server's read tools.
        assert app.openapi()["paths"]["/runs"]["get"]["tags"] == ["read"]

    def test_no_write_method_on_the_collection(self):
        assert set(app.openapi()["paths"]["/runs"]) == {"get"}
