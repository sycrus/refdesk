"""CLIP embedding retriever: the off-the-shelf similarity baseline (issue #33, FR-4).

Uses hand-made vectors, so the expected rankings can be checked by eye and CI needs no
torch."""

from datetime import UTC, datetime

import numpy as np
import pytest

from refdesk.embeddings import EmbeddingIndex
from refdesk.retrieval import Query, Retriever
from refdesk.retrieval.clip import EmbeddingRetriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 12, tzinfo=UTC)


def rec(object_id, artist=None, status=RightsStatus.OPEN):
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
        artist=artist,
        classification="Paintings",
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


RECORDS = [rec("1", "Claude Monet"), rec("2"), rec("3"), rec("4")]
# 2-D vectors at known angles from the x axis: 1 at 0°, 2 at 30°, 3 at 60°, 4 at 90°.
ANGLES = {"met:1": 0, "met:2": 30, "met:3": 60, "met:4": 90}
VECTORS = np.array(
    [[np.cos(np.radians(a)), np.sin(np.radians(a))] for a in ANGLES.values()], dtype=np.float32
)


class AxisEmbedder:
    """Text 'x' points along the x axis, 'y' along the y axis."""

    model_id, weights_hash = "fake/axis", "0"

    def embed_texts(self, texts):
        return np.array([[1.0, 0.0] if t == "x" else [0.0, 1.0] for t in texts], dtype=np.float32)

    def embed_images(self, paths):
        raise AssertionError("not used")


def retriever(records=RECORDS):
    return EmbeddingRetriever(records, EmbeddingIndex(list(ANGLES), VECTORS), AxisEmbedder())


def ids(query):
    return [h.record_id for h in retriever().search(query)]


def test_satisfies_the_retrieval_interface():
    assert isinstance(retriever(), Retriever)


def test_fixed_vector_ranking_by_cosine():
    # Query along x: cos 0° > cos 30° > cos 60° > cos 90°.
    assert ids(Query(brief="x")) == ["met:1", "met:2", "met:3", "met:4"]
    assert ids(Query(brief="y")) == ["met:4", "met:3", "met:2", "met:1"]


def test_scores_are_cosine_and_the_evidence_is_only_the_similarity():
    [top, *_] = retriever().search(Query(brief="x"))
    assert top.score == pytest.approx(1.0)
    assert top.matched == ("clip_cosine:1.000",)  # no invented attributes


def test_anchor_uses_the_anchor_image_and_excludes_it():
    # Anchor met:2 (30°): nearest are met:1 and met:3 (both 30° away), then met:4.
    assert ids(Query(anchor_id="met:2")) == ["met:1", "met:3", "met:4"]


def test_anchor_takes_precedence_over_the_brief():
    assert ids(Query(brief="y", anchor_id="met:1"))[0] == "met:2"


def test_unknown_anchor_is_an_error():
    with pytest.raises(KeyError):
        retriever().search(Query(anchor_id="met:404"))


def test_k_limits_results():
    assert len(retriever().search(Query(brief="x", k=2))) == 2


def test_avoid_by_id_and_by_term():
    assert ids(Query(brief="x", avoid=["met:2", "Monet"])) == ["met:3", "met:4"]


def test_conditions_are_ignored_by_this_baseline():
    assert ids(Query(brief="x", conditions={"period": "17th century"})) == ids(Query(brief="x"))


def test_records_without_an_image_vector_are_never_returned():
    # met:5 has no image (e.g. permission required): image similarity cannot rank it.
    records = RECORDS + [rec("5", status=RightsStatus.PERMISSION_REQUIRED)]
    assert "met:5" not in [h.record_id for h in retriever(records).search(Query(brief="x"))]


def test_empty_query_returns_nothing():
    assert retriever().search(Query()) == []
