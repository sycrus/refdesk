"""API contract (issue #13, PRD 13A): the OpenAPI spec is valid, lists every endpoint,
matches the committed file, and the skeleton contains no business logic yet."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from refdesk.api.app import app
from refdesk.wording import AttributionStatus, RightsStatus, StopReason

SPEC_FILE = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"

# PRD Section 13A, endpoint table.
PRD_13A = {
    ("post", "/boards"),
    ("get", "/runs/{run_id}"),
    ("post", "/runs/{run_id}/review"),
    ("post", "/runs/{run_id}/cap"),
    ("post", "/runs/{run_id}/approve"),
    ("post", "/runs/{run_id}/export"),
    ("post", "/reports"),
    ("get", "/healthz"),
    ("get", "/readyz"),
}


@pytest.fixture(scope="module")
def spec():
    return app.openapi()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def operations(spec):
    return {(method, path) for path, item in spec["paths"].items() for method in item}


class TestSpec:
    def test_spec_is_valid_openapi(self, spec):
        validate(spec)

    def test_lists_exactly_the_prd_13a_endpoints(self, spec):
        assert operations(spec) == PRD_13A

    def test_committed_spec_matches_the_app(self, spec):
        # Regenerate with: uv run python scripts/export_openapi.py
        committed = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
        assert committed == spec, "docs/api/openapi.json is stale"

    def test_committed_spec_is_valid(self):
        validate(json.loads(SPEC_FILE.read_text(encoding="utf-8")))

    def test_status_enums_carry_the_fixed_wording(self, spec):
        schemas = spec["components"]["schemas"]
        assert schemas["RightsStatus"]["enum"] == [s.value for s in RightsStatus]
        assert schemas["AttributionStatus"]["enum"] == [s.value for s in AttributionStatus]
        assert schemas["StopReason"]["enum"] == [s.value for s in StopReason]

    def test_gate_endpoints_document_the_blocked_response(self, spec):
        # The API enforces gates (PRD 8B rule 1): approve and export can refuse with 409.
        for path in ("/runs/{run_id}/approve", "/runs/{run_id}/export"):
            assert "409" in spec["paths"][path]["post"]["responses"]


class TestNoBusinessLogicYet:
    def test_healthz_is_live(self, client):
        assert client.get("/healthz").json() == {"status": "ok"}

    def test_readyz_reports_not_ready_with_reasons(self, client):
        response = client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False
        assert set(body["checks"]) == {"metadata_store", "embedding_index", "model_backend"}

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("post", "/boards", {"brief": "Mid-Autumn tin, festive but not red and gold"}),
            ("get", "/runs/r1", None),
            ("post", "/runs/r1/review", {"decisions": []}),
            ("post", "/runs/r1/cap", {"new_cap_usd": 0.1, "raised_by": "Joe"}),
            ("post", "/runs/r1/approve", {"approver": "Joe", "acknowledged": True}),
            ("post", "/runs/r1/export", {"format": "csv"}),
            (
                "post",
                "/reports",
                {"item_id": "met:1", "error_type": "attribution", "note": "wrong artist"},
            ),
        ],
    )
    def test_endpoints_are_stubs(self, client, method, path, body):
        response = client.request(method, path, json=body)
        assert response.status_code == 501


class TestRequestValidation:
    def test_approve_requires_the_acknowledgement(self, client):
        response = client.post("/runs/r1/approve", json={"approver": "Joe", "acknowledged": False})
        assert response.status_code == 422

    def test_keep_decision_requires_a_note(self, client):
        body = {"decisions": [{"item_id": "met:1", "decision": "keep"}]}
        assert client.post("/runs/r1/review", json=body).status_code == 422

    def test_cap_must_be_positive(self, client):
        body = {"new_cap_usd": 0, "raised_by": "Joe"}
        assert client.post("/runs/r1/cap", json=body).status_code == 422
