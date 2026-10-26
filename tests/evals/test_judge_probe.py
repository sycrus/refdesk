"""Judge probe: synthetic faithfulness items with known answers, and scoring."""

import re
from datetime import UTC, datetime

import pytest

from refdesk.evals.judge_probe import (
    ERROR_TYPES,
    HARD_ERROR_TYPES,
    OPINIONS,
    build_hard_items,
    build_items,
    hard_document,
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


# --- Hard set (issue #122): multi-claim, paraphrased, subtle errors -------------------

PREFIXES = ["Workshop of", "Attributed to", "Style of", "Follower of"]
SUBJECTS = [("Flowers", "Still Life"), ("Dogs",), ("Horses", "Landscapes"), ("Men", "Portraits")]


def hard_rec(i):
    base = rec(i)
    prefix = PREFIXES[i % len(PREFIXES)]
    return base.model_copy(
        update={
            "artist": f"{prefix} {ARTISTS[i % len(ARTISTS)]}" if i % 2 else ARTISTS[i % 4],
            "date": f"ca. {1640 + i}" if i % 3 else None,
            "date_begin": 1640 + i,
            "date_end": 1645 + i,
            "medium": "Oil on wood" if i % 2 else "Oil on canvas",
            "subject_tags": SUBJECTS[i % len(SUBJECTS)],
        }
    )


HARD_RECORDS = [hard_rec(i) for i in range(1, 81)]


@pytest.fixture(scope="module")
def hard_items():
    return build_hard_items(HARD_RECORDS, n_per_type=5, seed=0)


def _pairs(items):
    by_id = {i.id: i for i in items}
    return [(by_id[i.id[:-1] + "a"], i) for i in items if i.label == "unsupported"]


def _changed(good, bad):
    diff = [(g, b) for g, b in zip(good.claims, bad.claims, strict=True) if g != b]
    assert len(diff) == 1, (good.claims, bad.claims)
    return diff[0]


class TestHardItems:
    def test_balanced_labels_and_every_hard_error_type(self, hard_items):
        labels = [i.label for i in hard_items]
        assert labels.count("supported") == labels.count("unsupported") == 20
        types = [i.error_type for i in hard_items if i.label == "unsupported"]
        assert {t: types.count(t) for t in HARD_ERROR_TYPES} == {t: 5 for t in HARD_ERROR_TYPES}

    def test_each_corruption_changes_exactly_one_claim(self, hard_items):
        for good, bad in _pairs(hard_items):
            assert len(good.claims) == len(bad.claims) == 5
            _changed(good, bad)

    def test_rationale_is_the_claims_plus_an_opinion(self, hard_items):
        for item in hard_items:
            for claim in item.claims:
                assert claim in item.rationale
            assert any(o in item.rationale for o in OPINIONS)

    def test_the_false_claim_is_not_always_in_the_same_place(self, hard_items):
        positions = set()
        for good, bad in _pairs(hard_items):
            g, _ = _changed(good, bad)
            positions.add(good.claims.index(g))
        assert len(positions) > 2

    def test_near_dates_fall_just_outside_the_record_range(self, hard_items):
        for good, bad in _pairs(hard_items):
            if bad.error_type != "near_date":
                continue
            r = next(x for x in HARD_RECORDS if x.id == bad.record_id)
            _, claim = _changed(good, bad)
            year = int(re.search(r"\d{4}", claim).group(0))
            assert not r.date_begin <= year <= r.date_end
            assert min(abs(year - r.date_begin), abs(year - r.date_end)) <= 40

    def test_dropped_prefix_states_the_master_as_the_artist(self, hard_items):
        for good, bad in _pairs(hard_items):
            if bad.error_type != "dropped_prefix":
                continue
            r = next(x for x in HARD_RECORDS if x.id == bad.record_id)
            prefix, master = next(
                (p, r.artist[len(p) + 1 :]) for p in PREFIXES if r.artist.startswith(p)
            )
            g, b = _changed(good, bad)
            assert master in b and prefix.lower() not in b.lower()
            assert master in g and prefix.split()[0].lower() in g.lower()

    def test_overspecific_subject_is_not_a_record_tag(self, hard_items):
        for good, bad in _pairs(hard_items):
            if bad.error_type != "overspecific_subject":
                continue
            r = next(x for x in HARD_RECORDS if x.id == bad.record_id)
            _, b = _changed(good, bad)
            assert all(t.lower() not in b.lower() for t in r.subject_tags)

    def test_near_medium_swaps_the_support(self, hard_items):
        for good, bad in _pairs(hard_items):
            if bad.error_type != "near_medium":
                continue
            r = next(x for x in HARD_RECORDS if x.id == bad.record_id)
            _, b = _changed(good, bad)
            wrong = "canvas" if "wood" in r.medium.lower() else "wood"
            assert wrong in b.lower()

    def test_faithful_items_are_paraphrased_not_copied(self, hard_items):
        for item in hard_items:
            if item.label == "supported":
                r = next(x for x in HARD_RECORDS if x.id == item.record_id)
                assert r.medium not in item.rationale  # e.g. "an oil painting on canvas"
                assert "oil painting on" in item.rationale

    def test_the_document_gives_the_structured_years(self):
        doc = hard_document(HARD_RECORDS[0])
        assert "Years: 1641 to 1646" in doc and "Artist:" in doc

    def test_deterministic(self):
        assert build_hard_items(HARD_RECORDS, n_per_type=5, seed=0) == build_hard_items(
            HARD_RECORDS, n_per_type=5, seed=0
        )

    def test_refuses_when_too_few_eligible_records(self):
        with pytest.raises(ValueError, match="dropped_prefix"):
            build_hard_items([hard_rec(2), hard_rec(4)], n_per_type=1, seed=0)

    def test_scores_report_hard_error_types(self, hard_items):
        preds = [
            "unsupported" if i.error_type == "dropped_prefix" else "supported" for i in hard_items
        ]
        result = score_judge(hard_items, preds, seed=0)
        assert result.catch_by_type["dropped_prefix"] == 1.0
        assert result.catch_by_type["near_date"] == 0.0
