"""Period conditions: written forms of a century, BCE dates, and filters that cannot be
applied (issue #63). A filter that is silently dropped makes results look filtered when
they are not, so it is an error; a boost stays lenient."""

from datetime import UTC, datetime

import numpy as np
import pytest

from refdesk.embeddings import EmbeddingIndex
from refdesk.retrieval import Query
from refdesk.retrieval.combined import CombinedConfig, CombinedRetriever, ConditionNotUnderstood
from refdesk.retrieval.metadata import attributes, condition_attributes
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "period",
    [
        "17th century",
        "17th-century",
        "17th c.",
        "17th c",
        "17th cent.",
        "17TH CENTURY",
        "1650",
        "c. 1650",
        "ca. 1650",
    ],
)
def test_written_forms_of_the_17th_century(period):
    assert condition_attributes("period", period) == {"century:17"}


@pytest.mark.parametrize(
    ("period", "century"),
    [
        ("500 BCE", "5bce"),
        ("500 BC", "5bce"),
        ("500 B.C.", "5bce"),
        ("450 BCE", "5bce"),
        ("401 BCE", "5bce"),
        ("5th century BC", "5bce"),
        ("5th century BCE", "5bce"),
        ("5th-century B.C.E.", "5bce"),
        ("1st century BCE", "1bce"),
    ],
)
def test_bce_dates_give_a_bce_century(period, century):
    assert condition_attributes("period", period) == {f"century:{century}"}


def test_a_bce_century_never_matches_the_ce_century_with_the_same_number():
    assert condition_attributes("period", "500 BCE") != condition_attributes(
        "period", "5th century"
    )
    assert condition_attributes("period", "500 BCE") != condition_attributes("period", "500")


@pytest.mark.parametrize("period", ["Baroque", "Edo period", "", "the olden days"])
def test_named_and_unknown_periods_give_nothing(period):
    # Named periods need a cited mapping (issue #64); until then they give no attribute.
    assert condition_attributes("period", period) == set()


def rec(object_id, date_begin=None, date=None, status=RightsStatus.OPEN):
    rights = RightsRecord(
        source="met",
        object_id=object_id,
        flag_field="isPublicDomain",
        flag_value=True,
        licence_string=None,
        checked_at=CHECKED,
        status=status,
    )
    return ArtworkRecord(
        id=f"met:{object_id}",
        source="met",
        object_id=object_id,
        classification="Vases",
        date=date,
        date_begin=date_begin,
        date_end=date_begin,
        raw_record_ref=f"met/objects/{object_id}.json",
        rights=rights,
    )


@pytest.mark.parametrize(
    ("record", "century"),
    [
        (rec("1", date_begin=-500), "century:5bce"),
        (rec("2", date_begin=-450), "century:5bce"),
        (rec("3", date_begin=-1), "century:1bce"),
        (rec("4", date_begin=1650), "century:17"),
        (rec("5", date="500 BCE"), "century:5bce"),
        (rec("6", date="5th century B.C."), "century:5bce"),
    ],
)
def test_records_get_their_century_including_bce(record, century):
    assert century in attributes(record)


def test_a_record_with_year_zero_gets_no_century():
    # There is no year 0; a source that gives it has no usable start year.
    assert not {a for a in attributes(rec("7", date_begin=0)) if a.startswith("century:")}


# Filters in the combined retriever.

RECORDS = [rec("1", date_begin=-500), rec("4", date_begin=1650), rec("8")]


class AlongX:
    model_id, weights_hash = "fake/x", "0"

    def embed_texts(self, texts):
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)

    def embed_images(self, paths):
        raise AssertionError("not used")


def combined(**modes):
    index = EmbeddingIndex([r.id for r in RECORDS], np.ones((len(RECORDS), 2), dtype=np.float32))
    config = CombinedConfig(weights={"similarity": 0.6, "attributes": 0.4}, conditions=modes)
    return CombinedRetriever(RECORDS, index, AlongX(), config)


def test_a_bce_filter_keeps_only_bce_works():
    hits = combined(period="filter").search(Query(brief="vase", conditions={"period": "500 BCE"}))
    assert [h.record_id for h in hits] == ["met:1"]


def test_a_filter_that_cannot_be_parsed_is_an_error_naming_the_value_and_formats():
    with pytest.raises(ConditionNotUnderstood) as error:
        combined(period="filter").search(Query(brief="vase", conditions={"period": "Baroque"}))
    message = str(error.value)
    assert "'Baroque'" in message
    assert "17th century" in message and "500 BCE" in message  # the accepted formats


def test_an_unparseable_boost_stays_lenient():
    hits = combined(period="boost").search(Query(brief="vase", conditions={"period": "Baroque"}))
    assert hits  # ranked on similarity; the boost simply adds nothing


def test_an_unknown_condition_field_is_an_error():
    with pytest.raises(ConditionNotUnderstood, match="colour"):
        combined().search(Query(brief="vase", conditions={"colour": "red"}))


def test_check_conditions_can_run_before_a_search():
    # The API checks a board's conditions when it is created, before any retriever loads.
    from refdesk.retrieval.combined import check_conditions

    config = CombinedConfig(
        weights={"similarity": 0.6, "attributes": 0.4}, conditions={"period": "filter"}
    )
    check_conditions({"period": "17th-century"}, config)  # fine
    with pytest.raises(ConditionNotUnderstood):
        check_conditions({"period": "Baroque"}, config)
