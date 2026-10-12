"""POST /boards and GET /runs/{id} for retrieval-only runs (issue #45).

Responses are validated against the committed contract (docs/api/openapi.json), so the API
cannot drift from what the UI and MCP server are built against.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from refdesk.api.app import app, get_service
from refdesk.boards import BoardService, RunStore
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus
from refdesk.wording import AttributionStatus, StopReason

SPEC = json.loads(
    (Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json").read_text("utf-8")
)
CHECKED = datetime(2026, 10, 12, tzinfo=UTC)


def conforms(body, schema_name):
    schema = {"$ref": f"#/components/schemas/{schema_name}", "components": SPEC["components"]}
    errors = sorted(Draft202012Validator(schema).iter_errors(body), key=str)
    assert not errors, [e.message for e in errors]


def rec(object_id, tags, status=RightsStatus.OPEN, **fields):
    rights = RightsRecord(
        source="met",
        object_id=object_id,
        flag_field="isPublicDomain",
        flag_value=status is RightsStatus.OPEN,
        licence_string=None,
        checked_at=CHECKED,
        status=status,
    )
    return ArtworkRecord(
        id=f"met:{object_id}",
        source="met",
        object_id=object_id,
        classification="Paintings",
        subject_tags=tags,
        raw_record_ref=f"met/objects/{object_id}.json",
        record_url=f"https://www.metmuseum.org/art/collection/search/{object_id}",
        rights=rights,
        **fields,
    )


RECORDS = [
    rec("1", ("Boats", "Harbors"), medium="Oil on canvas", date="1650", date_begin=1650),
    rec("2", ("Boats",), RightsStatus.PERMISSION_REQUIRED, medium="Oil on wood"),
    rec("3", ("Flowers",), medium="Watercolor"),
]


def service(tmp_path, build=JaccardRetriever, name="jaccard"):
    return BoardService(RunStore(tmp_path / "runs.sqlite"), lambda: RECORDS, build, name)


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_service] = lambda: service(tmp_path)
    yield TestClient(app)
    app.dependency_overrides.clear()


def create(client, **body):
    response = client.post("/boards", json={"brief": "boats", **body})
    assert response.status_code == 202, response.text
    return response.json()


class TestContract:
    def test_post_returns_202_and_a_run_created_body(self, client):
        body = create(client)
        conforms(body, "RunCreated")
        assert body["state"] == "retrieve"

    def test_get_returns_a_run_view(self, client):
        run = client.get(f"/runs/{create(client)['run_id']}")
        assert run.status_code == 200
        conforms(run.json(), "RunView")

    def test_unknown_run_is_404_problem(self, client):
        response = client.get("/runs/run-nope")
        assert response.status_code == 404
        conforms(response.json(), "Problem")

    def test_unknown_anchor_is_400_problem(self, client):
        response = client.post("/boards", json={"brief": "boats", "anchor_id": "met:404"})
        assert response.status_code == 400
        conforms(response.json(), "Problem")
        assert response.json()["code"] == "unknown_anchor"


class TestRetrievalOnlyRun:
    def run(self, client, **body):
        return client.get(f"/runs/{create(client, **body)['run_id']}").json()

    def test_returns_items_with_evidence_and_rights(self, client):
        view = self.run(client)
        assert view["state"] == "done"
        # Jaccard: met:2 shares 1 of 4 attributes, met:1 1 of 6.
        assert [i["record"]["id"] for i in view["items"]] == ["met:2", "met:1"]
        items = {i["record"]["id"]: i for i in view["items"]}
        url = items["met:1"]["record"]["record_url"]
        assert {"field": "subject_tags", "value": "Boats", "record_url": url} in items["met:1"][
            "evidence"
        ]
        assert items["met:2"]["record"]["rights"]["status"] == RightsStatus.PERMISSION_REQUIRED

    def test_evidence_values_come_from_the_record_not_normalised_tokens(self, client):
        view = self.run(client, brief="oil", conditions={"period": "17th century"})
        evidence = {(e["field"], e["value"]) for e in view["items"][0]["evidence"]}
        assert ("medium", "Oil on canvas") in evidence  # not "oil"
        assert ("date", "1650") in evidence  # not "century:17"

    def test_no_item_is_ever_attribution_verified_before_the_verifier_exists(self, client):
        view = self.run(client)
        assert view["items"]
        for item in view["items"]:
            assert item["attribution_status"] == AttributionStatus.NEEDS_HUMAN_CHECK
            assert item["rationale"] is None
            assert item["flag_reasons"]

    def test_score_and_its_components_are_returned(self, client):
        item = self.run(client)["items"][0]
        assert item["score"] > 0
        assert sum(item["score_components"].values()) == pytest.approx(item["score"])

    def test_cost_is_zero_and_nothing_is_sent_anywhere(self, client):
        view = self.run(client, budget_cap_usd=0.02, keep_local=True)
        assert view["cost"] == {"spent_usd": 0.0, "cap_usd": 0.02, "currency": "USD"}
        assert view["sent_to"] == []
        assert view["keep_local"] is True

    def test_reproduction_mode_returns_only_open_works(self, client):
        view = self.run(client, usage_mode="reproduction")
        assert [i["record"]["id"] for i in view["items"]] == ["met:1"]

    def test_target_items_limits_the_board(self, client):
        assert len(self.run(client, target_items=1)["items"]) == 1


class TestGates:
    def gates(self, client, **body):
        view = client.get(f"/runs/{create(client, **body)['run_id']}").json()
        return {g["id"]: g for g in view["gates"]}

    def test_all_six_gates_in_order(self, client):
        view = client.get(f"/runs/{create(client)['run_id']}").json()
        assert [g["id"] for g in view["gates"]] == ["G0", "G1", "G2", "G3", "G4", "G5"]

    def test_checks_that_do_not_exist_yet_are_skipped_not_passed(self, client):
        gates = self.gates(client)
        assert gates["G0"]["state"] == "skipped"
        assert gates["G2"]["state"] == "skipped"
        assert "verifier" in gates["G2"]["status_text"]

    def test_review_is_active_for_the_operator_and_approval_waits(self, client):
        gates = self.gates(client)
        assert (gates["G3"]["state"], gates["G3"]["actor"]) == ("active", "operator")
        assert gates["G4"]["state"] == gates["G5"]["state"] == "pending"

    def test_no_human_gate_is_ever_passed(self, client):
        gates = self.gates(client)
        assert all(gates[g]["state"] != "passed" for g in ("G3", "G4", "G5"))


class TestStops:
    def test_no_results_stops_with_the_fixed_banner(self, client):
        view = client.get(f"/runs/{create(client, brief='zeppelins')['run_id']}").json()
        assert view["state"] == "stopped"
        assert view["stop_reason"] == StopReason.POOL_EXHAUSTED
        assert view["stop_banner"] == StopReason.POOL_EXHAUSTED.banner

    def test_a_retriever_that_cannot_load_stops_loudly_without_fallback(self, tmp_path):
        def broken(records):
            raise ModuleNotFoundError("No module named 'torch'")

        app.dependency_overrides[get_service] = lambda: service(tmp_path, broken, "combined")
        try:
            client = TestClient(app)
            view = client.get(f"/runs/{create(client)['run_id']}").json()
        finally:
            app.dependency_overrides.clear()
        assert view["state"] == "stopped"
        assert view["stop_reason"] == StopReason.SOURCE_UNAVAILABLE
        assert view["stop_banner"] == StopReason.SOURCE_UNAVAILABLE.banner
        assert "combined" in view["stop_detail"] and "torch" in view["stop_detail"]
        assert view["items"] == []
        conforms(view, "RunView")


class TestPersistence:
    def test_a_run_survives_a_new_service(self, tmp_path):
        first = service(tmp_path)
        app.dependency_overrides[get_service] = lambda: first
        try:
            run_id = create(TestClient(app))["run_id"]
            app.dependency_overrides[get_service] = lambda: service(tmp_path)  # fresh instance
            view = TestClient(app).get(f"/runs/{run_id}").json()
        finally:
            app.dependency_overrides.clear()
        assert view["run_id"] == run_id and view["state"] == "done"


class TestRunViewCarriesTheRequest:
    def test_the_view_shows_what_was_asked(self, client):
        run_id = create(client, brief="boats", usage_mode="reproduction")["run_id"]
        view = client.get(f"/runs/{run_id}").json()
        assert view["request"]["brief"] == "boats"
        assert view["request"]["usage_mode"] == "reproduction"


class TestRetrieverOverride:
    def test_env_names_the_retriever(self, tmp_path, monkeypatch):
        from refdesk.boards import default_service

        monkeypatch.setenv("REFDESK_RETRIEVER", "jaccard")
        assert default_service(tmp_path / "store.sqlite").retriever_name == "jaccard"

    def test_config_names_it_otherwise(self, tmp_path, monkeypatch):
        from refdesk.boards import default_service

        monkeypatch.delenv("REFDESK_RETRIEVER", raising=False)
        assert default_service(tmp_path / "store.sqlite").retriever_name == "combined"


class TestConditionsThatCannotBeApplied:
    """Issue #63: a filter that cannot be applied is refused when the board is created."""

    def client_with_filters(self, tmp_path):
        from refdesk.retrieval.combined import CombinedConfig, check_conditions

        config = CombinedConfig(
            weights={"similarity": 0.6, "attributes": 0.4}, conditions={"period": "filter"}
        )
        svc = BoardService(
            RunStore(tmp_path / "runs.sqlite"),
            lambda: RECORDS,
            JaccardRetriever,
            "jaccard",
            check_conditions=lambda conditions: check_conditions(conditions, config),
        )
        app.dependency_overrides[get_service] = lambda: svc
        return TestClient(app)

    def test_an_unparseable_filter_is_400_with_the_reason(self, tmp_path):
        client = self.client_with_filters(tmp_path)
        response = client.post(
            "/boards", json={"brief": "boats", "conditions": {"period": "Baroque"}}
        )
        assert response.status_code == 400
        conforms(response.json(), "Problem")
        assert response.json()["code"] == "condition_not_understood"
        assert "'Baroque'" in response.json()["message"]

    def test_a_parseable_filter_is_accepted(self, tmp_path):
        client = self.client_with_filters(tmp_path)
        body = {"brief": "boats", "conditions": {"period": "17th-century"}}
        assert client.post("/boards", json=body).status_code == 202
