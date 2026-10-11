"""Normalised record schema (PRD FR-1) and the rights invariants it enforces (FR-2)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from refdesk.schema import ArtworkRecord, RightsRecord, RightsStatus

CHECKED = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


def rights(**overrides):
    fields = dict(
        source="met",
        object_id="436535",
        flag_field="isPublicDomain",
        flag_value=True,
        licence_string="CC0",
        checked_at=CHECKED,
        status=RightsStatus.OPEN,
    )
    return RightsRecord(**(fields | overrides))


def record(**overrides):
    fields = dict(
        id="met:436535",
        source="met",
        object_id="436535",
        title="Wheat Field with Cypresses",
        artist="Vincent van Gogh",
        date="1889",
        raw_record_ref="data/raw/met/436535.json",
        rights=rights(),
    )
    return ArtworkRecord(**(fields | overrides))


class TestFixedWording:
    def test_status_values_use_the_fixed_badge_wording(self):
        # PRD 8A and design/design-system.md: these labels are never paraphrased.
        assert RightsStatus.OPEN.value == "Open (as stated by source)"
        assert RightsStatus.UNVERIFIED.value == "Unverified"
        assert RightsStatus.PERMISSION_REQUIRED.value == "Permission required"


class TestArtworkRecord:
    def test_valid_record(self):
        assert record().rights.status is RightsStatus.OPEN

    def test_rejects_a_record_with_no_rights_record(self):
        fields = record().model_dump()
        del fields["rights"]
        with pytest.raises(ValidationError, match="rights"):
            ArtworkRecord(**fields)

    def test_rejects_rights_record_for_a_different_object(self):
        with pytest.raises(ValidationError, match="different object"):
            record(rights=rights(object_id="999"))

    def test_rejects_id_not_derived_from_source_and_object_id(self):
        with pytest.raises(ValidationError, match="id must be"):
            record(id="436535")

    def test_unknown_fields_are_rejected(self):
        with pytest.raises(ValidationError):
            record(provenance_guess="probably from a sale in 1902")

    def test_descriptive_fields_may_be_missing_rather_than_invented(self):
        # CLAUDE.md: never invent attributions or dates. Missing stays None.
        r = record(artist=None, date=None, title=None)
        assert r.artist is None and r.date is None

    def test_records_are_immutable(self):
        with pytest.raises(ValidationError):
            record().title = "changed"


class TestRightsInvariants:
    def test_open_requires_the_flag_field(self):
        with pytest.raises(ValidationError, match="structured source field"):
            rights(flag_field=None)

    def test_open_requires_a_flag_value(self):
        with pytest.raises(ValidationError, match="structured source field"):
            rights(flag_value=None)

    def test_unverified_needs_no_flag(self):
        r = rights(flag_field=None, flag_value=None, licence_string=None, status="Unverified")
        assert r.status is RightsStatus.UNVERIFIED

    def test_unverified_helper_for_unknown_rights(self):
        r = RightsRecord.unverified(source="met", object_id="1", checked_at=CHECKED)
        assert r.status is RightsStatus.UNVERIFIED
        assert r.flag_field is None and r.flag_value is None

    def test_checked_at_must_be_timezone_aware(self):
        with pytest.raises(ValidationError, match="timezone"):
            rights(checked_at=datetime(2026, 10, 11, 9, 0))

    def test_source_and_object_id_are_required(self):
        with pytest.raises(ValidationError):
            rights(source="")


class TestDateRange:
    def test_begin_and_end_years_are_optional(self):
        r = record()
        assert r.date_begin is None and r.date_end is None

    def test_begin_after_end_is_rejected(self):
        with pytest.raises(ValidationError, match="date_begin"):
            record(date_begin=1900, date_end=1800)

    def test_bce_years_are_allowed(self):
        assert record(date_begin=-500, date_end=-450).date_begin == -500
