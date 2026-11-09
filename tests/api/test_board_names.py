"""Board names and the Boards list (issue #234).

A board's name is stored apart from its brief. A new board is named from its run ID
("Board b666b9"), never from the brief, because GET /runs is the redacted history (#159)
and is exposed through the MCP read tools (Joe, 2026-11-09). The list also says how far
each board has got, which works to show on its cover (open works only), and when its
shortlist was last saved.
"""

import pytest
from fastapi.testclient import TestClient
from test_boards_reasoning import WITH_ARTISTS, Mocks, service
from test_shortlist import shortlist

from refdesk.api.app import app, get_service

BRIEF = "Mid-Autumn tin, festive but not red and gold, boats"
# Every record has an image URL, so the cover test proves the rights filter does the work.
WITH_IMAGES = [
    r.model_copy(update={"image_url": f"https://images.metmuseum.org/{r.object_id}.jpg"})
    for r in WITH_ARTISTS
]


def board(tmp_path, judge_script=None, brief=BRIEF):
    svc = service(tmp_path, Mocks(judge_script=judge_script), records=WITH_IMAGES)
    svc.exports_dir = tmp_path / "exports"
    app.dependency_overrides[get_service] = lambda: svc
    client = TestClient(app)
    run_id = client.post("/boards", json={"brief": brief}).json()["run_id"]
    return client, run_id


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def summary(client, run_id):
    return next(r for r in client.get("/runs").json() if r["run_id"] == run_id)


def rename(client, run_id, name):
    return client.post(f"/runs/{run_id}/name", json={"name": name})


def approve(client, run_id):
    return client.post(f"/runs/{run_id}/approve", json={"approver": "Joe", "acknowledged": True})


class TestNames:
    def test_a_new_board_is_named_from_its_run_id_not_its_brief(self, tmp_path):
        client, run_id = board(tmp_path)
        expected = f"Board {run_id.removeprefix('run-')[:6]}"
        assert client.get(f"/runs/{run_id}").json()["name"] == expected
        row = summary(client, run_id)
        assert row["name"] == expected
        for word in ("Mid-Autumn", "festive", "boats"):
            assert word not in str(row)

    def test_renaming_changes_the_name_and_never_the_request(self, tmp_path):
        client, run_id = board(tmp_path)
        before = client.get(f"/runs/{run_id}").json()["request"]
        response = rename(client, run_id, "  Mid-Autumn tin  ")
        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Mid-Autumn tin"
        assert response.json()["request"] == before
        assert summary(client, run_id)["name"] == "Mid-Autumn tin"
        assert summary(client, run_id)["brief"] != BRIEF  # still redacted

    def test_an_empty_name_is_refused(self, tmp_path):
        client, run_id = board(tmp_path)
        assert rename(client, run_id, "   ").status_code == 422

    def test_an_unknown_run_is_refused(self, tmp_path):
        client, _ = board(tmp_path)
        assert rename(client, "run-nope", "x").status_code == 404

    def test_an_exported_board_cannot_be_renamed(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        approve(client, run_id)
        client.post(f"/runs/{run_id}/export", json={"format": "csv"})
        response = rename(client, run_id, "Later")
        assert response.status_code == 409 and "read-only" in response.json()["reason"]


class TestStage:
    def test_nothing_kept_is_at_the_shortlist(self, tmp_path):
        client, run_id = board(tmp_path)
        assert summary(client, run_id)["stage"] == "shortlist"

    def test_a_kept_flagged_work_waiting_for_a_decision_is_at_verify(self, tmp_path):
        client, run_id = board(tmp_path, judge_script=["unsupported"])
        shortlist(client, run_id, ("met:1", True))
        assert summary(client, run_id)["stage"] == "verify"

    def test_kept_works_all_decided_are_at_approve(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        assert summary(client, run_id)["stage"] == "approve"

    def test_approved_is_at_export_and_exported_says_so(self, tmp_path):
        client, run_id = board(tmp_path)
        shortlist(client, run_id, ("met:1", True))
        approve(client, run_id)
        assert summary(client, run_id)["stage"] == "export"
        client.post(f"/runs/{run_id}/export", json={"format": "csv"})
        assert summary(client, run_id)["stage"] == "exported"


class TestCoverAndSaved:
    def test_the_cover_shows_open_works_only_kept_first(self, tmp_path):
        client, run_id = board(tmp_path)  # met:1 open, met:2 permission required
        shortlist(client, run_id, ("met:2", True), ("met:1", True))
        cover = summary(client, run_id)["cover"]
        assert [c["record_id"] for c in cover] == ["met:1"]
        assert all(c["image_url"] for c in cover)
        assert len(cover) <= 4

    def test_saved_at_follows_the_shortlist(self, tmp_path):
        client, run_id = board(tmp_path)
        assert summary(client, run_id)["saved_at"] is None
        saved = shortlist(client, run_id, ("met:1", True)).json()["saved_at"]
        assert summary(client, run_id)["saved_at"] == saved
