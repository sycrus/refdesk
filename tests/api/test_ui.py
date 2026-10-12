"""The API serves the built UI at / (issue #41, PRD 8A, ADR-017)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from refdesk.api.app import UI_DIST, app, mount_ui


def api_with_ui(dist):
    test_app = FastAPI()

    @test_app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    mount_ui(test_app, dist)
    return TestClient(test_app)


def built(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>refdesk</title>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


def test_serves_the_built_index_at_root(tmp_path):
    response = api_with_ui(built(tmp_path)).get("/")
    assert response.status_code == 200
    assert "<title>refdesk</title>" in response.text


def test_serves_built_assets(tmp_path):
    assert api_with_ui(built(tmp_path)).get("/assets/app.js").status_code == 200


def test_api_routes_win_over_the_ui(tmp_path):
    assert api_with_ui(built(tmp_path)).get("/healthz").json() == {"status": "ok"}


def test_missing_build_says_how_to_build_it(tmp_path):
    response = api_with_ui(tmp_path / "missing").get("/")
    assert response.status_code == 503
    assert response.json()["code"] == "ui_not_built"
    assert "npm run build" in response.json()["message"]


def test_the_app_mounts_the_ui_without_changing_the_api_contract():
    assert UI_DIST.parts[-2:] == ("ui", "dist")
    assert "/" not in app.openapi()["paths"]  # the UI is not an API operation (MCP, FR-12)
