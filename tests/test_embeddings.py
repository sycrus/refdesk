"""Image embeddings and the FAISS index (issue #32). A fake embedder keeps these tests
free of torch, so they run in CI; the real OpenCLIP embedder is checked on the GPU."""

import hashlib
from datetime import UTC, datetime

import numpy as np
import pytest

from refdesk.embeddings import EmbeddingIndex, build_index, normalise
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus
from refdesk.store import Store

CHECKED = datetime(2026, 10, 12, tzinfo=UTC)


class FakeEmbedder:
    """Deterministic vectors from file bytes; counts calls to prove rebuilds are skipped."""

    model_id = "fake/v1"
    weights_hash = "0" * 12
    dim = 8

    def __init__(self):
        self.image_calls = 0

    def embed_images(self, paths):
        self.image_calls += 1
        out = []
        for p in paths:
            seed = int(hashlib.sha256(p.read_bytes()).hexdigest()[:8], 16)
            out.append(np.random.default_rng(seed).normal(size=self.dim))
        return np.array(out, dtype=np.float32)

    def embed_texts(self, texts):
        return np.array(
            [np.random.default_rng(len(t)).normal(size=self.dim) for t in texts], dtype=np.float32
        )


def rec(object_id, status=RightsStatus.OPEN):
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
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


@pytest.fixture
def setup(tmp_path):
    cache = tmp_path / "images"
    (cache / "met").mkdir(parents=True)
    store = Store(tmp_path / "db.sqlite")
    for i in range(1, 6):
        r = rec(str(i))
        store.save(r, {"objectID": i})
        data = f"image-{i}".encode()
        (cache / "met" / f"{i}.jpg").write_bytes(data)
        store.save_image(
            r.id,
            f"https://images.metmuseum.org/{i}.jpg",
            f"met/{i}.jpg",
            hashlib.sha256(data).hexdigest(),
            len(data),
        )
    store.save(rec("6", RightsStatus.PERMISSION_REQUIRED), {"objectID": 6})  # no image
    yield store, cache, tmp_path / "index"
    store.close()


def brute_force(vectors, query, k):
    scores = normalise(vectors) @ normalise(query[None, :])[0]
    order = np.argsort(-scores, kind="stable")[:k]
    return order, scores[order]


class TestIndex:
    def test_faiss_matches_brute_force_numpy_cosine(self):
        rng = np.random.default_rng(0)
        vectors = rng.normal(size=(50, 16)).astype(np.float32)
        ids = [f"met:{i}" for i in range(50)]
        index = EmbeddingIndex(ids, vectors)
        query = rng.normal(size=16).astype(np.float32)
        hits = index.search(query, k=10)
        order, scores = brute_force(vectors, query, 10)
        assert [h[0] for h in hits] == [ids[i] for i in order]
        np.testing.assert_allclose([h[1] for h in hits], scores, rtol=1e-5, atol=1e-6)

    def test_vectors_are_normalised_so_inner_product_is_cosine(self):
        index = EmbeddingIndex(["a", "b"], np.array([[3.0, 0.0], [0.0, 0.5]], dtype=np.float32))
        [(top, score)] = index.search(np.array([10.0, 0.0], dtype=np.float32), k=1)
        assert top == "a" and score == pytest.approx(1.0)

    def test_save_and_load_round_trip(self, tmp_path):
        index = EmbeddingIndex(["a", "b"], np.eye(2, dtype=np.float32))
        index.save(tmp_path / "ix")
        loaded = EmbeddingIndex.load(tmp_path / "ix")
        assert loaded.ids == ["a", "b"]
        assert loaded.search(np.array([0.0, 1.0], dtype=np.float32), k=1)[0][0] == "b"

    def test_vector_for_a_record(self):
        index = EmbeddingIndex(["a", "b"], np.eye(2, dtype=np.float32))
        np.testing.assert_allclose(index.vector("b"), [0.0, 1.0])


class TestBuild:
    def test_builds_from_cached_images_of_open_works(self, setup):
        store, cache, out = setup
        result = build_index(store, cache, FakeEmbedder(), out)
        assert result.built is True
        assert sorted(EmbeddingIndex.load(out).ids) == [f"met:{i}" for i in range(1, 6)]

    def test_rebuild_is_skipped_when_the_manifest_matches(self, setup):
        store, cache, out = setup
        build_index(store, cache, FakeEmbedder(), out)
        embedder = FakeEmbedder()
        result = build_index(store, cache, embedder, out)
        assert result.built is False and embedder.image_calls == 0

    def test_a_changed_image_triggers_a_rebuild(self, setup):
        store, cache, out = setup
        build_index(store, cache, FakeEmbedder(), out)
        data = b"image-1-new"
        (cache / "met" / "1.jpg").write_bytes(data)
        store.save_image(
            "met:1",
            "https://images.metmuseum.org/1.jpg",
            "met/1.jpg",
            hashlib.sha256(data).hexdigest(),
            len(data),
        )
        assert build_index(store, cache, FakeEmbedder(), out).built is True

    def test_manifest_records_the_model_and_weights(self, setup):
        store, cache, out = setup
        build_index(store, cache, FakeEmbedder(), out)
        manifest = EmbeddingIndex.load(out).manifest
        assert manifest["model_id"] == "fake/v1"
        assert manifest["weights_hash"] == "0" * 12
        assert manifest["index_type"] == "faiss.IndexFlatIP"
        assert manifest["count"] == 5
