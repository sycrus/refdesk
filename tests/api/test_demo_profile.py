"""The demo profile (issue #167, ADR-025): the public demo is read-only. Approval and
export are disabled by configuration and proved here by a test, not by hiding buttons
(PRD 8B: the API enforces gates).

The rule is by OpenAPI tag, so a route added later is covered without editing this
file: in the demo profile only `read` and `ops` operations answer; every other
operation (runs, gates, reports, or an untagged one) is refused with 403 before it
reaches the board service."""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from test_boards_reasoning import Mocks, service

from refdesk.api import app as app_module
from refdesk.api.app import app, get_service
from refdesk.api.profile import DEMO_ALLOWED_TAGS, get_profile

EXAMPLE = {"run_id": "r1", "record_id": "met:1"}


def operations():
    """Every API operation as (method, concrete path, tags)."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path_format.format(**EXAMPLE)
        for method in sorted(route.methods - {"HEAD"}):
            yield method, path, tuple(route.tags)


WRITES = [(m, p) for m, p, tags in operations() if not set(tags) <= DEMO_ALLOWED_TAGS]
READS = [(m, p) for m, p, tags in operations() if tags and set(tags) <= DEMO_ALLOWED_TAGS]


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("REFDESK_PROFILE", "demo")


class TestProfileSetting:
    def test_default_is_the_full_profile(self, monkeypatch):
        monkeypatch.delenv("REFDESK_PROFILE", raising=False)
        assert get_profile() == "full"

    def test_demo(self, demo):
        assert get_profile() == "demo"

    def test_an_unknown_profile_is_an_error_not_the_full_profile(self, monkeypatch):
        # A typo on the host ("dmeo") must not start a public instance with approval on.
        monkeypatch.setenv("REFDESK_PROFILE", "dmeo")
        with pytest.raises(ValueError, match="dmeo"):
            get_profile()

    def test_an_unknown_profile_stops_startup(self, monkeypatch):
        monkeypatch.setenv("REFDESK_PROFILE", "dmeo")
        with pytest.raises(ValueError):
            with TestClient(app):
                pass


class TestDemoRefusesWrites:
    def test_the_rule_covers_the_gates(self):
        # If approve or export were ever retagged `read`, the demo would open them.
        assert ("POST", "/runs/r1/approve") in WRITES
        assert ("POST", "/runs/r1/export") in WRITES
        assert ("POST", "/boards") in WRITES

    @pytest.mark.parametrize(("method", "path"), WRITES)
    def test_every_non_read_operation_is_refused(self, demo, method, path):
        # The autouse fixture makes the board service fail the test if reached.
        response = TestClient(app).request(method, path, json={})
        assert response.status_code == 403, response.text
        body = response.json()
        assert body["code"] == "disabled_in_demo"
        assert "demo" in body["message"].lower()

    def test_the_full_profile_does_not_refuse(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REFDESK_PROFILE", raising=False)
        svc = service(tmp_path, Mocks())
        app.dependency_overrides[get_service] = lambda: svc
        response = TestClient(app).post("/boards", json={"brief": "boats"})
        assert response.status_code == 202, response.text


class TestDemoServesReads:
    def test_read_operations_exist(self):
        assert ("GET", "/runs") in READS and ("GET", "/healthz") in READS

    def test_run_history_and_a_recorded_run_are_readable(self, tmp_path, demo, monkeypatch):
        svc = service(tmp_path, Mocks())
        app.dependency_overrides[get_service] = lambda: svc
        monkeypatch.delenv("REFDESK_PROFILE")
        run_id = TestClient(app).post("/boards", json={"brief": "boats"}).json()["run_id"]
        monkeypatch.setenv("REFDESK_PROFILE", "demo")
        client = TestClient(app)
        assert client.get("/runs").status_code == 200
        view = client.get(f"/runs/{run_id}")
        assert view.status_code == 200 and view.json()["run_id"] == run_id

    def test_the_ui_and_its_terms_page_are_not_refused(self, demo):
        # The terms page (#219) is static UI at /?terms=1; the read-only rule covers API
        # operations only. Without a built UI, / answers 503 ui_not_built, not 403.
        response = TestClient(app).get("/", params={"terms": "1"})
        assert response.status_code in (200, 503), response.text
        assert response.status_code != 403

    def test_healthz_answers_and_names_the_profile(self, demo):
        # The UI reads the profile here to show the demo home and banner (it hides
        # nothing the API would allow: the API still refuses every write). The demo is
        # always `recorded` (issue #251): nothing runs here, so no tier is named.
        assert TestClient(app).get("/healthz").json() == {
            "status": "ok",
            "profile": "demo",
            "mode": "recorded",
            "generator": None,
            "judge": None,
        }

    def test_healthz_names_the_full_profile_by_default(self, monkeypatch):
        monkeypatch.delenv("REFDESK_PROFILE", raising=False)
        assert TestClient(app).get("/healthz").json()["profile"] == "full"


class TestDemoStartup:
    def test_demo_does_not_resume_runs(self, demo, monkeypatch):
        # Resuming writes to the store; the demo's recorded runs are finished.
        monkeypatch.setenv("REFDESK_AUTO_RESUME", "1")

        def resume(_service):
            pytest.fail("the demo profile resumed runs")

        monkeypatch.setattr(app_module, "resume_interrupted", resume)
        monkeypatch.setattr(app_module, "get_service", lambda: pytest.fail("store opened"))
        with TestClient(app):
            pass
