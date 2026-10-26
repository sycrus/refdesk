"""Met adapter tests (add-museum-source skill): schema, rights, drift, rate limiting.

All tests use responses recorded by scripts/record_met_fixtures.py. Variants with a
missing or malformed flag are built from a real fixture in code, so it is clear which
field was changed and why.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from refdesk.schema import ArtworkRecord, RightsStatus
from refdesk.sources import met

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "met"
CHECKED = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def obj(name):
    return fixture(name)["body"]


OPEN = obj("object_436535_open_painting")
COPYRIGHT = obj("object_490190_copyright_notice")
COPYRIGHT_NO_NOTICE = obj("object_492759_copyright_no_notice")


class TestToRecord:
    def test_open_painting_maps_to_a_valid_record(self):
        r = met.to_record(OPEN, checked_at=CHECKED)
        assert isinstance(r, ArtworkRecord)
        assert r.id == "met:436535"
        assert r.title == "Wheat Field with Cypresses"
        assert r.artist == "Vincent van Gogh"
        assert r.date == "1889"
        assert r.classification == "Paintings"
        assert r.record_url == OPEN["objectURL"]
        assert r.raw_record_ref == "met/objects/436535.json"

    def test_empty_strings_become_none_not_placeholders(self):
        raw = copy.deepcopy(OPEN) | {"objectDate": "", "medium": ""}
        r = met.to_record(raw, checked_at=CHECKED)
        assert r.date is None and r.medium is None

    def test_attribution_qualifier_is_kept(self):
        # Dropping "Attributed to" would overstate the attribution (CLAUDE.md hard rule).
        raw = copy.deepcopy(OPEN) | {"artistPrefix": "Attributed to"}
        assert met.to_record(raw, checked_at=CHECKED).artist == "Attributed to Vincent van Gogh"

    def test_subject_tags_are_the_tag_terms(self):
        raw = copy.deepcopy(OPEN) | {"tags": [{"term": "Landscapes"}, {"term": "Trees"}]}
        assert met.to_record(raw, checked_at=CHECKED).subject_tags == ("Landscapes", "Trees")

    def test_credit_line_is_kept_verbatim(self):
        # Shown in S4 and the provenance pack as the source gives it (issue #99).
        r = met.to_record(OPEN, checked_at=CHECKED)
        assert r.credit_line == "Purchase, The Annenberg Foundation Gift, 1993"

    def test_an_empty_credit_line_is_none(self):
        raw = copy.deepcopy(OPEN) | {"creditLine": ""}
        assert met.to_record(raw, checked_at=CHECKED).credit_line is None

    def test_missing_tags_give_an_empty_tuple(self):
        raw = copy.deepcopy(OPEN) | {"tags": None}
        assert met.to_record(raw, checked_at=CHECKED).subject_tags == ()


class TestRights:
    def test_public_domain_flag_true_is_open(self):
        rights = met.to_record(OPEN, checked_at=CHECKED).rights
        assert rights.status is RightsStatus.OPEN
        assert rights.flag_field == "isPublicDomain"
        assert rights.flag_value is True
        assert rights.checked_at == CHECKED

    def test_only_objects_with_the_open_flag_are_marked_open(self):
        statuses = {
            name: met.to_record(o, checked_at=CHECKED).rights.status
            for name, o in [("open", OPEN), ("c1", COPYRIGHT), ("c2", COPYRIGHT_NO_NOTICE)]
        }
        assert statuses == {
            "open": RightsStatus.OPEN,
            "c1": RightsStatus.PERMISSION_REQUIRED,
            "c2": RightsStatus.PERMISSION_REQUIRED,
        }

    def test_copyright_notice_is_kept_as_the_licence_string(self):
        rights = met.to_record(COPYRIGHT, checked_at=CHECKED).rights
        assert rights.licence_string == COPYRIGHT["rightsAndReproduction"]
        assert rights.licence_string.startswith("©")

    def test_missing_flag_is_unverified(self):
        raw = {k: v for k, v in OPEN.items() if k != "isPublicDomain"}
        rights = met.to_record(raw, checked_at=CHECKED).rights
        assert rights.status is RightsStatus.UNVERIFIED
        assert rights.flag_field is None

    @pytest.mark.parametrize("value", ["true", 1, None, "yes"])
    def test_non_boolean_flag_is_unverified_and_keeps_the_raw_value(self, value):
        raw = copy.deepcopy(OPEN) | {"isPublicDomain": value}
        rights = met.to_record(raw, checked_at=CHECKED).rights
        assert rights.status is RightsStatus.UNVERIFIED

    def test_image_url_only_for_open_works(self):
        assert met.to_record(OPEN, checked_at=CHECKED).image_url == OPEN["primaryImageSmall"]
        # Even if a non-open record carried an image URL, it is not stored.
        raw = copy.deepcopy(COPYRIGHT) | {"primaryImageSmall": "https://example.org/x.jpg"}
        assert met.to_record(raw, checked_at=CHECKED).image_url is None


class TestDrift:
    """Contract tests: fail loudly if the Met's responses stop matching what we rely on."""

    def test_public_domain_flag_is_a_boolean(self):
        for o in (OPEN, COPYRIGHT, COPYRIGHT_NO_NOTICE):
            assert isinstance(o["isPublicDomain"], bool)

    def test_open_objects_have_no_copyright_notice_and_have_an_image(self):
        assert OPEN["rightsAndReproduction"] == ""
        assert OPEN["primaryImageSmall"].startswith("https://images.metmuseum.org/")

    def test_in_copyright_objects_have_no_image(self):
        for o in (COPYRIGHT, COPYRIGHT_NO_NOTICE):
            assert o["primaryImage"] == "" and o["primaryImageSmall"] == ""

    def test_v1_search_is_retired(self):
        # Retired 2026-10-01 per metmuseum.github.io; the adapter must use v1.1.
        assert fixture("search_v1_retired")["status"] == 410
        assert "/v1.1/search" in met.SEARCH_PATH

    def test_european_paintings_department_id(self):
        departments = fixture("departments")["body"]["departments"]
        assert {"departmentId": 11, "displayName": "European Paintings"} in departments
        assert met.PAINTINGS_DEPARTMENT_ID == 11


class FakeTransport:
    """Returns queued (status, body) responses and records requested URLs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        return self.responses.pop(0)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def client(responses, **kwargs):
    clock = FakeClock()
    transport = FakeTransport(responses)
    c = met.MetClient(transport=transport, clock=clock.monotonic, sleep=clock.sleep, **kwargs)
    return c, transport, clock


class TestRateLimiting:
    def test_requests_are_spaced_by_the_minimum_interval(self):
        c, _, clock = client([(200, OPEN), (200, OPEN), (200, OPEN)], min_interval=1.0)
        for _ in range(3):
            c.get_object(436535)
        assert sum(clock.sleeps) == pytest.approx(2.0)

    def test_default_interval_stays_far_under_the_documented_cap(self):
        assert met.MetClient.DEFAULT_MIN_INTERVAL >= 1 / 80

    def test_429_is_retried_with_backoff(self):
        c, transport, clock = client([(429, ""), (429, ""), (200, OPEN)], min_interval=0)
        assert c.get_object(436535)["objectID"] == 436535
        assert len(transport.urls) == 3
        assert clock.sleeps == [1.0, 2.0]

    def test_gives_up_after_max_retries(self):
        c, _, _ = client([(429, "")] * 4, min_interval=0, max_retries=3)
        with pytest.raises(met.MetUnavailable, match="429"):
            c.get_object(436535)

    def test_404_is_not_retried(self):
        c, transport, _ = client([(404, {"message": "Not a valid object"})], min_interval=0)
        with pytest.raises(met.MetNotFound):
            c.get_object(1)
        assert len(transport.urls) == 1


class TestIterRecords:
    def test_paintings_slice_skips_other_classifications_and_counts_why(self):
        sculpture = copy.deepcopy(OPEN) | {"objectID": 1, "classification": "Sculpture"}
        responses = [
            (200, {"total": 3, "objectIDs": [436535, 1, 2]}),
            (200, OPEN),
            (200, sculpture),
            (404, {"message": "Not a valid object"}),
        ]
        c, transport, _ = client(responses, min_interval=0)
        source = met.MetSource(c, now=lambda: CHECKED)
        records = list(source.iter_records())
        assert [r.id for r in records] == ["met:436535"]
        assert source.stats.ingested == 1
        assert source.stats.open == 1
        assert source.stats.skipped == {"classification:Sculpture": 1, "not_found": 1}
        assert "departmentIds=11" in transport.urls[0]

    def test_raw_response_is_returned_with_each_record(self):
        c, _, _ = client([(200, {"total": 1, "objectIDs": [436535]}), (200, OPEN)], min_interval=0)
        source = met.MetSource(c, now=lambda: CHECKED)
        [(record, raw)] = list(source.iter_items())
        assert raw == OPEN and record.id == "met:436535"


class TestPaintingClassifications:
    @pytest.mark.parametrize(
        "classification", ["Paintings", "Miniatures", "Pastels & Oil Sketches on Paper"]
    )
    def test_painting_like_classifications_are_kept(self, classification):
        raw = copy.deepcopy(OPEN) | {"classification": classification}
        c, _, _ = client([(200, raw)], min_interval=0)
        outcome = met.MetSource(c, now=lambda: CHECKED).fetch_one(436535)
        assert isinstance(outcome, met.Fetched)

    @pytest.mark.parametrize("classification", ["Drawings", "Manuscripts and Illuminations"])
    def test_non_paintings_are_skipped(self, classification):
        raw = copy.deepcopy(OPEN) | {"classification": classification}
        c, _, _ = client([(200, raw)], min_interval=0)
        outcome = met.MetSource(c, now=lambda: CHECKED).fetch_one(436535)
        assert outcome == met.Skipped(436535, f"classification:{classification}")


class TestDateRange:
    def test_structured_years_are_mapped(self):
        r = met.to_record(OPEN, checked_at=CHECKED)
        assert (r.date_begin, r.date_end) == (1889, 1889)

    def test_years_are_kept_when_the_display_date_is_empty(self):
        raw = copy.deepcopy(OPEN) | {
            "objectDate": "",
            "objectBeginDate": 1327,
            "objectEndDate": 1348,
        }
        r = met.to_record(raw, checked_at=CHECKED)
        assert r.date is None
        assert (r.date_begin, r.date_end) == (1327, 1348)

    @pytest.mark.parametrize("value", [None, "1500", True, 1.5])
    def test_non_integer_years_are_not_stored(self, value):
        raw = copy.deepcopy(OPEN) | {"objectBeginDate": value, "objectEndDate": value}
        r = met.to_record(raw, checked_at=CHECKED)
        assert r.date_begin is None and r.date_end is None
