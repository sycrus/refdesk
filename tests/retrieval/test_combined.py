"""Combined retriever: attributes plus embedding similarity in one weighted score (issue #34,
FR-3). Hand-made vectors and records, so each expected score can be checked by eye."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from refdesk.embeddings import EmbeddingIndex
from refdesk.retrieval import Query, Retriever
from refdesk.retrieval.clip import EmbeddingRetriever
from refdesk.retrieval.combined import CombinedConfig, CombinedRetriever, load_config
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 12, tzinfo=UTC)


def rec(object_id, tag, year, status=RightsStatus.OPEN):
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
        subject_tags=(tag,),
        date_begin=year,
        date_end=year,
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


# Attributes per record: tag, classification:painting, century.
RECORDS = [
    rec("1", "Boats", 1650),  # 0°, 17th century
    rec("2", "Boats", 1850),  # 30°, 19th century
    rec("3", "Flowers", 1650),  # 60°, 17th century
    rec("4", "Boats", None),  # 90°, no date
    # No image vector: images are cached only for open works.
    rec("5", "Boats", 1650, RightsStatus.PERMISSION_REQUIRED),
]
ANGLES = {"met:1": 0, "met:2": 30, "met:3": 60, "met:4": 90}
VECTORS = np.array(
    [[np.cos(np.radians(a)), np.sin(np.radians(a))] for a in ANGLES.values()], dtype=np.float32
)


class AxisEmbedder:
    """Text 'x' points along the x axis, anything else along the y axis."""

    model_id, weights_hash = "fake/axis", "0"

    def embed_texts(self, texts):
        return np.array([[1.0, 0.0] if t == "x" else [0.0, 1.0] for t in texts], dtype=np.float32)

    def embed_images(self, paths):
        raise AssertionError("not used")


def index():
    return EmbeddingIndex(list(ANGLES), VECTORS)


def retriever(similarity=0.6, attributes=0.4, **conditions):
    config = CombinedConfig(
        weights={"similarity": similarity, "attributes": attributes}, conditions=conditions
    )
    return CombinedRetriever(RECORDS, index(), AxisEmbedder(), config)


def ids(hits):
    return [h.record_id for h in hits]


def by_id(hits):
    return {h.record_id: h for h in hits}


def test_satisfies_the_retrieval_interface():
    assert isinstance(retriever(), Retriever)


QUERIES = [
    Query(brief="x"),
    Query(brief="boats"),
    Query(brief="x", conditions={"period": "17th century"}),
    Query(anchor_id="met:2"),
    Query(anchor_id="met:5"),
]


@pytest.mark.parametrize("query", QUERIES)
def test_each_hit_explanation_sums_to_its_score(query):
    hits = retriever().search(query)
    assert hits
    for hit in hits:
        assert [name for name, _ in hit.components] == ["similarity", "attributes"]
        assert sum(value for _, value in hit.components) == pytest.approx(hit.score)


def test_components_are_weight_times_signal():
    # met:3 at 60° for query 'x': cosine 0.5. Query attributes {century:17};
    # met:3 has {tag:flower, classification:painting, century:17}: Jaccard 1/3.
    hit = by_id(retriever().search(Query(brief="x", conditions={"period": "1650"})))["met:3"]
    assert dict(hit.components) == pytest.approx({"similarity": 0.6 * 0.5, "attributes": 0.4 / 3})
    assert "century:17" in hit.matched
    assert "clip_cosine:0.500" in hit.matched


def test_similarity_only_weights_reproduce_the_clip_ranking():
    query = Query(brief="x")
    clip = EmbeddingRetriever(RECORDS, index(), AxisEmbedder()).search(query)
    assert ids(retriever(similarity=1, attributes=0).search(query)) == ids(clip)


def test_attribute_only_weights_reproduce_the_jaccard_scores():
    query = Query(brief="boats", conditions={"period": "17th century"})
    jaccard = {h.record_id: h.score for h in JaccardRetriever(RECORDS).search(query)}
    combined = {
        h.record_id: h.score
        for h in retriever(similarity=0, attributes=1).search(query)
        if h.record_id in jaccard
    }
    assert combined == pytest.approx(jaccard)


def test_a_boost_condition_raises_matching_records_but_keeps_the_rest():
    hits = by_id(retriever(period="boost").search(Query(brief="x", conditions={"period": "1650"})))
    assert dict(hits["met:3"].components)["attributes"] > 0
    assert dict(hits["met:2"].components)["attributes"] == 0
    assert "met:2" in hits  # 19th century, but still a candidate on similarity


def test_boost_is_the_default_mode():
    query = Query(brief="x", conditions={"period": "1650"})
    assert ids(retriever().search(query)) == ids(retriever(period="boost").search(query))


def test_a_filter_condition_drops_records_without_it():
    hits = retriever(period="filter").search(Query(brief="x", conditions={"period": "1650"}))
    # met:2 is 19th century; met:4 has no date, so it cannot be shown to match.
    assert set(ids(hits)) == {"met:1", "met:3", "met:5"}


def test_a_filter_condition_does_not_also_add_to_the_attribute_score():
    hits = retriever(period="filter").search(Query(brief="x", conditions={"period": "1650"}))
    for hit in hits:
        assert dict(hit.components)["attributes"] == 0
        assert "filter:century:17" in hit.matched  # the filter is still shown as evidence


def test_records_without_an_image_vector_compete_on_attributes_only():
    hit = by_id(retriever().search(Query(brief="x boats")))["met:5"]
    assert dict(hit.components)["similarity"] == 0
    assert "no image vector" in hit.matched


def test_records_without_a_vector_or_shared_attributes_are_not_returned():
    assert "met:5" not in ids(retriever().search(Query(brief="x")))


def test_an_anchor_without_an_image_vector_uses_its_attributes():
    hits = retriever().search(Query(anchor_id="met:5"))
    assert hits and all(dict(h.components)["similarity"] == 0 for h in hits)
    assert "met:5" not in ids(hits)


def test_unknown_anchor_is_an_error():
    with pytest.raises(KeyError):
        retriever().search(Query(anchor_id="met:404"))


def test_avoid_and_k_apply():
    assert "met:2" not in ids(retriever().search(Query(brief="x", avoid=["met:2"])))
    assert len(retriever().search(Query(brief="x", k=2))) == 2


def test_empty_query_returns_nothing():
    assert retriever().search(Query()) == []


def test_ranking_is_by_score_then_record_id():
    hits = retriever().search(Query(brief="boats"))
    assert hits == sorted(hits, key=lambda h: (-round(h.score, 6), h.record_id))


@pytest.mark.parametrize(
    "bad",
    [
        {"weights": {"similarity": -0.1, "attributes": 1}},
        {"weights": {"similarity": 0, "attributes": 0}},
        {"weights": {"similarity": 0.5}},
        {"weights": {"similarity": 0.5, "attributes": 0.5}, "conditions": {"period": "maybe"}},
        {"weights": {"similarity": 0.5, "attributes": 0.5}, "conditions": {"colour": "boost"}},
    ],
)
def test_invalid_config_is_rejected(bad):
    with pytest.raises(ValueError):
        CombinedConfig(**bad)


def test_repo_config_loads():
    config = load_config(Path("config/retrieval.yaml"))
    assert config.weights == {"similarity": 0.6, "attributes": 0.4}
    assert set(config.conditions.values()) <= {"boost", "filter"}
