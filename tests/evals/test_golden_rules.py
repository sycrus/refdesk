"""Rules that derive golden-v0 expected references from the corpus (ADR-018)."""

from datetime import UTC, datetime

import pytest

from refdesk.evals.golden import RuleError, apply_rule, corpus_version
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 11, tzinfo=UTC)


def rec(
    object_id,
    *,
    tags=(),
    begin=None,
    title=None,
    artist=None,
    cls="Paintings",
    medium=None,
    status=RightsStatus.OPEN,
):
    flag = status is not RightsStatus.UNVERIFIED
    rights = RightsRecord(
        source="met",
        object_id=object_id,
        flag_field="isPublicDomain" if flag else None,
        flag_value=(status is RightsStatus.OPEN) if flag else None,
        licence_string=None,
        checked_at=CHECKED,
        status=status,
    )
    return ArtworkRecord(
        id=f"met:{object_id}",
        source="met",
        object_id=object_id,
        title=title,
        artist=artist,
        medium=medium,
        classification=cls,
        subject_tags=tuple(tags),
        date_begin=begin,
        date_end=begin,
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


CORPUS = [
    rec("1", tags=["Still Life", "Flowers"], begin=1650, title="Flowers in a Vase"),
    rec("2", tags=["Still Life", "Fruit"], begin=1660),
    rec("3", tags=["Flowers"], begin=1880, artist="Vincent van Gogh"),
    rec("4", tags=["Women"], begin=1790, cls="Miniatures", status=RightsStatus.PERMISSION_REQUIRED),
    rec(
        "5", tags=["Boats", "Night"], begin=1830, title="Harbour by Moonlight", medium="Oil on wood"
    ),
]


def ids(rule):
    return apply_rule(rule, CORPUS)


class TestApplyRule:
    def test_tags_all(self):
        assert ids({"tags_all": ["Still Life", "Flowers"]}) == ["met:1"]

    def test_tags_any(self):
        assert ids({"tags_any": ["Fruit", "Night"]}) == ["met:2", "met:5"]

    def test_tags_are_matched_case_insensitively(self):
        assert ids({"tags_all": ["still life", "FLOWERS"]}) == ["met:1"]

    def test_century_uses_the_structured_begin_year(self):
        assert ids({"century": 17}) == ["met:1", "met:2"]

    def test_year_range(self):
        assert ids({"year_range": [1785, 1835]}) == ["met:4", "met:5"]

    def test_title_any_matches_whole_words(self):
        assert ids({"title_any": ["moonlight"]}) == ["met:5"]
        assert ids({"title_any": ["moon"]}) == []

    def test_artist_contains(self):
        assert ids({"artist_contains": "gogh"}) == ["met:3"]

    def test_artist_excludes(self):
        assert ids({"tags_any": ["Flowers"], "artist_excludes": "gogh"}) == ["met:1"]

    def test_classification(self):
        assert ids({"classification": ["Miniatures"]}) == ["met:4"]

    def test_medium_any(self):
        assert ids({"medium_any": ["wood"]}) == ["met:5"]

    def test_rights_open_only(self):
        assert ids({"tags_any": ["Women", "Night"], "rights": "open"}) == ["met:5"]

    def test_exclude_ids(self):
        assert ids({"tags_any": ["Flowers"], "exclude_ids": ["met:1"]}) == ["met:3"]

    def test_clauses_combine_with_and(self):
        assert ids({"tags_any": ["Flowers", "Fruit"], "century": 17}) == ["met:1", "met:2"]

    def test_unknown_clause_is_an_error(self):
        with pytest.raises(RuleError, match="unknown"):
            ids({"tag": ["Flowers"]})

    def test_empty_rule_is_an_error(self):
        with pytest.raises(RuleError):
            ids({})


class TestCorpusVersion:
    def test_depends_on_the_set_of_ids_not_their_order(self):
        assert corpus_version(CORPUS) == corpus_version(list(reversed(CORPUS)))

    def test_changes_when_the_corpus_changes(self):
        assert corpus_version(CORPUS) != corpus_version(CORPUS[:-1])

    def test_names_source_and_count(self):
        assert corpus_version(CORPUS).startswith("met:5:")
