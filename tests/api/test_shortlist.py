"""The shortlist: POST /runs/{id}/shortlist (issue #231; PRD 8B "Shortlist" and rule 8).

The operator keeps works by eye between G2 and G3. A work nobody kept is not kept: Verify
(G3), Approve (G4) and Export (G5) cover kept works only. Once the board is approved the
shortlist is fixed (Joe, 2026-11-09). A permission-required work can be kept and exported
as a reference on a "For inspiration" board, with its rights column saying so (Joe,
2026-11-09).
"""

import csv

import pytest
from fastapi.testclient import TestClient
from test_boards_reasoning import Mocks, service

from refdesk.api.app import app, get_service
from refdesk.wording import AttributionStatus, RightsStatus


def board(tmp_path, judge_script=None):
    """The test board for "boats": met:1 (open) and met:2 (permission required)."""
    svc = service(tmp_path, Mocks(judge_script=judge_script))
    svc.exports_dir = tmp_path / "exports"
    app.dependency_overrides[get_service] = lambda: svc
    client = TestClient(app)
    run_id = client.post("/boards", json={"brief": "boats"}).json()["run_id"]
    return client, run_id


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def keep_all(client, run_id, operator="Joe"):
    """Keep every work on the board: for tests written before the shortlist (#231) that
    approve, review or export the whole board."""
    ids = [i["record"]["id"] for i in client.get(f"/runs/{run_id}").json()["items"]]
    if ids:
        response = shortlist(client, run_id, *[(i, True) for i in ids], operator=operator)
        assert response.status_code == 200, response.text


def keep_all_in(svc, run_id, operator="joe"):
    """keep_all for tests that call the service directly."""
    from refdesk.api.models import ShortlistChange, ShortlistRequest

    items = [ShortlistChange(item_id=i.record.id, keep=True) for i in svc.get(run_id).items]
    svc.shortlist(run_id, ShortlistRequest(operator=operator, items=items))


def shortlist(client, run_id, *changes, operator="Joe"):
    items = [{"item_id": item_id, "keep": keep} for item_id, keep in changes]
    return client.post(f"/runs/{run_id}/shortlist", json={"operator": operator, "items": items})


def approve(client, run_id):
    return client.post(f"/runs/{run_id}/approve", json={"approver": "Joe", "acknowledged": True})


def items_of(view):
    return {i["record"]["id"]: i for i in view["items"]}


def gate(view, gate_id):
    return next(g for g in view["gates"] if g["id"] == gate_id)


class TestKeeping:
    def test_a_new_board_has_nothing_kept(self, tmp_path):
        client, run_id = board(tmp_path)
        view = client.get(f"/runs/{run_id}").json()
        assert view["items"] and not [i for i in view["items"] if i["selected"]]
        assert view["saved_at"] is None

    def test_keeping_records_who_and_when_and_the_save_time(self, tmp_path):
        client, run_id = board(tmp_path)
        response = shortlist(client, run_id, ("met:1", True))
        assert response.status_code == 200, response.text
        view = response.json()
        kept = items_of(view)["met:1"]
        assert kept["selected"] is True
        assert kept["selected_by"] == "Joe" and kept["selected_at"]
        assert items_of(view)["met:2"]["selected"] is False
        assert view["saved_at"]

    def test_the_shortlist_is_stored_not_just_returned(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        assert items_of(client.get(f"/runs/{run_id}").json())["met:1"]["selected"] is True

    def test_a_kept_work_can_be_taken_off_again(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        view = shortlist(client, run_id, ("met:1", False)).json()
        assert items_of(view)["met:1"]["selected"] is False

    def test_a_flagged_work_can_be_kept_without_a_note(self, tmp_path):
        """The note is asked for at Verify (G3), not when shortlisting."""
        client, run_id = board(tmp_path, judge_script=["unsupported"])
        assert shortlist(client, run_id, ("met:1", True)).status_code == 200

    def test_an_unknown_item_is_refused(self, tmp_path):
        client, run_id = board(tmp_path)
        response = shortlist(client, run_id, ("met:999", True))
        assert response.status_code == 400 and response.json()["code"] == "unknown_item"

    def test_an_unknown_run_is_refused(self, tmp_path):
        client, _ = board(tmp_path)
        assert shortlist(client, "run-nope", ("met:1", True)).status_code == 404

    def test_an_operator_name_is_required(self, tmp_path):
        client, run_id = board(tmp_path)
        assert shortlist(client, run_id, ("met:1", True), operator="").status_code == 422


class TestGatesCoverKeptWorksOnly:
    def test_nothing_kept_means_nothing_to_approve(self, tmp_path):
        client, run_id = board(tmp_path)  # every item verified
        view = client.get(f"/runs/{run_id}").json()
        assert gate(view, "G4")["state"] == "pending"
        assert "shortlist" in gate(view, "G4")["status_text"].lower()
        response = approve(client, run_id)
        assert response.status_code == 409 and "shortlist" in response.json()["reason"].lower()

    def test_keeping_a_verified_work_opens_approval(self, tmp_path):
        client, run_id = board(tmp_path)
        view = shortlist(client, run_id, ("met:1", True)).json()
        assert gate(view, "G4")["state"] == "active"
        assert approve(client, run_id).status_code == 200

    def test_a_flagged_work_that_was_not_kept_does_not_block_approval(self, tmp_path):
        client, run_id = board(tmp_path, judge_script=["unsupported"])  # both flagged
        shortlist(client, run_id, ("met:1", True))
        review = client.post(
            f"/runs/{run_id}/review",
            json={"reviewer": "Joe", "decisions": [
                {"item_id": "met:1", "decision": "keep", "note": "Checked on the Met page."}
            ]},
        )  # fmt: skip
        assert review.status_code == 200, review.text
        assert gate(review.json(), "G3")["state"] == "passed"
        assert approve(client, run_id).status_code == 200

    def test_a_kept_flagged_work_still_needs_a_decision(self, tmp_path):
        client, run_id = board(tmp_path, judge_script=["unsupported"])
        shortlist(client, run_id, ("met:1", True))
        response = approve(client, run_id)
        assert response.status_code == 409 and "still need a decision" in response.json()["reason"]

    def test_only_kept_works_can_be_reviewed(self, tmp_path):
        client, run_id = board(tmp_path, judge_script=["unsupported"])
        response = client.post(
            f"/runs/{run_id}/review",
            json={"reviewer": "Joe", "decisions": [{"item_id": "met:2", "decision": "drop"}]},
        )
        assert response.status_code == 409 and "shortlist" in response.json()["reason"].lower()


class TestExport:
    def test_the_pack_holds_kept_works_only(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        approve(client, run_id)
        receipt = client.post(f"/runs/{run_id}/export", json={"format": "csv"})
        assert receipt.status_code == 200, receipt.text
        with open(receipt.json()["file"], encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert [r["item_id"] for r in rows] == ["met:1"]

    def test_a_kept_permission_required_work_is_exported_as_a_reference(self, tmp_path):
        client, run_id = board(tmp_path)
        view = client.get(f"/runs/{run_id}").json()
        assert (
            items_of(view)["met:2"]["record"]["rights"]["status"]
            == RightsStatus.PERMISSION_REQUIRED
        )
        assert items_of(view)["met:2"]["attribution_status"] == AttributionStatus.VERIFIED
        shortlist(client, run_id, ("met:1", True), ("met:2", True))
        approve(client, run_id)
        receipt = client.post(f"/runs/{run_id}/export", json={"format": "csv"}).json()
        with open(receipt["file"], encoding="utf-8", newline="") as f:
            rows = {r["item_id"]: r for r in csv.DictReader(f)}
        assert rows["met:2"]["rights_status"] == RightsStatus.PERMISSION_REQUIRED
        assert rows["met:2"]["usage_mode"] == "reference_only"


class TestFixedOnceApproved:
    def test_the_shortlist_cannot_change_after_approval(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        approve(client, run_id)
        response = shortlist(client, run_id, ("met:2", True))
        assert response.status_code == 409 and "approved" in response.json()["reason"]

    def test_the_shortlist_cannot_change_after_export(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        approve(client, run_id)
        client.post(f"/runs/{run_id}/export", json={"format": "csv"})
        assert shortlist(client, run_id, ("met:1", False)).status_code == 409
