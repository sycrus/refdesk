"""G4 approve and G5 export with the provenance pack (issue #101; FR-10; PRD 8B;
acceptance scenario 5; rights-check skill; ADR-015: neither is exposed through MCP)."""

import csv

import pytest
from fastapi.testclient import TestClient
from test_boards_reasoning import Mocks, service

from refdesk.api.app import app, get_service
from refdesk.wording import EXPORTED, NOT_LEGAL_ADVICE

PACK_COLUMNS = [
    "run_id", "item_id", "title", "artist", "date", "source", "object_id", "record_url",
    "usage_mode", "rights_status", "flag_field", "flag_value", "licence_string", "credit_line",
    "checked_at", "attribution_status", "review_decision", "review_note", "reviewed_by",
    "rationale", "opinion_flag", "tier_used", "generator_model", "judge_model", "retriever",
    "approver",
    "approved_at", "exported_at", "not_legal_advice",
]  # fmt: skip


def board(tmp_path, judge_script=None, **kwargs):
    svc = service(tmp_path, Mocks(judge_script=judge_script), **kwargs)
    svc.exports_dir = tmp_path / "exports"
    app.dependency_overrides[get_service] = lambda: svc
    client = TestClient(app)
    run_id = client.post("/boards", json={"brief": "boats"}).json()["run_id"]
    return client, run_id


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def approve(client, run_id, approver="Joe"):
    return client.post(f"/runs/{run_id}/approve", json={"approver": approver, "acknowledged": True})


def export(client, run_id, fmt="csv"):
    return client.post(f"/runs/{run_id}/export", json={"format": fmt})


def gate(view, gate_id):
    return next(g for g in view["gates"] if g["id"] == gate_id)


class TestApprove:
    def test_records_the_approver_and_opens_export(self, tmp_path):
        client, run_id = board(tmp_path)  # all verified: nothing to review
        response = approve(client, run_id)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["approval"]["approver"] == "Joe" and view["approval"]["approved_at"]
        assert gate(view, "G4")["state"] == "passed"
        assert gate(view, "G5")["state"] == "active"

    def test_undecided_flagged_items_block_approval(self, tmp_path):
        client, run_id = board(tmp_path, judge_script=["unsupported"])
        response = approve(client, run_id)
        assert response.status_code == 409
        assert (
            response.json()["gate"] == "G4" and "still need a decision" in response.json()["reason"]
        )

    def test_the_acknowledgement_is_required(self, tmp_path):
        client, run_id = board(tmp_path)
        body = {"approver": "Joe", "acknowledged": False}
        assert client.post(f"/runs/{run_id}/approve", json=body).status_code == 422

    def test_approving_twice_is_refused(self, tmp_path):
        client, run_id = board(tmp_path)
        approve(client, run_id)
        assert approve(client, run_id).status_code == 409

    def test_nothing_to_export_cannot_be_approved(self, tmp_path):
        client, run_id = board(tmp_path, judge_script=["unsupported"])
        items = [i["record"]["id"] for i in client.get(f"/runs/{run_id}").json()["items"]]
        client.post(
            f"/runs/{run_id}/review",
            json={
                "reviewer": "Joe",
                "decisions": [{"item_id": i, "decision": "drop"} for i in items],
            },
        )
        response = approve(client, run_id)
        assert response.status_code == 409 and "nothing" in response.json()["reason"]


class TestExport:
    """Scenario 5: export is impossible without approval."""

    def test_export_without_approval_is_refused(self, tmp_path):
        client, run_id = board(tmp_path)
        response = export(client, run_id)
        assert response.status_code == 409 and response.json()["gate"] == "G5"
        assert not (tmp_path / "exports").exists()

    def test_export_writes_the_pack_and_makes_the_board_read_only(self, tmp_path):
        client, run_id = board(tmp_path)
        approve(client, run_id)
        response = export(client, run_id)
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt["run_id"] == run_id and receipt["approver"] == "Joe"
        assert receipt["notice"] == EXPORTED and receipt["not_legal_advice"] == NOT_LEGAL_ADVICE
        assert receipt["versions"]["generator"] == "mock-1"
        view = client.get(f"/runs/{run_id}").json()
        assert view["read_only"] is True and gate(view, "G5")["state"] == "passed"
        assert view["export"]["file"] == receipt["file"]

    def test_the_pack_reads_back_with_the_fr10_columns(self, tmp_path):
        client, run_id = board(tmp_path)
        approve(client, run_id)
        receipt = export(client, run_id).json()
        with open(receipt["file"], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert list(rows[0]) == PACK_COLUMNS
        assert {r["run_id"] for r in rows} == {run_id}
        first = next(r for r in rows if r["object_id"] == "1")
        assert first["rights_status"] == "Open (as stated by source)"
        assert first["flag_field"] == "isPublicDomain" and first["flag_value"] == "True"
        assert first["attribution_status"] == "Attribution verified from record"
        assert first["generator_model"] == "mock-1" and first["approver"] == "Joe"
        assert first["not_legal_advice"] == NOT_LEGAL_ADVICE

    def test_dropped_items_are_left_out_and_kept_ones_carry_their_note(self, tmp_path):
        client, run_id = board(tmp_path, judge_script=["unsupported"])
        keep, drop = [i["record"]["id"] for i in client.get(f"/runs/{run_id}").json()["items"]]
        client.post(
            f"/runs/{run_id}/review",
            json={
                "reviewer": "Joe",
                "decisions": [
                    {"item_id": keep, "decision": "keep", "note": "Checked on the Met page."},
                    {"item_id": drop, "decision": "drop"},
                ],
            },
        )
        approve(client, run_id)
        with open(export(client, run_id).json()["file"], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert [r["item_id"] for r in rows] == [keep]
        assert rows[0]["review_decision"] == "keep"
        assert rows[0]["review_note"] == "Checked on the Met page."
        assert rows[0]["reviewed_by"] == "Joe"

    def test_after_export_the_board_cannot_change(self, tmp_path):
        client, run_id = board(tmp_path)
        approve(client, run_id)
        export(client, run_id)
        assert export(client, run_id).status_code == 409
        assert approve(client, run_id).status_code == 409

    def test_pdf_is_not_built_yet_and_says_so(self, tmp_path):
        client, run_id = board(tmp_path)
        approve(client, run_id)
        response = export(client, run_id, fmt="pdf")
        assert response.status_code == 400 and response.json()["code"] == "format_not_supported"

    def test_a_failed_export_leaves_the_board_unlocked(self, tmp_path):
        client, run_id = board(tmp_path)
        approve(client, run_id)
        app.dependency_overrides[get_service]().exports_dir = tmp_path / "not-a-dir"
        (tmp_path / "not-a-dir").write_text("a file where the folder should be")
        response = export(client, run_id)
        assert response.status_code == 500 and response.json()["code"] == "export_failed"
        view = client.get(f"/runs/{run_id}").json()
        assert view["read_only"] is False and gate(view, "G5")["state"] == "active"
