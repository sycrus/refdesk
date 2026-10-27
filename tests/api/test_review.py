"""G3 review: POST /runs/{id}/review (issue #100; PRD 8B; ADR-015).

Flagged items ("Needs human check") are kept with a note or dropped, with who and when.
Continue (G4) stays blocked until every flagged item is decided. The API enforces it; the
UI only reflects it.
"""

import pytest
from fastapi.testclient import TestClient
from test_boards_reasoning import Mocks, service

from refdesk.api.app import app, get_service
from refdesk.wording import AttributionStatus


@pytest.fixture
def api(tmp_path):
    """A finished board whose items the mock judge flagged (both need a human check)."""
    svc = service(tmp_path, Mocks(judge_script=["unsupported"]))
    app.dependency_overrides[get_service] = lambda: svc
    client = TestClient(app)
    run_id = client.post("/boards", json={"brief": "boats"}).json()["run_id"]
    yield client, run_id
    app.dependency_overrides.clear()


def flagged(client, run_id):
    view = client.get(f"/runs/{run_id}").json()
    return [
        i["record"]["id"]
        for i in view["items"]
        if i["attribution_status"] != AttributionStatus.VERIFIED
    ]


def review(client, run_id, *decisions, reviewer="Joe"):
    return client.post(
        f"/runs/{run_id}/review", json={"reviewer": reviewer, "decisions": list(decisions)}
    )


def gate(view, gate_id):
    return next(g for g in view["gates"] if g["id"] == gate_id)


class TestDecisions:
    def test_keep_with_a_note_and_drop_are_recorded_with_who_and_when(self, api):
        client, run_id = api
        keep, drop = flagged(client, run_id)
        response = review(
            client, run_id,
            {"item_id": keep, "decision": "keep", "note": "Date checked on the Met page."},
            {"item_id": drop, "decision": "drop"},
        )  # fmt: skip
        assert response.status_code == 200, response.text
        items = {i["record"]["id"]: i for i in response.json()["items"]}
        assert items[keep]["review"]["decision"] == "keep"
        assert items[keep]["review"]["note"] == "Date checked on the Met page."
        assert items[keep]["review"]["decided_by"] == "Joe"
        assert items[keep]["review"]["decided_at"]
        assert items[drop]["review"]["decision"] == "drop"

    def test_keep_without_a_note_is_refused(self, api):
        client, run_id = api
        item = flagged(client, run_id)[0]
        response = review(client, run_id, {"item_id": item, "decision": "keep", "note": " "})
        assert response.status_code == 422
        assert gate(client.get(f"/runs/{run_id}").json(), "G3")["state"] == "active"

    def test_a_verified_item_cannot_be_reviewed(self, tmp_path):
        svc = service(tmp_path, Mocks())  # judge supports everything: nothing flagged
        app.dependency_overrides[get_service] = lambda: svc
        try:
            client = TestClient(app)
            run_id = client.post("/boards", json={"brief": "boats"}).json()["run_id"]
            item = client.get(f"/runs/{run_id}").json()["items"][0]["record"]["id"]
            response = review(client, run_id, {"item_id": item, "decision": "drop"})
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 409
        assert response.json()["gate"] == "G3" and "not flagged" in response.json()["reason"]

    def test_an_unknown_item_is_refused(self, api):
        client, run_id = api
        response = review(client, run_id, {"item_id": "met:999", "decision": "drop"})
        assert response.status_code == 400 and response.json()["code"] == "unknown_item"

    def test_an_unknown_run_is_404(self, api):
        client, _ = api
        assert (
            review(client, "run-missing", {"item_id": "met:1", "decision": "drop"}).status_code
            == 404
        )

    def test_a_reviewer_name_is_required(self, api):
        client, run_id = api
        item = flagged(client, run_id)[0]
        assert (
            review(client, run_id, {"item_id": item, "decision": "drop"}, reviewer="").status_code
            == 422
        )

    def test_a_decision_can_be_changed_before_approval(self, api):
        client, run_id = api
        item = flagged(client, run_id)[0]
        review(client, run_id, {"item_id": item, "decision": "drop"})
        view = review(
            client, run_id, {"item_id": item, "decision": "keep", "note": "On reflection, fine."}
        ).json()
        assert (
            next(i for i in view["items"] if i["record"]["id"] == item)["review"]["decision"]
            == "keep"
        )


class TestGates:
    def test_undecided_items_keep_g3_active_and_block_approval(self, api):
        client, run_id = api
        first = flagged(client, run_id)[0]
        view = review(client, run_id, {"item_id": first, "decision": "drop"}).json()
        assert gate(view, "G3")["state"] == "active"
        assert "1 of 2" in gate(view, "G3")["status_text"]
        assert gate(view, "G4")["state"] == "pending"

    def test_when_every_flagged_item_is_decided_g3_passes_and_approval_opens(self, api):
        client, run_id = api
        keep, drop = flagged(client, run_id)
        view = review(
            client, run_id,
            {"item_id": keep, "decision": "keep", "note": "Checked."},
            {"item_id": drop, "decision": "drop"},
        ).json()  # fmt: skip
        assert gate(view, "G3")["state"] == "passed"
        assert "1 kept, 1 dropped" in gate(view, "G3")["status_text"]
        assert gate(view, "G4")["state"] == "active"
        # Reloading the run shows the same decisions: they are stored, not just returned.
        assert gate(client.get(f"/runs/{run_id}").json(), "G3")["state"] == "passed"
