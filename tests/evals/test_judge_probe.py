"""Judge probe: synthetic faithfulness items with known answers, and scoring."""

from datetime import UTC, datetime

import pytest

from refdesk.evals.judge_probe import (
    ERROR_TYPES,
    build_items,
    parse_verdict,
    record_document,
    score_judge,
)
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 12, tzinfo=UTC)
ARTISTS = ["Claude Monet", "Rembrandt van Rijn", "Johan Christian Dahl", "Rosa Bonheur"]


def rec(i):
    rights = RightsRecord(
        source="met",
        object_id=str(i),
        flag_field="isPublicDomain",
        flag_value=True,
        licence_string=None,
        checked_at=CHECKED,
        status=RightsStatus.OPEN,
    )
    return ArtworkRecord(
        id=f"met:{i}",
        source="met",
        object_id=str(i),
        title=f"Painting {i}",
        artist=ARTISTS[i % len(ARTISTS)],
        date=str(1800 + i),
        date_begin=1800 + i,
        date_end=1800 + i,
        medium="Oil on canvas",
        classification="Paintings",
        subject_tags=("Boats", "Night"),
        raw_record_ref=f"met/objects/{i}.json",
        rights=rights,
    )


RECORDS = [rec(i) for i in range(1, 41)]


@pytest.fixture(scope="module")
def items():
    return build_items(RECORDS, n_records=20, seed=0)


class TestItems:
    def test_half_faithful_half_corrupted(self, items):
        labels = [i.label for i in items]
        assert labels.count("supported") == labels.count("unsupported") == 20

    def test_every_error_type_is_used_equally(self, items):
        types = [i.error_type for i in items if i.label == "unsupported"]
        assert {t: types.count(t) for t in ERROR_TYPES} == {t: 4 for t in ERROR_TYPES}

    def test_faithful_rationales_only_state_record_facts(self, items):
        for item in items:
            if item.label == "supported":
                r = next(x for x in RECORDS if x.id == item.record_id)
                assert r.title in item.rationale and r.artist in item.rationale
                assert r.date in item.rationale and r.medium.lower() in item.rationale.lower()

    def test_each_corruption_changes_exactly_the_named_fact(self, items):
        for item in items:
            if item.label != "unsupported":
                continue
            r = next(x for x in RECORDS if x.id == item.record_id)
            if item.error_type == "wrong_date":
                assert r.date not in item.rationale
            if item.error_type == "wrong_artist":
                assert r.artist not in item.rationale
                assert any(a in item.rationale for a in ARTISTS)
            if item.error_type == "wrong_medium":
                assert r.medium.lower() not in item.rationale.lower()
            if item.error_type == "invented_provenance":
                assert "belonged to" in item.rationale
            if item.error_type == "invented_subject":
                assert all(t.lower() not in item.rationale.lower() for t in r.subject_tags)

    def test_the_document_lists_the_record_fields(self):
        doc = record_document(RECORDS[0])
        for field in (
            "Title: Painting 1",
            "Artist:",
            "Date: 1801",
            "Medium: Oil on canvas",
            "Subjects: Boats, Night",
        ):
            assert field in doc

    def test_deterministic(self):
        assert build_items(RECORDS, n_records=20, seed=0) == build_items(
            RECORDS, n_records=20, seed=0
        )


class TestParseVerdict:
    @pytest.mark.parametrize(
        ("text", "verdict"),
        [
            ("SUPPORTED", "supported"),
            ("Unsupported.", "unsupported"),
            ("**UNSUPPORTED** - the date is wrong", "unsupported"),
            ("Yes", "supported"),
            ("No", "unsupported"),
            ("I think it is fine", None),
            ("", None),
        ],
    )
    def test_parse(self, text, verdict):
        assert parse_verdict(text) == verdict


class TestScoring:
    def test_hand_computed_scores(self, items):
        # A judge that says "supported" for everything.
        result = score_judge(items, ["supported"] * len(items), seed=0)
        assert result.accuracy == pytest.approx(0.5)
        assert result.catch_rate == 0.0
        assert result.false_alarm_rate == 0.0
        assert result.invalid_rate == 0.0

    def test_invalid_outputs_count_as_wrong_and_are_reported(self, items):
        result = score_judge(items, [None] * len(items), seed=0)
        assert result.accuracy == 0.0 and result.invalid_rate == 1.0

    def test_catch_rate_per_error_type(self, items):
        preds = ["unsupported" if i.error_type == "wrong_date" else "supported" for i in items]
        result = score_judge(items, preds, seed=0)
        assert result.catch_by_type["wrong_date"] == 1.0
        assert result.catch_by_type["invented_subject"] == 0.0


class TestClaims:
    """Factual claims, split exactly, for claim-checker models (MiniCheck, Granite Guardian)."""

    def test_faithful_items_have_only_record_facts_as_claims(self, items):
        for item in items:
            if item.label == "supported":
                r = next(x for x in RECORDS if x.id == item.record_id)
                assert any(r.artist in c and r.date in c for c in item.claims)
                assert all("calm" not in c and "mood" not in c for c in item.claims)  # no opinion

    def test_corrupted_items_carry_the_false_fact_in_a_claim(self, items):
        for item in items:
            if item.error_type == "invented_provenance":
                assert any("belonged to" in c for c in item.claims)
            if item.error_type == "invented_subject":
                assert any(
                    s in " ".join(item.claims)
                    for s in ("lighthouse", "balloon", "locomotive", "windmill")
                )
