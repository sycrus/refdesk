"""What the provenance pack will hold, grouped for the Approve screen (issue #233).

GET /runs/{id}/pack groups every work on the board: open (as stated by source), marked
reviewed by you, kept as a reference only (permission required), and left out with the
reason. The groups come from the same rule as the export (pack_items), so the screen never
does its own arithmetic.
"""

import pytest
from fastapi.testclient import TestClient
from test_boards_reasoning import Mocks, service
from test_shortlist import shortlist

from refdesk.api.app import app, get_service
from refdesk.boards import pack_items


def board(tmp_path, judge_script=None):
    """For "boats": met:1 (open) and met:2 (permission required)."""
    svc = service(tmp_path, Mocks(judge_script=judge_script))
    svc.exports_dir = tmp_path / "exports"
    app.dependency_overrides[get_service] = lambda: svc
    client = TestClient(app)
    run_id = client.post("/boards", json={"brief": "boats"}).json()["run_id"]
    return client, run_id, svc


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def pack(client, run_id):
    response = client.get(f"/runs/{run_id}/pack")
    assert response.status_code == 200, response.text
    return response.json()


def test_nothing_kept_leaves_everything_out_with_the_reason(tmp_path):
    client, run_id, _ = board(tmp_path)
    summary = pack(client, run_id)
    assert summary["included"] == 0
    assert {(w["record_id"], w["reason"]) for w in summary["left_out"]} == {
        ("met:1", "Not kept"),
        ("met:2", "Not kept"),
    }


def test_open_and_reference_only_groups(tmp_path):
    client, run_id, _ = board(tmp_path)
    shortlist(client, run_id, ("met:1", True), ("met:2", True))
    summary = pack(client, run_id)
    assert summary["open"] == ["met:1"]
    assert summary["reference"] == ["met:2"]  # permission required: a reference row only
    assert summary["reviewed"] == [] and summary["left_out"] == []
    assert summary["included"] == 2


def test_reviewed_and_dropped_at_verify(tmp_path):
    client, run_id, _ = board(tmp_path, judge_script=["unsupported"])
    shortlist(client, run_id, ("met:1", True), ("met:2", True))
    client.post(
        f"/runs/{run_id}/review",
        json={"reviewer": "Joe", "decisions": [
            {"item_id": "met:1", "decision": "keep", "note": "Checked."},
            {"item_id": "met:2", "decision": "drop"},
        ]},
    )  # fmt: skip
    summary = pack(client, run_id)
    assert summary["reviewed"] == ["met:1"]
    left_out = [(w["record_id"], w["reason"]) for w in summary["left_out"]]
    assert left_out == [("met:2", "Dropped at Verify")]


def test_the_groups_match_the_export_rule_exactly(tmp_path):
    client, run_id, svc = board(tmp_path, judge_script=["unsupported"])
    shortlist(client, run_id, ("met:2", True))
    summary = pack(client, run_id)
    included, _, _ = pack_items(svc.get(run_id).items)
    grouped = summary["open"] + summary["reviewed"] + summary["reference"]
    assert sorted(grouped) == sorted(i.record.id for i in included)
    assert summary["included"] == len(included)


def test_an_unknown_run_is_refused(tmp_path):
    client, _, _ = board(tmp_path)
    assert client.get("/runs/run-nope/pack").status_code == 404
