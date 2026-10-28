"""S8 "This is wrong": POST /reports and GET /reports (issue #146; PRD 8A, 11.8).

A report queues one board item for Joe's review, with who and when. It never changes the
board: the item, its badges and the gates stay as they were. GET /reports is the review
queue. Neither is a `read` operation, so the MCP server never exposes them (ADR-015).
"""

import pytest
from fastapi.testclient import TestClient
from test_boards_reasoning import Mocks, service

from refdesk.api.app import app, get_service


@pytest.fixture
def api(tmp_path):
    svc = service(tmp_path, Mocks())
    app.dependency_overrides[get_service] = lambda: svc
    client = TestClient(app)
    run_id = client.post("/boards", json={"brief": "boats"}).json()["run_id"]
    item_id = client.get(f"/runs/{run_id}").json()["items"][0]["record"]["id"]
    yield client, run_id, item_id
    app.dependency_overrides.clear()


def report(client, run, item, **overrides):
    body = {
        "run_id": run,
        "item_id": item,
        "error_type": "attribution",
        "note": "The Met page gives a different artist.",
        "reporter": "Joe",
        **overrides,
    }
    return client.post("/reports", json=body)


class TestFiling:
    def test_a_report_is_queued_with_who_and_when(self, api):
        client, run_id, item_id = api
        response = report(client, run_id, item_id)
        assert response.status_code == 202, response.text
        accepted = response.json()
        assert accepted["status"] == "queued for review"
        queued = client.get("/reports").json()
        assert len(queued) == 1
        filed = queued[0]
        assert filed["report_id"] == accepted["report_id"]
        assert filed["run_id"] == run_id
        assert filed["item_id"] == item_id
        assert filed["error_type"] == "attribution"
        assert filed["note"] == "The Met page gives a different artist."
        assert filed["reported_by"] == "Joe"
        assert filed["reported_at"]
        assert filed["status"] == "queued for review"

    def test_a_report_does_not_change_the_board(self, api):
        client, run_id, item_id = api
        before = client.get(f"/runs/{run_id}").json()
        assert report(client, run_id, item_id).status_code == 202
        assert client.get(f"/runs/{run_id}").json() == before

    def test_reports_are_listed_oldest_first(self, api):
        client, run_id, item_id = api
        report(client, run_id, item_id, error_type="rights", note="first")
        report(client, run_id, item_id, error_type="rationale", note="second")
        assert [r["note"] for r in client.get("/reports").json()] == ["first", "second"]

    def test_an_exported_board_can_still_be_reported(self, api):
        # Reporting changes nothing on the board, so read-only is no reason to refuse.
        client, run_id, item_id = api
        client.post(f"/runs/{run_id}/approve", json={"approver": "Joe", "acknowledged": True})
        client.post(f"/runs/{run_id}/export", json={"format": "csv"})
        assert client.get(f"/runs/{run_id}").json()["read_only"] is True
        assert report(client, run_id, item_id).status_code == 202


class TestRefusals:
    def test_an_unknown_run_is_404(self, api):
        client, _, item_id = api
        response = report(client, "no-such-run", item_id)
        assert response.status_code == 404
        assert response.json()["code"] == "unknown_run"

    def test_an_item_not_on_the_board_is_refused(self, api):
        client, run_id, _ = api
        response = report(client, run_id, "met:999999999")
        assert response.status_code == 400
        assert response.json()["code"] == "unknown_item"
        assert client.get("/reports").json() == []

    @pytest.mark.parametrize(
        "overrides",
        [
            {"note": "   "},
            {"reporter": ""},
            {"error_type": "spelling"},
            {"run_id": None},
        ],
    )
    def test_an_incomplete_report_is_refused(self, api, overrides):
        client, run_id, item_id = api
        assert report(client, run_id, item_id, **overrides).status_code == 422
        assert client.get("/reports").json() == []


class TestNotExposedThroughMcp:
    def test_neither_operation_is_tagged_read(self):
        paths = app.openapi()["paths"]["/reports"]
        assert "read" not in paths["post"]["tags"]
        assert "read" not in paths["get"]["tags"]
