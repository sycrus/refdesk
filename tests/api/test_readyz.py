"""GET /readyz (issue #168; PRD 13A): it fails (503) when the metadata store, the
embedding index or the required model backend is unavailable, naming the reason, while
/healthz keeps answering -- liveness does not depend on what readiness checks.

The model-backend check never makes a paid call: free providers (mock, Ollama) are
probed with GET {base}/models; a paid provider is never probed -- the client's own
pre-call guards (model, price, key) are mirrored instead, because a tier the client
would refuse is exactly "unavailable".
"""

import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import uvicorn
from fastapi.testclient import TestClient

from refdesk import readiness
from refdesk.api import app as app_module
from refdesk.api.app import app, get_service
from refdesk.boards import BoardService, RunStore
from refdesk.embeddings import EmbeddingIndex
from refdesk.llm.config import ProvidersConfig
from refdesk.llm.mock_server import create_app
from refdesk.readiness import (
    check_embedding_index,
    check_metadata_store,
    check_model_backend,
    probe_models,
)
from refdesk.reasoning import Reasoner
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus
from refdesk.store import Store

CHECK_KEYS = {"metadata_store", "embedding_index", "model_backend"}


def record(object_id="1"):
    rights = RightsRecord(
        source="met", object_id=object_id, flag_field="isPublicDomain", flag_value=True,
        licence_string=None, checked_at=datetime(2026, 10, 27, tzinfo=UTC),
        status=RightsStatus.OPEN,
    )  # fmt: skip
    return ArtworkRecord(
        id=f"met:{object_id}", source="met", object_id=object_id,
        classification="Paintings", subject_tags=("Flowers",),
        raw_record_ref=f"met/objects/{object_id}.json",
        record_url=f"https://www.metmuseum.org/art/collection/search/{object_id}",
        rights=rights,
    )  # fmt: skip


def metadata_store(tmp_path, n=1) -> Path:
    path = tmp_path / "refdesk.sqlite"
    store = Store(path)
    for i in range(n):
        store.save(record(str(i)), {})
    store.close()
    return path


def index_dir(tmp_path) -> Path:
    target = tmp_path / "index"
    EmbeddingIndex(
        ["met:1"], np.ones((1, 8), dtype=np.float32),
        manifest={"model_id": "open_clip/ViT-B-32/laion2b_s34b_b79k"},
    ).save(target)  # fmt: skip
    return target


def providers_config(base_urls: dict[str, str]) -> ProvidersConfig:
    mock_judge = base_urls.get("mock-judge", base_urls["mock"])
    return ProvidersConfig.model_validate(
        {
            "providers": {
                "mock": {"family": "mock", "cloud": False, "paid": False,
                         "base_url": base_urls["mock"]},
                "mock-judge": {"family": "mock-judge", "cloud": False, "paid": False,
                               "base_url": mock_judge},
                "cloudy": {"family": "deepseek", "cloud": True, "paid": True,
                           "base_url": "http://c/v1", "key_env": "CLOUD_KEY"},
            },
            "tiers": {
                "mock": {"provider": "mock", "model": "mock-1"},
                "mock-judge": {"provider": "mock-judge", "model": "mock-1"},
                "cloud-flash": {"provider": "cloudy", "model": "flash",
                                "price_usd_per_mtok": {"input": 0.3, "output": 1.2}},
                "unpriced": {"provider": "cloudy", "model": "flash"},
                "model-less": {"provider": "mock"},
            },
            "routing": ["mock"],
            "judges": ["mock-judge"],
        }
    )


def no_probe(url):
    raise AssertionError(f"probed {url}; a paid tier must never be probed")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_port():
    """The real mock server on a free port, so the probe is exercised over real HTTP."""
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield port
    server.should_exit = True
    thread.join(timeout=5)


class TestMetadataStoreCheck:
    def test_open_store_with_records_is_ok(self, tmp_path):
        check = check_metadata_store(metadata_store(tmp_path, n=2))
        assert check.ok and "2" in check.detail

    def test_missing_file_fails_and_is_never_created(self, tmp_path):
        # mode=ro: a readiness probe must not create an empty database as a side effect.
        path = tmp_path / "absent.sqlite"
        check = check_metadata_store(path)
        assert not check.ok and "metadata store unavailable" in check.detail
        assert not path.exists()

    def test_corrupt_file_fails(self, tmp_path):
        path = tmp_path / "corrupt.sqlite"
        path.write_bytes(b"this is not a database")
        assert not check_metadata_store(path).ok


class TestEmbeddingIndexCheck:
    def test_loadable_index_is_ok(self, tmp_path):
        check = check_embedding_index(index_dir(tmp_path))
        assert check.ok and "1" in check.detail and "ViT-B-32" in check.detail

    def test_missing_index_fails(self, tmp_path):
        check = check_embedding_index(tmp_path / "nope")
        assert not check.ok and "unavailable" in check.detail

    def test_corrupt_index_fails(self, tmp_path):
        target = index_dir(tmp_path)
        (target / "vectors.npy").write_bytes(b"garbage")
        assert not check_embedding_index(target).ok


class TestModelBackendCheck:
    def test_probe_reaches_the_mock_models_endpoint(self, mock_port):
        assert probe_models(f"http://127.0.0.1:{mock_port}/v1/models").ok

    def test_probe_names_the_reason_when_unreachable(self):
        check = probe_models(f"http://127.0.0.1:{free_port()}/v1/models")
        assert not check.ok and "cannot reach" in check.detail

    def test_reachable_tiers_pass(self, mock_port):
        config = providers_config({"mock": f"http://127.0.0.1:{mock_port}/v1"})
        check = check_model_backend(config, ["mock", "mock-judge"], env={})
        assert check.ok and "mock" in check.detail

    def test_a_down_tier_names_the_tier(self, mock_port):
        config = providers_config(
            {"mock": f"http://127.0.0.1:{mock_port}/v1",
             "mock-judge": f"http://127.0.0.1:{free_port()}/v1"}
        )
        check = check_model_backend(config, ["mock", "mock-judge"], env={})
        assert not check.ok and "mock-judge" in check.detail

    def test_unknown_tier_fails(self):
        check = check_model_backend(providers_config({"mock": "http://x/v1"}), ["nope"], env={})
        assert not check.ok and "nope" in check.detail

    def test_tier_without_a_model_fails(self):
        check = check_model_backend(
            providers_config({"mock": "http://x/v1"}), ["model-less"], env={}, probe=no_probe
        )
        assert not check.ok and "model" in check.detail

    def test_paid_tier_is_never_probed(self):
        config = providers_config({"mock": "http://x/v1"})
        check = check_model_backend(
            config, ["cloud-flash"], env={"CLOUD_KEY": "k"}, probe=no_probe
        )
        assert check.ok and "not probed" in check.detail

    def test_paid_tier_without_a_key_is_unavailable(self):
        config = providers_config({"mock": "http://x/v1"})
        check = check_model_backend(config, ["cloud-flash"], env={}, probe=no_probe)
        assert not check.ok and "CLOUD_KEY" in check.detail

    def test_unpriced_paid_tier_is_unavailable(self):
        check = check_model_backend(
            providers_config({"mock": "http://x/v1"}), ["unpriced"], env={"CLOUD_KEY": "k"},
            probe=no_probe,
        )
        assert not check.ok and "price" in check.detail


class TestReport:
    def test_retrieval_only_needs_no_index_or_model(self, tmp_path):
        result = readiness.report(
            store_path=metadata_store(tmp_path), retriever_name="jaccard", reasoner=None,
            index_dir=tmp_path / "unused", env={},
        )
        assert result.ready and set(result.checks) == CHECK_KEYS
        assert "not required" in result.checks["embedding_index"]
        assert "not required" in result.checks["model_backend"]

    def test_index_is_checked_only_when_the_retriever_reads_it(self, tmp_path):
        missing = tmp_path / "no-index"
        jaccard = readiness.report(
            store_path=metadata_store(tmp_path), retriever_name="jaccard", reasoner=None,
            index_dir=missing, env={},
        )
        combined = readiness.report(
            store_path=metadata_store(tmp_path), retriever_name="combined", reasoner=None,
            index_dir=missing, env={},
        )
        assert jaccard.ready and not combined.ready

    def test_a_reasoner_makes_the_model_backend_required(self, tmp_path):
        reasoner = Reasoner(
            providers_config({"mock": f"http://127.0.0.1:{free_port()}/v1"}),
            generator_tier="mock",
        )
        result = readiness.report(
            store_path=metadata_store(tmp_path), retriever_name="jaccard", reasoner=reasoner,
            index_dir=index_dir(tmp_path), env={},
        )
        assert not result.ready
        assert "model backend unavailable" in result.checks["model_backend"]

    def test_everything_up_is_ready(self, tmp_path, mock_port):
        reasoner = Reasoner(
            providers_config({"mock": f"http://127.0.0.1:{mock_port}/v1"}),
            generator_tier="mock",
        )
        result = readiness.report(
            store_path=metadata_store(tmp_path), retriever_name="combined", reasoner=reasoner,
            index_dir=index_dir(tmp_path), env={},
        )
        assert result.ready, result.checks


def endpoint_service(tmp_path, *, retriever="jaccard", reasoner=None) -> BoardService:
    path = metadata_store(tmp_path)
    return BoardService(
        RunStore(path), lambda: [record()], JaccardRetriever, retriever, reasoner=reasoner
    )


class TestEndpoint:
    """The wired endpoint: 200 when ready, 503 with the failing check named, and
    /healthz still up in every failing case (the acceptance criterion)."""

    def readyz(self):
        return TestClient(app).get("/readyz")

    def healthz(self):
        return TestClient(app).get("/healthz")

    def test_healthy_service_is_ready(self, tmp_path, mock_port, monkeypatch):
        monkeypatch.setattr(app_module, "INDEX_DIR", index_dir(tmp_path))
        reasoner = Reasoner(
            providers_config({"mock": f"http://127.0.0.1:{mock_port}/v1"}),
            generator_tier="mock",
        )
        app.dependency_overrides[get_service] = lambda: endpoint_service(
            tmp_path, reasoner=reasoner
        )
        response = self.readyz()
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ready"] is True and set(body["checks"]) == CHECK_KEYS

    def test_metadata_store_down(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "INDEX_DIR", index_dir(tmp_path))
        service = endpoint_service(tmp_path)
        (tmp_path / "refdesk.sqlite").unlink()
        app.dependency_overrides[get_service] = lambda: service
        response = self.readyz()
        assert response.status_code == 503
        assert response.json()["ready"] is False
        assert "metadata store unavailable" in response.json()["checks"]["metadata_store"]
        assert self.healthz().json() == {"status": "ok"}

    def test_embedding_index_down(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "INDEX_DIR", tmp_path / "no-index")
        app.dependency_overrides[get_service] = lambda: endpoint_service(
            tmp_path, retriever="combined"
        )
        response = self.readyz()
        assert response.status_code == 503
        assert "unavailable" in response.json()["checks"]["embedding_index"]
        assert self.healthz().json() == {"status": "ok"}

    def test_model_backend_down(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "INDEX_DIR", index_dir(tmp_path))
        reasoner = Reasoner(
            providers_config({"mock": f"http://127.0.0.1:{free_port()}/v1"}),
            generator_tier="mock",
        )
        app.dependency_overrides[get_service] = lambda: endpoint_service(
            tmp_path, reasoner=reasoner
        )
        response = self.readyz()
        assert response.status_code == 503
        assert "model backend unavailable" in response.json()["checks"]["model_backend"]
        assert self.healthz().json() == {"status": "ok"}
