"""Verifier stage 1: plain-code checks of claims against the record (issue #96; ADR-022;
FR-2, FR-5, FR-6; acceptance scenario 6)."""

from datetime import UTC, datetime

import pytest

from refdesk.rationale import Claim, Rationale
from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus
from refdesk.verifier import JudgeVerdict, check_claims, item_status
from refdesk.wording import AttributionStatus


def record(**overrides):
    rights = RightsRecord(
        source="met", object_id="1", flag_field="isPublicDomain", flag_value=True,
        licence_string=None, checked_at=datetime(2026, 10, 27, tzinfo=UTC),
        status=RightsStatus.OPEN,
    )  # fmt: skip
    fields = dict(
        id="met:1", source="met", object_id="1", title="Still Life with Flowers",
        artist="Workshop of Jan van Huysum", date="ca. 1720", date_begin=1715, date_end=1725,
        medium="Oil on canvas", classification="Paintings",
        subject_tags=("Flowers", "Still Life"), raw_record_ref="met/objects/1.json",
        rights=rights,
    )  # fmt: skip
    return ArtworkRecord(**(fields | overrides))


def rationale(*claims):
    return Rationale(
        claims=tuple(Claim(field=f, value=v, text=t) for f, v, t in claims),
        fit="Its dark ground suits a luxury tin.",
    )


GOOD = rationale(
    ("artist", "Workshop of Jan van Huysum", "It is from the workshop of Jan van Huysum."),
    ("date", "ca. 1720", "It was painted around 1720."),
    ("medium", "Oil on canvas", "It is oil on canvas."),
    ("subject_tags", "Flowers", "Its subjects include flowers."),
)


class TestClaims:
    def test_correct_claims_pass(self):
        result = check_claims(GOOD, record())
        assert result.passed, result.failures
        assert [c.status for c in result.checks] == ["pass"] * 4

    @pytest.mark.parametrize(
        ("claim", "reason"),
        [
            (("medium", "Oil on wood", "It is oil on wood."), "medium"),
            (("subject_tags", "Tulips", "Its subjects include tulips."), "subject"),
            (("date", "1680", "It was painted in 1680."), "outside"),
            (("date_begin", "1700", "It was begun in 1700."), "date_begin"),
            (("classification", "Drawings", "It is a drawing."), "classification"),
            (("title", "Flowers in a Vase", "It is titled Flowers in a Vase."), "title"),
        ],
    )
    def test_a_wrong_value_fails_and_names_the_claim(self, claim, reason):
        result = check_claims(rationale(claim), record())
        assert not result.passed
        assert "claim 1" in result.failures[0] and reason in result.failures[0]

    def test_values_may_differ_in_case_and_spacing(self):
        r = rationale(
            ("medium", "oil  on canvas", "Oil on canvas."),
            ("classification", "Painting", "A painting."),
            ("subject_tags", "still life", "A still life."),
        )
        assert check_claims(r, record()).passed

    def test_a_date_inside_the_record_range_passes(self):
        r = rationale(("date", "1718", "It was painted in 1718."))
        assert check_claims(r, record()).passed
        r = rationale(("date", "1700-1730", "Painted between 1700 and 1730."))
        assert not check_claims(r, record()).passed  # wider than the record says

    def test_a_claim_on_a_field_the_record_leaves_empty_fails(self):
        r = rationale(("date", "ca. 1720", "It was painted around 1720."))
        result = check_claims(r, record(date=None, date_begin=None, date_end=None))
        assert not result.passed and "no date" in result.failures[0]


class TestAttribution:
    def test_a_dropped_prefix_in_the_value_fails(self):
        r = rationale(("artist", "Jan van Huysum", "It is by Jan van Huysum."))
        result = check_claims(r, record())
        assert not result.passed and "attribution" in result.failures[0]

    def test_a_dropped_prefix_in_the_text_fails_even_with_the_right_value(self):
        # The text is what the operator reads.
        r = rationale(("artist", "Workshop of Jan van Huysum", "It is by Jan van Huysum."))
        result = check_claims(r, record())
        assert not result.passed and "text" in result.failures[0]

    def test_a_record_with_no_artist_needs_a_human_check(self):
        result = check_claims(rationale(("medium", "Oil on canvas", "Oil.")), record(artist=None))
        assert not result.passed and "no attribution" in result.failures[0]


class TestRights:
    def test_rights_must_come_from_a_structured_source_field(self):
        no_field = record().rights.model_copy(
            update={"flag_field": None, "flag_value": None, "status": RightsStatus.UNVERIFIED}
        )
        result = check_claims(GOOD, record(rights=no_field))
        assert not result.passed and "rights" in result.failures[0]


class TestItemStatus:
    """Scenario 6: an item failing any check never has a verified badge."""

    def test_verified_only_when_code_and_judge_both_pass(self):
        code = check_claims(GOOD, record())
        judged = JudgeVerdict(passed=True, failures=())
        assert item_status(code, judged) is AttributionStatus.VERIFIED

    def test_never_verified_without_a_judge_verdict(self):
        assert (
            item_status(check_claims(GOOD, record()), None) is AttributionStatus.NEEDS_HUMAN_CHECK
        )

    def test_never_verified_when_code_fails(self):
        code = check_claims(rationale(("medium", "Oil on wood", "Oil on wood.")), record())
        judged = JudgeVerdict(passed=True, failures=())
        assert item_status(code, judged) is AttributionStatus.NEEDS_HUMAN_CHECK

    def test_never_verified_when_the_judge_fails(self):
        code = check_claims(GOOD, record())
        judged = JudgeVerdict(passed=False, failures=("claim 2: unsupported",))
        assert item_status(code, judged) is AttributionStatus.NEEDS_HUMAN_CHECK

    def test_never_verified_without_a_rationale(self):
        assert item_status(None, None) is AttributionStatus.NEEDS_HUMAN_CHECK
