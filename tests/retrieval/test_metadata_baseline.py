"""Metadata-only baseline (FR-4): Jaccard over attribute sets, behind the retrieval interface."""

import random
from datetime import UTC, datetime

import pytest

from refdesk.retrieval import Hit, Query, Retriever
from refdesk.retrieval.metadata import JaccardRetriever, attributes, normalise
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 11, tzinfo=UTC)


def rec(object_id, *, title=None, artist=None, date=None, medium=None, tags=(), cls="Paintings"):
    rights = RightsRecord(
        source="met",
        object_id=object_id,
        flag_field="isPublicDomain",
        flag_value=True,
        licence_string=None,
        checked_at=CHECKED,
        status=RightsStatus.OPEN,
    )
    return ArtworkRecord(
        id=f"met:{object_id}",
        source="met",
        object_id=object_id,
        title=title,
        artist=artist,
        date=date,
        medium=medium,
        classification=cls,
        subject_tags=tuple(tags),
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


# A small fixed corpus. Values are written like Met records, but these are test data.
CORPUS = [
    rec(
        "1",
        title="Wheat Field with Cypresses",
        artist="Vincent van Gogh",
        date="1889",
        medium="Oil on canvas",
        tags=["Landscapes", "Cypresses", "Wheat"],
    ),
    rec(
        "2",
        title="Cypresses",
        artist="Vincent van Gogh",
        date="1889",
        medium="Oil on canvas",
        tags=["Cypresses", "Trees"],
    ),
    rec(
        "3",
        title="Moonlit Harbour",
        artist="Unknown",
        date="ca. 1650",
        medium="Oil on wood",
        tags=["Boats", "Moon", "Night"],
    ),
    rec(
        "4",
        title="Orchard in Blossom",
        artist="Claude Monet",
        date="1879",
        medium="Oil on canvas",
        tags=["Landscapes", "Trees", "Flowers"],
    ),
    rec(
        "5",
        title="Portrait Miniature",
        artist=None,
        date="1790s",
        medium="Watercolor on ivory",
        tags=["Portraits", "Women"],
        cls="Miniatures",
    ),
]

FIXED_QUERY = Query(brief="A landscape with cypresses and trees", k=5)


class TestInterface:
    def test_jaccard_retriever_satisfies_the_retrieval_interface(self):
        assert isinstance(JaccardRetriever(CORPUS), Retriever)

    def test_hits_explain_what_matched(self):
        [top, *_] = JaccardRetriever(CORPUS).search(FIXED_QUERY)
        assert isinstance(top, Hit)
        assert top.matched  # evidence: the attributes shared with the query
        assert all(a in attributes(CORPUS[0]) | attributes(CORPUS[1]) for a in top.matched)


class TestAttributes:
    def test_record_attributes_are_named_by_source_field(self):
        attrs = attributes(CORPUS[0])
        assert {"tag:landscape", "tag:cypress", "medium:oil", "medium:canvas"} <= attrs
        assert "artist:vincent van gogh" in attrs
        assert "century:19" in attrs
        assert "classification:painting" in attrs

    def test_missing_fields_add_nothing(self):
        assert not any(a.startswith("artist:") for a in attributes(CORPUS[4]))

    @pytest.mark.parametrize(
        ("date", "century"),
        [("1889", "19"), ("ca. 1650", "17"), ("1790s", "18"), ("1520–25", "16")],
    )
    def test_century_is_read_from_the_date_string(self, date, century):
        assert f"century:{century}" in attributes(rec("9", date=date))

    def test_unparseable_date_gives_no_century(self):
        assert not any(a.startswith("century:") for a in attributes(rec("9", date="undated")))

    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("Cypresses", "cypress"),
            ("landscapes", "landscape"),
            ("Lilies", "lily"),
            ("trees", "tree"),
            ("glass", "glass"),
            ("canvas", "canvas"),
        ],
    )
    def test_normalise(self, word, expected):
        assert normalise(word) == expected


class TestRanking:
    def test_fixed_example_query_returns_a_stable_ranking(self):
        hits = JaccardRetriever(CORPUS).search(FIXED_QUERY)
        assert [h.record_id for h in hits] == ["met:2", "met:1", "met:4"]

    def test_ranking_does_not_depend_on_corpus_order(self):
        expected = [h.record_id for h in JaccardRetriever(CORPUS).search(FIXED_QUERY)]
        shuffled = CORPUS[:]
        for seed in range(5):
            random.Random(seed).shuffle(shuffled)
            assert [h.record_id for h in JaccardRetriever(shuffled).search(FIXED_QUERY)] == expected

    def test_scores_are_jaccard(self):
        hits = {h.record_id: h for h in JaccardRetriever(CORPUS).search(FIXED_QUERY)}
        hit = hits["met:2"]
        assert hit.score == pytest.approx(len(hit.matched) / hit.union_size)

    def test_no_overlap_means_no_hit(self):
        assert JaccardRetriever(CORPUS).search(Query(brief="zeppelin")) == []

    def test_k_limits_results(self):
        assert len(JaccardRetriever(CORPUS).search(Query(brief="oil canvas", k=2))) == 2


class TestConditionsAnchorAvoid:
    def test_conditions_add_named_attributes(self):
        query = Query(brief="harbour", conditions={"material": "wood"})
        [top] = JaccardRetriever(CORPUS).search(query)
        assert top.record_id == "met:3"
        assert "medium:wood" in top.matched

    def test_anchor_uses_the_anchor_records_attributes_and_excludes_it(self):
        hits = JaccardRetriever(CORPUS).search(Query(anchor_id="met:1"))
        assert hits[0].record_id == "met:2"  # same artist, date, medium, cypresses
        assert "met:1" not in [h.record_id for h in hits]

    def test_unknown_anchor_is_an_error(self):
        with pytest.raises(KeyError):
            JaccardRetriever(CORPUS).search(Query(anchor_id="met:404"))

    def test_avoid_excludes_records_by_id_or_matching_term(self):
        query = Query(brief="landscape trees cypresses", avoid=["met:2", "Monet"])
        ids = [h.record_id for h in JaccardRetriever(CORPUS).search(query)]
        assert ids == ["met:1"]


class TestConditionMapping:
    @pytest.mark.parametrize(
        ("conditions", "expected"),
        [
            ({"material": "Oil on wood"}, {"medium:oil", "medium:wood"}),
            ({"motif": "Cypresses"}, {"tag:cypress"}),
            ({"department": "Miniatures"}, {"classification:miniature"}),
            ({"period": "17th century"}, {"century:17"}),
            ({"period": "1650"}, {"century:17"}),
        ],
    )
    def test_each_condition_becomes_its_named_attribute(self, conditions, expected):
        retriever = JaccardRetriever(CORPUS)
        assert retriever.query_attributes(Query(conditions=conditions)) == expected
